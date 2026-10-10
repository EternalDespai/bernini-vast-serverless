#!/usr/bin/env python3
"""Fail-fast Bernini readiness checks; no inference, downloads or GPU rental.

Validates exact model names and minimum file sizes from the pinned manifest,
all broken .safetensors symlinks, ComfyUI node registration and writable
input/output paths. Exits nonzero if anything is missing.
"""
import argparse
import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

REQUIRED_NODES = ("BerniniStudio", "VHS_LoadVideo", "VHS_VideoCombine",
                  "CLIPLoader", "VAELoader", "UNETLoader", "LoraLoaderModelOnly",
                  "ModelSamplingSD3", "KSamplerSelect", "BasicScheduler",
                  "SplitSigmas", "SamplerCustom", "VAEDecode", "LoadImage")
MIN_FREE_GB = 8


def check(manifest_path, comfy_dir, base_url, check_api=True, min_free_gb=MIN_FREE_GB):
    errors = []
    root = Path(comfy_dir)
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    records = manifest.get("models", [])
    if not isinstance(records, list) or len(records) != 6:
        errors.append(f"Expected six model entries; got {len(records) if isinstance(records, list) else 'invalid'}")
        records = []
    for item in records:
        relative = item.get("target", "")
        if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            errors.append(f"Unsafe model target: {relative!r}")
            continue
        target = root / "models" / relative
        if target.is_symlink() and not target.exists():
            errors.append(f"BROKEN MODEL LINK: {target}")
        elif not target.is_file():
            errors.append(f"MISSING MODEL: {target}")
        elif target.stat().st_size < item.get("min_bytes", 0):
            errors.append(f"MODEL TOO SMALL: {target} ({target.stat().st_size} bytes)")
        else:
            print(f"OK model: {relative}", flush=True)

    model_root = root / "models"
    if model_root.is_dir():
        for link in model_root.rglob("*.safetensors"):
            if link.is_symlink() and not link.exists():
                msg = f"BROKEN LINK: {link}"
                if msg not in errors:
                    errors.append(msg)

    for name in ("input", "output"):
        path = root / name
        if not path.is_dir() or not os.access(path, os.W_OK):
            errors.append(f"Missing/unwritable ComfyUI {name} directory: {path}")

    if root.exists():
        free_gb = shutil.disk_usage(root).free / (1024 ** 3)
        print(f"Free disk: {free_gb:.1f} GiB", flush=True)
        if free_gb < min_free_gb:
            errors.append(f"Insufficient free disk: {free_gb:.1f} GiB (<{min_free_gb})")

    # Full-video mode relies on FFmpeg even when all ComfyUI nodes load.
    if os.getenv("BERNINI_FULL_VIDEO", "1") == "1":
        for binary in ("ffmpeg", "ffprobe"):
            if not shutil.which(binary):
                errors.append(f"Missing required video tool: {binary}")

    if check_api:
        for node in REQUIRED_NODES:
            try:
                with urllib.request.urlopen(
                    base_url.rstrip("/") + "/object_info/" + node, timeout=15
                ) as response:
                    info = json.load(response)
                if node not in info:
                    errors.append(f"NODE NOT REGISTERED: {node}")
                else:
                    print(f"OK node: {node}", flush=True)
            except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
                errors.append(f"ComfyUI unavailable or node missing ({node}): {exc}")

    for error in errors:
        print("FAIL:", error, file=sys.stderr, flush=True)
    if errors:
        print(f"PRE-FLIGHT FAILED: {len(errors)} problem(s)", file=sys.stderr, flush=True)
        return False
    print("PRE-FLIGHT OK: six models, links, disk, paths and required nodes", flush=True)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="model_manifest.example.json")
    parser.add_argument("--comfy-dir", default=os.getenv("COMFY_DIR", "/workspace/ComfyUI"))
    parser.add_argument("--api-url", default=os.getenv("COMFY_API_URL", "http://127.0.0.1:18188"))
    parser.add_argument("--skip-api", action="store_true",
                        help="Offline file-only check (not sufficient for worker readiness)")
    args = parser.parse_args()
    sys.exit(0 if check(args.manifest, args.comfy_dir, args.api_url,
                        check_api=not args.skip_api) else 1)
