#!/usr/bin/env python3
"""Repair broken Hugging Face blob symlinks under ComfyUI models.

Only repairs links whose exact blob hash matches one regular file in the
configured HF cache. Never downloads or deletes model contents.
"""
import argparse
from pathlib import Path


def repair(models_dir: Path, hf_home: Path) -> tuple[int, list[str]]:
    cache = hf_home / "hub"
    fixed = 0
    problems = []
    for link in models_dir.rglob("*.safetensors"):
        if not link.is_symlink() or link.exists():
            continue
        blob = link.readlink().name
        matches = [p for p in cache.glob("models--*/blobs/" + blob) if p.is_file()]
        if len(matches) != 1:
            problems.append(f"{link}: found {len(matches)} candidate blobs")
            continue
        target = matches[0].resolve()
        link.unlink()
        link.symlink_to(target)
        print(f"FIXED {link.name} -> {target}", flush=True)
        fixed += 1
    return fixed, problems


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--models-dir", default="/workspace/ComfyUI/models")
    parser.add_argument("--hf-home", default="/workspace/.hf_home")
    args = parser.parse_args()
    fixed, problems = repair(Path(args.models_dir), Path(args.hf_home))
    print(f"Repaired: {fixed}; unresolved: {len(problems)}")
    for problem in problems:
        print("UNRESOLVED", problem)
    if problems:
        raise SystemExit(1)
