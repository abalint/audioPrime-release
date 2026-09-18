#!/usr/bin/env python3
"""Regenerate data/piper_voices.json from the upstream Piper voice catalog.

The upstream voices.json (rhasspy/piper-voices on Hugging Face) is ~230 KB and
carries per-file md5 digests for every quality tier plus MODEL_CARD entries we
never read. This script slims it to just what the app needs to list and download
a voice, and writes it sorted for stable diffs.

Run this when new Piper voices are published:

    .venv/bin/python scripts/fetch_piper_catalog.py
"""

import json
import sys
import urllib.request
from pathlib import Path

CATALOG_URL = "https://huggingface.co/rhasspy/piper-voices/raw/main/voices.json"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "piper_voices.json"

# Quality tiers ordered worst -> best. "low" and "medium" are both ~63 MB and
# differ only in sample rate (16 vs 22.05 kHz), so medium is always preferred.
QUALITY_ORDER = ["x_low", "low", "medium", "high"]


def slim(catalog):
    """Reduce the upstream catalog to the fields the app uses."""
    voices = []
    for key, entry in catalog.items():
        onnx_path = next(
            (p for p in entry["files"] if p.endswith(".onnx")), None)
        config_path = next(
            (p for p in entry["files"] if p.endswith(".onnx.json")), None)
        if not onnx_path or not config_path:
            print(f"  skipping {key}: missing model or config file", file=sys.stderr)
            continue

        language = entry["language"]
        voices.append({
            "key": key,
            "name": entry["name"],
            "lang_code": language["code"],
            "lang_family": language["family"],
            "lang_english": language["name_english"],
            "country": language.get("country_english", ""),
            "quality": entry["quality"],
            "onnx_path": onnx_path,
            "onnx_size": entry["files"][onnx_path]["size_bytes"],
            "onnx_md5": entry["files"][onnx_path]["md5_digest"],
            "config_path": config_path,
        })

    voices.sort(key=lambda v: (
        v["lang_english"],
        v["lang_code"],
        -QUALITY_ORDER.index(v["quality"]) if v["quality"] in QUALITY_ORDER else 0,
        v["name"],
    ))
    return voices


def main():
    print(f"Fetching {CATALOG_URL}")
    with urllib.request.urlopen(CATALOG_URL, timeout=60) as response:
        catalog = json.load(response)
    print(f"  {len(catalog)} voices upstream")

    voices = slim(catalog)
    families = {v["lang_family"] for v in voices}

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps({"voices": voices}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    size_kb = OUTPUT_PATH.stat().st_size / 1024
    print(f"Wrote {OUTPUT_PATH} — {len(voices)} voices, "
          f"{len(families)} languages, {size_kb:.0f} KB")


if __name__ == "__main__":
    main()
