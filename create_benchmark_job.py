#!/usr/bin/env python3
"""Create a reusable, private R2 benchmark job BEFORE creating the endpoint.

Run locally with your R2 environment variables, a small 17-frame MP4, a
reference JPEG and the known-good ComfyUI API JSON. Prints only the job ID.
"""
import argparse
import json
import shutil
import uuid
import subprocess
import tempfile
from pathlib import Path
from r2_bridge import s3_client, env, MAX_VIDEO, MAX_IMAGE, MAX_WORKFLOW

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--video", required=True)
    p.add_argument("--photo", required=True)
    p.add_argument("--workflow", required=True)
    args = p.parse_args()
    # One long video is enough: derive a reusable 17-frame benchmark clip.
    # The original long video is NOT uploaded as the benchmark.
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg must be installed to extract benchmark frames")
    with tempfile.TemporaryDirectory(prefix="bernini_bench_") as tmp:
        benchmark = Path(tmp) / "benchmark.mp4"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(Path(args.video)), "-vf", "fps=16",
                        "-frames:v", "17", "-an", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", str(benchmark)], check=True)
        _upload(benchmark, Path(args.photo), Path(args.workflow))


def _upload(video, photo, workflow):
    files = [(video, "source.mp4", MAX_VIDEO, "video/mp4"),
             (photo, "reference.jpg", MAX_IMAGE, "image/jpeg"),
             (workflow, "workflow_api.json", MAX_WORKFLOW, "application/json")]
    for path, name, limit, _ in files:
        if not path.is_file() or path.stat().st_size > limit or path.stat().st_size == 0:
            raise SystemExit(f"Missing/empty/oversized {name}: {path}")
    if b"ftyp" not in files[0][0].read_bytes()[:32]:
        raise SystemExit("Not an MP4 video")
    if files[1][0].read_bytes()[:3] != bytes([0xff, 0xd8, 0xff]):
        raise SystemExit("Reference must be JPEG")
    graph = json.loads(files[2][0].read_text(encoding="utf-8"))
    if graph.get("5", {}).get("class_type") != "BerniniStudio":
        raise SystemExit("Workflow must contain BerniniStudio node 5")
    bucket = env("R2_BUCKET")
    job_id = uuid.uuid4().hex
    s3 = s3_client()
    for path, name, _, content_type in files:
        s3.upload_file(str(path), bucket, f"jobs/{job_id}/{name}",
                       ExtraArgs={"ContentType": content_type})
    print("BERNINI_BENCHMARK_JOB_ID=" + job_id)
    print("Keep this job's three inputs in R2; worker benchmark reuses them.")
if __name__ == "__main__":
    main()
