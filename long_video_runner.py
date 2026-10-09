"""Sequential full-video Bernini inference at 16 fps.

Normalizes the entire source to 16fps, processes overlapping <=81-frame
chunks, discards duplicated overlap frames, joins the video and restores
source audio. No silent truncation. Quality at chunk boundaries must still
be evaluated on a real GPU before production.
"""
import json
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import requests

from job_status import start_progress_watcher
from video_chunks import FPS, plan_chunks


def command(args, timeout=1800):
    try:
        return subprocess.run(args, check=True, capture_output=True, text=True,
                              timeout=timeout).stdout
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("FFmpeg failed: " + exc.stderr[-1800:]) from exc


def frame_count(path):
    data = json.loads(command([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-count_frames", "-show_entries", "stream=nb_read_frames",
        "-of", "json", str(path)], timeout=120))
    streams = data.get("streams", [])
    if not streams or not streams[0].get("nb_read_frames"):
        raise RuntimeError("Cannot determine decoded video frame count")
    return int(streams[0]["nb_read_frames"])


def process_full_video(original, reference_name, workflow, input_dir,
                       output_dir, base, job_id, timeout, status):
    """Return a verified, stitched MP4 path in a temporary workspace.

    Caller must keep the returned TemporaryDirectory alive until R2 upload.
    """
    from r2_bridge import prepare_workflow, post_json, wait_for_result, output_candidates

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("Both ffmpeg and ffprobe must be installed on the GPU")
    temp = tempfile.TemporaryDirectory(prefix="bernini_full_")
    work = Path(temp.name)
    created_inputs = []
    created_outputs = []
    deadline = time.monotonic() + timeout
    try:
        normalized = work / "normalized.mp4"
        status.publish(state="running", stage="normalizing", force=True)
        command(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                 "-i", str(original), "-vf", f"fps={FPS}",
                 "-an", "-c:v", "libx264", "-preset", "fast",
                 "-pix_fmt", "yuv420p", "-r", str(FPS), str(normalized)])
        total = frame_count(normalized)
        chunks = plan_chunks(total)
        print(f"Full video: {total} frames at {FPS} fps; {len(chunks)} chunks", flush=True)
        encoded = []
        with requests.Session() as session:
            for chunk in chunks:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Full video generation timeout")
                name = f"bernini_{job_id}_part_{chunk.index:04d}.mp4"
                clip = input_dir / name
                created_inputs.append(clip)
                # Select exact frame indices; clone last frame to satisfy 4n+1
                # for a final partial chunk. Excess generated frames are trimmed.
                filtergraph = (
                    f"select='between(n,{chunk.start_frame},"
                    f"{chunk.start_frame + chunk.source_frames - 1})',"
                    f"setpts=N/({FPS}*TB),"
                    f"tpad=stop_mode=clone:stop_duration=2"
                )
                command(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                         "-i", str(normalized), "-vf", filtergraph,
                         "-frames:v", str(chunk.model_frames), "-r", str(FPS),
                         "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                         str(clip)])
                if frame_count(clip) != chunk.model_frames:
                    raise RuntimeError(f"Chunk {chunk.index} has incorrect input frames")
                # Clone the original workflow so per-chunk edits never accumulate.
                graph = json.loads(json.dumps(workflow))
                graph["5"]["inputs"]["length"] = chunk.model_frames
                graph["21"]["inputs"]["frame_load_cap"] = chunk.model_frames
                graph["21"]["inputs"]["force_rate"] = FPS
                graph["22"]["inputs"]["frame_rate"] = FPS
                prefix = f"Bernini_{job_id}_part_{chunk.index:04d}"
                prepare_workflow(graph, name, reference_name, prefix)
                status.publish(state="running", stage="chunk", force=True)
                status.publish_chunk(chunk.index + 1, len(chunks))
                client_id = str(uuid.uuid4())
                payload = post_json(session, base, "/prompt",
                                    {"prompt": graph, "client_id": client_id})
                if payload.get("node_errors"):
                    raise RuntimeError("Chunk validation failed: " + repr(payload["node_errors"])[:2000])
                prompt_id = payload["prompt_id"]
                stop = start_progress_watcher(base, client_id, prompt_id, status)
                try:
                    record = wait_for_result(session, base, prompt_id,
                                             max(30, int(deadline - time.monotonic())))
                finally:
                    stop.set()
                candidates = list(output_candidates(record))
                if not candidates:
                    raise RuntimeError(f"Chunk {chunk.index} produced no MP4")
                out_name, subfolder = candidates[0]
                rendered = (output_dir / subfolder / out_name).resolve()
                if output_dir not in rendered.parents or not rendered.is_file():
                    raise RuntimeError("ComfyUI chunk output missing/outside output dir")
                created_outputs.append(rendered)
                trimmed = work / f"trim_{chunk.index:04d}.mp4"
                # Drop overlapping first frame from all chunks except first;
                # trim the model's final padding to original source frame count.
                end = chunk.trim_first + chunk.output_frames
                command(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                         "-i", str(rendered),
                         "-vf", f"trim=start_frame={chunk.trim_first}:end_frame={end},setpts=PTS-STARTPTS",
                         "-an", "-r", str(FPS), "-c:v", "libx264",
                         "-pix_fmt", "yuv420p", str(trimmed)])
                if frame_count(trimmed) != chunk.output_frames:
                    raise RuntimeError(f"Chunk {chunk.index} output frame mismatch")
                encoded.append(trimmed)
                # Release input and output storage before the next expensive chunk.
                clip.unlink(missing_ok=True)
                rendered.unlink(missing_ok=True)
        playlist = work / "parts.txt"
        playlist.write_text("".join(f"file '{part.name}'\n" for part in encoded),
                            encoding="utf-8")
        stitched = work / "stitched.mp4"
        status.publish(state="running", stage="stitching", force=True)
        command(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                 "-f", "concat", "-safe", "0", "-i", str(playlist),
                 "-c:v", "libx264", "-r", str(FPS), "-pix_fmt", "yuv420p",
                 "-an", str(stitched)])
        if frame_count(stitched) != total:
            raise RuntimeError(f"Final video truncated: expected {total} frames")
        final = work / "final.mp4"
        # Restore original audio when present. Video frames determine duration;
        # do not let audio extend the output or cause silent video truncation.
        command(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                 "-i", str(stitched), "-i", str(original),
                 "-map", "0:v:0", "-map", "1:a:0?",
                 "-c:v", "copy", "-c:a", "aac", "-t", f"{total / FPS:.6f}",
                 "-movflags", "+faststart", str(final)])
        if frame_count(final) != total:
            raise RuntimeError("Audio mux changed output frame count")
        return temp, final, total, len(chunks)
    except Exception:
        temp.cleanup()
        raise
    finally:
        for path in created_inputs + created_outputs:
            path.unlink(missing_ok=True)
