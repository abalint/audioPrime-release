#!/usr/bin/env python3
"""Generate/update yt-dlp hotfix manifest entries with SHA-256 hashes.

Usage:
    python scripts/update_manifest.py --version 2025.03.31
    python scripts/update_manifest.py --version 2025.03.31 --platform darwin_arm64 --platform linux_x86_64
"""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

DEFAULT_MANIFEST = Path("update/tool_manifest.json")
USER_AGENT = "audioPrime-manifest-updater/1.0"

SUPPORTED_PLATFORMS = {
    "darwin_arm64": "yt-dlp_macos",
    "linux_x86_64": "yt-dlp_linux",
    "windows_x86_64": "yt-dlp.exe",
}


def _asset_url(version: str, asset_name: str) -> str:
    return f"https://github.com/yt-dlp/yt-dlp/releases/download/{version}/{asset_name}"


def _download_sha256(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=60) as resp:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest().lower()


def _load_manifest(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_manifest(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Update yt-dlp tool manifest with verified SHA-256 hashes.")
    parser.add_argument("--version", required=True, help="yt-dlp release tag, e.g. 2025.03.31")
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST),
        help="Path to tool_manifest.json (default: update/tool_manifest.json)",
    )
    parser.add_argument(
        "--platform",
        action="append",
        choices=sorted(SUPPORTED_PLATFORMS.keys()),
        help="Platform(s) to update (default: all supported platforms)",
    )
    parser.add_argument(
        "--disable",
        action="store_true",
        help="Write entries with enabled=false (default: enabled=true)",
    )
    args = parser.parse_args()

    version = args.version.lstrip("v")
    manifest_path = Path(args.manifest)
    platforms = args.platform or sorted(SUPPORTED_PLATFORMS.keys())
    enabled = not args.disable

    data = _load_manifest(manifest_path)
    if "yt-dlp" not in data or not isinstance(data["yt-dlp"], dict):
        data["yt-dlp"] = {}

    print(f"Version: {version}")
    print(f"Manifest: {manifest_path}")
    print(f"Platforms: {', '.join(platforms)}")
    print()

    for plat in platforms:
        asset = SUPPORTED_PLATFORMS[plat]
        url = _asset_url(version, asset)
        print(f"[{plat}]")
        print(f"  URL: {url}")
        sha256 = _download_sha256(url)
        print(f"  SHA256: {sha256}")
        data["yt-dlp"][plat] = {
            "enabled": enabled,
            "version": version,
            "url": url,
            "sha256": sha256,
        }
        print()

    _save_manifest(manifest_path, data)
    print(f"Updated manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
