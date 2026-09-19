# Building audioPrime

> Step-by-step from-scratch instructions for both platforms, and a table of
> the macOS/Windows differences, are in the README under **Building a
> Standalone App**. This file covers per-platform build notes, provisioning a
> fresh build machine, and what gets bundled.

audioPrime ships as a standalone Nuitka build per platform:

| Platform | Command | Output |
|----------|---------|--------|
| macOS    | `.venv/bin/python scripts/build.py`     | `dist/audioPrime.app`   |
| Windows  | `python scripts\build_win.py`           | `dist/audioPrime.dist/` |

There is **one build script per platform** (`build.py` for macOS/Linux,
`build_win.py` for Windows). They must be kept in sync — when you change what
gets bundled in one, mirror it in the other. The shared constant is
`BUNDLED_PIPER_VOICE` (see [Bundled data](#bundled-data)).

---

## Windows build

```bat
.venv\Scripts\python.exe scripts\build_win.py    REM -> dist\audioPrime.dist\
```

Nuitka compiles with MSVC, so `cl.exe` must be on `PATH`. Run the build from a
*Developer Command Prompt for VS 2022*, or source `vcvars64.bat` first:

```bat
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
```

`build_win.py` passes `--assume-yes-for-downloads` so Nuitka never blocks on a
prompt in a non-interactive shell. Last verified with Python **3.11.9**.

---

## macOS build

```sh
.venv/bin/python scripts/build.py      # → dist/audioPrime.app
```

Note: Nuitka 4.1.3 only *experimentally* supports Python 3.14 (it builds but
warns; 3.13 is the recommended pairing).

---

## Provisioning a fresh build machine

Large binaries and models are **gitignored** and fetched, not committed. On a
new checkout, run these before the first build (all are one-time unless the
upstream changes):

| Step | Command | Produces |
|------|---------|----------|
| Binaries | `python scripts/fetch_binaries.py` (macOS/Linux) or `scripts/fetch_binaries_win.py` (Windows) | `bin/<platform>/` — ffmpeg, ffprobe, yt-dlp, qjs |
| ReazonSpeech models | `python scripts/fetch_models.py` (needs `pip install huggingface_hub`) | `models/reazonspeech-k2-v2/` (ONNX + tokens.txt) |
| Default voice | download `en_US-amy-medium.onnx` + `.onnx.json` into `voices/` | the one bundled Piper voice |

`build.py`/`build_win.py` also refresh binaries automatically at build time, but
the models and the default voice must already be present — the preflight check
aborts the build if they are missing.

**Committed to the repo** (no fetch needed): `assets/` icons,
`update/tool_manifest.json`, `data/piper_voices.json`, `data/ja_frequency.txt`.

---

## Bundled data

Since the multilingual-TTS change, only **one** Piper voice ships in the
installer; every other voice downloads on demand at runtime.

- **Bundled:** `voices/en_US-amy-medium.onnx` (+ `.json`) — the constant
  `BUNDLED_PIPER_VOICE` in both build scripts and `src/config.py`.
- **Catalog:** `data/piper_voices.json` (166 voices, 45 languages) ships and is
  read by `src/core/voice_manager.py`. Regenerate it from upstream with:

  ```sh
  python scripts/fetch_piper_catalog.py
  ```

- **On demand:** any other selected voice is downloaded from Hugging Face into
  `voices-downloaded/` (next to the app's output dir) on first use.

Also bundled: `models/` (ReazonSpeech), `update/`, `bin/<platform>/`, `assets/`,
and `data/{piper_voices.json,ja_frequency.txt}`. The full `data/` directory is
**not** bundled wholesale (it can contain a multi-GB scrape) — only the two
files above are included explicitly.

---

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| Preflight `FAIL  Bundled voice present` | `voices/en_US-amy-medium.onnx` missing — download it. |
| Preflight `FAIL  ReazonSpeech model files found` | run `scripts/fetch_models.py`. |
| Preflight `FAIL  bin/... exists` | run `scripts/fetch_binaries.py` (or `_win`). |
| Nuitka prompts for a tool download and hangs | Windows: `build_win.py` passes `--assume-yes-for-downloads` for non-interactive runs. |
