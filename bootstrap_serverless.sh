#!/usr/bin/env bash
# Manual fallback inside a Vast container with ComfyUI already installed.
# PYWORKER_REPO templates automatically invoke worker.py instead.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
python -m pip install -r requirements.txt
exec python -u worker.py
