# Bernini: local one-click UI + status tracking (integration prototype)

## What is implemented

- `local_ui.html`: Russian MP4/JPG/PNG upload page with generate button,
  live status, ComfyUI sampling-step percentage, and MP4 download button.
- `local_ui.py`: local-only backend; uploads MP4, converts JPG/PNG to JPG,
  uploads original ComfyUI API JSON to private R2, triggers an authenticated
  worker, polls `status.json`, returns a 15-minute presigned MP4 URL.
- `job_status.py`: observes ComfyUI WebSocket `progress` events and publishes
  `jobs/<id>/status.json` to R2 (throttled, best effort). Cold start is shown
  as waiting; sampling-step percent is **not** end-to-end percent.
- `r2_bridge.py`: publishes download, loading, sampling, upload, complete,
  and failure stages; final MP4 remains `jobs/<id>/result.mp4`.
- `start_windows.bat`: installs Python dependencies and launches the local UI.
  Does not provision a GPU or create a Vast endpoint.

## Configure once on your Windows computer

1. Install Python 3.11+ and clone/download this branch.
2. Copy `.env.example` to `.env` **locally** and fill the variables.
   Never paste credentials in chat or commit `.env`.
3. `BERNINI_WORKFLOW_PATH` must point to your exact working ComfyUI
   **API-format** workflow JSON (not the UI graph export).
4. `BERNINI_VAST_GENERATE_URL` must be the **actual authenticated worker
   route** that accepts `{"job_id":"<32-hex>"}`. The Vast endpoint does not
   exist yet. The request/response contract must be validated against the
   chosen Vast routing method; the local UI does not implement Vast route
   discovery or cold-worker activation on its own.
5. Double-click `start_windows.bat`, then open `http://127.0.0.1:8765`.

The UI binds only to `127.0.0.1` and keeps R2/Vast secrets in the Python
backend. Do not expose port 8765 to the internet. Limit R2 permissions to the
one private bucket and rotate keys after testing on untrusted GPU hosts.

## Worker requirements

- A real Vast Serverless endpoint and correct custom worker bootstrapping.
- All six Bernini model weights and registered ComfyUI custom nodes.
- Private R2 environment variables, `COMFY_INPUT_DIR`, `COMFY_OUTPUT_DIR`.
- `start_bridge.sh` must run after provisioning and ComfyUI readiness.
- `BERNINI_BENCHMARK_JOB_ID` must be a dedicated, expendable benchmark job.

**Not yet tested**: live Serverless startup, endpoint routing/authentication,
local UI end-to-end with Serverless, cold-start latency, SDK compatibility,
percentage events with the exact Bernini graph, and multiple simultaneous
clients. No one-command GPU provisioning is currently proven. The new local
Windows launcher is a one-click **client** launcher, not a Serverless installer.

## Progress semantics

`status.json` includes `state`, `stage`, `percent`, `step_percent`,
`percent_kind`, and `updated_at`. `percent_kind="sampling_step"` indicates
a percentage **of the current ComfyUI sampling stage only**. Stages that cannot
report reliable percentages set `percent=null`. A full output becomes 100%
only after successful R2 upload.

Use the UI only after the worker route has been validated. The existing
manual R2 → H100 → R2 smoke test is already proven, but does not validate
the new browser/Vast orchestration.

## Single command on a provisioned Vast ComfyUI container

```bash
bash bootstrap_serverless.sh
```

This installs dependencies and model weights, restarts ComfyUI through the
supervisor config found on the successful on-demand image, runs readiness
checks, and starts the bridge + PyWorker. It needs **all** private R2 env vars,
`BERNINI_BENCHMARK_JOB_ID`, an already-installed ComfyUI instance, and a
compatible Vast Serverless startup environment. The script has **not** been
executed on Serverless. The real Serverless template must be configured to
invoke it during startup; setting `PYWORKER_REPO` alone may instead run
`worker.py` directly, skipping provisioning. Validate template hooks before
spending money. It does **not** create an endpoint or configure autoscaling.
