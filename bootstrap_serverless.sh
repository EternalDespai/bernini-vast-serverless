#!/usr/bin/env bash
# Single command *inside an already running Vast ComfyUI worker container*.
# Installs Bernini models, restarts ComfyUI and starts bridge + Vast PyWorker.
# This does NOT create a Vast endpoint, allocate a GPU or install ComfyUI.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

export COMFY_DIR="${COMFY_DIR:-/workspace/ComfyUI}"
export COMFY_INPUT_DIR="${COMFY_INPUT_DIR:-$COMFY_DIR/input}"
export COMFY_OUTPUT_DIR="${COMFY_OUTPUT_DIR:-$COMFY_DIR/output}"
export COMFY_API_URL="${COMFY_API_URL:-http://127.0.0.1:18188}"
export BERNINI_MODEL_MANIFEST="${BERNINI_MODEL_MANIFEST:-$PWD/model_manifest.example.json}"

: "${BERNINI_BENCHMARK_JOB_ID:?Set a dedicated R2 benchmark job ID}"
: "${R2_ACCOUNT_ID:?Missing R2_ACCOUNT_ID}"
: "${R2_ACCESS_KEY_ID:?Missing R2_ACCESS_KEY_ID}"
: "${R2_SECRET_ACCESS_KEY:?Missing R2_SECRET_ACCESS_KEY}"
: "${R2_BUCKET:?Missing R2_BUCKET}"
test -d "$COMFY_DIR/custom_nodes" || { echo "ComfyUI not installed: $COMFY_DIR" >&2; exit 1; }

python -m pip install -r requirements.txt
bash setup_bernini.sh

# On the proven Vast ComfyUI on-demand image, supervisor owns the service.
# Do not assume that all Serverless templates use this same configuration.
if [[ -f /etc/supervisor/supervisord.conf ]]; then
  supervisorctl -c /etc/supervisor/supervisord.conf restart comfyui
else
  echo "Supervisor config missing; set a valid ComfyUI restart hook" >&2
  exit 1
fi

for i in $(seq 1 60); do
  if python preflight.py --comfy-dir "$COMFY_DIR" \
       --manifest "$BERNINI_MODEL_MANIFEST" --api-url "$COMFY_API_URL"; then
    exec bash start_bridge.sh
  fi
  sleep 5
done
echo "Bernini preflight failed after restart; refusing to start PyWorker" >&2
exit 1
