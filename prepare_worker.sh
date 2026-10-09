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
stage benchmark_inputs
python - <<'PY'
import os
from r2_bridge import s3_client, JOB_RE
job = os.environ['BERNINI_BENCHMARK_JOB_ID']
if not JOB_RE.fullmatch(job):
    raise SystemExit('Invalid BERNINI_BENCHMARK_JOB_ID')
s3 = s3_client()
for name in ('source.mp4', 'reference.jpg', 'workflow_api.json'):
    try:
        meta = s3.head_object(Bucket=os.environ['R2_BUCKET'], Key=f'jobs/{job}/{name}')
        if meta['ContentLength'] <= 0:
            raise ValueError('Empty input')
    except Exception as exc:
        raise SystemExit(f'Benchmark input unavailable: {name} ({type(exc).__name__}); check R2 and benchmark ID') from None
print('BERNINI_BENCHMARK_INPUTS_READY', flush=True)
PY
stage setup_bernini
bash setup_bernini.sh
stage restart_comfyui
bash restart_comfyui.sh

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
