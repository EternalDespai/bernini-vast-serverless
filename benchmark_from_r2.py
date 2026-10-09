#!/usr/bin/env python3
"""Create a dedicated 17-frame Vast benchmark from an existing R2 UI upload.

Call create_from_job(job_id) in the Windows UI immediately after its normal
three-file R2 upload. No second file picker or local video paths are needed.
Requires ffmpeg on the UI host and the same R2 env credentials as upload.
"""
import argparse
import json
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from r2_bridge import JOB_RE, MAX_IMAGE, MAX_VIDEO, MAX_WORKFLOW, env, s3_client

INPUTS = (("source.mp4", MAX_VIDEO), ("reference.jpg", MAX_IMAGE),
          ("workflow_api.json", MAX_WORKFLOW))


def create_from_job(source_job_id: str) -> str:
    """Return a NEW persistent benchmark job ID; never mutate source job."""
    if not JOB_RE.fullmatch(source_job_id):
        raise ValueError("Expected a 32-character lowercase hexadecimal job ID")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required on the UI host to create benchmark")
    bucket = env("R2_BUCKET")
    s3 = s3_client()
    prefix = f"jobs/{source_job_id}/"
    with tempfile.TemporaryDirectory(prefix="bernini_benchmark_") as td:
        directory = Path(td)
        for name, maximum in INPUTS:
            key = prefix + name
            metadata = s3.head_object(Bucket=bucket, Key=key)
            size = metadata["ContentLength"]
            if not 0 < size <= maximum:
                raise ValueError(f"Invalid size for {name}")
            s3.download_file(bucket, key, str(directory / name))

        photo = directory / "reference.jpg"
        if photo.open("rb").read(3) != b"\\xff\\xd8\\xff":
            raise ValueError("reference.jpg must be JPEG")
        graph = json.loads((directory / "workflow_api.json").read_text(encoding="utf-8"))
        if graph.get("5", {}).get("class_type") != "BerniniStudio":
            raise ValueError("Workflow must contain BerniniStudio node 5")

        clip = directory / "benchmark.mp4"
        subprocess.run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(directory / "source.mp4"),
            "-vf", "fps=16", "-frames:v", "17", "-an",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip),
        ], check=True, timeout=180)
        if not clip.is_file() or not 0 < clip.stat().st_size <= MAX_VIDEO:
            raise RuntimeError("FFmpeg did not produce a valid benchmark clip")

        benchmark_id = uuid.uuid4().hex
        target = f"jobs/{benchmark_id}/"
        # Upload the clip first; publish the other two objects only after success.
        s3.upload_file(str(clip), bucket, target + "source.mp4",
                       ExtraArgs={"ContentType": "video/mp4"})
        s3.copy_object(Bucket=bucket, Key=target + "reference.jpg",
                       CopySource={"Bucket": bucket, "Key": prefix + "reference.jpg"},
                       ContentType="image/jpeg", MetadataDirective="REPLACE")
        s3.copy_object(Bucket=bucket, Key=target + "workflow_api.json",
                       CopySource={"Bucket": bucket, "Key": prefix + "workflow_api.json"},
                       ContentType="application/json", MetadataDirective="REPLACE")
        return benchmark_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True, help="Existing UI-uploaded R2 job ID")
    args = parser.parse_args()
    print("BERNINI_BENCHMARK_JOB_ID=" + create_from_job(args.job_id))


if __name__ == "__main__":
    main()
