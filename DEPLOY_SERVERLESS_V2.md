# Vast Serverless — deployment checklist (October 2026)

## Implemented in this branch

- Vast template can use `PYWORKER_REPO=https://github.com/EternalDespai/bernini-vast-serverless`
  and `PYWORKER_REF=feat/r2-comfy-bridge`. Official template starts
  `python worker.py`; worker.py now runs `prepare_worker.sh` automatically
  before starting the private bridge and PyWorker. This closes the earlier
  missing-bootstrap hook. **Still requires a compatible ComfyUI template.**
- Worker provisions BerniniStudio, VideoHelperSuite, their dependencies and
  the six model weights; restarts supervisor-managed ComfyUI, checks all nodes
  and model files, then binds the private bridge on 127.0.0.1:18300.
- Browser UI v5 uses official Vast `Serverless` SDK, resolves endpoint by name,
  and calls `endpoint.request("/generate/sync", {"job_id": job_id})`.
  The local UI and R2 keys remain private.
- Full-video path processes all frames at 16fps in a single continuous pass,
  verifies count and restores audio. **Long clips may exceed GPU VRAM.**
- Status writes R2 snapshots with stage/chunk/sampling-step percent; successful
  jobs remove input objects. Add R2 lifecycle `jobs/` expiry 7 days in console.

## Initial configuration — must be done by account owner

1. Install the official Vast CLI on your own machine and authenticate there.
   Do not paste Vast/R2 keys in chat. An admin-scope Vast key and a positive
   deposited team balance may be required for worker groups.
2. Choose/create a **Vast Serverless-compatible ComfyUI template**, at least
   48GB GPU VRAM and 120GB disk, with a supervisor-managed ComfyUI instance.
   The exact image startup and supervisor program name must be confirmed on
   that template; a generic Vast on-demand ComfyUI image is **not** automatically
   a working Serverless template.
3. Set template/account environment variables: `PYWORKER_REPO`,
   `PYWORKER_REF`, `COMFY_DIR`, `COMFY_API_URL`,
   `BERNINI_COMFY_SUPERVISOR_NAME`, `R2_ACCOUNT_ID`,
   `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`,
   `BERNINI_BENCHMARK_JOB_ID`. Set the benchmark ID to a **separate 17-frame
   expendable job** already uploaded to R2. Do not use the user-facing job ID.
4. Obtain the resulting template hash. Check it actually starts the cloned
   repo's `worker.py` and that supervisor restart name is correct.
5. Preview the one-command endpoint deployment (does not spend money):

```bash
python deploy_serverless.py --template-hash YOUR_TEMPLATE_HASH
```

6. Only after explicitly approving Vast costs, create the endpoint and
   worker group (may incur GPU/storage/benchmark charges):

```bash
python deploy_serverless.py --template-hash YOUR_TEMPLATE_HASH --apply
```

The deployment script sets `min_load=0`, `min_workers=0`,
`cold_workers=0`, `cold_mult=0`, `max_workers=1`, and
`inactivity_timeout=600` seconds. It **does not** create the template,
register secrets, or verify GPU compatibility. If the workergroup creation
fails, the endpoint may remain and must be inspected in Vast console.

7. Configure Windows UI v5 `vast_config.env` with
   `BERNINI_ENDPOINT_NAME=bernini-rv2v` and your Vast API key locally.
   Install dependencies via `INSTALL_R2_WINDOWS.bat` and launch
   `START_WINDOWS.bat`.
8. Check worker logs and run a paid 6–12-second MP4. Confirm real worker
   readiness, R2 output, single-pass mode, preserved audio, progress and
   signed download. Confirm GPU reaches zero after inactivity. **Do not call
   the system production-ready until these checks pass.**

## Verified versus not verified

**Verified:** previous 17-frame on-demand H100 R2→ComfyUI→R2 generation;
offline V5 UI syntax and a mocked official SDK request to
`/generate/sync`; Bash/Python syntax for local bootstrap files.

**Not verified:** live Vast endpoint creation, PyWorker SDK/benchmark runtime,
actual Serverless template on-start, real cold starts, arbitrary-duration
Bernini inference, automatic zero-worker scale-down or GPU charges.
No Vast account connection is available in this chat, so no paid endpoint
was created or charged. This is not a claim of a fully deployed service.

## Cost controls

The 17-frame benchmark itself performs GPU inference on each fresh worker
start. Scale-to-zero saves idle GPU time but repeated cold starts can incur
model-download, storage and benchmark costs. Long video uses one generation and may fail with CUDA OOM even on a 96GB GPU.
The endpoint created by this script is configured to scale to zero after
600 seconds of inactivity, but existing Vast endpoints must be checked
separately. Do not destroy workers or stop a shared endpoint from inside
the request handler; that can interrupt concurrent or queued jobs.
