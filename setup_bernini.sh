#!/usr/bin/env bash
# Setup on an already initialized Vast ComfyUI image.
# Deliberately NOT a full Vast Serverless on-start replacement.
set -euo pipefail
: "${COMFY_DIR:?Set COMFY_DIR to the installed ComfyUI root}"
: "${BERNINI_MODEL_MANIFEST:?Point to your completed verified model manifest}"
test -d "$COMFY_DIR/custom_nodes" || { echo "ComfyUI custom_nodes missing" >&2; exit 1; }
test -d "$COMFY_DIR/models" || { echo "ComfyUI models missing" >&2; exit 1; }
# Pin custom nodes so a later upstream update cannot silently change inference.
git_install_pinned() {
  local url="$1" path="$2" revision="$3"
  if [[ ! -d "$path/.git" ]]; then
    if [[ -e "$path" ]]; then echo "Directory exists but is not a git repo: $path" >&2; exit 1; fi
    git init "$path"
    git -C "$path" remote add origin "$url"
  fi
  if [[ -n "$(git -C "$path" status --porcelain)" ]]; then
    echo "Custom node has local changes; refusing to overwrite: $path" >&2
    exit 1
  fi
  if [[ "$(git -C "$path" rev-parse HEAD 2>/dev/null || true)" != "$revision" ]]; then
    git -C "$path" fetch --depth 1 "$url" "$revision"
    git -C "$path" checkout --detach "$revision"
  fi
  echo "BERNINI_NODE_REVISION $(basename "$path")=$revision"
}
git_install_pinned https://github.com/CCpt5/ComfyUI-BerniniStudio.git "$COMFY_DIR/custom_nodes/ComfyUI-BerniniStudio" ca69274a2d2135052489bc0c67a2d79a64225e86
git_install_pinned https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git "$COMFY_DIR/custom_nodes/ComfyUI-VideoHelperSuite" 4d907bee61e92c2e65af3bd6383a4e4d356126d1
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
# The v0.20.1 base image predates native Bernini support. Install the
# official merge commit, while retaining the image's CUDA-enabled torch stack.
COMFY_REVISION=f8e51b674c75f41b3960d65ce83f77301ab297c9
if [[ ! -d "$COMFY_DIR/.git" ]]; then
  echo "ComfyUI must be a git checkout for the pinned core upgrade" >&2; exit 1
fi
if ! git -C "$COMFY_DIR" diff --quiet || ! git -C "$COMFY_DIR" diff --cached --quiet; then
  echo "ComfyUI has tracked local modifications; refusing to overwrite" >&2; exit 1
fi
if [[ "$(git -C "$COMFY_DIR" rev-parse HEAD)" != "$COMFY_REVISION" ]]; then
  git -C "$COMFY_DIR" fetch --depth 1 https://github.com/Comfy-Org/ComfyUI.git "$COMFY_REVISION"
  git -C "$COMFY_DIR" checkout --detach "$COMFY_REVISION"
fi
echo "BERNINI_COMFY_REVISION=$COMFY_REVISION"
constraints=$(mktemp)
trap 'rm -f "$constraints"' EXIT
"$COMFY_PYTHON" - <<'PYTORCH' > "$constraints"
from importlib.metadata import version
for package in ('torch', 'torchvision', 'torchaudio'):
    print(f'{package}=={version(package)}')
PYTORCH
export PIP_CONSTRAINT="$constraints"
"$COMFY_PYTHON" -m pip install -r "$COMFY_DIR/requirements.txt"
# Check the actual image core before downloading 38 GB of weights.
"$COMFY_PYTHON" - <<'PYCORE'
import os, sys
from pathlib import Path
root = Path(os.environ['COMFY_DIR'])
sys.path.insert(0, str(root))
import comfy.conds
if not hasattr(comfy.conds, 'CONDList'):
    raise SystemExit('ComfyUI core lacks Bernini CONDList support; use a compatible image')
for name in ('comfy/model_base.py', 'comfy/ldm/wan/model.py'):
    if 'context_latents' not in (root / name).read_text(encoding='utf-8'):
        raise SystemExit(f'ComfyUI core lacks Bernini context_latents support: {name}')
print('BERNINI_CORE_SUPPORT_READY', flush=True)
PYCORE
if [[ -f "$COMFY_DIR/custom_nodes/ComfyUI-BerniniStudio/requirements.txt" ]]; then
  "$COMFY_PYTHON" -m pip install -r "$COMFY_DIR/custom_nodes/ComfyUI-BerniniStudio/requirements.txt"
fi
if [[ -f "$COMFY_DIR/custom_nodes/ComfyUI-VideoHelperSuite/requirements.txt" ]]; then
  "$COMFY_PYTHON" -m pip install -r "$COMFY_DIR/custom_nodes/ComfyUI-VideoHelperSuite/requirements.txt"
fi
# Keep HF cache and ComfyUI models on the same filesystem so installer can
# hardlink downloaded blobs instead of storing a second full-sized copy.
export HF_HOME="${HF_HOME:-$COMFY_DIR/models/.huggingface-cache}"
mkdir -p "$HF_HOME"
echo "BERNINI_HF_HOME=$HF_HOME" >&2
python install_models.py --check-sources --manifest "$BERNINI_MODEL_MANIFEST" --models-dir "$COMFY_DIR/models"
echo "Models installed. Restart ComfyUI and validate node imports before starting PyWorker."
