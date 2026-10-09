# Vast startup compatibility

Keep the stock on-start script unchanged. With BACKEND=comfyui-json, the Vast starter worker is located at workers/comfyui-json/worker.py. This branch now supplies that adapter, which installs requirements and launches the root Bernini worker.

Before deploying, create a persistent dedicated 17-frame benchmark job:

```
python create_benchmark_job.py --video benchmark.mp4 --photo reference.jpg --workflow workflow_api.json
```

Set BERNINI_BENCHMARK_JOB_ID in the Vast environment to the printed 32-character job ID. Benchmark inputs must stay in R2 across cold starts; bridge cleanup now skips them.

Template environment PYWORKER_REPO and PYWORKER_REF stay as configured. The local UI uses the Vast SDK and submits job_id to our custom /generate/sync endpoint.

Still requires paid validation on the actual Vast template: cloning and executing the adapter, downloading weights, restarting ComfyUI, worker readiness, benchmark, full video and scale-to-zero. Do not create a paid endpoint until the dedicated benchmark exists.

## Automatic benchmark from an existing Windows UI upload

The Windows UI should upload its normal three R2 inputs first, then call
`benchmark_from_r2.create_from_job(job_id)` from its existing R2-capable
backend (same process credentials). This generates a **separate** reusable
17-frame benchmark in R2 without asking the user to select/upload files again.
The function returns the dedicated `BERNINI_BENCHMARK_JOB_ID`.

Requirements: FFmpeg on the UI backend PATH, boto3, R2 credentials already
used by the upload. This operation downloads the source video temporarily,
uses FFmpeg locally (no paid GPU), and copies the reference/workflow within R2.
The original job is unchanged. Store the returned ID in private endpoint
configuration; **do not** use the original user job ID as the benchmark.

A one-off integration test (not a required user workflow):
`python benchmark_from_r2.py --job-id <existing-ui-job-id>`

**Integration still outstanding:** The actual Windows UI code is not part of
this repository; wire the call into its upload-complete handler and arrange
secure endpoint environment configuration. The Vast template still needs a
live paid validation. Do not claim end-to-end one-click readiness yet.
