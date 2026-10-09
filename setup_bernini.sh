#!/usr/bin/env bash
# Setup on an already initialized Vast ComfyUI image.
# Deliberately NOT a full Vast Serverless on-start replacement.
set -euo pipefail
: "${COMFY_DIR:?Set COMFY_DIR to the installed ComfyUI root}"
: "${BERNINI_MODEL_MANIFEST:?Point to your completed verified model manifest}"
test -d "$COMFY_DIR/custom_nodes" || { echo "ComfyUI custom_nodes missing" >&2; exit 1; }
test -d "$COMFY_DIR/models" || { echo "ComfyUI models missing" >&2; exit 1; }
git_clone_if_missing() {
  local url="$1" path="$2"
  if [[ ! -d "$path/.git" ]]; then
    if [[ -e "$path" ]]; then echo "Directory exists but is not a git repo: $path" >&2; exit 1; fi
    git clone --depth 1 "$url" "$path"
  fi
}
git_clone_if_missing https://github.com/CCpt5/ComfyUI-BerniniStudio.git "$COMFY_DIR/custom_nodes/ComfyUI-BerniniStudio"
git_clone_if_missing https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git "$COMFY_DIR/custom_nodes/ComfyUI-VideoHelperSuite"
# BerniniStudio has its own Python requirements; missing dependencies can
# prevent node registration even when the model files are correct.
# Install node dependencies into the Python environment running ComfyUI,
# not the separate Vast PyWorker environment.
COMFY_PYTHON="${COMFY_PYTHON:-/venv/main/bin/python}"
if [[ ! -x "$COMFY_PYTHON" ]]; then
  echo "ComfyUI Python not executable: $COMFY_PYTHON (set COMFY_PYTHON)" >&2
  exit 1
fi
echo "BERNINI_SETUP_COMFY_PYTHON=$COMFY_PYTHON" >&2
if [[ -f "$COMFY_DIR/custom_nodes/ComfyUI-BerniniStudio/requirements.txt" ]]; then
  "$COMFY_PYTHON" -m pip install -r "$COMFY_DIR/custom_nodes/ComfyUI-BerniniStudio/requirements.txt"
fi
if [[ -f "$COMFY_DIR/custom_nodes/ComfyUI-VideoHelperSuite/requirements.txt" ]]; then
  "$COMFY_PYTHON" -m pip install -r "$COMFY_DIR/custom_nodes/ComfyUI-VideoHelperSuite/requirements.txt"
fi
python install_models.py --manifest "$BERNINI_MODEL_MANIFEST" --models-dir "$COMFY_DIR/models"
echo "Models installed. Restart ComfyUI and validate node imports before starting PyWorker."
