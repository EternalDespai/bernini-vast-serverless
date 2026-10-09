"""Private HTTP backend for Vast PyWorker.

The API binds to 127.0.0.1, not a public port. Vast PyWorker proxies
POST /generate/sync; an authenticated Vast endpoint is still required.
"""
import os
import threading
import requests

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from r2_bridge import JOB_RE, run

app = FastAPI(title="Bernini R2 Bridge", docs_url=None, redoc_url=None)
busy = threading.Lock()


class JobRequest(BaseModel):
    job_id: str = Field(min_length=32, max_length=32)


@app.get("/health")
def health():
    # An HTTP bridge alone is not a healthy GPU worker. ComfyUI must be
    # reachable and have the Bernini node registered.
    base = os.getenv("COMFY_API_URL", "http://127.0.0.1:18188").rstrip("/")
    try:
        response = requests.get(base + "/object_info/BerniniStudio", timeout=5)
        response.raise_for_status()
        if "BerniniStudio" not in response.json():
            raise RuntimeError("BerniniStudio is not registered")
    except (requests.RequestException, ValueError, RuntimeError):
        raise HTTPException(status_code=503, detail="ComfyUI not ready")
    return {"status": "ok"}


@app.post("/generate/sync")
def generate(request: JobRequest):
    if not JOB_RE.fullmatch(request.job_id):
        raise HTTPException(status_code=422, detail="Invalid job_id")
    if not busy.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="GPU worker is busy")
    try:
        timeout = int(os.getenv("BERNINI_JOB_TIMEOUT_SECONDS", "7200"))
        if not 30 <= timeout <= 86400:
            raise RuntimeError("Invalid BERNINI_JOB_TIMEOUT_SECONDS")
        run(request.job_id, timeout)
        return {"ok": True, "job_id": request.job_id,
                "result_key": f"jobs/{request.job_id}/result.mp4"}
    except Exception:
        # Avoid leaking environment secrets or internal paths in API responses.
        raise HTTPException(status_code=500, detail="Generation failed; inspect worker logs")
    finally:
        busy.release()


if __name__ == "__main__":
    import uvicorn
    # Do not expose R2 access to the public internet through this service.
    uvicorn.run(app, host="127.0.0.1",
                port=int(os.getenv("BERNINI_BRIDGE_PORT", "18300")),
                log_level="info")
