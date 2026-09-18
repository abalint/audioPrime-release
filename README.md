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
- ✅ Multi-language support (32 languages with customizable AI prompts)
- ✅ Multi-site support (1000+ yt-dlp compatible sites)
- ✅ Subtitle extraction and audio transcription (with ElevenLabs fallback)
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

Currently in active development with focus on testing and optimization.

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
- **5 Voice Options**: Amy (friendly), Lessac (expressive), LJSpeech (bright), Ryan (professional), Jenny (British)
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

## Installation

### Prerequisites

- **Python 3.9+**
- **ffmpeg** (for audio processing and validation)
- **OpenAI API key** (for translation and punctuation — ~$0.10-0.30 per 10-minute video)
- **ElevenLabs API key** (optional, only for transcription fallback when videos lack subtitles)

### Setup

1. **Clone the repository:**
```bash
git clone <repo-url>
cd audioPrimeProd
```

2. **Create a virtual environment:**
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. **Install Python dependencies:**
```bash
pip install -r requirements.txt
```

4. **(Optional) Download bundled binaries:**
```bash
python scripts/fetch_binaries.py
```
This downloads precompiled `ffmpeg`, `piper`, and `yt-dlp` for your platform. If skipped, the app will use system-installed versions. Works with:
- macOS (arm64, x86_64)
- Linux (x86_64)
- Windows (x86_64)

5. **Place voice models in the `voices/` directory:**
- Download `.onnx` and `.onnx.json` files from [Piper voice releases](https://github.com/rhasspy/piper/releases)
- 5 voices are pre-configured: Amy, Lessac, LJSpeech, Ryan, Jenny
- Example voice files:
  - `en_US-amy-medium.onnx` + `en_US-amy-medium.onnx.json`
  - `en_US-lessac-high.onnx` + `en_US-lessac-high.onnx.json`
  - (repeat for other voices)

## Building a Standalone App

The build system uses [Nuitka](https://nuitka.net/) to compile audioPrime into a standalone application. The resulting binary contains native machine code (no `.pyc` bytecode) and bundles all dependencies, voice models, and platform binaries so end users don't need Python installed.

### Prerequisites (All Platforms)

1. **Python 3.9+** with a working venv
2. **A C compiler** (see platform-specific notes below)
3. **Nuitka**:
   ```bash
   pip install nuitka
   ```
4. **All Python dependencies** installed:
   ```bash
   pip install -r requirements.txt
   ```
5. **Voice models** in `voices/` (`.onnx` + `.onnx.json` files)
6. **Platform binaries** fetched:
   ```bash
   python scripts/fetch_binaries.py
   ```

### macOS

**Extra requirements**: Xcode Command Line Tools (provides `clang`).

```bash
xcode-select --install   # if not already installed
```

**Build**:
```bash
python scripts/build.py
```

**Output**: `dist/audioPrime.app`

**Run**:
```bash
open dist/audioPrime.app
```

Or double-click `audioPrime.app` in Finder. Output files (audio, Anki decks) are written to an `output/` directory next to the `.app`, not inside the bundle.

### Linux

**Extra requirements**: `gcc` and development headers.

```bash
# Debian/Ubuntu
sudo apt install gcc python3-dev

# Fedora
sudo dnf install gcc python3-devel
```

**Build**:
```bash
python scripts/build.py
```

**Output**: `dist/main.dist/` (directory containing the `main` executable and all dependencies)

**Run**:
```bash
./dist/main.dist/main
```

### Windows

**Extra requirements**: A C compiler. The easiest option is [MinGW-w64](https://www.mingw-w64.org/) or [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) with the "Desktop development with C++" workload.

**Build** (from a terminal with the compiler on PATH):
```bash
python scripts/build.py
```

**Output**: `dist\main.dist\` (directory containing `main.exe` and all dependencies)

**Run**:
```bash
dist\main.dist\main.exe
```

### What Gets Bundled

| Category | Source | Destination in bundle |
|---|---|---|
| Voice models | `voices/*.onnx`, `voices/*.onnx.json` | `voices/` |
| Tool manifest | `update/tool_manifest.json` | `update/` |
| Platform binaries | `bin/{platform}/ffmpeg`, `ffprobe`, `yt-dlp`, `piper` | `bin/{platform}/` |
| Python deps | All packages from `requirements.txt` | Compiled to native C |
| App source | All `src/**/*.py` + `main.py` | Compiled to native C |

### Verifying the Build

1. Launch the app and confirm the UI appears (no terminal/Python needed)
2. Select a voice — models should load from the bundled `voices/` directory
3. Process a video — bundled `yt-dlp` and `ffmpeg` should be found automatically
4. Check that output files land next to the app, not inside the bundle
5. Confirm no `.pyc` or readable `.py` files exist inside the build output

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

Five English voices are available:

| Voice | Region | Quality | Use Case |
|-------|--------|---------|----------|
| Amy | US | Medium | Clear, friendly delivery |
| Lessac | US | High | Natural, expressive speech |
| LJSpeech | US | High | Bright, energetic tone |
| Ryan | US | High | Deep, professional voice |
| Jenny | GB | Medium | British accent |

All voices use Piper ONNX models for offline, privacy-friendly synthesis.

### Languages Supported

**32 languages** with language-specific punctuation and translation rules:

Arabic, Bengali, Cantonese, Chinese (Simplified/Traditional/Taiwanese), Czech, Danish, Dutch, Finnish, French, German, Greek, Hebrew, Hindi, Hungarian, Indonesian, Italian, **Japanese**, Korean, Malay, Norwegian, Polish, Portuguese, Romanian, Russian, Spanish, Swedish, Thai, Turkish, Ukrainian, Vietnamese

Each language has customizable translation and punctuation prompts. CJK languages (Chinese, Japanese, Korean, Cantonese) use special punctuation rules (。？！) vs. Latin scripts (.!?).

## Technology Stack

- **UI Framework**: PySide6 (Qt 6) with dark mode theming and collapsible sections
- **TTS Engine**: Piper (ONNX runtime for offline synthesis)
- **Translation & Punctuation**: OpenAI API with selectable models (gpt-4o-mini, gpt-4o, gpt-4.5-preview, gpt-4-turbo, o3-mini)
- **Transcription Fallback**: ElevenLabs Scribe V2 API
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
Download voice models from [Piper GitHub releases](https://github.com/rhasspy/piper/releases):
1. Download `.onnx` and `.onnx.json` files for your desired voices
2. Place them in the `voices/` directory
3. Files should be named like: `en_US-amy-medium.onnx`

Pre-configured voice names:
- `en_US-amy-medium.onnx`
- `en_US-lessac-high.onnx`
- `en_US-ljspeech-high.onnx`
- `en_US-ryan-high.onnx`
- `en_GB-jenny_dioco-medium.onnx`

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
