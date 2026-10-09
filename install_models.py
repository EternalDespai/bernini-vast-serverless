#!/usr/bin/env python3
"""Manifest-driven and resumable Hugging Face model installer.

Requires verified repo_id + revision + filename for every model.
Downloads in HF cache then hardlinks/copies to ComfyUI model path; disk
requirements may exceed 100 GB while caching. Set HF_HOME to persistent
storage, or mount an already populated cache.
"""
import argparse
import json
import os
from pathlib import Path, PurePosixPath

from huggingface_hub import hf_hub_download


def validate_model(record):
    target = record.get("target", "")
    parts = PurePosixPath(target)
    if (not target or parts.is_absolute() or ".." in parts.parts
            or len(parts.parts) != 2 or parts.suffix != ".safetensors"):
        raise ValueError(f"Unsafe target: {target!r}")
    if parts.parts[0] not in {"diffusion_models", "loras", "vae", "text_encoders", "clip"}:
        raise ValueError(f"Unexpected model directory: {target}")
    for key in ("repo_id", "revision", "filename"):
        if not isinstance(record.get(key), str) or not record[key].strip():
            raise ValueError(f"Missing {key} for {target}")
    if not isinstance(record.get("min_bytes"), int) or record["min_bytes"] < 1000000:
        raise ValueError(f"Invalid min_bytes for {target}")
    return parts


def install(manifest_path, models_dir, dry_run=False):
    manifest = json.loads(Path(manifest_path).read_text("utf-8"))
    records = manifest["models"]
    if not isinstance(records, list) or len(records) < 2:
        raise ValueError("Model manifest incomplete")
    validated = [(record, validate_model(record)) for record in records]
    paths = [str(path) for _, path in validated]
    if len(paths) != len(set(paths)):
        raise ValueError("Duplicate model targets")
    root = Path(models_dir).resolve()
    for record, relative in validated:
        dest = root.joinpath(*relative.parts)
        if dest.is_file() and dest.stat().st_size >= record["min_bytes"]:
            print(f"SKIP existing {dest}", flush=True)
            continue
        if dry_run:
            print(f"WOULD DOWNLOAD {record['repo_id']}@{record['revision']}/{record['filename']} -> {dest}")
            continue
        source = Path(hf_hub_download(
            repo_id=record["repo_id"],
            revision=record["revision"],
            filename=record["filename"],
        ))
        if source.stat().st_size < record["min_bytes"]:
            raise RuntimeError(f"Downloaded model too small: {source}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        temp = dest.with_name(dest.name + ".partial")
        try:
            if temp.exists():
                temp.unlink()
            try:
                os.link(source, temp)
                print(f"LINKED cached model without duplicate disk usage: {dest}", flush=True)
            except OSError as exc:
                # A copy across filesystems can silently double the storage
                # required by multi-GB checkpoints. Fail with an actionable
                # message rather than exhausting the worker's disk.
                raise RuntimeError(
                    f"Cannot hardlink cached model {source} to {dest}: {exc}. "
                    "Place HF_HOME on the same filesystem as models_dir "
                    "(e.g. $COMFY_DIR/models/.huggingface-cache)."
                ) from exc
            temp.replace(dest)
        finally:
            temp.unlink(missing_ok=True)
        print(f"INSTALLED {dest}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="model_manifest.example.json")
    parser.add_argument("--models-dir", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    install(args.manifest, args.models_dir, args.dry_run)
