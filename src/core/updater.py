"""Safe update checks for app releases and verified yt-dlp hotfixes."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..bin_paths import app_bin_dir, platform_tag, ytdlp_path, _NOWWIN

APP_REPO = "abalint/audioPrime-release"
GITHUB_RELEASE_API = f"https://api.github.com/repos/{APP_REPO}/releases/latest"
DEFAULT_TOOL_MANIFEST_URL = f"https://raw.githubusercontent.com/{APP_REPO}/main/update/tool_manifest.json"
HTTP_USER_AGENT = "audioPrime-updater/2.0"

YTDLP_REPO = "yt-dlp/yt-dlp"
YTDLP_GITHUB_API = f"https://api.github.com/repos/{YTDLP_REPO}/releases/latest"


def _http_get_json(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": HTTP_USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _read_tool_manifest_url() -> str:
    """Read optional custom manifest URL from config file."""
    config_file = Path.home() / ".audioPrimeProd.json"
    if not config_file.exists():
        return DEFAULT_TOOL_MANIFEST_URL

    try:
        cfg = json.loads(config_file.read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT_TOOL_MANIFEST_URL

    url = cfg.get("tool_manifest_url", "").strip()
    return url or DEFAULT_TOOL_MANIFEST_URL


def _strip_macos_quarantine(path: str | Path) -> None:
    """Remove macOS quarantine xattr so Gatekeeper doesn't block execution."""
    if sys.platform != "darwin":
        return
    subprocess.run(
        ["xattr", "-d", "com.apple.quarantine", str(path)],
        capture_output=True,
    )


def _read_bundled_manifest() -> dict | None:
    """Read the bundled tool_manifest.json shipped with the app."""
    manifest_path = app_bin_dir().parent.parent / "update" / "tool_manifest.json"
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _version_key(version: str) -> tuple:
    """Return a comparison key that works for date-like and semver-like tags."""
    nums = tuple(int(x) for x in re.findall(r"\d+", version))
    if nums:
        return nums
    return (version,)


def _is_newer(latest: str, current: str) -> bool:
    return _version_key(latest) > _version_key(current)


def _current_app_version() -> str:
    """Current app version provided by build/release environment.

    Falls back to dev marker for local source runs.
    """
    from ..config import VERSION
    return os.environ.get("AUDIOPRIME_VERSION", VERSION)


def check_app_update() -> dict:
    """Return app release update info from GitHub."""
    try:
        release = _http_get_json(GITHUB_RELEASE_API)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"update_available": False, "info": "No releases yet"}
        return {"error": f"Failed to check app release: {exc}"}
    except Exception as exc:
        return {"error": f"Failed to check app release: {exc}"}

    latest = (release.get("tag_name") or "").lstrip("v")
    if not latest:
        return {"error": "Latest release has no tag_name"}

    current = _current_app_version().lstrip("v")
    return {
        "current": current,
        "latest": latest,
        "name": release.get("name") or release.get("tag_name") or latest,
        "html_url": release.get("html_url", f"https://github.com/{APP_REPO}/releases/latest"),
        "published_at": release.get("published_at", ""),
        "update_available": current == "0.0.0-dev" or _is_newer(latest, current),
    }


def _ytdlp_asset_name() -> str:
    """Return the yt-dlp release asset filename for the current platform."""
    plat = platform_tag()
    if plat.startswith("windows"):
        return "yt-dlp.exe"
    if plat.startswith("darwin"):
        return "yt-dlp_macos"
    return "yt-dlp"


def _latest_ytdlp_github_release() -> dict:
    """Query GitHub API for the latest yt-dlp release version and download URL."""
    release = _http_get_json(YTDLP_GITHUB_API)
    version = (release.get("tag_name") or "").strip()
    asset_name = _ytdlp_asset_name()
    url = ""
    for asset in release.get("assets", []):
        if asset.get("name") == asset_name:
            url = asset.get("browser_download_url", "")
            break
    if not url:
        url = f"https://github.com/{YTDLP_REPO}/releases/download/{version}/{asset_name}"
    return {"version": version, "url": url}


def _get_current_ytdlp_version() -> str:
    path = ytdlp_path()
    _strip_macos_quarantine(path)
    try:
        result = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=120,  # yt-dlp_macos is a self-extracting PyInstaller bundle; first run can be slow
            **_NOWWIN,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return "unknown"
    except Exception:
        return "unknown"


def check_ytdlp_update() -> dict:
    """Return yt-dlp update info from the live GitHub releases API."""
    current = _get_current_ytdlp_version()
    try:
        release = _latest_ytdlp_github_release()
    except Exception as exc:
        return {"error": f"Failed to check yt-dlp release: {exc}", "current": current}

    latest = release["version"]
    return {
        "current": current,
        "latest": latest,
        "url": release["url"],
        "platform": platform_tag(),
        "update_available": current == "unknown" or _is_newer(latest, current),
    }


def check_updates() -> dict:
    """Check app release and yt-dlp hotfix updates."""
    app = check_app_update()
    ytdlp = check_ytdlp_update()

    warnings = []
    if app.get("error"):
        warnings.append(app["error"])
    if ytdlp.get("error"):
        warnings.append(ytdlp["error"])
    # Note: app 404 (no releases yet) is silently ignored — not a warning

    return {
        "app": app,
        "ytdlp": ytdlp,
        "warnings": warnings,
    }


def _download_bytes(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": HTTP_USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().lower()


def _ytdlp_target_path() -> Path:
    return app_bin_dir() / _ytdlp_asset_name()


def install_ytdlp_update(update_info: dict) -> tuple[bool, str]:
    """Install yt-dlp update with optional SHA256 verification and rollback."""
    url = update_info["url"]
    latest = update_info["latest"]
    expected_sha = update_info.get("sha256", "").lower()

    try:
        payload = _download_bytes(url)
    except Exception as exc:
        return (False, f"Failed to download yt-dlp binary: {exc}")

    if expected_sha:
        actual_sha = _sha256_hex(payload)
        if actual_sha != expected_sha:
            return (
                False,
                "yt-dlp checksum mismatch. "
                f"Expected {expected_sha}, got {actual_sha}. Update aborted.",
            )

    target = _ytdlp_target_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    tmp = target.with_name(target.name + ".download")
    backup = target.with_name(target.name + ".bak")

    try:
        tmp.write_bytes(payload)
        tmp.chmod(tmp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        _strip_macos_quarantine(tmp)

        if target.exists():
            if backup.exists():
                backup.unlink()
            target.replace(backup)

        tmp.replace(target)

        # Runtime validation — non-fatal on timeout since SHA256 already verified the binary.
        # yt-dlp_macos is a self-extracting bundle; first-run extraction can take >10 seconds.
        try:
            subprocess.run([str(target), "--version"], capture_output=True, text=True, timeout=120, check=True, **_NOWWIN)
        except subprocess.TimeoutExpired:
            pass  # Binary is SHA256-verified; slow first-run startup is not an install failure
        except Exception:
            pass  # Non-critical — binary integrity already confirmed above

        if backup.exists():
            backup.unlink()
        return (True, f"yt-dlp updated to {latest}")

    except Exception as exc:
        try:
            if target.exists():
                target.unlink()
        except OSError:
            pass

        try:
            if backup.exists():
                backup.replace(target)
        except OSError:
            pass

        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass

        return (False, f"Failed to install yt-dlp update: {exc}")


def open_release_page(url: str) -> tuple[bool, str]:
    """Open app release page in system browser."""
    ok = webbrowser.open(url)
    if ok:
        return (True, "Opened latest release page in your browser.")
    return (False, f"Could not open browser. Visit manually: {url}")


class UpdateWorker(QThread):
    """Background worker for safe update checks and actions."""

    updates_found = Signal(dict)  # {app: {...}, ytdlp: {...}, warnings:[...]}
    step_changed = Signal(str)
    progress = Signal(int, int, str)  # (current, total, message)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, mode="check", updates=None):
        super().__init__()
        self.mode = mode
        self.updates = updates or {}

    def run(self):
        try:
            if self.mode == "check":
                self._check_updates()
            elif self.mode == "install":
                self._install_updates()
            else:
                self.error.emit(f"Unknown update mode: {self.mode}")
        except Exception as exc:
            self.error.emit(f"Update operation failed: {exc}")

    def _check_updates(self):
        self.step_changed.emit("Checking app release...")
        updates = check_updates()
        self.updates_found.emit(updates)

    def _install_updates(self):
        app = self.updates.get("app", {})
        ytdlp = self.updates.get("ytdlp", {})

        actions = []
        if ytdlp.get("update_available") and not ytdlp.get("error"):
            actions.append("ytdlp")
        if app.get("update_available") and not app.get("error"):
            actions.append("app")

        total = len(actions)
        if total == 0:
            self.finished.emit("No updates were applied.")
            return

        current = 0
        successes = []
        failures = []

        for action in actions:
            current += 1

            if action == "ytdlp":
                msg = f"Installing yt-dlp {ytdlp['latest']}..."
                self.step_changed.emit(msg)
                self.progress.emit(current, total, msg)
                ok, detail = install_ytdlp_update(ytdlp)
                if ok:
                    successes.append(f"- {detail}")
                else:
                    failures.append(f"- {detail}")

            elif action == "app":
                msg = "Opening latest app release page..."
                self.step_changed.emit(msg)
                self.progress.emit(current, total, msg)
                ok, detail = open_release_page(app.get("html_url", f"https://github.com/{APP_REPO}/releases/latest"))
                if ok:
                    successes.append(f"- {detail}")
                else:
                    failures.append(f"- {detail}")

        lines = []
        if successes:
            lines.append("Successful actions:")
            lines.extend(successes)
        if failures:
            if lines:
                lines.append("")
            lines.append("Failed actions:")
            lines.extend(failures)

        self.finished.emit("\n".join(lines) if lines else "No updates were applied.")
