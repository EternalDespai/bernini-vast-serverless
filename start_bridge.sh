#!/usr/bin/env bash
# Starts *only* the bridge and the SDK adapter, after ComfyUI and models
# have already been provisioned. Do not use as a complete Vast startup script.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
: "${BERNINI_BENCHMARK_JOB_ID:?Required: real test job uploaded to R2}"
: "${R2_ACCOUNT_ID:?Missing R2_ACCOUNT_ID}"
: "${R2_ACCESS_KEY_ID:?Missing R2_ACCESS_KEY_ID}"
: "${R2_SECRET_ACCESS_KEY:?Missing R2_SECRET_ACCESS_KEY}"
: "${R2_BUCKET:?Missing R2_BUCKET}"
: "${COMFY_INPUT_DIR:?Missing COMFY_INPUT_DIR}"
: "${COMFY_OUTPUT_DIR:?Missing COMFY_OUTPUT_DIR}"

# Refuse to accept paid requests until all six model files and ComfyUI nodes
# are confirmed healthy. This check does not run inference.
export COMFY_DIR="${COMFY_DIR:-/workspace/ComfyUI}"
export COMFY_API_URL="${COMFY_API_URL:-http://127.0.0.1:18188}"
python -u preflight.py --comfy-dir "$COMFY_DIR" \\
  --manifest "${BERNINI_MODEL_MANIFEST:-model_manifest.example.json}" \\
  --api-url "$COMFY_API_URL"

export BERNINI_BRIDGE_LOG="${BERNINI_BRIDGE_LOG:-/tmp/bernini-bridge.log}"
touch "$BERNINI_BRIDGE_LOG"
python -u bridge_api.py >>"$BERNINI_BRIDGE_LOG" 2>&1 &
bridge_pid=$!
trap 'kill "$bridge_pid" 2>/dev/null || true' EXIT

python - <<'PY'
import os, time, urllib.request
base = 'http://127.0.0.1:' + os.getenv('BERNINI_BRIDGE_PORT', '18300')
for _ in range(60):
    try:
        with urllib.request.urlopen(base + '/health', timeout=2) as response:
            if response.status == 200:
                break
    except Exception:
        pass
    time.sleep(1)
else:
    raise SystemExit('Bernini bridge did not start')
PY
printf '%s\n' "BERNINI_BRIDGE_READY" >>"$BERNINI_BRIDGE_LOG"
exec python -u worker.py
