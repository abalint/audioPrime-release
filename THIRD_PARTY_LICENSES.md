# Third-Party Licenses

audioPrime itself is MIT licensed (see `LICENSE`). It depends on and, in
release builds, bundles the following third-party components. Each keeps its
own license; verify current terms against the upstream project before
redistributing.

## Python packages

| Package | License | Notes |
|---------|---------|-------|
| PySide6 / Qt | LGPL v3 | GUI framework |
| openai | Apache 2.0 | OpenAI API client |
| anthropic | MIT | Anthropic API client |
| tiktoken | MIT | Token counting |
| piper-tts | MIT | Offline TTS engine |
| onnxruntime | MIT | Neural inference |
| yt-dlp (package) | Unlicense | Media download |
| genanki | MIT | Anki deck generation |
| requests | Apache 2.0 | HTTP client |
| fugashi | MIT | Japanese tokenizer (MeCab bindings) |
| unidic-lite | BSD / LGPL / GPL (triple) | MeCab dictionary |
| simplemma | MIT | Lemmatizer |
| pathvalidate | MIT | Filename sanitization |
| reazonspeech-k2-asr | Apache 2.0 | Offline Japanese ASR |

## Bundled binaries and models

| Component | License | Source |
|-----------|---------|--------|
| ffmpeg / ffprobe | GPL v3 (static builds) | Prebuilt binaries from ffmpeg.martin-riedl.de (macOS arm64, 1.0.0 ships ffmpeg 9.0.1), BtbN/FFmpeg-Builds (Windows, `ffmpeg-master-latest-win64-gpl`), johnvansickle.com (Linux, untested). Invoked as separate processes, never linked. Corresponding source: https://ffmpeg.org/download.html (git.ffmpeg.org/ffmpeg.git, matching release tag); each build host publishes its build scripts. |
| yt-dlp (binary) | Unlicense | github.com/yt-dlp/yt-dlp |
| quickjs-ng | MIT | github.com/quickjs-ng/quickjs |
| Piper voice `en_US-amy-medium` and on-demand voices | Per-voice, see each MODEL_CARD | huggingface.co/rhasspy/piper-voices |
| ReazonSpeech k2-v2 model | Apache 2.0 | huggingface.co/reazon-research/reazonspeech-k2-v2 |

## Data

| File | License | Source |
|------|---------|--------|
| `data/ja_frequency.txt` | CC BY | University of Leeds Internet Corpora, Japanese word frequency list |

## Build tooling (not distributed)

| Tool | License |
|------|---------|
| Nuitka | Apache 2.0 |
