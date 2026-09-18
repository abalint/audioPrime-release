"""Resolve paths for bundled binaries (ffmpeg, yt-dlp).

Checks APP_DIR/bin/{platform_tag}/ first, then falls back to PATH.
"""

import os
import platform
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

# Suppress CMD windows when spawning subprocesses from a GUI app on Windows.
# Empty dict on macOS/Linux so callers can always do **_NOWWIN unconditionally.
_NOWWIN: dict = (
    {"creationflags": subprocess.CREATE_NO_WINDOW}
    if sys.platform == "win32"
    else {}
)


def _get_app_dir() -> Path:
    """Return app root, handling PyInstaller and Nuitka frozen builds."""
    if getattr(sys, "frozen", False) or "__compiled__" in globals():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _platform_tag() -> str:
    """Return e.g. 'darwin_arm64', 'linux_x86_64'."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    # Normalise common machine names
    if machine in ("x86_64", "amd64"):
        machine = "x86_64"
    elif machine in ("arm64", "aarch64"):
        machine = "arm64"
    return f"{system}_{machine}"


def _bin_dir() -> Path:
    return _get_app_dir() / "bin" / _platform_tag()


def platform_tag() -> str:
    """Public platform tag helper used by update tooling."""
    return _platform_tag()


def app_bin_dir() -> Path:
    """Public bin directory helper used by update tooling."""
    return _bin_dir()


def _resolve(name: str) -> str:
    """Return path to bundled binary if it exists, else fall back to PATH."""
    # Windows bundled binaries use .exe extension (e.g. ffmpeg.exe, yt-dlp.exe)
    bin_name = name + ".exe" if sys.platform == "win32" and not name.endswith(".exe") else name
    bundled = _bin_dir() / bin_name
    if bundled.is_file():
        return str(bundled)
    found = shutil.which(name)
    if found:
        return found
    return name  # bare name — will fail at subprocess.run with FileNotFoundError


@lru_cache(maxsize=1)
def ffmpeg_path() -> str:
    return _resolve("ffmpeg")


@lru_cache(maxsize=1)
def ffprobe_path() -> str:
    return _resolve("ffprobe")


@lru_cache(maxsize=1)
def ytdlp_path() -> str:
    # On macOS, the updater downloads yt-dlp_macos — prefer it over the generic yt-dlp binary
    if sys.platform == "darwin":
        path = _resolve("yt-dlp_macos")
        if path != "yt-dlp_macos":
            return path
    return _resolve("yt-dlp")


@lru_cache(maxsize=1)
def qjs_path() -> str:
    return _resolve("qjs")


def ytdlp_extra_args() -> list[str]:
    """Return yt-dlp args for JS runtime and ffmpeg location.

    Bundled builds (.app) have a minimal PATH that won't include
    ffmpeg or qjs.  Pass explicit paths so yt-dlp can find them.
    """
    args = ["--remote-components", "ejs:github"]

    qjs = qjs_path()
    if qjs != "qjs":
        args.extend(["--js-runtimes", f"quickjs:{qjs}"])

    ff = ffmpeg_path()
    if ff != "ffmpeg":
        # --ffmpeg-location accepts a directory or a path to ffmpeg
        args.extend(["--ffmpeg-location", ff])

    return args


def check_tool(name: str) -> bool:
    """Return True if the named tool is available (bundled or on PATH)."""
    lookup = {"ffmpeg": ffmpeg_path, "yt-dlp": ytdlp_path}
    fn = lookup.get(name)
    if fn is None:
        return shutil.which(name) is not None
    path = fn()
    if path == name:
        # bare name — not found anywhere
        return False
    return True
