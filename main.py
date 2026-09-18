#!/usr/bin/env python3
"""audioPrime — Desktop app for interleaving English TTS with Japanese audio."""

# ── Bootstrap: ensure we're running inside a venv with deps installed ──
# Only stdlib imports are allowed above main(); third-party imports live in main().

import hashlib
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_VENV = os.path.join(_HERE, ".venv")
_REQ = os.path.join(_HERE, "requirements.txt")
_STAMP = os.path.join(_VENV, ".requirements_stamp")
_TAG = "[audioPrime]"


def _in_venv() -> bool:
    return sys.prefix != sys.base_prefix


def _req_hash() -> str:
    with open(_REQ, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def _stamp_matches() -> bool:
    try:
        with open(_STAMP, "r") as f:
            return f.read().strip() == _req_hash()
    except FileNotFoundError:
        return False


def _write_stamp() -> None:
    with open(_STAMP, "w") as f:
        f.write(_req_hash())


def _venv_python() -> str:
    if sys.platform == "win32":
        return os.path.join(_VENV, "Scripts", "python.exe")
    return os.path.join(_VENV, "bin", "python")


def _parse_requirements() -> list[str]:
    """Return non-empty, non-comment lines from requirements.txt."""
    with open(_REQ, "r") as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]


def _bootstrap() -> None:
    """Create venv, install deps if needed, then re-exec into the venv Python."""

    if not os.path.isfile(_REQ):
        print(f"{_TAG} Error: requirements.txt not found at {_REQ}", file=sys.stderr)
        sys.exit(1)

    # ── Create venv ──
    if not os.path.isdir(_VENV):
        print(f"{_TAG} Creating virtual environment...")
        try:
            import venv

            venv.create(_VENV, with_pip=True)
        except Exception as exc:
            print(f"{_TAG} Failed to create virtual environment: {exc}", file=sys.stderr)
            if "debian" in (os.popen("cat /etc/os-release 2>/dev/null").read().lower()):
                print(
                    f"{_TAG} Hint: run  sudo apt install python3-venv  and try again.",
                    file=sys.stderr,
                )
            sys.exit(1)

    # ── Install / update deps (one at a time for continuous feedback) ──
    if not _stamp_matches():
        pkgs = _parse_requirements()
        total = len(pkgs)
        python = _venv_python()
        print(f"{_TAG} Installing {total} dependencies...")
        for i, pkg in enumerate(pkgs, 1):
            name = pkg.split(">=")[0].split("==")[0].split("<")[0].split(">")[0]
            print(f"{_TAG}   [{i}/{total}] {name}...", flush=True)
            result = subprocess.run(
                [python, "-m", "pip", "install", pkg],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            if result.returncode != 0:
                print(f"\n{_TAG} Failed to install {pkg}:", file=sys.stderr)
                print(result.stderr.decode(errors="replace"), file=sys.stderr)
                sys.exit(1)
        _write_stamp()
        print(f"{_TAG} Setup complete. Launching...")

    # ── Re-exec into venv Python ──
    python = _venv_python()
    argv = [python] + sys.argv
    if sys.platform == "win32":
        sys.exit(subprocess.run(argv).returncode)
    else:
        os.execv(python, argv)


def main():
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from src.ui.main_window import MainWindow
    from src.ui.styles import STYLESHEET

    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)

    # Set application icon
    icon_path = os.path.join(_HERE, "assets", "icon_1024.png")
    if os.path.isfile(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    app.aboutToQuit.connect(window._shutdown_worker)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    if not (getattr(sys, "frozen", False) or "__compiled__" in globals()) and not _in_venv():
        _bootstrap()
    main()
