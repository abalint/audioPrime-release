#!/usr/bin/env python3
"""Download static builds of ffmpeg and yt-dlp into bin/{platform_tag}/.

Piper TTS is handled via the piper-tts Python package (no binary needed).

Run by developers / CI — not by end users.

Usage:
    python scripts/fetch_binaries.py                 # fetch all for current platform
    python scripts/fetch_binaries.py --tool ffmpeg    # fetch only ffmpeg
    python scripts/fetch_binaries.py --platform darwin_arm64
"""

import argparse
import io
import json
import platform
import stat
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Version pins
# ---------------------------------------------------------------------------
# yt-dlp: always fetched at latest (sites change frequently, pinning breaks quickly)
QJS_VERSION = "v0.12.1"
# ffmpeg: evermeet.cx (macOS), johnvansickle.com (Linux)

# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _latest_ytdlp_version() -> str:
    """Return the latest yt-dlp release tag from the GitHub API."""
    url = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
    req = urllib.request.Request(url, headers={"User-Agent": "audioPrime-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["tag_name"]


def _ytdlp_url(plat: str, version: str) -> str:
    base = f"https://github.com/yt-dlp/yt-dlp/releases/download/{version}"
    if plat.startswith("darwin"):
        return f"{base}/yt-dlp_macos"
    elif "x86_64" in plat:
        return f"{base}/yt-dlp_linux"
    elif "arm64" in plat or "aarch64" in plat:
        return f"{base}/yt-dlp_linux_aarch64"
    raise RuntimeError(f"No yt-dlp binary for platform: {plat}")


def _qjs_url(plat: str) -> str:
    base = f"https://github.com/quickjs-ng/quickjs/releases/download/{QJS_VERSION}"
    if plat.startswith("darwin"):
        return f"{base}/qjs-darwin"
    elif "linux" in plat and "x86_64" in plat:
        return f"{base}/qjs-linux-x86_64"
    elif "linux" in plat and ("arm64" in plat or "aarch64" in plat):
        return f"{base}/qjs-linux-aarch64"
    raise RuntimeError(f"No qjs binary for platform: {plat}")


def _ffmpeg_urls(plat: str) -> list[tuple[str, str]]:
    """Return list of (url, archive_format) for ffmpeg and ffprobe."""
    if plat.startswith("darwin"):
        return [
            ("https://evermeet.cx/ffmpeg/getrelease/zip", "zip"),        # ffmpeg
            ("https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip", "zip"),  # ffprobe
        ]
    elif "x86_64" in plat:
        # Linux static builds include both ffmpeg and ffprobe in one archive
        return [(
            "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
            "tar",
        )]
    elif "arm64" in plat or "aarch64" in plat:
        return [(
            "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz",
            "tar",
        )]
    raise RuntimeError(f"No ffmpeg binary for platform: {plat}")


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def _download(url: str) -> bytes:
    print(f"  Downloading {url} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "audioPrime-fetch/1.0"})
    with urllib.request.urlopen(req) as resp:
        return resp.read()


def _make_executable(path: Path):
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


# ---------------------------------------------------------------------------
# Tool fetchers
# ---------------------------------------------------------------------------

FFMPEG_TOOLS = ("ffmpeg", "ffprobe")


def _extract_tool(name: str, data: bytes, fmt: str, dest: Path) -> bool:
    """Write `name` out of an archive if present. Returns True if extracted."""
    if fmt == "zip":
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for entry in zf.namelist():
                if entry == name or entry.endswith(f"/{name}"):
                    out = dest / name
                    out.write_bytes(zf.read(entry))
                    _make_executable(out)
                    print(f"  -> {out}")
                    return True
    else:
        with tarfile.open(fileobj=io.BytesIO(data)) as tf:
            for member in tf.getmembers():
                if member.name == name or member.name.endswith(f"/{name}"):
                    f = tf.extractfile(member)
                    if f is None:
                        continue
                    out = dest / name
                    out.write_bytes(f.read())
                    _make_executable(out)
                    print(f"  -> {out}")
                    return True
    return False


def fetch_ffmpeg(dest: Path, plat: str):
    print("[ffmpeg]")
    found = set()
    for url, fmt in _ffmpeg_urls(plat):
        data = _download(url)
        for name in FFMPEG_TOOLS:
            if name not in found and _extract_tool(name, data, fmt, dest):
                found.add(name)

    missing = [name for name in FFMPEG_TOOLS if name not in found]
    if missing:
        raise RuntimeError(f"not found in archive(s): {', '.join(missing)}")


def fetch_ytdlp(dest: Path, plat: str):
    print("[yt-dlp]")
    version = _latest_ytdlp_version()
    print(f"  Latest release : {version}")
    url = _ytdlp_url(plat, version)
    data = _download(url)
    out = dest / "yt-dlp"
    out.write_bytes(data)
    _make_executable(out)
    print(f"  -> {out}")


def fetch_qjs(dest: Path, plat: str):
    print("[qjs]")
    url = _qjs_url(plat)
    data = _download(url)
    out = dest / "qjs"
    out.write_bytes(data)
    _make_executable(out)
    print(f"  -> {out}")


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

def current_platform_tag() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        machine = "x86_64"
    elif machine in ("arm64", "aarch64"):
        machine = "arm64"
    return f"{system}_{machine}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

ALL_TOOLS = {"ffmpeg", "qjs", "yt-dlp"}
FETCHERS = {"ffmpeg": fetch_ffmpeg, "qjs": fetch_qjs, "yt-dlp": fetch_ytdlp}


def main():
    parser = argparse.ArgumentParser(description="Fetch bundled binaries for audioPrime")
    parser.add_argument(
        "--platform",
        default=current_platform_tag(),
        help="Target platform tag (default: auto-detect)",
    )
    parser.add_argument(
        "--tool",
        choices=sorted(ALL_TOOLS),
        action="append",
        dest="tools",
        help="Fetch only specific tool(s). Can be repeated.",
    )
    args = parser.parse_args()

    plat = args.platform
    tools = set(args.tools) if args.tools else ALL_TOOLS

    project_root = Path(__file__).resolve().parent.parent
    dest = project_root / "bin" / plat
    dest.mkdir(parents=True, exist_ok=True)

    print(f"Platform: {plat}")
    print(f"Destination: {dest}")
    print()

    for tool in sorted(tools):
        FETCHERS[tool](dest, plat)
        print()

    print("Done.")


if __name__ == "__main__":
    main()
