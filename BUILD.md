# Building audioPrime

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

## Branch workflow

- Develop on **`dev`**.
- The Windows build slave builds **`origin/main`**, not `dev`.
- To release/build new work: merge `dev` → `main` and push before building.

`main` is maintained by merging `dev` into it (merge commits), not by
fast-forward. From a clean tree:

```sh
git checkout main
git reset --hard origin/main      # discard any local drift on main
git merge dev --no-edit           # creates a "Merge branch 'dev'" commit
git push origin main
git checkout dev
```

---

## Windows build slave

The Windows box is a **build slave**: `pull_and_build.bat` resets its working
tree to `origin/main` on every run, discarding local drift, so builds are
reproducible.

### Access — use the right user

- SSH into the build box as the **same Windows user whose Credential Manager
  holds the GitHub credentials**. Windows Credential Manager (`wincredman`) is
  per-user and DPAPI-scoped, so a credential stored under one account is
  invisible to any other. Building as a different service account fails at
  `git fetch` with:

  ```
  fatal: Unable to persist credentials with the 'wincredman' credential store.
  fatal: could not read Username for 'https://github.com': terminal prompts disabled
  ```

### One-command build

```sh
ssh <build-user>@<build-host> F:\audioPrime\pull_and_build.bat
```

`pull_and_build.bat` (in `F:\audioPrime`) does:

1. `git -c credential.interactive=false fetch --prune origin` (non-interactive)
2. `git reset --hard origin/main`
3. `.venv\Scripts\python.exe scripts\build_win.py`

Output lands in `F:\audioPrime\dist\audioPrime.dist`.

### Box environment (reference)

- Repo: `F:\audioPrime`
- Python: `F:\audioPrime\.venv\Scripts\python.exe` (**3.11.9**)
- Git: `C:\Program Files\Git\cmd\git.exe` (not on the default non-interactive
  `PATH`; `pull_and_build.bat` calls it by full path)
- Windows binaries already fetched into `bin\windows_x86_64\`

---

## macOS build

```sh
.venv/bin/python scripts/build.py      # → dist/audioPrime.app
```

Note: Nuitka 4.1.3 only *experimentally* supports Python 3.14 (it builds but
warns; 3.13 is the recommended pairing). The Windows box is on 3.11.9.

---

## Provisioning a fresh build box

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
| `Unable to persist credentials with 'wincredman'` / `could not read Username` | SSH'd in as a Windows user other than the one holding the GitHub credential. |
| Preflight `FAIL  Bundled voice present` | `voices/en_US-amy-medium.onnx` missing — download it. |
| Preflight `FAIL  ReazonSpeech model files found` | run `scripts/fetch_models.py`. |
| Preflight `FAIL  bin/... exists` | run `scripts/fetch_binaries.py` (or `_win`). |
| Nuitka prompts for a tool download and hangs | Windows: `build_win.py` passes `--assume-yes-for-downloads` for headless runs. |
