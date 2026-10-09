#!/usr/bin/env bash
# Interactive, one-command Vast On-Demand runner for an existing R2 Bernini job.
# Usage: bash -c "$(curl -fsSL https://raw.githubusercontent.com/EternalDespai/bernini-vast-serverless/feat/r2-comfy-bridge/run_ondemand.sh)"
set -Eeuo pipefail
umask 077
stage="init"
trap 'rc=$?; if (( rc != 0 )); then echo "BERNINI_ONDEMAND_FAILED stage=$stage exit=$rc" >&2; fi' EXIT
stage_log() { stage="$1"; echo "BERNINI_ONDEMAND_STAGE=$stage"; }

JOB_ID="${BERNINI_JOB_ID:-85cb2049fa924b6793946438d147eb4e}"
[[ "$JOB_ID" =~ ^[a-f0-9]{32}$ ]] || { echo "Invalid BERNINI_JOB_ID" >&2; exit 1; }
export BERNINI_BENCHMARK_JOB_ID="$JOB_ID"
export BERNINI_FULL_VIDEO=1
export BERNINI_DELETE_INPUTS_AFTER_SUCCESS=0
export R2_BUCKET="${R2_BUCKET:-bernini-rv2v}"
export COMFY_DIR="${COMFY_DIR:-/workspace/ComfyUI}"
export COMFY_INPUT_DIR="$COMFY_DIR/input"
export COMFY_OUTPUT_DIR="$COMFY_DIR/output"
export COMFY_API_URL="${COMFY_API_URL:-http://127.0.0.1:18188}"
export COMFY_PYTHON="${COMFY_PYTHON:-/venv/main/bin/python}"
export HF_HOME="${HF_HOME:-$COMFY_DIR/models/.huggingface-cache}"
REPO_DIR="${BERNINI_REPO_DIR:-/workspace/bernini-vast-serverless}"
RUN_PYTHON="${BERNINI_RUN_PYTHON:-/workspace/bernini-runner-venv/bin/python}"
[[ -d "$COMFY_DIR/custom_nodes" && -d "$COMFY_DIR/models" ]] || { echo "Expected Vast ComfyUI image at $COMFY_DIR" >&2; exit 1; }
[[ -x "$COMFY_PYTHON" ]] || { echo "ComfyUI Python missing: $COMFY_PYTHON" >&2; exit 1; }
for tool in git curl ffmpeg ffprobe; do command -v "$tool" >/dev/null || { echo "Missing $tool" >&2; exit 1; }; done

# Read R2 secrets only from existing environment or the interactive terminal.
# Never echo secret values, write them to a config file or include them in URLs.
prompt_var() {
  local name="$1" label="$2" secret="$3" value=""
  if [[ -n "${!name:-}" ]]; then return; fi
  [[ -t 0 ]] || { echo "Missing $name; run in an interactive terminal" >&2; exit 1; }
  if [[ "$secret" == 1 ]]; then
    read -r -s -p "$label: " value; printf '\n'
  else
    read -r -p "$label: " value
  fi
  [[ -n "$value" ]] || { echo "Missing $name" >&2; exit 1; }
  printf -v "$name" '%s' "$value"
  export "$name"
}
stage_log credentials
prompt_var R2_ACCOUNT_ID "R2 Account ID" 0
prompt_var R2_ACCESS_KEY_ID "R2 Access Key ID" 1
prompt_var R2_SECRET_ACCESS_KEY "R2 Secret Access Key" 1

stage_log checkout
if [[ ! -d "$REPO_DIR/.git" ]]; then
  [[ ! -e "$REPO_DIR" ]] || { echo "Repo path exists but is not Git: $REPO_DIR" >&2; exit 1; }
  git clone --depth 1 --branch feat/r2-comfy-bridge https://github.com/EternalDespai/bernini-vast-serverless.git "$REPO_DIR"
fi
cd "$REPO_DIR"
git fetch --depth 1 origin feat/r2-comfy-bridge
git checkout --detach FETCH_HEAD
export BERNINI_MODEL_MANIFEST="$REPO_DIR/model_manifest.example.json"

stage_log runner_dependencies
if [[ ! -x "$RUN_PYTHON" ]]; then
  python3 -m venv "$(dirname "$(dirname "$RUN_PYTHON")")"
fi
"$RUN_PYTHON" -m pip install --disable-pip-version-check 'boto3>=1.34,<2' 'requests>=2.31,<3' 'websocket-client>=1.7,<2' 'huggingface_hub>=0.26,<2'

# Verify job exists before spending time downloading 35+ GB of models.
stage_log r2_inputs
"$RUN_PYTHON" - <<'PY'
from r2_bridge import s3_client, env
job = env("BERNINI_BENCHMARK_JOB_ID")
bucket = env("R2_BUCKET")
s3 = s3_client()
for name in ("source.mp4", "reference.jpg", "workflow_api.json"):
    key = f"jobs/{job}/{name}"
    meta = s3.head_object(Bucket=bucket, Key=key)
    print(f"R2 input OK: {name} ({meta['ContentLength']} bytes)", flush=True)
PY

stage_log install_models_and_nodes
# setup_bernini uses 'python' for the model downloader; prepend the isolated
# runner venv so boto3/Hugging Face are available without altering ComfyUI.
export PATH="$(dirname "$RUN_PYTHON"):$PATH"
bash setup_bernini.sh

stage_log restart_comfyui
command -v supervisorctl >/dev/null || { echo "supervisorctl unavailable" >&2; exit 1; }
supervisor=(supervisorctl)
if [[ -f /etc/supervisor/supervisord.conf ]]; then supervisor+=(-c /etc/supervisor/supervisord.conf); fi
service="${BERNINI_COMFY_SUPERVISOR_NAME:-}"
if [[ -z "$service" ]]; then
  service="$("${supervisor[@]}" status 2>/dev/null | awk 'tolower($1) ~ /comfyui/ && tolower($1) !~ /wrapper/ {print $1; exit}')"
fi
[[ -n "$service" ]] || { echo "ComfyUI supervisor service not found" >&2; exit 1; }
"${supervisor[@]}" restart "$service"

stage_log preflight
ready=0
for attempt in $(seq 1 60); do
  if "$RUN_PYTHON" preflight.py --comfy-dir "$COMFY_DIR" --manifest "$BERNINI_MODEL_MANIFEST" --api-url "$COMFY_API_URL"; then
    ready=1; break
  fi
  sleep 5
done
(( ready == 1 )) || { echo "Bernini preflight failed" >&2; exit 1; }

stage_log full_video
echo "Generating complete video for job $JOB_ID (16 fps; chunked; R2 output jobs/$JOB_ID/result.mp4)"
"$RUN_PYTHON" -u r2_bridge.py "$JOB_ID" --timeout "${BERNINI_TIMEOUT:-7200}"
stage_log complete
echo "BERNINI_ONDEMAND_DONE R2: jobs/$JOB_ID/result.mp4"
