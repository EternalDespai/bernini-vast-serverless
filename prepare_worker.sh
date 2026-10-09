#!/usr/bin/env bash
# Run by worker.py when Vast template launches PYWORKER_REPO/worker.py.
set -euo pipefail
BERNINI_BOOTSTRAP_STAGE="init"
trap 'code=$?; if (( code != 0 )); then echo "BERNINI_BOOTSTRAP_FAILED stage=$BERNINI_BOOTSTRAP_STAGE exit=$code" >&2; fi' EXIT
stage() { BERNINI_BOOTSTRAP_STAGE="$1"; echo "BERNINI_BOOTSTRAP_STAGE=$1" >&2; }
cd "$(dirname "$(readlink -f "$0")")"
if [[ -z "${COMFY_DIR:-}" ]]; then
  for candidate in /workspace/ComfyUI /opt/ComfyUI /opt/comfyui /workspace/comfyui; do
    if [[ -d "$candidate/custom_nodes" && -d "$candidate/models" ]]; then
      export COMFY_DIR="$candidate"
      break
    fi
  done
fi
: "${COMFY_DIR:?ComfyUI root not found; set COMFY_DIR}"
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
stage setup_bernini
bash setup_bernini.sh
stage restart_comfyui
if command -v supervisorctl >/dev/null 2>&1; then
  supervisor=(supervisorctl)
  if [[ -f /etc/supervisor/supervisord.conf ]]; then
    supervisor+=(-c /etc/supervisor/supervisord.conf)
  fi
  service="${BERNINI_COMFY_SUPERVISOR_NAME:-}"
  if [[ -z "$service" ]]; then
    # Detect the real ComfyUI supervisor process name instead of assuming it.
    service="$("${supervisor[@]}" status 2>/dev/null |
      awk 'tolower($1) ~ /comfyui/ && tolower($1) !~ /wrapper/ {print $1; exit}')"
  fi
  if [[ -z "$service" ]]; then
    echo "No ComfyUI supervisor service found; set BERNINI_COMFY_SUPERVISOR_NAME" >&2
    exit 1
  fi
  "${supervisor[@]}" restart "$service"
else
  echo "Cannot restart ComfyUI: supervisorctl missing" >&2
  exit 1
fi
stage preflight
for attempt in $(seq 1 60); do
  if python preflight.py --comfy-dir "$COMFY_DIR" --manifest "$BERNINI_MODEL_MANIFEST" --api-url "$COMFY_API_URL"; then
    echo BERNINI_PREFLIGHT_READY >&2
    exit 0
  fi
  sleep 5
done
echo "Bernini preflight failed after 5 minutes" >&2
exit 1
