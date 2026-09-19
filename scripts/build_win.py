#!/usr/bin/env python3
"""Build audioPrime into a standalone Windows application using Nuitka.

Windows-only counterpart to build.py (which handles macOS / Linux).
Run this script from the project root after fetching binaries:

    python scripts/fetch_binaries_win.py   # one-time: download ffmpeg, yt-dlp, qjs
    python scripts/build_win.py            # compile and bundle

Produces:
    dist/audioPrime.dist/   — standalone folder ready to zip/distribute
        audioPrime.exe
        ...dependencies...
"""

import shutil
import subprocess
import sys
from pathlib import Path

if sys.platform != "win32":
    print("ERROR: build_win.py is for Windows only.", file=sys.stderr)
    print("       Use scripts/build.py on macOS / Linux.", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
VOICES_DIR = ROOT / "voices"
# Only this Piper voice ships in the installer; every other voice is downloaded
# on demand at runtime (see core/voice_manager.py). Keep in sync with
# config.BUNDLED_PIPER_VOICE and scripts/build.py.
BUNDLED_PIPER_VOICE = "en_US-amy-medium"
BIN_DIR = ROOT / "bin"
MODELS_DIR = ROOT / "models"
UPDATE_DIR = ROOT / "update"
DATA_DIR = ROOT / "data"
ASSETS_DIR = ROOT / "assets"
ICON_ICO = ASSETS_DIR / "audioPrime.ico"

APP_NAME = "audioPrime"
PLATFORM_TAG = "windows_x86_64"
WIN_BIN_DIR = BIN_DIR / PLATFORM_TAG

# Binaries that must be present before building
REQUIRED_BINS = ["ffmpeg.exe", "ffprobe.exe", "yt-dlp.exe"]


# ── Preflight checks ─────────────────────────────────────────────────────────


def _check(condition: bool, msg: str) -> None:
    if not condition:
        print(f"FAIL  {msg}", file=sys.stderr)
        sys.exit(1)
    print(f"  OK  {msg}")


def preflight() -> None:
    print("Preflight checks")
    print("-" * 50)

    # Nuitka installed
    _check(
        shutil.which("nuitka") is not None
        or subprocess.run(
            [sys.executable, "-m", "nuitka", "--version"],
            capture_output=True,
        ).returncode == 0,
        "Nuitka is installed (pip install nuitka)",
    )

    # C compiler: check PATH first, then ask Nuitka (it can find MSVC even when not on PATH)
    has_compiler = any(shutil.which(c) is not None for c in ("cl", "gcc", "clang", "cc"))
    if not has_compiler:
        result = subprocess.run(
            [sys.executable, "-m", "nuitka", "--version"],
            capture_output=True, text=True,
        )
        has_compiler = "Version C compiler:" in result.stdout
    _check(
        has_compiler,
        "C compiler available (cl.exe / gcc / clang — install MSVC Build Tools or MinGW-w64)",
    )

    # The single bundled voice must be present; the rest download at runtime.
    bundled_voice = VOICES_DIR / f"{BUNDLED_PIPER_VOICE}.onnx"
    _check(bundled_voice.is_file(), f"Bundled voice present ({BUNDLED_PIPER_VOICE})")
    catalog = DATA_DIR / "piper_voices.json"
    _check(catalog.is_file(), "Piper voice catalog present (data/piper_voices.json)")

    # Windows binaries present
    _check(WIN_BIN_DIR.is_dir(), f"bin/{PLATFORM_TAG}/ exists (run scripts/fetch_binaries_win.py)")
    if WIN_BIN_DIR.is_dir():
        missing = [b for b in REQUIRED_BINS if not (WIN_BIN_DIR / b).is_file()]
        _check(
            len(missing) == 0,
            f"Required binaries present: {', '.join(REQUIRED_BINS)}"
            + (f"  — missing: {', '.join(missing)}" if missing else ""),
        )

    # ReazonSpeech model files present
    rs_dir = MODELS_DIR / "reazonspeech-k2-v2"
    rs_onnx = list(rs_dir.glob("*.onnx")) if rs_dir.is_dir() else []
    _check(
        len(rs_onnx) >= 3 and (rs_dir / "tokens.txt").is_file(),
        f"ReazonSpeech model files found ({len(rs_onnx)} .onnx + tokens.txt) — run scripts/fetch_models.py",
    )

    # Update manifest
    _check(
        (UPDATE_DIR / "tool_manifest.json").is_file(),
        "update/tool_manifest.json exists",
    )

    # App icon
    _check(
        ICON_ICO.is_file(),
        "App icon found (run scripts/generate_icon.py to create audioPrime.ico)",
    )

    print()


# ── Refresh binaries ─────────────────────────────────────────────────────────


def refresh_binaries() -> None:
    """Fetch the latest yt-dlp and ffmpeg before compiling."""
    print("Refreshing bundled binaries")
    print("-" * 50)
    fetch_script = ROOT / "scripts" / "fetch_binaries_win.py"
    result = subprocess.run(
        [sys.executable, str(fetch_script)],
        check=False,
    )
    if result.returncode != 0:
        print(
            "WARNING: Binary refresh failed — proceeding with existing binaries.",
            file=sys.stderr,
        )
    print()


# ── Build ─────────────────────────────────────────────────────────────────────


def build() -> Path:
    dist_dir = ROOT / "dist"
    entry_point = ROOT / "main.py"
    nuitka_stem = entry_point.stem  # "main" → Nuitka outputs main.dist/

    cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--standalone",
        # Non-interactive builds: auto-approve tool downloads (e.g. Dependency
        # Walker) instead of prompting, which fatals in non-interactive runs
        "--assume-yes-for-downloads",
        f"--output-dir={dist_dir}",
        # Data directories bundled into the distribution
        f"--include-data-dir={MODELS_DIR}=models",
        f"--include-data-dir={UPDATE_DIR}=update",
        # Ship only the default voice + its config; the rest download on demand.
        f"--include-data-files={VOICES_DIR / (BUNDLED_PIPER_VOICE + '.onnx')}=voices/{BUNDLED_PIPER_VOICE}.onnx",
        f"--include-data-files={VOICES_DIR / (BUNDLED_PIPER_VOICE + '.onnx.json')}=voices/{BUNDLED_PIPER_VOICE}.onnx.json",
        # Only the frequency list and the voice catalog are read at runtime.
        f"--include-data-files={DATA_DIR / 'ja_frequency.txt'}=data/ja_frequency.txt",
        f"--include-data-files={DATA_DIR / 'piper_voices.json'}=data/piper_voices.json",
        # PySide6 plugin (Qt DLLs, platforms, etc.)
        "--enable-plugin=pyside6",
        # Trim unused stdlib
        "--nofollow-import-to=tkinter",
        "--nofollow-import-to=unittest",
        "--nofollow-import-to=test",
        # Exclude torch/torchvision — pulled in transitively by piper-tts but
        # not used at runtime (piper uses onnxruntime for inference, not torch)
        "--nofollow-import-to=torch",
        "--nofollow-import-to=torchvision",
        "--nofollow-import-to=torchaudio",
        # librosa crashes Nuitka compiler (KeyError in librosa.core.fft) —
        # exclude from compilation; source files are copied post-build
        "--nofollow-import-to=librosa",
        "--no-deployment-flag=excluded-module-usage",
        # Piper phoneme data (espeak-ng)
        "--include-package-data=piper",
        # sherpa-onnx data (ReazonSpeech offline transcription)
        "--include-package-data=sherpa_onnx",
        # openai>=3 and anthropic>=1 import their resources submodules lazily
        # (importlib under TYPE_CHECKING), which Nuitka cannot trace, so the
        # bundle ends up without e.g. openai.resources.chat.chat. Include whole.
        "--include-package=openai",
        "--include-package=anthropic",
        # unidic_lite uses __file__ to locate its dicdir/ — must be source, not compiled
        "--nofollow-import-to=unidic_lite",
        # Name the output executable
        f"--output-filename={APP_NAME}.exe",
        # Windows: hide the console window (GUI app)
        "--windows-console-mode=disable",
        # Embed the .ico into the .exe
        f"--windows-icon-from-ico={ICON_ICO}",
    ]

    # Bundle Windows binaries using --include-data-files (Nuitka 4.x filters .exe
    # from --include-data-dir, so we include each executable explicitly).
    if WIN_BIN_DIR.is_dir():
        for exe in WIN_BIN_DIR.iterdir():
            if exe.is_file():
                cmd.append(f"--include-data-files={exe}=bin/{PLATFORM_TAG}/{exe.name}")

    # Bundle assets (icons, etc.)
    if ASSETS_DIR.is_dir():
        cmd.append(f"--include-data-dir={ASSETS_DIR}=assets")

    cmd.append(str(entry_point))

    print("Running Nuitka")
    print("-" * 50)
    print(" ".join(str(c) for c in cmd))
    print()

    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("\nBuild FAILED.", file=sys.stderr)
        sys.exit(1)

    # Nuitka names the output folder after the entry point: main.dist → audioPrime.dist
    nuitka_out = dist_dir / f"{nuitka_stem}.dist"
    final_out = dist_dir / f"{APP_NAME}.dist"

    if nuitka_out.exists() and nuitka_out != final_out:
        if final_out.exists():
            _release_locked_app(final_out)
            shutil.rmtree(final_out)
        nuitka_out.rename(final_out)
        print(f"Renamed {nuitka_out.name} -> {final_out.name}")

    # Copy librosa (and pure-Python deps not compiled by Nuitka) into the bundle.
    # librosa crashes the Nuitka compiler so we ship its source .py files instead.
    _copy_excluded_packages(final_out)

    # Remove Nuitka's intermediate build cache
    build_cache = dist_dir / f"{nuitka_stem}.build"
    if build_cache.exists():
        shutil.rmtree(build_cache)
        print(f"Cleaned up {build_cache.name}")

    return final_out


def _release_locked_app(target_dir: Path) -> None:
    """Kill any audioPrime.exe still running out of target_dir.

    A leftover GUI from a previous build holds an open handle on the .exe, and
    Windows then fails the rmtree with WinError 5 ("Access is denied") — which
    looks like a filesystem permission problem but is really a file lock. On the
    exFAT build drive there are no ACLs to get wrong, so a lock is the only way
    this can fail.

    A non-admin build account can only kill processes it owns. If the stale GUI
    belongs to a different user (e.g. an interactive desktop session), say so
    explicitly rather than letting the caller hit a bare PermissionError.
    """
    query = (
        "Get-CimInstance Win32_Process -Filter \"Name='audioPrime.exe'\" | "
        f"Where-Object {{ $_.ExecutablePath -like '{target_dir}\\*' }} | "
        "ForEach-Object { "
        "$o = (Invoke-CimMethod -InputObject $_ -MethodName GetOwner).User; "
        "\"$($_.ProcessId) $o\" }"
    )
    try:
        found = subprocess.run(
            ["powershell", "-NoProfile", "-Command", query],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return  # best-effort: fall through to rmtree and report the real error

    for line in filter(None, (ln.strip() for ln in found.splitlines())):
        pid, _, owner = line.partition(" ")
        killed = subprocess.run(
            ["taskkill", "/PID", pid, "/F"], capture_output=True, text=True
        )
        if killed.returncode == 0:
            print(f"  Stopped running {APP_NAME}.exe (pid {pid}) to free the output dir")
            continue
        print(
            f"\nERROR: {APP_NAME}.exe (pid {pid}) is running from {target_dir}\n"
            f"       and is owned by '{owner}', so this build account cannot stop it.\n"
            f"       Close that instance and re-run the build.",
            file=sys.stderr,
        )
        sys.exit(1)


# Packages that crash Nuitka and must be copied as source into the bundle
_EXCLUDED_PACKAGES = [
    "librosa",
    "lazy_loader",
    "audioread",
    "standard_aifc",
    "standard_sunau",
    "unidic_lite",
]


def _copy_excluded_packages(app_out: Path) -> None:
    """Copy excluded packages from site-packages into the built app bundle."""
    import importlib.util

    print("\nCopying excluded packages into bundle")
    print("-" * 50)

    for pkg_name in _EXCLUDED_PACKAGES:
        spec = importlib.util.find_spec(pkg_name)
        if spec is None or spec.origin is None:
            print(f"  SKIP  {pkg_name} (not installed)")
            continue

        src = Path(spec.origin).parent
        if not src.is_dir():
            print(f"  SKIP  {pkg_name} (not a package directory)")
            continue

        dest = app_out / pkg_name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        print(f"  OK  {pkg_name} ({sum(1 for _ in dest.rglob('*.py'))} .py files)")


# ── Report ────────────────────────────────────────────────────────────────────


def report(out: Path) -> None:
    print()
    print("Build complete")
    print("-" * 50)
    print(f"Output: {out}")
    if out.exists():
        total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
        mb = total / (1024 * 1024)
        print(f"Size:   {mb:.1f} MB")
        print()
        print("To distribute: zip the dist/audioPrime.dist/ folder.")
        print(f"  Launcher: {out / 'audioPrime.exe'}")
    else:
        print("WARNING: output path does not exist — check Nuitka output above")


# ── Main ──────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    preflight()
    refresh_binaries()
    out = build()
    report(out)
