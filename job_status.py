"""R2 status snapshots and ComfyUI WebSocket progress (best-effort).

The percentage during inference is the *current sampling node's* percentage,
not a mathematically exact percentage of the entire workflow. Never display
it as an exact end-to-end progress value.
"""
import json
import logging
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

import websocket

LOG = logging.getLogger(__name__)


class JobStatus:
    def __init__(self, s3, bucket, job_id):
        self.s3 = s3
        self.bucket = bucket
        self.key = f"jobs/{job_id}/status.json"
        self.job_id = job_id
        self.lock = threading.Lock()
        self.last_upload = 0.0
        self.state = {
            "job_id": job_id, "state": "queued", "stage": "queued",
            "step_percent": None, "percent": None, "percent_kind": "sampling_step",
            "updated_at": "",
        }

    def publish_chunk(self, index, total):
        with self.lock:
            self.state["chunk_index"] = index
            self.state["chunk_total"] = total
            self.state["step_percent"] = None
            self.state["percent"] = None
        self.publish(state="running", stage="chunk", force=True)

    def publish(self, state=None, stage=None, step_percent=None, force=False):
        with self.lock:
            if state is not None:
                self.state["state"] = state
            if stage is not None:
                self.state["stage"] = stage
            if step_percent is not None:
                self.state["step_percent"] = max(0, min(100, int(step_percent)))
                self.state["percent"] = self.state["step_percent"]
            elif stage in ("downloading", "loading", "normalizing", "chunk", "stitching", "uploading", "complete", "failed"):
                self.state["step_percent"] = None
                self.state["percent"] = 100 if stage == "complete" else None
            if stage == "complete":
                self.state["percent_kind"] = "complete"
            self.state["updated_at"] = datetime.now(timezone.utc).isoformat()
            now = time.monotonic()
            if not force and now - self.last_upload < 5:
                return
            self.last_upload = now
            try:
                self.s3.put_object(
                    Bucket=self.bucket, Key=self.key,
                    Body=json.dumps(self.state, ensure_ascii=False).encode("utf-8"),
                    ContentType="application/json", CacheControl="no-store",
                )
            except Exception as exc:
                # Status is best effort: a transient R2 failure must not abort
                # a long-running, expensive GPU generation.
                LOG.warning("Could not upload job status: %s", type(exc).__name__)


def watch_comfy_progress(base_url, client_id, prompt_id, status, stop):
    """Listen to progress messages from ComfyUI; reconnect on interruptions."""
    parsed = urlsplit(base_url)
    ws_scheme = "wss" if parsed.scheme == "https" else "ws"
    ws_url = urlunsplit((ws_scheme, parsed.netloc,
                         "/ws", "clientId=" + client_id, ""))
    while not stop.is_set():
        sock = None
        try:
            sock = websocket.create_connection(ws_url, timeout=4)
            sock.settimeout(2)
            while not stop.is_set():
                try:
                    message = sock.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                if not isinstance(message, str):
                    continue
                event = json.loads(message)
                payload = event.get("data") or {}
                if payload.get("prompt_id") not in (None, prompt_id):
                    continue
                kind = event.get("type")
                if kind == "progress":
                    value, maximum = payload.get("value"), payload.get("max")
                    if isinstance(value, (int, float)) and isinstance(maximum, (int, float)) and maximum > 0:
                        status.publish(state="running", stage="sampling",
                                       step_percent=round(value / maximum * 100))
                elif kind == "executing" and payload.get("node") is not None:
                    status.publish(state="running", stage="executing_node",
                                   force=False)
        except Exception as exc:
            LOG.warning("ComfyUI progress socket unavailable: %s", type(exc).__name__)
            stop.wait(3)
        finally:
            if sock:
                sock.close()


def start_progress_watcher(base_url, client_id, prompt_id, status):
    stop = threading.Event()
    thread = threading.Thread(
        target=watch_comfy_progress,
        args=(base_url, client_id, prompt_id, status, stop),
        daemon=True,
    )
    thread.start()
    return stop
