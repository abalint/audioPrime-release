# Contributing to audioPrime

audioPrime is in maintenance mode. The original author is not actively adding
features, so contributions are the main way the project moves forward.

## What is welcome

- Bug fixes, especially anything that breaks downloading, transcription, or
  TTS as upstream services change.
- Keeping bundled tools current (`update/tool_manifest.json` for yt-dlp).
- New TTS, transcription, or translation providers that follow the existing
  engine interfaces in `src/core/tts.py` and `src/core/transcriber.py`.
- Documentation fixes.

## How to contribute

1. Fork the repo and create a branch from `main`.
2. Set up a virtual environment and install `requirements.txt`. See the
   Installation section of `README.md`.
3. Make focused changes. One fix or feature per pull request.
4. Run the app end to end on at least one video before opening the PR.
5. Describe what changed and why in the PR. Include the platform you tested on.

## Building release binaries

See `BUILD.md` for the macOS and Windows build process using Nuitka.

## Code layout

`CLAUDE.md` is a detailed map of the codebase: pipeline stages, UI structure,
engines, and configuration. Start there.

## Reporting issues

Open a GitHub issue with your OS, the app version, the URL or file that failed,
and the relevant log from the `logs/` directory. Redact API keys.
