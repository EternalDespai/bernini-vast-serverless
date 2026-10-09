# Vast startup compatibility

Keep the stock on-start script unchanged. With BACKEND=comfyui-json, the Vast starter worker is located at workers/comfyui-json/worker.py. This branch now supplies that adapter, which installs requirements and launches the root Bernini worker.

Before deploying, create a persistent dedicated 17-frame benchmark job:

```
python create_benchmark_job.py --video benchmark.mp4 --photo reference.jpg --workflow workflow_api.json
```

Set BERNINI_BENCHMARK_JOB_ID in the Vast environment to the printed 32-character job ID. Benchmark inputs must stay in R2 across cold starts; bridge cleanup now skips them.

Template environment PYWORKER_REPO and PYWORKER_REF stay as configured. The local UI uses the Vast SDK and submits job_id to our custom /generate/sync endpoint.

Still requires paid validation on the actual Vast template: cloning and executing the adapter, downloading weights, restarting ComfyUI, worker readiness, benchmark, full video and scale-to-zero. Do not create a paid endpoint until the dedicated benchmark exists.
