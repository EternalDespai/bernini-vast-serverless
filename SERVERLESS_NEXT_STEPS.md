# Bernini Serverless deployment checklist (after successful H100 smoke test)

The on-demand H100 run succeeded for R2 job
`a5186804b4d848c0acc1792d64d97024`, returning
`jobs/<job-id>/result.mp4`. This confirms the native ComfyUI + R2 path,
**not** the Vast Serverless endpoint.

## Fixes captured in this branch

- `r2_bridge.py` patches **all** `LoadImage` nodes as well as Bernini
  `slot_images`, avoiding the `Invalid image file: reference.jpg` validation failure.
- ComfyUI validation/execution errors are included in CLI diagnostics.
- `repair_model_links.py` repairs broken HF-cache blob links without downloading.
  The original failure came from symlinks pointing to nonexistent `../../../blobs`
  instead of the actual `/workspace/.hf_home/hub/models--*/blobs`.
- `install_models.py` already installs real hardlinks/copies rather than creating
  fragile relative links. Run `python -m unittest test_r2_bridge.py` before deployment.

## Before creating a paid Serverless endpoint

1. Destroy the previous on-demand H100 after verifying the result and preserving
   any instance-only changes. Stopping may still incur disk costs.
2. Choose the **Vast ComfyUI Serverless** template with a sufficiently large disk
   (120 GB was used successfully for the smoke test; verify headroom).
3. Provision BerniniStudio + VideoHelperSuite and all six weights. Ensure
   `BerniniStudio`, `VHS_LoadVideo`, `VHS_VideoCombine` register **after**
   restarting ComfyUI. Verify model files are real and readable, not broken links.
4. Install the bridge's Python dependencies and launch the local HTTP bridge and
   SDK PyWorker **as part of the Serverless startup**, not merely by SSH on a
   temporary on-demand instance. Existing `start_bridge.sh` is only a partial
   launcher; its integration with the Vast template has **not been tested**.
5. Configure `BERNINI_BENCHMARK_JOB_ID` to a dedicated non-sensitive 17-frame
   test job in R2. Benchmarking performs real inference and costs GPU time.
6. Configure restricted R2 credentials as private environment variables; do not
   commit them or pass them to clients. Rotate credentials previously used on a
   temporary GPU. The current bridge trusts a supplied job ID: use Vast endpoint
   authentication and bucket-scoped credentials, and do not publicly expose port 18300.
7. Check the worker is healthy, benchmarks complete, and an authenticated
   `POST /generate/sync` request containing `{"job_id":"<32 hex>"}` succeeds.
   This is an intended API contract, **not yet proven against the live SDK**.
8. Configure `max_workers=1` to cap parallel spend. To permit zero total workers,
   Vast docs require `min_load=0`, `cold_workers=0`, and a positive
   `inactivity_timeout`. Review `min_workers` too. Cold starts can be long and
   storage/bandwidth may still incur charges.
9. Only after live endpoint validation, add the authenticated Vast request to the
   Windows upload UI. The current UI uploads to R2 but does not start Serverless.

## Verified manual on-demand job command

```bash
export COMFY_INPUT_DIR=/workspace/ComfyUI/input
export COMFY_OUTPUT_DIR=/workspace/ComfyUI/output
export COMFY_API_URL=http://127.0.0.1:18188
# Set R2_* variables securely in the private runtime.
python -u r2_bridge.py a5186804b4d848c0acc1792d64d97024 --timeout 7200
```

## References

- https://github.com/vast-ai/pyworker
- https://docs.vast.ai/guides/serverless/managing-scale
- https://docs.vast.ai/guides/serverless/comfyui-wan-2.2
