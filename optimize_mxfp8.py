#!/usr/bin/env python3
"""Reduce MXFP8 eager quantization peak VRAM without changing model arithmetic.

Comfy-kitchen's eager quantize_mxfp8 path used a torch.where expression that
allocated both a full-size zeros_like tensor and a full-size output tensor.
At inference time, replacing it with an in-place masked fill avoids those
temporary allocations. Only patch the exact known upstream statement.
"""
import ast
import os
import re
import sys
from pathlib import Path

OLD = "data_scaled = torch.where(zero_mask.unsqueeze(-1), torch.zeros_like(data_scaled), data_scaled)"
NEW = "data_scaled.masked_fill_(zero_mask.unsqueeze(-1), 0)"
MARKER = "Bernini MXFP8 eager in-place zero-mask optimization"


def main():
    if os.environ.get("BERNINI_OPTIMIZE_MXFP8", "1") == "0":
        print("BERNINI_MXFP8_OPTIMIZATION=disabled", flush=True)
        return 0

    try:
        import comfy_kitchen
    except ImportError:
        print("BERNINI_MXFP8_OPTIMIZATION=unavailable (comfy_kitchen missing)", flush=True)
        return 0

    source = Path(comfy_kitchen.__file__).resolve().parent / "backends" / "eager" / "quantization.py"
    if not source.is_file():
        print("BERNINI_MXFP8_OPTIMIZATION=unavailable (source missing)", flush=True)
        return 0

    original = source.read_text(encoding="utf-8")
    if MARKER in original and NEW in original:
        print("BERNINI_MXFP8_OPTIMIZATION=already_applied", flush=True)
        return 0

    count = original.count(OLD)
    if count != 1:
        print(
            f"BERNINI_MXFP8_OPTIMIZATION=skipped (expected one matching expression, found {count})",
            flush=True,
        )
        return 0

    # Only replace the known eager expression; do not change CUDA/Triton paths,
    # quantization scales, output dtype, or any model/workflow parameters.
    updated = re.sub(
        r"(?m)^(?P<indent>[ \\t]*)" + re.escape(OLD) + r"$",
        lambda match: (
            f"{match.group('indent')}# {MARKER}\\n"
            f"{match.group('indent')}{NEW}"
        ),
        original,
        count=1,
    )
    try:
        ast.parse(updated, filename=str(source))
    except SyntaxError as exc:
        print(f"BERNINI_MXFP8_OPTIMIZATION=skipped (syntax: {exc})", flush=True)
        return 0

    backup = source.with_name(source.name + ".bernini-original")
    if not backup.exists():
        backup.write_text(original, encoding="utf-8")
    temporary = source.with_name(source.name + ".bernini-tmp")
    temporary.write_text(updated, encoding="utf-8")
    temporary.replace(source)
    print("BERNINI_MXFP8_OPTIMIZATION=applied (in-place zero mask)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
