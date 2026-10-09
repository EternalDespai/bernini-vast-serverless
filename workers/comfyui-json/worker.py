"""Vast starter template expects workers/comfyui-json/worker.py for BACKEND=comfyui-json.

The implementation lives in the repository root. This adapter makes the
standard Vast bootstrap load our R2 job-id worker rather than its stock
workflow_json worker.
"""
import os
import runpy
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
# The upstream starter template only guarantees its own dependencies.
# Install Bernini bridge requirements before importing r2_bridge.
subprocess.run([sys.executable, "-m", "pip", "install", "-r",
                str(ROOT / "requirements.txt")], check=True)
runpy.run_path(str(ROOT / "worker.py"), run_name="__main__")
