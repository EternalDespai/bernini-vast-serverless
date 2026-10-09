#!/usr/bin/env python3
"""Create a cost-capped Vast endpoint/workergroup with an EXISTING template.

Default is dry-run; --apply is an explicit paid-resource opt-in. Does not
guess a template hash, account permissions, or GPU compatibility.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys

def commands(name, template_hash):
    if not re.fullmatch(r"[a-z0-9_-]{3,64}", name):
        raise ValueError("Endpoint name must be 3-64 lowercase letters, digits, _ or -")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{5,128}", template_hash):
        raise ValueError("Provide an existing Vast Serverless-compatible template hash")
    return [
        ["vastai", "create", "endpoint", "--endpoint_name", name,
         "--min_load", "0", "--min_workers", "0", "--cold_workers", "0",
         "--cold_mult", "0", "--max_workers", "1", "--target_util", "0.9",
         "--inactivity_timeout", "600", "--max_queue_time", "120",
         "--target_queue_time", "30", "--raw"],
        ["vastai", "create", "workergroup", "--template_hash", template_hash,
         "--endpoint_name", name, "--cold_workers", "0", "--raw"],
    ]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint-name", default="bernini-rv2v")
    parser.add_argument("--template-hash", required=True)
    parser.add_argument("--apply", action="store_true",
                        help="Actually create resources that can incur Vast charges")
    args = parser.parse_args()
    steps = commands(args.endpoint_name, args.template_hash)
    for step in steps:
        print(" ".join(step), flush=True)
    if not args.apply:
        print("DRY RUN ONLY. Validate template startup and credentials, then add --apply.")
        return 0
    if not shutil.which("vastai"):
        raise SystemExit("Install official Vast CLI and authenticate locally first")
    print("WARNING: Vast GPU/worker storage and benchmarks may incur charges.")
    print("The template must already have PYWORKER_REPO, PYWORKER_REF, R2 secrets,")
    print("a dedicated benchmark job, correct ComfyUI supervisor and >=48GB VRAM.")
    for index, step in enumerate(steps):
        result = subprocess.run(step, text=True, capture_output=True, check=False)
        if result.returncode:
            print(f"FAILED step {index+1}: {result.stderr[-2500:]}", file=sys.stderr)
            if index == 1:
                print("Endpoint may exist without a worker group; inspect Vast console.",
                      file=sys.stderr)
            return result.returncode
        print(result.stdout[-3500:], flush=True)
    print("Created resources; NOT YET VERIFIED as ready. Check endpoint and worker logs.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
