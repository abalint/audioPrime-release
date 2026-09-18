#!/usr/bin/env python3
"""Download Windows static builds of ffmpeg, yt-dlp, and qjs into bin/windows_x86_64/.

This is the Windows-specific counterpart to fetch_binaries.py (which handles
macOS and Linux). Run this on Windows (or point at it from CI) before building.

Run by developers — not by end users.

Usage:
    python scripts/fetch_binaries_win.py              # fetch all tools
    python scripts/fetch_binaries_win.py --tool ffmpeg
    python scripts/fetch_binaries_win.py --tool yt-dlp
    python scripts/fetch_binaries_win.py --tool qjs
"""

import argparse
import hashlib
import io
import json
import sys
import zipfile
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Version pins
# ---------------------------------------------------------------------------
# yt-dlp: always fetched at latest (sites change frequently, pinning breaks quickly)
QJS_VERSION = "v0.12.1"

PLATFORM_TAG = "windows_x86_64"

# ---------------------------------------------------------------------------
# Download URLs and known SHA-256 hashes
# ---------------------------------------------------------------------------

# BtbN FFmpeg GPL static build for Windows x64 (always latest; includes ffmpeg.exe + ffprobe.exe)
FFMPEG_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest"
    "/ffmpeg-master-latest-win64-gpl.zip"
)

# QuickJS-NG Windows binary
QJS_URL = (
    f"https://github.com/quickjs-ng/quickjs/releases/download/{QJS_VERSION}/qjs-windows-x86_64.exe"
)

# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------


def _download(url: str) -> bytes:
    print(f"  Downloading {url} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "audioPrime-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def _verify_sha256(data: bytes, expected: str, label: str) -> None:
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        print(f"  ERROR: SHA-256 mismatch for {label}", file=sys.stderr)
        print(f"    Expected: {expected}", file=sys.stderr)
        print(f"    Got:      {actual}", file=sys.stderr)
        sys.exit(1)
    print(f"  SHA-256 verified ({actual[:16]}...)")


# ---------------------------------------------------------------------------
# Tool fetchers
# ---------------------------------------------------------------------------


def fetch_ffmpeg(dest: Path) -> None:
    """Extract ffmpeg.exe and ffprobe.exe from the BtbN zip archive."""
    print("[ffmpeg + ffprobe]")
    data = _download(FFMPEG_URL)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        found = {"ffmpeg.exe": False, "ffprobe.exe": False}
        for entry in zf.namelist():
            # BtbN zip layout: ffmpeg-master-latest-win64-gpl/bin/ffmpeg.exe
            base = entry.split("/")[-1].lower()
            if base in found and not found[base]:
                out = dest / base
                out.write_bytes(zf.read(entry))
                print(f"  -> {out}")
                found[base] = True
            if all(found.values()):
                break

    missing = [name for name, ok in found.items() if not ok]
    if missing:
        raise RuntimeError(f"Missing from ffmpeg archive: {', '.join(missing)}")


def _latest_ytdlp_version() -> str:
    """Return the latest yt-dlp release tag from the GitHub API."""
    api_url = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
    req = urllib.request.Request(api_url, headers={"User-Agent": "audioPrime-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["tag_name"]


def fetch_ytdlp(dest: Path) -> None:
    print("[yt-dlp]")
    version = _latest_ytdlp_version()
    print(f"  Latest release : {version}")
    url = f"https://github.com/yt-dlp/yt-dlp/releases/download/{version}/yt-dlp.exe"
    data = _download(url)
    out = dest / "yt-dlp.exe"
    out.write_bytes(data)
    print(f"  -> {out}")


def fetch_qjs(dest: Path) -> None:
    print("[qjs]")
    data = _download(QJS_URL)
    out = dest / "qjs.exe"
    out.write_bytes(data)
    print(f"  -> {out}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

ALL_TOOLS = {"ffmpeg", "qjs", "yt-dlp"}
FETCHERS = {"ffmpeg": fetch_ffmpeg, "qjs": fetch_qjs, "yt-dlp": fetch_ytdlp}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch Windows binaries for audioPrime (windows_x86_64 only)"
    )
    parser.add_argument(
        "--tool",
        choices=sorted(ALL_TOOLS),
        action="append",
        dest="tools",
        help="Fetch only a specific tool. Can be repeated.",
    )
    args = parser.parse_args()

    tools = set(args.tools) if args.tools else ALL_TOOLS

    project_root = Path(__file__).resolve().parent.parent
    dest = project_root / "bin" / PLATFORM_TAG
    dest.mkdir(parents=True, exist_ok=True)

    print(f"Platform : {PLATFORM_TAG}")
    print(f"Dest     : {dest}")
    print(f"Tools    : {', '.join(sorted(tools))}")
    print()

    for tool in sorted(tools):
        try:
            FETCHERS[tool](dest)
        except Exception as exc:
            print(f"  ERROR fetching {tool}: {exc}", file=sys.stderr)
            sys.exit(1)
        print()

    print("Done.")


if __name__ == "__main__":
    main()
