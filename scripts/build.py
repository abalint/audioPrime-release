#!/usr/bin/env python3
"""Build audioPrime into a standalone application using Nuitka.

Usage:  python scripts/build.py

Produces:
  macOS  → dist/audioPrime.app
  Other  → dist/audioPrime.dist/
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VOICES_DIR = ROOT / "voices"
# Only this Piper voice ships in the installer; every other voice is downloaded
# on demand at runtime (see core/voice_manager.py). Keep in sync with
# config.BUNDLED_PIPER_VOICE.
BUNDLED_PIPER_VOICE = "en_US-amy-medium"
BIN_DIR = ROOT / "bin"
MODELS_DIR = ROOT / "models"
UPDATE_DIR = ROOT / "update"
DATA_DIR = ROOT / "data"
ASSETS_DIR = ROOT / "assets"
ICON_ICNS = ASSETS_DIR / "audioPrime.icns"
ICON_ICO = ASSETS_DIR / "audioPrime.ico"

APP_NAME = "audioPrime"


# ── Preflight checks ────────────────────────────────────────────────────────

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
        "Nuitka is installed",
    )

    # C compiler available
    _check(
        shutil.which("cc") is not None or shutil.which("gcc") is not None,
        "C compiler available",
    )

    # The single bundled voice must be present; the rest download at runtime.
    bundled_voice = VOICES_DIR / f"{BUNDLED_PIPER_VOICE}.onnx"
    _check(bundled_voice.is_file(), f"Bundled voice present ({BUNDLED_PIPER_VOICE})")
    catalog = DATA_DIR / "piper_voices.json"
    _check(catalog.is_file(), "Piper voice catalog present (data/piper_voices.json)")

    # Bundled binaries present
    bin_subdirs = [d for d in BIN_DIR.iterdir() if d.is_dir()] if BIN_DIR.is_dir() else []
    _check(len(bin_subdirs) > 0, f"bin/ platform dirs found ({', '.join(d.name for d in bin_subdirs)})")

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
        ICON_ICNS.is_file() or ICON_ICO.is_file(),
        "App icon found (run scripts/generate_icon.py to create)",
    )

    print()


# ── Refresh binaries ─────────────────────────────────────────────────────────

def refresh_binaries() -> None:
    """Fetch the latest yt-dlp and ffmpeg before compiling."""
    print("Refreshing bundled binaries")
    print("-" * 50)
    fetch_script = ROOT / "scripts" / "fetch_binaries.py"
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


# ── Build ────────────────────────────────────────────────────────────────────

def build() -> Path:
    dist_dir = ROOT / "dist"
    entry_point = ROOT / "main.py"
    # Nuitka names output based on entry point filename (main.py → main.app / main.dist)
    nuitka_stem = entry_point.stem

    cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--standalone",
        f"--output-dir={dist_dir}",
        # Data directories
        f"--include-data-dir={MODELS_DIR}=models",
        f"--include-data-dir={UPDATE_DIR}=update",
        # Ship only the default voice + its config; the rest download on demand.
        f"--include-data-files={VOICES_DIR / (BUNDLED_PIPER_VOICE + '.onnx')}=voices/{BUNDLED_PIPER_VOICE}.onnx",
        f"--include-data-files={VOICES_DIR / (BUNDLED_PIPER_VOICE + '.onnx.json')}=voices/{BUNDLED_PIPER_VOICE}.onnx.json",
        # Only the frequency list and the voice catalog are read at runtime.
        # Bundling all of data/ would sweep in the multi-GB irasutoya scrape and
        # blow past codesign's command-line limit.
        f"--include-data-files={DATA_DIR / 'ja_frequency.txt'}=data/ja_frequency.txt",
        f"--include-data-files={DATA_DIR / 'piper_voices.json'}=data/piper_voices.json",
        # Plugins
        "--enable-plugin=pyside6",
        # Exclude unused stdlib
        "--nofollow-import-to=tkinter",
        "--nofollow-import-to=unittest",
        "--nofollow-import-to=test",
        # Exclude torch/torchvision — pulled in transitively by piper-tts but
        # not used at runtime (piper uses onnxruntime for inference, not torch)
        "--nofollow-import-to=torch",
        "--nofollow-import-to=torchvision",
        "--nofollow-import-to=torchaudio",
        # Include piper package data (espeak-ng phoneme data for TTS)
        "--include-package-data=piper",
        # Include sherpa-onnx data (ReazonSpeech offline transcription)
        "--include-package-data=sherpa_onnx",
        # openai>=3 and anthropic>=1 import their resources submodules lazily
        # (importlib under TYPE_CHECKING), which Nuitka cannot trace, so the
        # bundle ends up without e.g. openai.resources.chat.chat. Include whole.
        "--include-package=openai",
        "--include-package=anthropic",
        # unidic_lite uses __file__ to locate its dicdir/ — must be source, not compiled
        "--nofollow-import-to=unidic_lite",
        # librosa crashes Nuitka compiler (KeyError in librosa.core.fft) —
        # exclude from compilation; source files are copied post-build
        "--nofollow-import-to=librosa",
        "--no-deployment-flag=excluded-module-usage",
    ]

    # Include bin/ platform directories that exist
    if BIN_DIR.is_dir():
        for sub in sorted(BIN_DIR.iterdir()):
            if sub.is_dir():
                cmd.append(f"--include-data-dir={sub}=bin/{sub.name}")

    # Include assets (icons)
    if ASSETS_DIR.is_dir():
        cmd.append(f"--include-data-dir={ASSETS_DIR}=assets")

    # macOS-specific
    if sys.platform == "darwin":
        cmd.extend([
            "--macos-create-app-bundle",
            f"--macos-app-name={APP_NAME}",
        ])
        if ICON_ICNS.is_file():
            cmd.append(f"--macos-app-icon={ICON_ICNS}")

    # Windows-specific
    if sys.platform == "win32" and ICON_ICO.is_file():
        cmd.append(f"--windows-icon-from-ico={ICON_ICO}")

    cmd.append(str(entry_point))

    print("Running Nuitka")
    print("-" * 50)
    print(" ".join(cmd))
    print()

    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("\nBuild FAILED.", file=sys.stderr)
        sys.exit(1)

    # Nuitka outputs based on entry point name, rename to APP_NAME
    if sys.platform == "darwin":
        nuitka_out = dist_dir / f"{nuitka_stem}.app"
        final_out = dist_dir / f"{APP_NAME}.app"
    else:
        nuitka_out = dist_dir / f"{nuitka_stem}.dist"
        final_out = dist_dir / f"{APP_NAME}.dist"

    if nuitka_out.exists() and nuitka_out != final_out:
        if final_out.exists():
            shutil.rmtree(final_out)
        nuitka_out.rename(final_out)
        print(f"Renamed {nuitka_out.name} → {final_out.name}")

    # Copy librosa (and pure-Python deps not compiled by Nuitka) into the bundle.
    # librosa crashes the Nuitka compiler so we ship its source .py files instead.
    _copy_excluded_packages(final_out)

    # Copying files in after Nuitka's ad-hoc signing breaks the bundle seal
    # ("a sealed resource is missing or invalid"), and Gatekeeper then reports
    # a downloaded copy as damaged. Re-seal ad-hoc so the zip is launchable
    # via right-click > Open.
    if sys.platform == "darwin":
        _reseal_adhoc(final_out)

    # Clean up Nuitka build cache
    build_cache = dist_dir / f"{nuitka_stem}.build"
    if build_cache.exists():
        shutil.rmtree(build_cache)
        print(f"Cleaned up {build_cache.name}")

    return final_out


# Packages that crash Nuitka and must be copied as source into the bundle
_EXCLUDED_PACKAGES = [
    "librosa",
    "lazy_loader",
    "audioread",
    "standard_aifc",
    "standard_sunau",
    "unidic_lite",
]


def _reseal_adhoc(app_out: Path) -> None:
    """Re-sign the bundle ad-hoc (identity "-") after post-build file copies."""
    print("\nRe-sealing bundle (ad-hoc codesign)")
    print("-" * 50)
    subprocess.run(
        ["codesign", "--force", "--deep", "--sign", "-", str(app_out)],
        check=True,
    )
    subprocess.run(
        ["codesign", "--verify", "--deep", "--strict", str(app_out)],
        check=True,
    )
    print("  OK  bundle seal verified")


def _copy_excluded_packages(app_out: Path) -> None:
    """Copy excluded packages from site-packages into the built app bundle."""
    import importlib.util

    # Determine the target directory inside the bundle
    if sys.platform == "darwin":
        target = app_out / "Contents" / "MacOS"
    else:
        target = app_out

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

        dest = target / pkg_name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        print(f"  OK  {pkg_name} ({sum(1 for _ in dest.rglob('*.py'))} .py files)")


# ── Report ───────────────────────────────────────────────────────────────────

def report(out: Path) -> None:
    print()
    print("Build complete")
    print("-" * 50)
    print(f"Output: {out}")
    if out.exists():
        # Compute total size
        if out.is_dir():
            total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
        else:
            total = out.stat().st_size
        mb = total / (1024 * 1024)
        print(f"Size:   {mb:.1f} MB")
    else:
        print("WARNING: output path does not exist — check Nuitka output above")


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    preflight()
    refresh_binaries()
    out = build()
    report(out)
