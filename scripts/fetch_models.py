#!/usr/bin/env python3
"""Download ReazonSpeech k2-v2 int8 model files for bundling.

Run by developers / CI — not by end users.

Downloads the 4 int8 model files from HuggingFace into models/reazonspeech-k2-v2/.
These are then bundled into the Nuitka build so the packaged app never needs to
download anything at runtime.

Usage:
    python scripts/fetch_models.py
"""

import shutil
import sys
from pathlib import Path

HF_REPO_ID = "reazon-research/reazonspeech-k2-v2"

MODEL_FILES = [
    "encoder-epoch-99-avg-1.int8.onnx",
    "decoder-epoch-99-avg-1.int8.onnx",
    "joiner-epoch-99-avg-1.int8.onnx",
    "tokens.txt",
]

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "models" / "reazonspeech-k2-v2"


def main():
    try:
        import huggingface_hub as hf
    except ImportError:
        print("ERROR: huggingface_hub is not installed.", file=sys.stderr)
        print("  pip install huggingface_hub", file=sys.stderr)
        sys.exit(1)

    print(f"Downloading ReazonSpeech k2-v2 int8 model files")
    print(f"  Repo:        {HF_REPO_ID}")
    print(f"  Destination: {DEST}")
    print()

    # Download via huggingface_hub (uses cache, resolves symlinks)
    print("Fetching from HuggingFace (cached if available)...")
    cache_dir = hf.snapshot_download(HF_REPO_ID, allow_patterns=MODEL_FILES)
    cache_path = Path(cache_dir)

    # Copy actual files (resolving symlinks) into project directory
    DEST.mkdir(parents=True, exist_ok=True)

    for filename in MODEL_FILES:
        src = cache_path / filename
        dst = DEST / filename

        if not src.exists():
            print(f"  MISSING  {filename} — not found in HuggingFace download", file=sys.stderr)
            sys.exit(1)

        # resolve() follows symlinks to the actual blob file
        shutil.copy2(src.resolve(), dst)
        size_mb = dst.stat().st_size / (1024 * 1024)
        print(f"  OK  {filename} ({size_mb:.1f} MB)")

    print()
    total_mb = sum((DEST / f).stat().st_size for f in MODEL_FILES) / (1024 * 1024)
    print(f"Done. Total: {total_mb:.1f} MB in {DEST}")


if __name__ == "__main__":
    main()
