"""Vast PyWorker: automatically provision Bernini and start private R2 bridge."""
import os
import subprocess
import threading
import sys
import time
import urllib.request
from pathlib import Path

def benchmark_payload():
    from r2_bridge import JOB_RE
    job_id = os.getenv("BERNINI_BENCHMARK_JOB_ID", "")
    if not JOB_RE.fullmatch(job_id):
        raise RuntimeError("Dedicated 32-hex BERNINI_BENCHMARK_JOB_ID is required")
    return {"job_id": job_id}

def make_config():
    from vastai import WorkerConfig, HandlerConfig, BenchmarkConfig, LogActionConfig
    benchmark_payload()
    return WorkerConfig(
        model_server_url="http://127.0.0.1",
        model_server_port=int(os.getenv("BERNINI_BRIDGE_PORT", "18300")),
        model_log_file=os.getenv("BERNINI_BRIDGE_LOG", "/tmp/bernini-bridge.log"),
        model_healthcheck_url="/health",
        handlers=[HandlerConfig(
            route="/generate/sync", allow_parallel_requests=False,
            max_queue_time=10.0, workload_calculator=lambda payload: 100.0,
            benchmark_config=BenchmarkConfig(generator=benchmark_payload, runs=1, concurrency=1),
        )],
        log_action_config=LogActionConfig(
            on_load=["BERNINI_BRIDGE_READY"],
            on_error=["BERNINI_BRIDGE_FATAL"], on_info=[],
        ),
    )

def start_backend():
    root = Path(__file__).resolve().parent
    env = os.environ.copy()
    env.setdefault("COMFY_DIR", "/workspace/ComfyUI")
    env.setdefault("COMFY_INPUT_DIR", env["COMFY_DIR"] + "/input")
    env.setdefault("COMFY_OUTPUT_DIR", env["COMFY_DIR"] + "/output")
    env.setdefault("COMFY_API_URL", "http://127.0.0.1:18188")
    env.setdefault("BERNINI_MODEL_MANIFEST", str(root / "model_manifest.example.json"))
    env.setdefault("BERNINI_BRIDGE_LOG", "/tmp/bernini-bridge.log")
    subprocess.run(["bash", str(root / "prepare_worker.sh")], cwd=root, env=env, check=True)
    log_path = Path(env["BERNINI_BRIDGE_LOG"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("ab", buffering=0)
    process = subprocess.Popen([sys.executable, "-u", str(root / "bridge_api.py")],
                               cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)
    base = "http://127.0.0.1:" + env.get("BERNINI_BRIDGE_PORT", "18300")
    try:
        for _ in range(60):
            if process.poll() is not None:
                raise RuntimeError("Bernini bridge exited before readiness")
            try:
                with urllib.request.urlopen(base + "/health", timeout=2) as response:
                    if response.status == 200:
                        return process
            except Exception:
                pass
            time.sleep(1)
        raise RuntimeError("Bernini bridge readiness timeout")
    except Exception:
        process.terminate()
        raise
    finally:
        log.close()

if __name__ == "__main__":
    from vastai import Worker
    backend = start_backend()
    # The SDK tails the model log only after Worker.run() starts.
    # Emit readiness after startup, rather than before the SDK log tail exists.
    def emit_ready():
        time.sleep(8)
        if backend.poll() is None:
            with open(os.getenv("BERNINI_BRIDGE_LOG", "/tmp/bernini-bridge.log"),
                      "ab", buffering=0) as log:
                log.write(b"BERNINI_BRIDGE_READY\\n")
    threading.Thread(target=emit_ready, daemon=True).start()
    try:
        Worker(make_config()).run()
    finally:
        backend.terminate()
        try:
            backend.wait(timeout=10)
        except subprocess.TimeoutExpired:
            backend.kill()
