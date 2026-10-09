"""Local-only browser backend: upload -> R2 -> Vast -> status -> download.

Run with: uvicorn local_ui:app --host 127.0.0.1 --port 8765
Secrets must be in environment variables; NEVER expose this app on 0.0.0.0.
"""
import asyncio
import json
import os
import threading
import uuid
from pathlib import Path

import requests
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from PIL import Image, ImageOps
from io import BytesIO

from r2_bridge import s3_client, env

app = FastAPI(docs_url=None, redoc_url=None)
_jobs = {}
_lock = threading.Lock()
MAX_VIDEO = 512 * 1024 * 1024
MAX_IMAGE = 30 * 1024 * 1024


def bucket():
    return env("R2_BUCKET")


def upload_bytes(s3, key, data, content_type):
    s3.put_object(Bucket=bucket(), Key=key, Body=data, ContentType=content_type)


async def read_limited(file, maximum):
    data = bytearray()
    while True:
        chunk = await file.read(min(1024 * 1024, maximum + 1 - len(data)))
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > maximum:
            raise HTTPException(413, "File too large")
    return bytes(data)


async def submit_vast(job_id):
    from vastai import Serverless
    endpoint_name = env("BERNINI_ENDPOINT_NAME")
    token = env("VAST_API_KEY")
    async with Serverless(token) as client:
        endpoint = await client.get_endpoint(name=endpoint_name)
        response = await endpoint.request("/generate/sync", {"job_id": job_id})
        if isinstance(response, dict) and response.get("ok") is False:
            raise RuntimeError("Vast worker reported failure")


def invoke_vast(job_id):
    try:
        asyncio.run(submit_vast(job_id))
    except Exception as exc:
        with _lock:
            _jobs[job_id] = "error: " + type(exc).__name__


@app.get("/", response_class=HTMLResponse)
def index():
    return Path(__file__).with_name("local_ui.html").read_text(encoding="utf-8")


@app.post("/api/jobs")
async def create_job(video: UploadFile = File(...), photo: UploadFile = File(...)):
    if not video.filename or not video.filename.lower().endswith(".mp4"):
        raise HTTPException(422, "Video must be MP4")
    if not photo.filename or not photo.filename.lower().endswith((".jpg", ".jpeg", ".png")):
        raise HTTPException(422, "Photo must be JPG or PNG")
    video_data = await read_limited(video, MAX_VIDEO)
    image_data = await read_limited(photo, MAX_IMAGE)
    if len(video_data) < 12 or b"ftyp" not in video_data[:32]:
        raise HTTPException(422, "Invalid MP4 file")
    try:
        with Image.open(BytesIO(image_data)) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            if im.width * im.height > 60_000_000:
                raise ValueError("Image too large")
            output = BytesIO()
            im.save(output, format="JPEG", quality=95)
            image_data = output.getvalue()
    except Exception:
        raise HTTPException(422, "Invalid photo")
    workflow_path = Path(env("BERNINI_WORKFLOW_PATH"))
    workflow_data = workflow_path.read_bytes()
    if len(workflow_data) > 5 * 1024 * 1024:
        raise HTTPException(422, "Workflow too large")
    json.loads(workflow_data)
    job_id = uuid.uuid4().hex
    prefix = f"jobs/{job_id}/"
    s3 = s3_client()
    upload_bytes(s3, prefix + "source.mp4", video_data, "video/mp4")
    upload_bytes(s3, prefix + "reference.jpg", image_data, "image/jpeg")
    upload_bytes(s3, prefix + "workflow_api.json", workflow_data, "application/json")
    with _lock:
        _jobs[job_id] = "submitted"
    threading.Thread(target=invoke_vast, args=(job_id,), daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    if len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
        raise HTTPException(404)
    with _lock:
        local_state = _jobs.get(job_id)
    if local_state is None:
        raise HTTPException(404)
    s3 = s3_client()
    key = f"jobs/{job_id}/status.json"
    try:
        result = s3.get_object(Bucket=bucket(), Key=key)
        status = json.loads(result["Body"].read())
    except s3.exceptions.NoSuchKey:
        status = {"job_id": job_id, "state": "queued", "stage": "waiting_for_gpu", "percent": None}
    except Exception:
        status = {"job_id": job_id, "state": "queued", "stage": "waiting_for_gpu", "percent": None}
    if local_state.startswith("error:") and status.get("state") != "complete":
        status = {"job_id": job_id, "state": "failed", "stage": "failed", "percent": None}
    if status.get("state") == "complete":
        result_key = f"jobs/{job_id}/result.mp4"
        try:
            s3.head_object(Bucket=bucket(), Key=result_key)
            status["download_url"] = s3.generate_presigned_url(
                "get_object", Params={"Bucket": bucket(), "Key": result_key},
                ExpiresIn=900,
            )
        except Exception:
            status["state"] = "uploading"
            status["stage"] = "uploading"
            status["percent"] = None
    return status
