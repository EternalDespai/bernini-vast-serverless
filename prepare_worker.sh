#!/usr/bin/env bash
# Run by worker.py when Vast template launches PYWORKER_REPO/worker.py.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
export COMFY_DIR="${COMFY_DIR:-/workspace/ComfyUI}"
export COMFY_INPUT_DIR="${COMFY_INPUT_DIR:-$COMFY_DIR/input}"
export COMFY_OUTPUT_DIR="${COMFY_OUTPUT_DIR:-$COMFY_DIR/output}"
export COMFY_API_URL="${COMFY_API_URL:-http://127.0.0.1:18188}"
export BERNINI_MODEL_MANIFEST="${BERNINI_MODEL_MANIFEST:-$PWD/model_manifest.example.json}"
: "${BERNINI_BENCHMARK_JOB_ID:?Required dedicated R2 benchmark job}"
: "${R2_ACCOUNT_ID:?Required R2_ACCOUNT_ID}"
: "${R2_ACCESS_KEY_ID:?Required R2_ACCESS_KEY_ID}"
: "${R2_SECRET_ACCESS_KEY:?Required R2_SECRET_ACCESS_KEY}"
: "${R2_BUCKET:?Required R2_BUCKET}"
test -d "$COMFY_DIR/custom_nodes" || { echo "ComfyUI missing: $COMFY_DIR" >&2; exit 1; }
bash setup_bernini.sh
if command -v supervisorctl >/dev/null 2>&1; then
  if [[ -f /etc/supervisor/supervisord.conf ]]; then
    supervisorctl -c /etc/supervisor/supervisord.conf restart "${BERNINI_COMFY_SUPERVISOR_NAME:-comfyui}"
  else
    supervisorctl restart "${BERNINI_COMFY_SUPERVISOR_NAME:-comfyui}"
  fi
else
  echo "Cannot restart ComfyUI: supervisorctl missing" >&2
  exit 1
fi
for attempt in $(seq 1 60); do
  if python preflight.py --comfy-dir "$COMFY_DIR" --manifest "$BERNINI_MODEL_MANIFEST" --api-url "$COMFY_API_URL"; then
    echo BERNINI_PREFLIGHT_READY >&2
    exit 0
  fi
  sleep 5
done
echo "Bernini preflight failed after 5 minutes" >&2
exit 1
