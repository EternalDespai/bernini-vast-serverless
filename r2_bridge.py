#!/usr/bin/env python3
"""Run one already-uploaded R2 job in a *running* ComfyUI instance.

Usage: python r2_bridge.py a5186804b4d848c0acc1792d64d97024

This is a job runner, NOT yet a Vast PyWorker or API endpoint.
Never publish credentials or user content in the git repository.
"""
import argparse
import json
import os
import re
import time
import uuid
from pathlib import Path

import boto3
import requests

JOB_RE = re.compile(r"^[a-f0-9]{32}$")
MAX_VIDEO = 512 * 1024 * 1024
MAX_IMAGE = 30 * 1024 * 1024
MAX_WORKFLOW = 5 * 1024 * 1024


def env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{env('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
        aws_access_key_id=env("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=env("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
    )


def download(s3, bucket, key, destination, limit):
    metadata = s3.head_object(Bucket=bucket, Key=key)
    if metadata["ContentLength"] > limit:
        raise ValueError(f"R2 object too large: {key}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    s3.download_file(bucket, key, str(destination))


def prepare_workflow(workflow, video_name, reference_name, prefix):
    """Patch the original Bernini API JSON, preserving its graph."""
    if not isinstance(workflow, dict):
        raise ValueError("Expected ComfyUI API-format workflow object")
    if workflow.get("5", {}).get("class_type") != "BerniniStudio":
        raise ValueError("Bernini node 5 was not found")
    if workflow.get("21", {}).get("class_type") != "VHS_LoadVideo":
        raise ValueError("Video loader node 21 was not found")
    if workflow.get("22", {}).get("class_type") != "VHS_VideoCombine":
        raise ValueError("Video output node 22 was not found")
    workflow["21"]["inputs"]["video"] = video_name
    slots = workflow["5"]["inputs"].get("slot_images", "")
    if isinstance(slots, str):
        slots = json.loads(slots)
    if not isinstance(slots, list) or len(slots) < 1:
        raise ValueError("Invalid Bernini slot_images")
    slots[0] = reference_name
    workflow["5"]["inputs"]["slot_images"] = json.dumps(slots)
    workflow["22"]["inputs"]["filename_prefix"] = prefix
    workflow["22"]["inputs"]["save_output"] = True
    return workflow


def post_json(session, base, path, payload):
    resp = session.post(f"{base}{path}", json=payload, timeout=90)
    resp.raise_for_status()
    return resp.json()


def wait_for_result(session, base, prompt_id, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = session.get(f"{base}/history/{prompt_id}", timeout=30)
        response.raise_for_status()
        record = response.json().get(prompt_id)
        if record:
            status = record.get("status", {})
            if status.get("status_str") == "error":
                raise RuntimeError("ComfyUI reported failed execution (see server logs)")
            if record.get("outputs") is not None:
                return record
        time.sleep(3)
    raise TimeoutError("ComfyUI generation timed out")


def output_candidates(record):
    """VHS_VideoCombine usually lists output under gifs, despite MP4 format."""
    for node in record.get("outputs", {}).values():
        for key in ("gifs", "videos", "images"):
            for item in node.get(key, []):
                name = item.get("filename", "")
                if name.lower().endswith(".mp4") and item.get("type", "output") == "output":
                    yield name, item.get("subfolder", "")


def run(job_id, timeout):
    if not JOB_RE.fullmatch(job_id):
        raise ValueError("Job ID must be 32 lowercase hexadecimal characters")
    bucket = env("R2_BUCKET")
    base = os.getenv("COMFY_API_URL", "http://127.0.0.1:18188").rstrip("/")
    input_dir = Path(env("COMFY_INPUT_DIR")).resolve()
    output_dir = Path(env("COMFY_OUTPUT_DIR")).resolve()
    s3 = s3_client()
    prefix = f"jobs/{job_id}/"
    video_name = f"bernini_{job_id}_source.mp4"
    photo_name = f"bernini_{job_id}_reference.jpg"
    video_path = input_dir / video_name
    photo_path = input_dir / photo_name
    workflow_path = input_dir / f"bernini_{job_id}_workflow.json"
    try:
        download(s3, bucket, prefix + "source.mp4", video_path, MAX_VIDEO)
        download(s3, bucket, prefix + "reference.jpg", photo_path, MAX_IMAGE)
        download(s3, bucket, prefix + "workflow_api.json", workflow_path, MAX_WORKFLOW)
        workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
        workflow = prepare_workflow(workflow, video_name, photo_name, f"Bernini_{job_id}")
        with requests.Session() as session:
            payload = post_json(session, base, "/prompt", {
                "prompt": workflow, "client_id": str(uuid.uuid4())
            })
            if payload.get("node_errors"):
                raise RuntimeError("ComfyUI workflow validation errors: " + repr(payload["node_errors"]))
            prompt_id = payload["prompt_id"]
            record = wait_for_result(session, base, prompt_id, timeout)
        candidates = list(output_candidates(record))
        if not candidates:
            raise RuntimeError("ComfyUI history has no MP4 in output nodes; inspect history")
        name, subfolder = candidates[0]
        result = (output_dir / subfolder / name).resolve()
        if output_dir not in result.parents or not result.is_file():
            raise RuntimeError("Output MP4 absent or outside configured output directory")
        output_key = prefix + "result.mp4"
        s3.upload_file(str(result), bucket, output_key, ExtraArgs={"ContentType": "video/mp4"})
        print(json.dumps({"ok": True, "bucket": bucket, "result_key": output_key, "prompt_id": prompt_id}))
    finally:
        for path in (video_path, photo_path, workflow_path):
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("job_id")
    parser.add_argument("--timeout", type=int, default=7200)
    args = parser.parse_args()
    run(args.job_id, args.timeout)
