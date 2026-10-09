#!/usr/bin/env python3
"""Manifest-driven and resumable Hugging Face model installer.

Requires verified repo_id + revision + filename for every model.
Downloads into the HF cache and hardlinks into ComfyUI models (same filesystem
required). Set HF_HOME to a directory on the models filesystem; avoid
cross-filesystem copies that can exhaust serverless disk.
"""
import argparse
import hashlib
import json
import os
import shutil
import re
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
    sha = record.get("sha256")
    if sha is not None and (not isinstance(sha, str) or
                            not re.fullmatch(r"[a-fA-F0-9]{64}", sha)):
        raise ValueError(f"Invalid sha256 for {target}")
    return parts


def verify_sha256(path, expected):
    if not expected:
        return True
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().lower() == expected.lower()


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
            if verify_sha256(dest, record.get("sha256")):
                print(f"SKIP existing {dest}", flush=True)
                continue
            raise RuntimeError(f"Existing model SHA256 mismatch: {dest}")
        if dry_run:
            print(f"WOULD DOWNLOAD {record['repo_id']}@{record['revision']}/{record['filename']} -> {dest}")
            continue
        # Check capacity before beginning a large transfer. A model's
        # min_bytes is a lower bound, not an exact download size.
        free_bytes = shutil.disk_usage(root).free
        reserve_bytes = 8 * 1024 ** 3
        required_bytes = record["min_bytes"] + reserve_bytes
        if free_bytes < required_bytes:
            raise RuntimeError(
                f"Insufficient disk before downloading {relative}: "
                f"{free_bytes / 1024**3:.1f} GiB free; at least "
                f"{required_bytes / 1024**3:.1f} GiB required "
                "(model minimum plus 8 GiB reserve)."
            )
        print(f"BERNINI_MODEL_DOWNLOAD_START {relative} "
              f"free_gib={free_bytes / 1024**3:.1f}", flush=True)
        source = Path(hf_hub_download(
            repo_id=record["repo_id"],
            revision=record["revision"],
            filename=record["filename"],
        )).resolve(strict=True)
        # Hugging Face snapshots are symlinks. os.link(snapshot, ...) may
        # hardlink the symlink itself, creating a broken ComfyUI model path.
        # Resolve to the actual blob before making a hardlink.
        if source.stat().st_size < record["min_bytes"]:
            raise RuntimeError(f"Downloaded model too small: {source}")
        if not verify_sha256(source, record.get("sha256")):
            raise RuntimeError(f"Downloaded model SHA256 mismatch: {source}")
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
