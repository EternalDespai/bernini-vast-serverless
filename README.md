# Bernini RV2V / Vast.ai Serverless

**Status: integration in progress — do not launch a paid endpoint yet.**

The repository currently provides a *standalone* R2 → ComfyUI → R2 job runner,
not yet a deployable custom Vast PyWorker. The default Vast `/generate/sync`
expects ComfyUI workflow JSON and cannot consume an R2 job ID directly.

## Existing input contract

The Windows upload UI puts these objects in the private Cloudflare R2 bucket:

```
jobs/<32-hex-job-id>/source.mp4
jobs/<32-hex-job-id>/reference.jpg
jobs/<32-hex-job-id>/workflow_api.json
```

`r2_bridge.py` downloads these files, patches BerniniStudio node `5`
(`slot_images[0]`), VHS video loader node `21` and output node `22`,
calls ComfyUI native `/prompt`, polls `/history/{prompt_id}` and uploads
`jobs/<job-id>/result.mp4` on success. It expects your exact API workflow nodes.

## Smoke test on an already configured GPU with ComfyUI running

```bash
python -m pip install -r requirements.txt
export R2_ACCOUNT_ID="YOUR_ACCOUNT_ID"
export R2_ACCESS_KEY_ID="YOUR_LIMITED_KEY"
export R2_SECRET_ACCESS_KEY="YOUR_LIMITED_SECRET"
export R2_BUCKET="bernini-rv2v"
export COMFY_API_URL="http://127.0.0.1:18188"
export COMFY_INPUT_DIR="/path/to/ComfyUI/input"
export COMFY_OUTPUT_DIR="/path/to/ComfyUI/output"
python r2_bridge.py a5186804b4d848c0acc1792d64d97024
```

**Security:** Do not put actual keys in this repository or chat. Prefer
short-lived, bucket-scoped credentials or signed URLs on untrusted GPU hosts.

## Blocking work before Serverless

1. Install and validate BerniniStudio, VideoHelperSuite and all model weights
   (~35 GB), including correct paths and download URLs.
2. Plan and price persistent cache/storage: the template's 16 GB disk is insufficient.
3. Implement Vast SDK `Worker/HandlerConfig` custom HTTP route and startup
   that invokes this job runner, without disturbing base ComfyUI wrapper.
4. Provide a representative Bernini RV2V benchmark, not default SD1.5.
5. Test VHS_VideoCombine history output filename and actual GPU run.
6. Add Windows UI request submission, polling and result download.

Vast reference: https://github.com/vast-ai/pyworker/tree/main/workers/comfyui-json
