"""Vast starter template expects workers/comfyui-json/worker.py for BACKEND=comfyui-json.

The implementation lives in the repository root. This adapter makes the
standard Vast bootstrap load our R2 job-id worker rather than its stock
workflow_json worker.
"""
import os
import runpy
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
# Vast start_server.sh installs root requirements with uv before this entrypoint.
# uv-created Python 3.10 environments do not necessarily include pip.
# Manual launches should use bootstrap_serverless.sh to install requirements.
try:
    print("BERNINI_BOOTSTRAP_STAGE=start_worker", flush=True)
    runpy.run_path(str(ROOT / "worker.py"), run_name="__main__")
except Exception:
    print("BERNINI_BOOTSTRAP_FAILED", file=sys.stderr, flush=True)
    traceback.print_exc()
    raise
