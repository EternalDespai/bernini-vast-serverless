# Bernini RV2V — paid Serverless test gate (2026-10-09)

## Changes already made in this branch

- ComfyUI custom-node requirements install into `/venv/main/bin/python` (override with `COMFY_PYTHON` if the template uses another interpreter).
- Model cache defaults to `$COMFY_DIR/models/.huggingface-cache` and model installation hardlinks instead of duplicating multi-GB weights across filesystems.
- Model installer checks a minimum free-disk reserve before each download; SHA256 is checked for entries that pin a hash.
- Worker writes a newline-terminated readiness marker; bootstrap stages and failures are printed.
- Full-video preflight checks ffmpeg and ffprobe.
- CI compiles Python, checks shell syntax, validates the manifest dry-run and runs offline unit tests.

## Before authorizing a paid GPU cold start

1. Confirm the latest **GitHub Actions** run on `feat/r2-comfy-bridge` is green. No GPU is needed for this check.
2. In Vast template attached to Worker Group **50321** / endpoint **40317** (`ylxfcvlr`), verify `PYWORKER_REPO=https://github.com/EternalDespai/bernini-vast-serverless`, `PYWORKER_REF=feat/r2-comfy-bridge`, `BERNINI_BENCHMARK_JOB_ID=85cb2049fa924b6793946438d147eb4e`.
3. Verify template **contains**, without sharing their values, `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, and `R2_BUCKET=bernini-rv2v`. Account-only variables were missing from earlier serverless workers.
4. Confirm image `vastai/comfy:v0.20.1-cuda-12.9-py312`, onstart and Docker settings remain unchanged. Verify `/venv/main/bin/python` is the ComfyUI interpreter from the previous instance logs; if not, set `COMFY_PYTHON` appropriately.
5. Check the template's disk allocation (120 GB), available balance, max_workers=1, min_workers=0, and ability to pause/stop further starts.
6. Keep the benchmark inputs in R2; do **not** regenerate or upload the 17-frame benchmark. Never paste secrets in chat.

## Single controlled paid test

- Authorize only **one** worker start; do not auto-retry on failure.
- First inspect Vast **Instance Logs**, not only Docker daemon logs.
- Look for `BERNINI_BOOTSTRAP_STAGE=setup_bernini`, `BERNINI_MODEL_DOWNLOAD_START`, `BERNINI_BOOTSTRAP_STAGE=restart_comfyui`, `BERNINI_BOOTSTRAP_STAGE=preflight`, `BERNINI_PREFLIGHT_READY`, then `BERNINI_BRIDGE_READY`.
- If a `BERNINI_BOOTSTRAP_FAILED` or missing-model / missing-node / ffmpeg / disk error appears, stop and fix that specific issue before another worker start.
- A running Docker container, `BACKENDS_READY`, or a ComfyUI port alone **does not** establish that Bernini is ready.
- After benchmark readiness, run the intended test job and verify output MP4 in R2, expected frames, audio, chunk stitching, and scale-to-zero.

## Unverified until a paid run

Live Vast template/Worker Group configuration, model download availability and exact size, PyWorker SDK behavior, benchmark inference, model node registration, long-video quality, and shutdown/billing behavior. Offline tests cannot certify any of these.
