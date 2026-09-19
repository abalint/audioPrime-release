# audioPrime — Multilingual Audio Interleaver for Language Learning

A desktop application that automatically creates interleaved audio from videos and online content in any language. It extracts or transcribes subtitles, translates them to English, generates English TTS, and produces an interleaved audio file where each English translation is followed by the original language audio. Perfect for language learners who want immersive audio study material.

**Supported**: 33 languages, 1000+ websites (YouTube, stand.fm, Vimeo, etc.), customizable AI prompts, offline and cloud TTS

> **Project status: maintenance mode.** audioPrime 1.0.0 is a feature-complete
> release. The original author is no longer actively developing it. The code is
> MIT licensed so anyone can fork it, fix it, or extend it. Pull requests that
> fix bugs or keep bundled tools (yt-dlp, ffmpeg) working are welcome, but
> there is no roadmap and no guaranteed response time on issues.

## Current Status

**Version**: 1.0.0 (Feature Complete, maintenance mode)

All core features are implemented and functional:
- ✅ Single and batch video/audio processing
- ✅ Multi-language support (33 languages, any as source or target, with customizable AI prompts)
- ✅ Multi-site support (1000+ yt-dlp compatible sites)
- ✅ Subtitle extraction and audio transcription (ElevenLabs, Soniox, or offline ReazonSpeech)
- ✅ AI-powered translation and punctuation
- ✅ TTS in the learner's language via Piper (offline) or OpenAI, Azure, Google, ElevenLabs (cloud)
- ✅ Audio interleaving and mixing
- ✅ Anki deck generation (subs2srs format)
- ✅ Browser cookie authentication
- ✅ Customizable prompts per language
- ✅ Settings persistence and update checker
- ✅ Cache management and logging
- ✅ Binary bundling support
- ✅ Dark-mode UI with PySide6


## Features

### Core Functionality
- **Multi-Language Support**: Process content in 32 languages (Arabic, Bengali, Chinese, French, German, Hebrew, Hindi, Japanese, Korean, Russian, Spanish, Thai, Vietnamese, and more)
- **Multi-Site Support**: Works with 1000+ websites supported by yt-dlp (YouTube, stand.fm, Vimeo, Twitch, Dailymotion, and many more)
- **Batch Processing**: Process multiple videos/playlists/channels in a single session
- **Subtitle & Transcription**: Automatic subtitle extraction, optional transcription fallback (ElevenLabs), or force transcription mode (skip subtitles entirely)

### AI & Translation
- **Selectable AI Models**: Choose from gpt-5.2, gpt-5.1, gpt-5, gpt-5-mini, gpt-5-nano, gpt-4o-mini, gpt-4o, gpt-4.5-preview, gpt-4-turbo, or o3-mini for translation and punctuation tasks
- **Customizable Prompts**: Edit translation and punctuation prompts per language with {LANGUAGE} placeholders
- **Automatic Translation**: Translates subtitles to English using OpenAI API with your selected model
- **Punctuation Insertion**: Uses AI to add sentence-ending punctuation to transcribed or unpunctuated text
- **Language-Aware Rules**: Special handling for CJK punctuation (Japanese, Chinese, Korean, Cantonese)
- **Non-Speech Filtering**: Automatically removes subtitle blocks containing only non-speech annotations ([Music], [Applause], etc.)

### Audio Processing
- **Offline TTS**: Generates natural English text-to-speech using Piper (ONNX models, completely offline)
- **Piper Voices**: 166 offline voices across 45 languages, downloaded on demand (one voice, Amy, ships in the app)
- **Speed Control**: Adjustable playback speed (25% - 300%)
- **Audio Interleaving**: Creates alternating pattern: [English TTS] → [Original Audio] → [English TTS] → [Original Audio]
- **Smart Merging**: Collapses short subtitle segments to enforce minimum 2-second audio duration
- **Audio Condensing**: Optional feature to trim long silences (≥2s between subtitles) while preserving all speech content
- **Segment Grouping**: Advanced option to group multiple English TTS segments before Japanese audio for customized interleaving patterns

### Study Tools
- **Anki Deck Generation**: Creates subs2srs-style flashcard decks with source language audio
- **Deterministic IDs**: Update existing decks across multiple runs with consistent card IDs

### Authentication & Security
- **Browser Cookie Support**: Authenticate with YouTube using cookies from Safari, Chrome, Firefox, Brave, or Edge
- **API Key Management**: Secure storage of OpenAI and ElevenLabs API keys in ~/.audioPrimeProd.json
- **Content Safety**: Refusal detection to avoid processing restricted content

### Developer Tools
- **Cache Management**: Clear intermediate files with one click
- **Update Checker**: Built-in update notification system
- **Safe Hotfix Updates**: Optional SHA-256 verified `yt-dlp` binary updates from a manifest
- **Comprehensive Logging**: Per-run logs saved to .work/logs/ for debugging
- **Binary Bundling**: Automatic platform-specific binary resolution

### UI/UX
- **Multiple Built-in Themes**: Choose from "grey" (professional), "terminal" (hacker), "pastel" (light), "burgundy" (warm dark), or create custom themes
- **Extensible Theme System**: Each theme defines 5 primary colors; 17 derived UI colors are auto-computed for consistency
- **Two-Tab Interface**: Process tab for configuration, Settings tab for customization
- **Collapsible Settings Sections**: Organized categories (Appearance, API Keys, AI Prompts) for easier navigation
- **Real-Time Progress**: Live status updates with batch progress indicators
- **Responsive Design**: Scrollable layouts for small windows
- **Persistent Settings**: All preferences saved and restored on restart
- **Comprehensive Logging**: Per-run JSON logs with timestamps, stages, and metrics for debugging

## Installation (running from source)

### Prerequisites

| Requirement | Notes |
|---|---|
| **Python 3.10 – 3.13** | `anthropic>=1.0` needs 3.10+. Nuitka's support for 3.14 is experimental (it builds, with warnings); 3.13 is the recommended pairing. The Windows release was built on 3.11.9, the macOS release on 3.14.6. |
| **Git** | `requirements.txt` installs `reazonspeech-k2-asr` straight from GitHub. |
| **ffmpeg / ffprobe** | Fetched by `scripts/fetch_binaries.py` (below). If you skip that step the app falls back to whatever is on your `PATH`. |
| **API keys** | OpenAI **or** Anthropic for translation. Optional: ElevenLabs / Soniox (transcription), OpenAI / Azure / Google / ElevenLabs (cloud voices). Piper TTS needs none. |

### Setup

1. **Clone the repository**

   ```bash
   git clone https://github.com/abalint/audioPrime-release.git
   cd audioPrime-release
   ```

2. **Create and activate a virtual environment** (the build scripts assume it is named `.venv`)

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   ```

3. **Install Python dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Fetch platform binaries** (ffmpeg, ffprobe, yt-dlp, qjs) into `bin/<platform>/`

   ```bash
   python scripts/fetch_binaries.py         # macOS / Linux
   python scripts\fetch_binaries_win.py     # Windows
   ```

5. **Download the default Piper voice** into `voices/`. Only `en_US-amy-medium` is required; every other voice is downloaded by the app on first use.

   ```bash
   mkdir -p voices
   curl -L -o voices/en_US-amy-medium.onnx \
     https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx
   curl -L -o voices/en_US-amy-medium.onnx.json \
     https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json
   ```

   On Windows use `curl.exe` (ships with Windows 10+) or download the two files in a browser. Every other voice in `data/piper_voices.json` lives at the same Hugging Face path layout.

6. **(Optional for running, required for building) Fetch the ReazonSpeech models** for offline Japanese transcription into `models/reazonspeech-k2-v2/`

   ```bash
   pip install huggingface_hub
   python scripts/fetch_models.py
   ```

7. **Run**

   ```bash
   python main.py
   ```

   Output, cache, and logs are written next to the repo root: `output/`, `.work/`, `logs/`, `voices-downloaded/`. Settings and encrypted keys go to `~/.audioPrimeProd.json` and `~/.audioPrimeProd.key`.

## Building a Standalone App

The build uses [Nuitka](https://nuitka.net/) to compile the app and its Python dependencies to native code and bundle the binaries, models, and default voice so end users do not need Python. There is **one build script per platform**: `scripts/build.py` for macOS (and, untested, Linux) and `scripts/build_win.py` for Windows. They must be kept in sync when you change what gets bundled.

### Prerequisites (both platforms)

1. Everything from [Installation](#installation-running-from-source), including the default voice **and** the ReazonSpeech models. The preflight check aborts the build if either is missing.
2. Nuitka in the same venv:

   ```bash
   pip install nuitka
   ```

3. A C compiler (see the platform sections).
4. Network access. The build re-runs the binary fetch every time to pick up the latest yt-dlp and ffmpeg; if that fails it warns and continues with the binaries already in `bin/`.

### macOS (Apple Silicon)

Extra requirement: Xcode Command Line Tools, which provide `clang`.

```bash
xcode-select --install          # once
.venv/bin/python scripts/build.py
```

Output: `dist/audioPrime.app` (about 1.1 GB). Run it with `open dist/audioPrime.app`.

The build script re-signs the bundle **ad-hoc** at the end. This is required because it copies `librosa` and `unidic_lite` into the bundle as source after Nuitka has signed it, which would otherwise break the bundle seal. There is no Developer ID signature and no notarization.

To distribute the app, archive it with `ditto` so the signature survives. Do **not** use Python's `zipfile` or a plain `zip` that drops resource forks:

```bash
cd dist
ditto -c -k --sequesterRsrc --keepParent audioPrime.app audioPrime-macos-arm64.zip
```

Anyone who downloads that zip must clear the quarantine flag once before macOS will open an un-notarized app (right-click > Open no longer works on macOS 15+):

```bash
xattr -dr com.apple.quarantine /Applications/audioPrime.app
```

The build produces an arm64-only binary. Building on an Intel Mac has not been tested and there is no Intel release.

### Windows 10/11 (x64)

Extra requirement: a C compiler on `PATH`, either [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) with the "Desktop development with C++" workload or [MinGW-w64](https://www.mingw-w64.org/). The script passes `--assume-yes-for-downloads`, so Nuitka fetches any extra tooling it needs (for example Dependency Walker) without prompting.

```bat
.venv\Scripts\python.exe scripts\build_win.py
```

Output: `dist\audioPrime.dist\`, a folder containing `audioPrime.exe` and everything it needs. Zip the whole folder to distribute it; users unzip anywhere and run the exe. The console window is disabled, so nothing prints when the app is launched by double-click.

If a previous `audioPrime.exe` is still running from `dist\`, the build stops it first, because Windows will not let Nuitka replace a locked executable.

There is no code signing. SmartScreen warns on first launch; users choose "More info", then "Run anyway".

### Linux

`scripts/build.py` and `scripts/fetch_binaries.py` both branch on Linux (x86_64 and arm64 static ffmpeg from johnvansickle.com, `yt-dlp_linux`, `qjs-linux-*`) and would produce `dist/audioPrime.dist/main`. Nobody has run a Linux build of 1.0.0 and there is no Linux release, so treat it as a starting point rather than a supported target.

### Differences between the macOS and Windows builds

| | macOS | Windows |
|---|---|---|
| Build script | `scripts/build.py` | `scripts/build_win.py` |
| Binary fetch | `scripts/fetch_binaries.py`: ffmpeg/ffprobe from martin-riedl.de (native arm64), `yt-dlp_macos`, `qjs-darwin` | `scripts/fetch_binaries_win.py`: ffmpeg/ffprobe from BtbN FFmpeg-Builds, `yt-dlp.exe`, `qjs-windows-x86_64.exe` |
| Binary directory | `bin/darwin_arm64/` | `bin/windows_x86_64/` |
| Compiler | `clang` from Xcode Command Line Tools | MSVC Build Tools or MinGW-w64; Nuitka may download extra tools itself |
| Nuitka output | `--macos-create-app-bundle` → `dist/audioPrime.app` | `--output-filename=audioPrime.exe` → `dist/audioPrime.dist/` folder |
| Icon | `assets/audioPrime.icns` via `--macos-app-icon` | `assets/audioPrime.ico` via `--windows-icon-from-ico` |
| Console | not applicable | hidden with `--windows-console-mode=disable` |
| Bundled binaries | `--include-data-dir` for the whole `bin/darwin_arm64/` | each `.exe` added with `--include-data-files` (Nuitka 4 filters `.exe` out of data dirs) |
| Post-build | copies `librosa` + `unidic_lite` source into `Contents/MacOS/`, then ad-hoc `codesign --force --deep` and verify | copies the same packages into the `.dist` folder; no signing |
| Packaging | `ditto -c -k --sequesterRsrc --keepParent` (preserves the signature) | any zip of the `.dist` folder |
| First launch for users | `xattr -dr com.apple.quarantine <app>` or "Open Anyway" in Privacy & Security | SmartScreen: More info → Run anyway |
| Locked output handling | none needed | kills a running `audioPrime.exe` that holds `dist\` open |
| Python used for 1.0.0 | 3.14.6 (Nuitka support experimental) | 3.11.9 |
| Runtime data dirs | next to the `.app`: `output/`, `.work/`, `logs/`, `voices-downloaded/` | next to `audioPrime.exe`, same names |

Everything else (Nuitka flags for excluded packages, the PySide6 plugin, the one bundled voice, the voice catalog, the ReazonSpeech models, `update/tool_manifest.json`, `data/ja_frequency.txt`) is identical on both platforms.

### What gets bundled

| Category | Source in repo | Location in build |
|---|---|---|
| App source and Python dependencies | `main.py`, `src/`, everything in `requirements.txt` | compiled to native code (`openai` and `anthropic` are included whole because they import lazily) |
| Packages Nuitka cannot compile | `librosa`, `lazy_loader`, `unidic_lite` | copied as source after the build |
| Platform binaries | `bin/<platform>/` | `bin/<platform>/` |
| Default Piper voice | `voices/en_US-amy-medium.onnx` + `.onnx.json` | `voices/` |
| Piper voice catalog | `data/piper_voices.json` | `data/` |
| Japanese frequency list | `data/ja_frequency.txt` | `data/` |
| ReazonSpeech model | `models/reazonspeech-k2-v2/` | `models/` |
| yt-dlp hotfix manifest | `update/tool_manifest.json` | `update/` |
| Icons | `assets/` | `assets/` |

The rest of `data/` and `voices/` is deliberately not bundled.

### Verifying the build

1. Launch the app without Python on `PATH` and confirm the UI appears.
2. Pick a non-default Piper voice and confirm it downloads into `voices-downloaded/` next to the app.
3. Process one video end to end. Bundled `yt-dlp` and `ffmpeg` should be found without anything installed on the system. On macOS, `lipo -archs dist/audioPrime.app/Contents/MacOS/bin/darwin_arm64/ffmpeg` should print `arm64` only; an `x86_64` ffmpeg runs under Rosetta and triggers the "support for Intel-based apps is ending" notice.
4. Check that output files land next to the app, not inside the bundle.
5. macOS only: `codesign --verify --deep --strict dist/audioPrime.app` must print nothing. If it reports "a sealed resource is missing or invalid", the reseal step did not run.

## Usage

### Launch the Application

```bash
python main.py
```

### Process Tab Workflow

1. **Enter Media URLs**: Paste one or more URLs (videos, playlists, channels) into the text area
   - Examples: YouTube videos, stand.fm episodes, Vimeo links, or any yt-dlp-supported site
   - One URL per line for batch processing

2. **Select Voice**: Choose your preferred English voice:
   - Amy (US, Medium) — Clear, friendly
   - Lessac (US, High) — Natural, expressive
   - LJSpeech (US, High) — Bright, energetic
   - Ryan (US, High) — Deep, professional
   - Jenny (GB, Medium) — British accent

3. **Adjust Speed**: Set TTS playback speed (25% - 300%, default 100%)

4. **Select Source Language**: Choose the original language of your video from 32 available languages
   - Language-specific punctuation and translation rules are automatically applied

5. **Configure Authentication** (if needed):
   - **Cookies**: Select a browser if the site requires authentication (YouTube, etc.)
   - **API Keys**: Configure in Settings tab (OpenAI required; ElevenLabs optional for transcription)

6. **Optional Settings**:
   - **Create Anki Deck**: Generate a subs2srs-style flashcard deck with audio
   - **Use Transcription Fallback**: Enable audio transcription when no subtitles are available
   - **Force Transcription**: Skip subtitles entirely and always transcribe the audio
   - **Output Directory**: Change where files are saved

7. **Manage Cache**: Click "Clear Cache" to remove intermediate files and free up space

8. **Process**: Click "Process" to start the pipeline

### Settings Tab

The Settings tab is organized with collapsible sections for easy navigation:

1. **Appearance Section**:
   - **Theme Selector**: Choose between available UI themes

2. **API Keys Section**:
   - **OpenAI API Key**: Required for translation and punctuation (auto-saves when changed)
   - **ElevenLabs API Key**: Optional for transcription fallback (auto-saves when changed)
   - Direct links to get/manage API keys from provider websites

3. **AI Prompts Section** (collapsible):
   - **Translation Prompt**: Customize how the AI translates subtitles with {LANGUAGE} placeholder
   - **AI Model Selection**: Choose your preferred model for translation (gpt-5.2, gpt-5.1, gpt-5, gpt-5-mini, gpt-5-nano, gpt-4o-mini, gpt-4o, gpt-4.5-preview, gpt-4-turbo, or o3-mini)
   - **Punctuation Prompt**: Customize how the AI adds sentence-ending punctuation
   - **AI Model Selection**: Choose your preferred model for punctuation
   - Different rules for CJK languages (。？！) vs. Latin-script languages (.!?)
   - Reset to default buttons available for each prompt

4. **Check for Updates**: Click to see if a newer version is available
   - Opens the latest GitHub release page for full app updates
   - Can apply verified `yt-dlp` hotfixes from `update/tool_manifest.json`

### Output Structure

For each video processed, you'll get:

```
output/
└── [Channel Name]/
    ├── [Video Title]_interleaved.mp3      # Final mixed audio
    ├── [Video Title]_original.mp3         # Copy of original audio
    └── [Video Title].apkg                 # (Optional) Anki deck
```

## How It Works

The pipeline runs automatically through these steps:

1. **Download**: Fetches media from 1000+ supported sites using yt-dlp
   - Supports videos, playlists, channels, live streams (depending on site)

2. **Extract or Transcribe**:
   - By default, attempts to extract subtitles in your selected language
   - If "Force Transcription" is enabled, skips subtitle extraction and directly transcribes audio
   - If no subtitles found and fallback enabled, transcribes audio via ElevenLabs API (requires API key)

3. **Parse & Clean**:
   - Extracts and deduplicates SRT subtitles
   - Collapses short segments to enforce minimum 2-second audio duration
   - Merges subtitle blocks into logical sentences

4. **Punctuation**:
   - Uses OpenAI with your customizable punctuation prompt
   - Adds sentence-ending punctuation to transcript or unpunctuated text
   - Language-aware rules (CJK vs. Latin punctuation)

5. **Translate**:
   - Sends sentences to OpenAI using your customizable translation prompt
   - Provides context (previous/next sentences) for better translation accuracy
   - Applies refusal detection for safety

6. **TTS**:
   - Generates English audio using Piper (offline, completely private)
   - Caches model on first use for fast subsequent runs
   - Applies your selected voice and speed setting

7. **Interleave**:
   - Creates the final audio file with alternating pattern:
   - [English TTS] → [Original Audio] → [English TTS] → [Original Audio] → ...
   - Uses ffmpeg for precise audio alignment

8. **Anki** (optional):
   - Generates subs2srs-style flashcard deck
   - Each card contains source-language sentence + audio clip
   - Deterministic IDs allow updates across multiple runs

All steps cache their outputs, so re-running with the same video skips completed work. Check `.work/` directory for intermediate files and logs.

## Configuration

### Settings File
Settings are persisted to `~/.audioPrimeProd.json`:
- OpenAI and ElevenLabs API keys
- Voice selection and TTS speed
- Browser cookie preference
- Output directory
- Anki deck and transcription fallback preferences
- Source language selection
- Custom translation and punctuation prompts (per language)
- Optional override for update manifest URL: `tool_manifest_url`

### Theme System

The application uses a **5-color complementary palette** system designed for beautiful, cohesive UI theming.

**Built-in Themes:**
- **"grey"** — Professional neutral with steel-blue accents on light grey backgrounds
- **"terminal"** — Classic hacker terminal with phosphor green on near-black
- **"pastel"** — Light theme with pastel pink and mauve for modern, soft aesthetics
- **"burgundy"** — Warm dark theme with vibrant coral, sandy brown, and banana cream accents

**Creating a Custom Theme:**

1. Open `src/ui/themes.py`
2. Add a new Theme to the `THEMES` dictionary with 5 primary colors (the system auto-derives 17 more):
   ```python
   THEMES: dict[str, Theme] = {
       "my-theme": Theme(
           name="my-theme",
           primary="#...",           # buttons, progress bars, sliders
           secondary="#...",         # selections, checked checkboxes
           accent="#...",            # text, titles
           danger="#...",            # danger/cancel buttons
           highlight="#...",         # section headers
           # Optional overrides (auto-derived if omitted):
           bg="#...",                # main background
           bg_surface="#...",        # input fields, cards
           bg_deep="#...",           # deep background
           border="#...",            # borders
           border_hover="#...",      # border hover
           text="#...",              # foreground text
           text_muted="#...",        # muted text
           text_disabled="#...",     # disabled text
           primary_hover="#...",     # button hover
           primary_pressed="#...",   # button pressed
           primary_text="#...",      # text on buttons
           danger_hover="#...",      # danger hover
           danger_text="#...",       # text on danger buttons
           surface_hover="#...",     # surface hover
           link="#...",              # links
       ),
       # ... existing themes ...
   }
   ```
3. Set `ACTIVE_THEME = "my-theme"` to activate your theme

**How It Works:**

Each Theme defines:
- **5 primary color roles**: `primary`, `secondary`, `accent`, `danger`, `highlight`
- **17 derived UI colors** (auto-computed): backgrounds, borders, text variants, button states, hovers, etc.

The Theme class generates QSS stylesheets at runtime that map these colors to all Qt widgets. Override specific derived colors for full customization (e.g., custom `bg_surface` for light themes).

When creating a custom theme, specify only the 5 primary colors if you want auto-derivation, or provide all 22 colors explicitly for complete control.

### Hotfix Manifest (`yt-dlp`)

`yt-dlp` hotfixes are controlled by `update/tool_manifest.json`.

- Each platform entry includes `version`, `url`, and `sha256`
- Set `enabled: true` to allow installing that platform hotfix from the app
- Keep `enabled: false` to disable live binary updates (default)
- Publish manifest changes in GitHub so clients can fetch them
- Supported platform keys: `darwin_arm64`, `linux_x86_64`, `windows_x86_64`

Generate/update manifest hashes automatically:

```bash
python scripts/update_manifest.py --version 2025.03.31
```

This downloads the official yt-dlp binaries for supported platforms, computes SHA-256 hashes, and writes updated entries to `update/tool_manifest.json`.

Generate hashes but keep live rollout disabled:

```bash
python scripts/update_manifest.py --version 2025.03.31 --disable
```

#### Hotfix Release Workflow

1. Generate manifest entries for the new yt-dlp version:
```bash
python scripts/update_manifest.py --version <yt-dlp-version>
```
2. Confirm/adjust `enabled` flags per platform in `update/tool_manifest.json`.
3. Commit and push `update/tool_manifest.json` to `main`.
4. In the app, click **Check for Updates**:
   - App update action opens the latest GitHub release page.
   - yt-dlp action installs the binary only if checksum validation passes.

### Voice Models

Piper voices are ONNX models from the [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices) repository. The catalog in `data/piper_voices.json` lists 166 voices across 45 languages; regenerate it with `scripts/fetch_piper_catalog.py`. Only `en_US-amy-medium` ships in the app. When you pick any other Piper voice, `src/core/voice_manager.py` downloads it into `voices-downloaded/` next to the app and verifies its MD5. Piper has no voices for Japanese, Korean, Thai, Hebrew, Malay, or Cantonese; use a cloud engine for those target languages.

Cloud voices (OpenAI, Azure Speech, Google Cloud, ElevenLabs) are listed from the provider's API once its key is entered and are cached in the settings file.

### Languages Supported

**32 languages** with language-specific punctuation and translation rules:

Arabic, Bengali, Cantonese, Chinese (Simplified/Traditional/Taiwanese), Czech, Danish, Dutch, Finnish, French, German, Greek, Hebrew, Hindi, Hungarian, Indonesian, Italian, **Japanese**, Korean, Malay, Norwegian, Polish, Portuguese, Romanian, Russian, Spanish, Swedish, Thai, Turkish, Ukrainian, Vietnamese

Each language has customizable translation and punctuation prompts. CJK languages (Chinese, Japanese, Korean, Cantonese) use special punctuation rules (。？！) vs. Latin scripts (.!?).

## Technology Stack

- **UI Framework**: PySide6 (Qt 6) with dark mode theming and collapsible sections
- **TTS Engines**: Piper (ONNX runtime, offline), OpenAI, Azure Speech, Google Cloud, ElevenLabs
- **Translation & Punctuation**: OpenAI or Anthropic models, list fetched from the provider
- **Transcription**: ElevenLabs Scribe V2, Soniox stt-async-v5, ReazonSpeech k2-v2 (offline, Japanese)
- **Media Download**: yt-dlp (CLI) — supports 1000+ sites
- **Audio Processing**: ffmpeg + ffprobe for format conversion and validation
- **Flashcards**: genanki (Anki format generation)
- **Language Support**: Full Unicode support with language-specific text processing
- **Logging**: Timestamped JSON-friendly logs to LOGS_DIR/

## Anki Deck Format

Generated decks follow the **subs2srs standard**:
- **Front**: Source-language sentence + audio clip
- **Back**: (Empty by default; add your notes during study)

Each card includes a short audio clip of just that sentence from the original media. Deterministic deck IDs ensure that re-running the same video updates the existing deck rather than creating duplicates.

## Troubleshooting

### "Required tools not found"
Install missing tools:
- **macOS**: `brew install ffmpeg`
- **Ubuntu/Debian**: `sudo apt-get install ffmpeg`
- **Windows**: Download from [ffmpeg.org](https://ffmpeg.org/download.html)

Or download bundled binaries:
```bash
python scripts/fetch_binaries.py
```

### "Voice models missing"
The app needs `voices/en_US-amy-medium.onnx` and `.onnx.json` next to the source tree (or inside the bundle). Download them with the `curl` commands in [Installation](#installation-running-from-source). Any other Piper voice downloads automatically on first use; if that fails, check your network and that `voices-downloaded/` next to the app is writable.

### "API Key Required" or "OpenAI Error"
1. Get your API key at [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
2. Enter it in the API Key field (Process tab)
3. Make sure your OpenAI account has billing enabled and sufficient credits

### "No subtitles found"
The video must have auto-generated or user-provided subtitles in your selected language. You have three options:
1. **Select a different language** (if the video has subtitles in other languages)
2. **Enable transcription fallback** (requires ElevenLabs API key) — the app will transcribe the audio instead
3. **Enable force transcription** — always transcribe the audio, ignoring subtitle availability (requires ElevenLabs API key)

### "Transcription not working"
Enable transcription fallback in the Process tab and ensure:
1. You have an ElevenLabs API key (get one at [elevenlabs.io](https://elevenlabs.io/app/settings/api-keys))
2. The key is entered in the Settings tab
3. Your ElevenLabs account has available credits

### Slow performance on first run
The first run with a new voice downloads the Piper ONNX model (~50-150 MB). Subsequent runs with the same voice are much faster due to caching.

### "Cache full" or slow runs
Click "Clear Cache" in the Process tab to remove intermediate files. The app will regenerate them on next run.

### "Subtitles look wrong"
This may happen with:
- Auto-generated subtitles with OCR errors
- Videos with scrolling or karaoke-style subtitles
- Unsupported subtitle formats

Try:
1. Enable transcription fallback if available
2. Manually check the downloaded subtitles in `.work/` directory
3. Consider downloading official subtitle tracks if available

## API & Cost Information

### OpenAI API (Translation & Punctuation)
- **Cost**: ~$0.10-0.30 per 10-minute video (using gpt-4o-mini model)
- **Pricing**: Check [OpenAI pricing](https://openai.com/pricing) for current rates
- **Optimization**: The app counts tokens and uses context-aware prompts to minimize costs

### ElevenLabs API (Optional Transcription Fallback)
- **Cost**: Varies by model; typically $0.10-0.30 per hour transcribed
- **When Used**: Only when video lacks subtitles in your selected language
- **Pricing**: Check [ElevenLabs pricing](https://elevenlabs.io/pricing) for current rates

### Piper TTS (Offline)
- **Cost**: Free (completely offline, no API calls)
- **Model Size**: 50-150 MB per voice (downloaded once)
- **Privacy**: All processing happens locally

## Advanced Features

### Customizable Prompts
Edit translation and punctuation prompts in the Settings tab to customize how the AI processes your content:
- **Translation Prompt**: Controls how sentences are translated to English
- **Punctuation Prompt**: Controls how sentence-ending punctuation is inserted
- Use `{LANGUAGE}` placeholder to reference the source language dynamically
- Language-specific templates for CJK vs. Latin scripts
- Reset to default anytime with the "Reset to Default" button

### Audio Condensing
- **Removes long silences**: Trims gaps ≥2 seconds between subtitles from the original audio
- **Preserves all speech**: Only removes silence, keeps all words and sound effects
- **Subtitle-aware detection**: Uses subtitle timing instead of audio amplitude analysis for precision
- **Optional feature**: Enable in the Process tab for condensed versions of both original and interleaved audio
- **Padding preservation**: Keeps 250ms padding on each side of gaps for natural transitions

### Segment Grouping
- **Advanced interleaving control**: Group multiple English TTS segments before each Japanese audio chunk
- **Custom patterns**: Use `group_size > 1` for different learning styles (e.g., 2 English sentences per Japanese clip)
- **Maintains audio continuity**: All audio preserved, just reordered for alternating pattern

### Batch Processing Tips
- **Large Playlists**: The app efficiently handles 50+ videos by reusing the TTS model
- **Monitoring Progress**: Check `output/logs/` for detailed per-run logs in JSON format with metrics
- **Cache Reuse**: Intermediate files are cached intelligently; re-running skips completed steps
- **Cancellation**: Press the cancel button to gracefully stop batch processing
- **Per-run Logging**: Each run generates a timestamped log with stage labels, timing info, and error context

### Output Organization
Files are organized by channel/source:
```
output/
├── Channel Name 1/
│   ├── Video Title 1_interleaved.mp3      # Final audio
│   ├── Video Title 1.apkg                  # Anki deck (if created)
│   └── ...
└── Channel Name 2/
    ├── ...
```

### Caching & Working Directory
- **Cache Location**: `.work/` directory
- **Logs**: `.work/logs/` (timestamped JSON logs per run)
- **Clear Cache**: Use "Clear Cache" button to remove intermediate files
- **Preserve Outputs**: Clearing cache does NOT delete final output files

## Performance Notes

- **First Run**: Slower due to Piper model download (50-150 MB per voice)
- **Batch Processing**: TTS model loaded once and reused for all videos
- **Subtitle Parsing**: Typically < 1 second
- **Translation**: Depends on subtitle length and OpenAI API response time
- **TTS Generation**: ~1-2 seconds per 10-minute video
- **Interleaving**: ~5-10 seconds per video
- **Total for 10-min Video**: ~30-60 seconds after first run

## License

MIT. See [LICENSE](LICENSE). Bundled third-party components keep their own
licenses; see [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Short version: fork, branch, keep
changes focused, run the app once end to end, open a pull request.

## Support & Feedback

- **Issues & Bugs**: Open an issue on GitHub
- **Feature Requests**: Discuss in GitHub issues
- **Questions**: Check existing issues first, then create a new one with detailed information

### Getting Help

When reporting issues, include:
- Operating system and Python version
- Steps to reproduce the issue
- Any error messages from the status area or `.work/logs/`
- Whether the issue occurs on first run or after modifications
