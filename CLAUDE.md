# audioPrime Codebase Summary

## Development Environment

- **Python**: Use `.venv/bin/python` for all Python commands (e.g. `.venv/bin/python -c "..."`)
- The virtual environment is at `.venv/` in the project root

## Current Status

**Version**: 1.0.0 (maintenance mode, MIT licensed)

### Completed Features
- ✅ PySide6 desktop UI with persistent settings and collapsible sections
- ✅ Single and batch video pipeline (download → parse → translate → TTS → interleave)
- ✅ Multi-site support (1000+ yt-dlp compatible sites: YouTube, stand.fm, Vimeo, etc.)
- ✅ Multi-language support (32 languages with customizable translation/punctuation prompts)
- ✅ Anki deck generation (subs2srs format)
- ✅ Browser cookie authentication (Safari, Chrome, Firefox, Brave, Edge)
- ✅ Binary management system for cross-platform support
- ✅ TTS model caching and reuse (Piper ONNX)
- ✅ Settings persistence (~/.audioPrimeProd.json) with encrypted API keys
- ✅ Multiple theme support: grey, terminal, pastel, burgundy (plus extensible custom themes)
- ✅ Real-time progress reporting with batch progress indicators
- ✅ Transcription fallback (ElevenLabs Scribe V2) for audio without subtitles
- ✅ Force transcription mode (skip subtitles, always transcribe)
- ✅ Customizable AI prompts (translation and punctuation) per language
- ✅ Selectable AI models (gpt-5.2, gpt-5.1, gpt-5, gpt-5-mini, gpt-5-nano, gpt-4o-mini, gpt-4o, gpt-4.5-preview, gpt-4-turbo, o3-mini)
- ✅ Cache cleanup utility and update checker
- ✅ Subtitle collapsing to enforce minimum 2-second audio duration per TTS segment
- ✅ Non-speech filtering ([Music], [Applause], (singing), etc.)
- ✅ Structured per-run logging system with JSON metrics (logs/ directory)
- ✅ Audio condensing feature (trim silences ≥2s between subtitles)
- ✅ Segment grouping support (customizable interleaving patterns with group_size parameter)
- ✅ Collapsible Settings sections (Appearance, API Keys, AI Prompts) with auto-save
- ✅ Lemma-based comprehensibility analysis with i+1 sentence identification
- ✅ Unlisted knowledge adjustment (frequency-ranked reclassification of unknown words)
- ✅ Check-first mode (pause after comprehensibility analysis to Continue or Skip per video)
- ✅ Configurable target (translation) language with ⇄ Swap direction button — supports reverse flows like Spanish speakers learning English (Source: English, Translate to: Spanish)
- ✅ English available as a source language (33 languages total)
- ✅ Selectable TTS engine: Piper (offline, English voices) or ElevenLabs (cloud, multilingual voices incl. Spanish; voice list fetched from the account)
- ✅ Soniox transcription engine (cloud, 60+ languages) alongside ElevenLabs and ReazonSpeech
- ✅ Dynamic AI model lists fetched from OpenAI/Anthropic (/v1/models), cached in config with hardcoded fallback + Refresh Model List button

### In Development
- Testing and optimization
- Edge case handling
- Performance profiling
- Distribution and binary builds

## Output Format

**CRITICAL**: The final output of audioPrime is an **audio file** with a specific interleaving pattern:

```
[Translation (TTS)] → [Original Audio] → [Translation (TTS)] → [Original Audio] → ...
```

The translation language is configurable ("Translate to" on the Process tab, default English). A Spanish speaker learning English sets Source = English and Translate to = Spanish (with an ElevenLabs Spanish-capable voice), producing: [Spanish translation TTS] → [Original English audio] → ...

The classic flow (e.g. learning Japanese with English as native language):

This pattern repeats for **every sentence** in the video:
1. First, you hear the English translation spoken via TTS
2. Then, you hear the original Japanese audio from the video
3. This alternates continuously throughout the entire audio file

**Example**: If a video has 3 Japanese sentences:
- English TTS: "Hello, how are you?"
- Japanese Audio: "こんにちは、元気ですか？"
- English TTS: "I'm doing well."
- Japanese Audio: "元気です。"
- English TTS: "That's great to hear."
- Japanese Audio: "それは良かったです。"

This interleaved audio format is designed for language learning, allowing listeners to hear the translation before the original language for comprehension support.

## Overview
**audioPrime** is a PySide6 desktop application that creates interleaved audio files from online videos and audio content. It supports **YouTube, stand.fm, Vimeo, and 1000+ sites** supported by yt-dlp. The app downloads media, extracts or transcribes subtitles, translates them to English, generates English TTS, and produces a final audio file where **each English translation is followed by its corresponding original audio clip**. The application supports batch processing of multiple videos from URLs, playlists, or channels, with optional Anki deck generation for language learning.

## Project Structure

### Data (`data/`)
- **ja_frequency.txt** — Japanese word frequency list (44,998 words, University of Leeds Corpus, CC-licensed). One word per line, most frequent first. Used for unlisted knowledge reclassification.

### Entry Point
- `main.py` — Initializes PySide6 app, loads styles, displays MainWindow

### UI Layer (`src/ui/`)
- **main_window.py** — Main application window with two tabs:
  - **Process Tab**:
    - Multi-line URL input (supports videos, playlists, channels)
    - Voice selection dropdown (5 English voices available)
    - Speed slider for TTS playback (25% - 300%)
    - Browser cookie selector (None, Safari, Chrome, Firefox, Brave, Edge)
    - Source language selector (32 languages supported)
    - Anki deck generation checkbox
    - Transcription fallback checkbox (uses ElevenLabs when no subtitles)
    - Force transcription checkbox (skip subtitles, always transcribe)
    - Output directory selector
    - Clear Cache button
    - Progress bar with estimated progress animation
    - Batch progress indicator (current video of total)
    - Detailed status messages and error handling
  - **Settings Tab** (collapsible sections):
    - **Appearance**: Theme selector with live switching
    - **API Keys**: OpenAI and ElevenLabs API key inputs with show/hide toggles (auto-saves)
    - **AI Prompts** (collapsible):
      - Translation prompt editor with {LANGUAGE} placeholder support
      - AI model selector for translation (gpt-4o-mini, gpt-4o, gpt-4.5-preview, gpt-4-turbo, o3-mini)
      - Punctuation prompt editor with language-specific rules (CJK vs. Latin)
      - AI model selector for punctuation
      - Reset to default buttons for both prompts
      - Update checker button
  - Persistent settings storage to ~/.audioPrimeProd.json
- **themes.py** — Themeable color system with generated QSS stylesheets:
  - Defines colors from a 5-color palette (primary, secondary, accent, danger, highlight)
  - Derives all UI element colors automatically (backgrounds, borders, text, states)
  - Includes two theme presets: "vivid" (bright, modern) and "catppuccin" (dark, muted)
  - Color utility functions: darken, lighten, hex/RGB conversion
  - Dynamic stylesheet generation via `generate_stylesheet()`
  - Easily extensible: add new themes to THEMES dict
- **styles.py** — Loads and applies QSS stylesheet from active theme

### Core Pipeline (`src/core/`)
**pipeline.py** contains:
- **BatchWorker** — QThread orchestrator for processing multiple videos sequentially:
  - Resolves URLs (expands playlists/channels to individual videos)
  - Loads TTS model once, reuses for all videos
  - Processes each video through full pipeline
  - Tracks success/failure for summary report
  - Supports both subtitle and transcription-based workflows
- **PipelineWorker** — QThread orchestrator for single video:
  1. **downloader.py** — Downloads media using yt-dlp CLI
     - Supports 1000+ sites (YouTube, stand.fm, Vimeo, etc.)
     - URL resolution (playlists, channels)
     - Browser cookie authentication
     - Subtitle extraction with language code mapping
     - Force transcription mode (skip subtitles, always transcribe)
  2. **transcriber.py** — Transcribes audio via ElevenLabs Scribe V2 API (fallback when no subtitles)
  3. **srt_parser.py** — Parses SRT subtitles, deduplicates, merges to sentences
     - Subtitle collapsing to enforce minimum 2-second audio duration
     - Robust handling of scrolling subtitles and timing issues
  4. **translator.py** — Translates subtitles via OpenAI API with selectable model
     - User-selectable models: gpt-4o-mini, gpt-4o, gpt-4.5-preview, gpt-4-turbo, o3-mini
     - Customizable translation prompts per language
     - Refusal detection for content safety
     - Quality validation (rejects translations with >25% unclear blocks)
  5. **tts.py** — Generates TTS using Piper (ONNX models via Python API)
     - Offline, privacy-friendly voice synthesis
     - Piper model caching for performance
  6. **interleaver.py** — Creates the final interleaved audio file: [English TTS] → [Original Audio] → [English TTS] → [Original Audio] repeating for every sentence
  7. **audio.py** — Audio utility functions (slice, loudness, speed, concatenate, validation via ffprobe)
  8. **anki.py** — Generates subs2srs-style Anki decks with audio clips
     - Deterministic deck IDs for consistent updates across runs
  9. **cache_manager.py** — Manages caching of intermediate outputs
  10. **updater.py** — Checks for application updates
  11. **lemma_analyzer.py** — Lemma-based comprehensibility analysis (tokenization, i+1 detection)
  12. **lemma_report.py** — Generates JSON and text comprehensibility reports

### Configuration (`src/config.py`)
- Directory paths (voices, output, working directory)
- Voice registry (5 English voices with different characteristics)
- API key storage (~/.audioPrimeProd.json with extended settings)
- ffmpeg availability check

### Binary Management (`src/bin_paths.py`)
- Resolves bundled binaries (ffmpeg, piper, yt-dlp) by platform
- Falls back to system PATH if bundled binaries not found
- Supports PyInstaller frozen builds
- Handles different architectures (arm64, x86_64)

## Key Technologies
- **UI**: PySide6 (Qt 6) with custom dark-mode QSS styling, collapsible sections
- **TTS**: Piper (ONNX runtime, offline)
- **Translation**: OpenAI API with selectable models (gpt-4o-mini, gpt-4o, gpt-4.5-preview, gpt-4-turbo, o3-mini)
- **Transcription**: ElevenLabs Scribe V2 API (fallback or forced mode for audio without subtitles)
- **Media Download**: yt-dlp CLI (1000+ sites), ffmpeg
- **Subtitle Handling**: Custom SRT parser with deduplication
- **Flashcards**: genanki (Anki format generation)
- **Binary Resolution**: Platform-aware bundled binary fallback

## Voice Models Available
- Amy (US, Medium) — Clear, friendly
- Lessac (US, High) — Natural, expressive
- LJSpeech (US, High) — Bright, energetic
- Ryan (US, High) — Deep, professional
- Jenny (GB, Medium) — British accent

## Languages Supported (33 Total)
Arabic, Bengali, Cantonese, Chinese (Simplified/Traditional/Taiwanese), Czech, Danish, Dutch, English, Finnish, French, German, Greek, Hebrew, Hindi, Hungarian, Indonesian, Italian, Japanese, Korean, Malay, Norwegian, Polish, Portuguese, Romanian, Russian, Spanish, Swedish, Thai, Turkish, Ukrainian, Vietnamese

Any language can be either the **source** (video language / language being learned) or the **target** ("Translate to" — the learner's native language). Prompts support both `{LANGUAGE}` (source) and `{TARGET_LANGUAGE}` placeholders.

## Transcription Engines
- **ElevenLabs Scribe V2** (cloud, all languages) — `src/core/transcriber.py`
- **Soniox stt-async-v5** (cloud, 60+ languages incl. English/Spanish/Japanese) — upload → poll → transcript flow with automatic file cleanup
- **ReazonSpeech k2-v2** (offline, Japanese only, bundled ONNX models)
- Engine selection via the Transcription combo (Auto prefers ElevenLabs, then Soniox, then ReazonSpeech for Japanese); shared resolver in `src/core/transcriber.py:resolve_transcription_engine`

## TTS Engines
Five selectable engines, all sharing one interface (`tts_id`, `cache_key`, `synthesize_to_mp3`) behind the factory `src/core/tts.py:create_tts_engine`. The Process-tab voice list is filtered by the "Translate to" (target) language.

- **Piper** (offline, free) — default. Covers 27 of the app's 33 languages (all but Japanese, Korean, Thai, Hebrew, Malay, Cantonese). Only `en_US-amy-medium` ships in the installer; every other voice is listed in `data/piper_voices.json` (166 voices, 45 languages) and **downloaded on demand** into `voices-downloaded/` on first use — see `src/core/voice_manager.py`. Regenerate the catalog with `scripts/fetch_piper_catalog.py`.
- **OpenAI** (cloud, `gpt-4o-mini-tts`/`tts-1`/`tts-1-hd`) — reuses the existing OpenAI key; multilingual, no per-language voice filtering. ~$15/1M chars.
- **Azure Speech** (cloud) — widest coverage (100+ locales, covers all 33). Needs an Azure Speech key + region. ~$15/1M chars. Voice list fetched from the regional `/voices/list` endpoint, cached in config.
- **Google Cloud** (cloud) — cheapest, with a free monthly allowance. Plain API key (not a service-account JSON). ~$4/1M chars. Voice list fetched from `/v1/voices`.
- **ElevenLabs** (cloud) — highest quality/cost. Model selectable (`eleven_flash_v2_5` default — 32 languages at ~half cost — `eleven_turbo_v2_5`, or `eleven_multilingual_v2`). Voice list fetched from `/v1/voices`.

Cloud voice lists are fetched in the background by `VoiceFetchWorker` and cached per provider. Per-engine cost hints (`TTS_ENGINE_COST_PER_1M`) show an approximate $/hour of video under the voice picker. **Deliberately not added:** edge-tts (silent audio truncation under load; ToS risk) and XTTS-v2 (non-commercial license, licensor defunct).

Each language has customizable translation and punctuation prompts optimized for its linguistic features (CJK languages use different punctuation rules than Latin-script languages).

## Single Video Workflow
1. User provides media URL (1000+ supported sites), selects voice, source language, and configuration
2. Worker downloads media in background thread
3. Extracts subtitles in specified language, or transcribes audio via ElevenLabs if no subtitles found
4. Deduplicates scrolling subtitles, collapses short segments (minimum 2 seconds), merges to sentences
5. Inserts sentence-ending punctuation using customizable OpenAI-powered punctuation rules
6. Translates sentences to English via OpenAI (using customizable translation prompt)
7. Generates English TTS audio with Piper (cached model reuse)
8. **Interleaves TTS with original audio using ffmpeg** — Creates alternating pattern: [English TTS] → [Original Audio] → [English TTS] → [Original Audio] for every sentence
9. Outputs mixed audio file to organized directory structure
10. (Optional) Generates Anki deck with source sentences and corresponding audio clips

**Final Output**: An audio file where each sentence follows the pattern: English translation (TTS) followed by original audio clip.

## Batch Workflow
1. User provides multiple URLs (videos, playlists, channels from 1000+ supported sites)
2. URLs are resolved to individual video URLs
3. TTS model is loaded once and reused for all videos
4. Each video goes through single video workflow (producing an interleaved audio file)
5. Results are consolidated with success/failure summary report
6. Real-time progress updates show current video being processed

**Final Output**: One interleaved audio file per video processed, organized by channel/source.

## Dependencies
### Python Packages
- PySide6 >= 6.6 (GUI framework)
- openai >= 1.0 (translation and punctuation API)
- tiktoken >= 0.5 (token counting for API cost management)
- piper-tts >= 1.2 (text-to-speech Python API)
- yt-dlp >= 2024.0 (video download and 1000+ site support)
- onnxruntime >= 1.16 (TTS neural network inference)
- genanki >= 0.13 (Anki deck generation)
- pathvalidate (filename sanitization)
- requests >= 2.31 (HTTP client for API calls)
- fugashi >= 1.3 (Japanese morphological analysis via MeCab)
- unidic-lite >= 1.0.8 (MeCab dictionary for Japanese lemmatization)
- simplemma >= 0.9 (lightweight lemmatizer for non-Japanese languages)

### External Tools (bundled or system PATH)
- ffmpeg (audio mixing and format conversion) — required
- ffprobe (audio metadata and validation) — part of ffmpeg
- piper (offline TTS engine) — bundled
- yt-dlp (media download) — bundled or system

## Advanced Features

### Multi-Language Support (32 Languages)
- Supports any language with OpenAI API translation capability
- Customizable translation and punctuation prompts per language
- CJK-specific punctuation rules (Japanese, Chinese, Korean, Cantonese)
- Dynamic {LANGUAGE} placeholder in custom prompts
- Settings persisted per language

### Multi-Site Support (1000+ Sites)
- Any site supported by yt-dlp (YouTube, stand.fm, Vimeo, Twitch, etc.)
- Automatic site detection and format resolution
- Playlist and channel expansion to individual videos
- Batch processing across multiple sources

### Transcription Fallback & Force Transcription
- **Fallback Mode**: Automatic transcription via ElevenLabs Scribe V2 API when no subtitles found
- **Force Transcription Mode**: Checkbox to skip subtitle extraction entirely and always transcribe
  - Useful for videos without subtitles or when transcription quality is preferred
  - Requires ElevenLabs API key
- ElevenLabs API key management in Settings tab
- Seamless integration with subtitle-based workflows
- Reduces dependency on availability of subtitle tracks

### Customizable AI Prompts & Selectable Models
- Translation prompt editor with full control over OpenAI behavior
- Punctuation prompt editor for sentence boundary detection
- Language-specific prompt templates (CJK vs. Latin)
- Live preview and reset-to-default functionality
- Custom prompts saved to ~/.audioPrimeProd.json
- **Selectable AI Models**: Choose different models for translation and punctuation tasks
  - Available models: gpt-5.2, gpt-5.1, gpt-5, gpt-5-mini, gpt-5-nano, gpt-4o-mini, gpt-4o, gpt-4.5-preview, gpt-4-turbo, o3-mini
  - Separate model selection for translation and punctuation
  - Settings persist across sessions

### Batch Processing
- Process multiple videos in a single session
- Supports playlists and channel URLs (auto-resolved to individual videos)
- Reuses TTS model across videos for performance
- Consolidated success/failure reporting
- Real-time batch progress updates

### Anki Deck Generation
- Optional subs2srs-style Anki deck creation
- Includes source-language sentences with synchronized audio clips
- Deterministic deck IDs for consistent updates across runs
- Follows standard Anki model format

### Browser Cookie Authentication
- Support for authentication via browser cookies
- Enables downloading from age-restricted or private videos (with permission)
- Browser options: Safari, Chrome, Firefox, Brave, Edge

### Subtitle Processing Enhancements
- Subtitle collapsing to enforce minimum 2-second Japanese audio duration per TTS segment
- Automatic deduplication of scrolling subtitles
- Robust sentence boundary detection
- Punctuation insertion via AI for unpunctuated transcripts
- Non-speech filtering: Removes subtitle blocks containing only annotations ([Music], [Applause], (singing), 【拍手】, music symbols ♪♫🎵🎶, etc.)
- Improves transcript quality by focusing on actual speech content

### Audio Condensing
- **Optional feature**: Trim long silences (≥2 seconds between subtitles) from the original audio
- **Preserves all speech**: Uses subtitle timing for precision, removes only silence not speech
- **Subtitle-aware gap detection**: Built into `src/core/audio.py` with gap analysis and keep-segment computation
- **Padding preservation**: Keeps 250ms padding on each side of gaps for natural audio transitions
- **Output options**: Generates both condensed interleaved audio and condensed original audio files
- Reduces total audio duration while preserving all meaningful content

### Segment Grouping
- **Advanced interleaving control**: Group multiple English TTS segments before each Japanese audio chunk
- **Custom patterns**: `group_size` parameter allows 1:1, 2:1, 3:1, etc. English-to-Japanese patterns
- **Flexible learning styles**: Enables different study approaches (more translations before listening vs. less)
- **Audio continuity**: Maintains all audio content, just reorders segment concatenation
- **Implementation**: Built into `src/core/interleaver.py` with segment reordering logic

### Comprehensibility Analysis
- **Lemma-based analysis**: Rates video comprehensibility based on user's known vocabulary list
- **i+1 sentence identification**: Finds sentences with exactly 1 unknown word (Krashen's input hypothesis)
- **Japanese support**: Uses `fugashi` + `unidic-lite` for MeCab morphological analysis (dictionary-form lemmas)
- **Multi-language support**: Uses `simplemma` for lightweight lemmatization of all other languages
- **Dual output**: Generates both JSON (machine-readable) and text (human-readable) reports
- **Pipeline integration**: Runs after sentence parsing (step 2b), before translation
- **UI controls**: Checkbox + file picker in Process tab for selecting lemma list (.txt, one word per line)
- **Unlisted knowledge adjustment**: QSpinBox (0-75%, step 5) estimates words known but not in lemma list
  - Slider at X% means "X% of my known vocabulary is missing from the list"
  - Calculates `estimated_true_known = known_from_list / (1 - slider/100)`
  - Reclassifies top N unknown lemmas as "probably known" using frequency ranking
  - Japanese: uses bundled 44,998-word frequency list (`data/ja_frequency.txt`, University of Leeds Corpus)
  - Other languages: alphabetical sort (no frequency data)
  - Reports show raw score, adjusted score, and reclassified word list
  - Setting persists as `unlisted_knowledge` in config
- **Implementation**: `src/core/lemma_analyzer.py` (analysis), `src/core/lemma_report.py` (report generation)
- **Check-first mode**: "Check first" sub-checkbox under comprehensibility
  - Pauses pipeline after comprehensibility analysis to show score dialog
  - User clicks **Continue** (run full pipeline) or **Skip** (next video in batch)
  - Cross-thread: `BatchWorker` emits signal → `MainWindow` shows `QMessageBox` → sets response via `threading.Event`
  - Comprehensibility report is written before the dialog so it's available regardless of user choice
  - Setting persists as `check_first` in config

### Cache Management
- Clear Cache button in UI for manual cache cleanup
- Structural and quality validation for cached files
- Refusal pattern detection for translation safety
- Selective cache invalidation based on content quality

### Utilities
- Update checker button in Settings tab
- **Structured per-run logging system** (`logs/` directory):
  - Timestamped JSON-friendly logs with millisecond precision
  - `RunLogger` class for easy structured logging
  - Logs include: stage labels, progress metrics, error context, video URLs, cache directories
  - Separate from work directory for organized debugging
  - Batch and single video logs tracked separately
- Platform-aware binary resolution (darwin, linux, windows)
- Automatic fallback to system PATH for tools

### Bundled Binary Support
- `scripts/fetch_binaries.py` downloads platform-specific binaries
- Automatic fallback to system PATH
- Supports darwin (arm64, x86_64), linux (x86_64), windows (x86_64)
- PyInstaller-compatible for standalone distribution

### UI Theme System
- **Built-in Themes**: Four pre-configured themes with carefully designed color palettes:
  - **"grey"**: Professional neutral with steel-blue accents on light grey backgrounds
  - **"terminal"**: Classic hacker terminal with phosphor green on near-black
  - **"pastel"**: Light theme with soft pastel pink and mauve aesthetics
  - **"burgundy"**: Warm dark theme with vibrant coral, sandy brown, and banana cream accents
- **5-Color Palette System**: Each theme defined by 5 primary colors (primary, secondary, accent, danger, highlight)
- **17 Derived Colors**: Auto-computed from 5 primary colors (backgrounds, borders, text variants, button states, hovers, etc.)
- **Dynamic Stylesheet Generation**: QSS stylesheets generated at runtime for consistency across all UI elements
- **Extensibility**: Add custom themes by defining 5 primary colors in `src/ui/themes.py` (derived colors auto-computed) or override all 22 colors explicitly
- **Color Utility Functions**: `darken()` and `lighten()` helpers for creating harmonious color schemes

### Enhanced Settings Persistence
- Extended config file (`~/.audioPrimeProd.json`) with:
  - OpenAI and ElevenLabs API keys
  - Voice preference and TTS speed setting
  - Browser cookie preference
  - Output directory
  - Anki deck, transcription fallback, and force transcription preferences
  - Custom translation and punctuation prompts per language
  - AI model selections for translation and punctuation (per-task)
  - Source language selection
  - Active theme selection
- All settings restored on app restart
- Auto-save for API keys when entered in Settings tab

### Smart UI Features
- Two-tab interface (Process and Settings)
- **Collapsible Settings Sections**: Organized sections for Appearance, API Keys, and AI Prompts
  - API Keys section with auto-save functionality
  - Appearance section with theme switcher
  - AI Prompts section with model selection and custom prompt editors
- Estimated progress animation (smooth progress bars)
- Batch progress indicator (current/total videos)
- Cancel button with graceful shutdown
- Startup validation checks (ffmpeg, voices directory)
- Show/hide toggles for API keys
- Multiple built-in themes: "grey" (professional), "terminal" (hacker), "pastel" (light), "burgundy" (warm dark)
- Extensible theme system: add new themes by defining 5 primary colors + optional 17 derived colors in `src/ui/themes.py`
- Responsive scrollable layouts for small windows
- Per-run structured logging with timestamps, stage labels, and JSON metrics
