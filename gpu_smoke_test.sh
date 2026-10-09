#!/usr/bin/env bash
# Paid GPU smoke-test helper for an EXISTING rented Vast GPU instance.
# Do not run against an uninitialized ComfyUI directory.
set -euo pipefail
: "${COMFY_DIR:?Set COMFY_DIR to the actual ComfyUI directory}"
: "${BERNINI_JOB_ID:?Set to a 32-character test job ID already uploaded to R2}"
export COMFY_API_URL="${COMFY_API_URL:-http://127.0.0.1:18188}"
: "${R2_ACCOUNT_ID:?Missing R2 account ID}"
: "${R2_ACCESS_KEY_ID:?Missing limited R2 key}"
: "${R2_SECRET_ACCESS_KEY:?Missing limited R2 secret}"
: "${R2_BUCKET:?Missing R2 bucket}"
if [[ ! "$BERNINI_JOB_ID" =~ ^[0-9a-f]{32}$ ]]; then
  echo "Invalid BERNINI_JOB_ID" >&2; exit 1
fi
export COMFY_INPUT_DIR="$COMFY_DIR/input"
export COMFY_OUTPUT_DIR="$COMFY_DIR/output"
export BERNINI_MODEL_MANIFEST="${BERNINI_MODEL_MANIFEST:-$PWD/model_manifest.example.json}"
echo "Installing dependencies, nodes and model weights (may require > 40GB download)..."
python -m pip install -r requirements.txt
bash setup_bernini.sh
echo "Restart/reload ComfyUI NOW if it was already running before node install."
python - <<'PY'
import json,os,urllib.request
base=os.environ["COMFY_API_URL"].rstrip("/")
for node in ("BerniniStudio","VHS_LoadVideo","VHS_VideoCombine"):
  with urllib.request.urlopen(base + "/object_info/" + node, timeout=15) as r:
    info=json.load(r)
  if node not in info: raise SystemExit("Missing node: " + node + " -- restart ComfyUI")
  print("OK node:",node)
PY
echo "Submitting R2 test job $BERNINI_JOB_ID"
time python -u r2_bridge.py "$BERNINI_JOB_ID" --timeout 7200
echo "Finished: jobs/$BERNINI_JOB_ID/result.mp4 in R2"
