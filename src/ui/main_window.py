"""Main application window with all widgets."""

import os
import re
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..bin_paths import check_tool
from ..config import (
    DEFAULT_AI_MODEL,
    DEFAULT_TARGET_LANGUAGE,
    DEFAULT_TRANSCRIPTION_ENGINE,
    LANGUAGE_REGISTRY,
    OUTPUT_DIR,
    OutputConfig,
    TRANSCRIPTION_ENGINE_OPTIONS,
    TTS_ENGINE_OPTIONS,
    VERSION,
    VOICES_DIR,
    AI_MODEL_SEPARATOR,
    AZURE_REGIONS,
    ELEVENLABS_TTS_MODEL_OPTIONS,
    OPENAI_TTS_MODELS,
    OPENAI_TTS_VOICES,
    TTS_ENGINE_COST_PER_1M,
    get_anthropic_api_key,
    get_api_key,
    get_azure_api_key,
    get_azure_region,
    get_azure_voice,
    get_cached_azure_voices,
    get_cached_elevenlabs_voices,
    get_cached_google_voices,
    get_elevenlabs_api_key,
    get_elevenlabs_tts_model,
    get_elevenlabs_voice,
    get_google_api_key,
    get_google_voice,
    get_openai_tts_model,
    get_openai_tts_voice,
    get_piper_voice,
    get_language_config,
    get_lemma_list_path,
    get_soniox_api_key,
    DEFAULT_SUMMARY_PROMPT,
    get_punctuation_model,
    get_punctuation_prompt_raw,
    get_summary_model,
    get_summary_prompt_raw,
    get_target_language,
    get_transcription_engine,
    get_translation_model,
    get_translation_prompt_raw,
    get_tts_engine,
    is_anthropic_model,
    load_config,
    migrate_output_configs,
    reset_punctuation_prompt,
    reset_summary_prompt,
    reset_translation_prompt,
    save_config,
    set_anthropic_api_key,
    set_api_key,
    set_azure_api_key,
    set_azure_region,
    set_azure_voice,
    set_cached_azure_voices,
    set_cached_elevenlabs_voices,
    set_cached_google_voices,
    set_custom_punctuation_prompt,
    set_custom_summary_prompt,
    set_custom_translation_prompt,
    set_elevenlabs_api_key,
    set_elevenlabs_tts_model,
    set_elevenlabs_voice,
    set_google_api_key,
    set_google_voice,
    set_lemma_list_path,
    set_openai_tts_model,
    set_openai_tts_voice,
    set_piper_voice,
    set_punctuation_model,
    set_soniox_api_key,
    set_summary_model,
    set_target_language,
    set_translation_model,
    set_tts_engine,
)
from ..core import voice_manager
from ..core.local_file import SUPPORTED_EXTENSIONS, is_local_file
from ..core.model_catalog import get_ai_model_options, refresh_model_catalog
from ..core.pipeline import BatchWorker
from ..core.tts import (
    fetch_azure_voices,
    fetch_elevenlabs_voices,
    fetch_google_voices,
)
from . import themes as _themes_module
from .themes import THEMES, generate_stylesheet, get_theme


class CollapsibleSection(QWidget):
    """A collapsible section with a clickable header and hideable content."""

    def __init__(self, title, parent=None, expanded=True):
        super().__init__(parent)
        self._title = title
        self._expanded = expanded

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.toggle_btn = QPushButton(self._header_text())
        self.toggle_btn.setObjectName("collapsible_header")
        self.toggle_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_btn.clicked.connect(self._on_toggle)
        outer.addWidget(self.toggle_btn)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 6, 0, 0)
        self.content_layout.setSpacing(10)
        self.content.setVisible(expanded)
        outer.addWidget(self.content)

    def _header_text(self):
        arrow = "\u25BC" if self._expanded else "\u25B6"
        return f"  {arrow}  {self._title}"

    def _on_toggle(self):
        self._expanded = not self._expanded
        self.content.setVisible(self._expanded)
        self.toggle_btn.setText(self._header_text())

    def addWidget(self, widget):
        self.content_layout.addWidget(widget)

    def addLayout(self, layout):
        self.content_layout.addLayout(layout)


class ModelFetchWorker(QThread):
    """Fetches current AI model lists from OpenAI/Anthropic in the background."""

    fetched = Signal(list, list)  # (options, errors)

    def run(self):
        try:
            options, errors = refresh_model_catalog()
        except Exception as e:
            options, errors = get_ai_model_options(), [str(e)]
        self.fetched.emit(options, errors)


class VoiceFetchWorker(QThread):
    """Fetches a cloud provider's voice list in the background.

    Each provider's list is cached in config so the combo stays populated
    offline and between runs.
    """

    fetched = Signal(list)
    error = Signal(str)

    def __init__(self, engine):
        super().__init__()
        self._engine = engine

    def run(self):
        try:
            if self._engine == "ElevenLabs (Cloud)":
                voices = fetch_elevenlabs_voices(get_elevenlabs_api_key())
                set_cached_elevenlabs_voices(voices)
            elif self._engine == "Azure (Cloud)":
                voices = fetch_azure_voices(get_azure_api_key(), get_azure_region())
                set_cached_azure_voices(voices)
            elif self._engine == "Google (Cloud)":
                voices = fetch_google_voices(get_google_api_key())
                set_cached_google_voices(voices)
            else:
                voices = []
            self.fetched.emit(voices)
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"audioPrime v{VERSION}")
        self.setMinimumWidth(560)
        self.worker = None
        self.update_worker = None  # For update operations
        self.cache_worker = None  # For cache operations
        self.model_fetch_worker = None  # For AI model list fetches
        self.voice_fetch_worker = None  # For ElevenLabs voice list fetches

        self._estimated_timer = QTimer()
        self._estimated_timer.timeout.connect(self._tick_estimated_progress)
        self._progress_cap = 0
        self._progress_scale = 1000

        self._build_ui()
        self._apply_inline_styles()
        self._load_settings()
        self._startup_checks()
        self._check_cache_size_warning()

        # Refresh AI model lists from providers in the background
        self._model_fetch_silent = True
        self._start_model_fetch(silent=True)

        # Set initial window size after UI is built
        self.resize(800, 600)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 16, 20, 16)

        # Prevent layout from forcing window size based on content
        from PySide6.QtWidgets import QLayout
        layout.setSizeConstraint(QLayout.SetNoConstraint)

        # Title
        title = QLabel(f"audioPrime v{VERSION}")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Tab widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Create tabs
        self._build_process_tab()
        self._build_settings_tab()

    def _build_process_tab(self):
        """Build the Process tab with video processing controls."""
        # Use scroll area to handle content that's taller than window
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)

        process_widget = QWidget()
        layout = QVBoxLayout(process_widget)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # URL / file input area
        url_header = QHBoxLayout()
        url_header.addWidget(QLabel("Media:"))
        url_header.addStretch()
        self.import_btn = QPushButton("Import Files")
        self.import_btn.clicked.connect(self._on_import_files)
        url_header.addWidget(self.import_btn)
        layout.addLayout(url_header)

        self.url_input = QPlainTextEdit()
        self.url_input.setPlaceholderText(
            "One URL or file path per line\n"
            "Examples:\n"
            "  https://www.youtube.com/watch?v=...\n"
            "  https://stand.fm/episodes/...\n"
            "  /path/to/local/audio.mp3\n"
            "  /path/to/video.mp4"
        )
        self.url_input.setMaximumHeight(100)
        layout.addWidget(self.url_input)

        # Voice row (TTS engine + voice)
        voice_row = QHBoxLayout()
        voice_row.addWidget(QLabel("TTS:"))
        self.tts_engine_combo = QComboBox()
        self.tts_engine_combo.addItems(TTS_ENGINE_OPTIONS)
        self.tts_engine_combo.setToolTip(
            "Piper: offline and free, 45 languages. Voices download on first use.\n"
            "OpenAI: cloud, multilingual, uses the OpenAI key you already have.\n"
            "Azure: cloud, widest language coverage (100+ locales).\n"
            "Google: cloud, cheapest, with a free monthly allowance.\n"
            "ElevenLabs: cloud, highest quality and highest cost.\n\n"
            "Voice lists are filtered by the 'Translate to' language."
        )
        self.tts_engine_combo.currentTextChanged.connect(self._on_tts_engine_changed)
        voice_row.addWidget(self.tts_engine_combo)
        voice_row.addWidget(QLabel("Voice:"))
        self.voice_combo = QComboBox()
        self.voice_combo.setMaxVisibleItems(15)
        self.voice_combo.currentIndexChanged.connect(lambda _: self._update_voice_status())
        voice_row.addWidget(self.voice_combo, 1)

        self.refresh_voices_btn = QPushButton("Refresh")
        self.refresh_voices_btn.setObjectName("secondary_btn")
        self.refresh_voices_btn.setFixedWidth(80)
        self.refresh_voices_btn.setToolTip(
            "Reload the voice list from the selected cloud provider.")
        self.refresh_voices_btn.clicked.connect(self._start_voice_fetch)
        self.refresh_voices_btn.setVisible(False)
        voice_row.addWidget(self.refresh_voices_btn)
        layout.addLayout(voice_row)

        # Explains an empty voice list, a pending download, or per-hour cost.
        self.voice_status_label = QLabel()
        self.voice_status_label.setObjectName("hint_label")
        self.voice_status_label.setWordWrap(True)
        self.voice_status_label.setVisible(False)
        layout.addWidget(self.voice_status_label)

        # Speed row
        speed_row = QHBoxLayout()
        speed_row.addWidget(QLabel("Speed:"))
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setMinimum(25)
        self.speed_slider.setMaximum(300)
        self.speed_slider.setValue(100)
        self.speed_slider.setTickInterval(25)
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        speed_row.addWidget(self.speed_slider, 1)
        self.speed_label = QLabel("1.0x")
        self.speed_label.setMinimumWidth(40)
        speed_row.addWidget(self.speed_label)
        layout.addLayout(speed_row)

        # Browser cookies row
        cookie_row = QHBoxLayout()
        cookie_row.addWidget(QLabel("Cookies:"))
        self.cookie_combo = QComboBox()
        self.cookie_combo.addItems(["None", "Safari", "Chrome", "Firefox", "Brave", "Edge"])
        cookie_row.addWidget(self.cookie_combo, 1)
        layout.addLayout(cookie_row)

        # Source language row
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("Source:"))
        self.language_combo = QComboBox()
        self.language_combo.setMaxVisibleItems(12)
        self.language_combo.addItems(sorted(LANGUAGE_REGISTRY.keys()))
        self.language_combo.setToolTip("Language of the video (the language you are learning)")
        lang_row.addWidget(self.language_combo, 1)
        self.swap_langs_btn = QPushButton("⇄ Swap")
        self.swap_langs_btn.setObjectName("secondary_btn")
        self.swap_langs_btn.setFixedWidth(90)
        self.swap_langs_btn.setToolTip(
            "Swap the learning flow direction (source ↔ translate to).\n"
            "E.g. a Spanish speaker learning English: Source = English, Translate to = Spanish."
        )
        self.swap_langs_btn.clicked.connect(self._on_swap_languages)
        lang_row.addWidget(self.swap_langs_btn)
        layout.addLayout(lang_row)

        # Target (translation output) language row
        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("Translate to:"))
        self.target_language_combo = QComboBox()
        self.target_language_combo.setMaxVisibleItems(12)
        self.target_language_combo.addItems(sorted(LANGUAGE_REGISTRY.keys()))
        self.target_language_combo.setCurrentText(DEFAULT_TARGET_LANGUAGE)
        self.target_language_combo.setToolTip(
            "Language of the spoken translations (your native language).\n"
            "The voice list updates to match — Piper covers 27 of these\n"
            "offline; the cloud engines cover all of them."
        )
        self.target_language_combo.currentTextChanged.connect(
            self._on_target_language_changed)
        target_row.addWidget(self.target_language_combo, 1)
        layout.addLayout(target_row)

        # Resolution row
        res_row = QHBoxLayout()
        res_row.addWidget(QLabel("Resolution:"))
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(["Audio Only", "360p", "480p", "720p", "1080p", "1440p", "4K", "Best"])
        res_row.addWidget(self.resolution_combo, 1)
        layout.addLayout(res_row)

        # ── Outputs section ─────────────────────────────────────────────
        outputs_group = QGroupBox("Outputs")
        outputs_layout = QVBoxLayout(outputs_group)
        outputs_layout.setSpacing(8)

        # Configure row 1: Format, Mode, Groups
        config_row1 = QHBoxLayout()
        config_row1.addWidget(QLabel("Format:"))
        self.output_format_combo = QComboBox()
        self.output_format_combo.addItems(["MP3", "MP4", "M4B"])
        self.output_format_combo.setFixedWidth(70)
        config_row1.addWidget(self.output_format_combo)

        config_row1.addWidget(QLabel("Mode:"))
        self.output_mode_combo = QComboBox()
        self.output_mode_combo.addItems(["Sentence", "Summary"])
        self.output_mode_combo.setFixedWidth(100)
        self.output_mode_combo.currentTextChanged.connect(self._on_output_mode_changed)
        config_row1.addWidget(self.output_mode_combo)

        config_row1.addWidget(QLabel("Groups:"))
        self.output_group_spin = QSpinBox()
        self.output_group_spin.setMinimum(1)
        self.output_group_spin.setMaximum(99)
        self.output_group_spin.setValue(1)
        self.output_group_spin.setFixedWidth(60)
        self.output_group_spin.setToolTip(
            "Number of sentences to group together before switching languages.\n"
            "1 = default alternating pattern (EN, JP, EN, JP, ...)\n"
            "3 = three EN sentences, then three JP clips, then repeat"
        )
        config_row1.addWidget(self.output_group_spin)
        config_row1.addStretch()
        outputs_layout.addLayout(config_row1)

        # Configure row 2: Condensed checkbox, Add button
        config_row2 = QHBoxLayout()
        self.output_condensed_check = QCheckBox("Condensed")
        self.output_condensed_check.setToolTip("Remove long silences (≥2s) between subtitles")
        config_row2.addWidget(self.output_condensed_check)
        config_row2.addStretch()
        self.add_output_btn = QPushButton("+ Add")
        self.add_output_btn.setFixedWidth(80)
        self.add_output_btn.clicked.connect(self._on_add_output)
        config_row2.addWidget(self.add_output_btn)
        outputs_layout.addLayout(config_row2)

        # Output list
        self.output_list = QListWidget()
        self.output_list.setMaximumHeight(120)
        outputs_layout.addWidget(self.output_list)

        # Anki checkboxes (separate from output configs)
        self.anki_checkbox = QCheckBox("Create Anki Deck")
        outputs_layout.addWidget(self.anki_checkbox)

        self.anki_only_checkbox = QCheckBox("Anki Only (skip interleaved audio)")
        self.anki_only_checkbox.toggled.connect(self._on_anki_only_toggled)
        outputs_layout.addWidget(self.anki_only_checkbox)

        self.keep_original_audio_checkbox = QCheckBox("Keep Original Audio")
        self.keep_original_audio_checkbox.setToolTip("Save a copy of the original audio (MP3) in the output folder")
        self.keep_original_audio_checkbox.setChecked(True)
        outputs_layout.addWidget(self.keep_original_audio_checkbox)

        self.keep_original_video_checkbox = QCheckBox("Keep Original Video")
        self.keep_original_video_checkbox.setToolTip("Save a copy of the original video (MP4) in the output folder")
        outputs_layout.addWidget(self.keep_original_video_checkbox)

        layout.addWidget(outputs_group)

        # Transcription fallback checkbox
        self.transcription_checkbox = QCheckBox("Use Transcription Fallback (when no subtitles)")
        layout.addWidget(self.transcription_checkbox)

        # Force transcription checkbox
        self.force_transcription_checkbox = QCheckBox("Force Transcription (ignore subtitles, always transcribe)")
        layout.addWidget(self.force_transcription_checkbox)

        # Transcription engine row
        engine_row = QHBoxLayout()
        engine_row.addWidget(QLabel("Transcription:"))
        self.transcription_engine_combo = QComboBox()
        self.transcription_engine_combo.addItems(TRANSCRIPTION_ENGINE_OPTIONS)
        engine_row.addWidget(self.transcription_engine_combo, 1)
        layout.addLayout(engine_row)

        # Comprehensibility analysis checkbox and file picker
        self.comprehensibility_checkbox = QCheckBox("Comprehensibility Analysis (requires lemma list)")
        self.comprehensibility_checkbox.setToolTip(
            "Analyze video comprehensibility based on your known vocabulary.\n"
            "Identifies i+1 sentences (exactly 1 unknown word) for optimal learning."
        )
        self.comprehensibility_checkbox.toggled.connect(self._on_comprehensibility_toggled)
        layout.addWidget(self.comprehensibility_checkbox)

        self.lemma_row = QHBoxLayout()
        self.lemma_path_label = QLabel("No file selected")
        self.lemma_path_label.setStyleSheet(f"color: {get_theme().text_muted}; font-size: 12px;")
        self.lemma_row.addWidget(self.lemma_path_label, 1)
        self.lemma_browse_btn = QPushButton("Browse...")
        self.lemma_browse_btn.setObjectName("secondary_btn")
        self.lemma_browse_btn.setFixedWidth(120)
        self.lemma_browse_btn.clicked.connect(self._on_browse_lemma_list)
        self.lemma_row.addWidget(self.lemma_browse_btn)
        layout.addLayout(self.lemma_row)

        self.unlisted_row = QHBoxLayout()
        self.unlisted_label = QLabel("Known words not in list:")
        self.unlisted_spin = QSpinBox()
        self.unlisted_spin.setRange(0, 75)
        self.unlisted_spin.setSingleStep(5)
        self.unlisted_spin.setSuffix("%")
        self.unlisted_spin.setValue(0)
        self.unlisted_spin.setToolTip(
            "Estimate what % of all the words you know are NOT represented\n"
            "in your lemma list (learned from immersion, classes, etc.)"
        )
        self.unlisted_row.addWidget(self.unlisted_label)
        self.unlisted_row.addWidget(self.unlisted_spin)
        self.unlisted_row.addStretch()
        layout.addLayout(self.unlisted_row)

        self.check_first_checkbox = QCheckBox("Check first")
        self.check_first_checkbox.setToolTip(
            "Pause after comprehensibility analysis to review the score.\n"
            "Choose Continue or Skip for each video."
        )
        layout.addWidget(self.check_first_checkbox)

        # Hide lemma rows initially
        self.lemma_path_label.setVisible(False)
        self.lemma_browse_btn.setVisible(False)
        self.unlisted_label.setVisible(False)
        self.unlisted_spin.setVisible(False)
        self.check_first_checkbox.setVisible(False)

        # Output directory row
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output:"))
        self.output_label = QLabel(str(OUTPUT_DIR))
        self.output_label.setStyleSheet(f"color: {get_theme().text_muted};")
        out_row.addWidget(self.output_label, 1)
        change_btn = QPushButton("Change...")
        change_btn.setObjectName("secondary_btn")
        change_btn.setFixedWidth(120)
        change_btn.clicked.connect(self._change_output_dir)
        out_row.addWidget(change_btn)
        layout.addLayout(out_row)

        # Clear Cache button
        cache_row = QHBoxLayout()
        cache_row.addStretch()
        self.cache_btn = QPushButton("Clear Cache")
        self.cache_btn.setObjectName("secondary_btn")
        self.cache_btn.setFixedWidth(180)
        self.cache_btn.clicked.connect(self._on_clear_cache)
        cache_row.addWidget(self.cache_btn)
        layout.addLayout(cache_row)

        # Auto-clear cache setting
        auto_clear_row = QHBoxLayout()
        self.auto_clear_checkbox = QCheckBox("Auto-clear cache above")
        auto_clear_row.addWidget(self.auto_clear_checkbox)
        self.cache_threshold_spin = QSpinBox()
        self.cache_threshold_spin.setRange(1, 100)
        self.cache_threshold_spin.setValue(10)
        self.cache_threshold_spin.setSuffix(" GB")
        self.cache_threshold_spin.setFixedWidth(90)
        self.cache_threshold_spin.setEnabled(False)
        auto_clear_row.addWidget(self.cache_threshold_spin)
        auto_clear_row.addStretch()
        self.auto_clear_checkbox.toggled.connect(self.cache_threshold_spin.setEnabled)
        layout.addLayout(auto_clear_row)

        # Status group
        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout(status_group)

        self.status_label = QLabel("Ready")
        self.status_label.setWordWrap(True)
        status_layout.addWidget(self.status_label)

        self.batch_label = QLabel("")
        self.batch_label.setStyleSheet(f"color: {get_theme().accent}; font-size: 12px; font-weight: bold;")
        status_layout.addWidget(self.batch_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        status_layout.addWidget(self.progress_bar)

        self.detail_label = QLabel("")
        self.detail_label.setStyleSheet(f"color: {get_theme().text_muted}; font-size: 12px;")
        self.detail_label.setWordWrap(True)
        status_layout.addWidget(self.detail_label)

        layout.addWidget(status_group)

        # Process button
        self.process_btn = QPushButton("Process")
        self.process_btn.clicked.connect(self._on_process)
        layout.addWidget(self.process_btn)

        layout.addStretch()

        scroll_area.setWidget(process_widget)
        self.tabs.addTab(scroll_area, "Process")

    def _build_settings_tab(self):
        """Build the Settings tab with collapsible sections."""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)

        settings_widget = QWidget()
        layout = QVBoxLayout(settings_widget)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # ── Appearance section ───────────────────────────────────────────
        appearance_section = CollapsibleSection("Appearance")

        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Theme:"))
        self.theme_combo = QComboBox()
        for theme_name in THEMES:
            self.theme_combo.addItem(theme_name.capitalize(), theme_name)
        self.theme_combo.setCurrentText(_themes_module.ACTIVE_THEME.capitalize())
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        theme_row.addWidget(self.theme_combo, 1)
        appearance_section.addLayout(theme_row)

        layout.addWidget(appearance_section)

        # ── API Keys section ─────────────────────────────────────────────
        keys_section = CollapsibleSection("API Keys")

        # OpenAI
        openai_group = QGroupBox("OpenAI")
        openai_layout = QVBoxLayout(openai_group)

        self.openai_info_label = QLabel()
        self.openai_info_label.setOpenExternalLinks(True)
        self.openai_info_label.setWordWrap(True)
        openai_layout.addWidget(self.openai_info_label)

        openai_key_row = QHBoxLayout()
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.Password)
        self.key_input.setPlaceholderText("sk-...")
        self.key_input.textChanged.connect(self._on_openai_key_changed)
        openai_key_row.addWidget(self.key_input, 1)

        self.show_key_btn = QPushButton("Show")
        self.show_key_btn.setObjectName("secondary_btn")
        self.show_key_btn.setFixedWidth(80)
        self.show_key_btn.clicked.connect(self._toggle_key_visibility)
        openai_key_row.addWidget(self.show_key_btn)

        openai_layout.addLayout(openai_key_row)

        openai_tts_row = QHBoxLayout()
        openai_tts_row.addWidget(QLabel("TTS model:"))
        self.openai_tts_model_combo = QComboBox()
        self.openai_tts_model_combo.addItems(OPENAI_TTS_MODELS)
        self.openai_tts_model_combo.setToolTip(
            "Model used when OpenAI is the TTS engine. gpt-4o-mini-tts is the "
            "newest and most expressive; tts-1 is cheapest.")
        self.openai_tts_model_combo.currentTextChanged.connect(set_openai_tts_model)
        openai_tts_row.addWidget(self.openai_tts_model_combo, 1)
        openai_layout.addLayout(openai_tts_row)
        keys_section.addWidget(openai_group)

        # ElevenLabs
        elevenlabs_group = QGroupBox("ElevenLabs")
        elevenlabs_layout = QVBoxLayout(elevenlabs_group)

        self.elevenlabs_info_label = QLabel()
        self.elevenlabs_info_label.setOpenExternalLinks(True)
        self.elevenlabs_info_label.setWordWrap(True)
        elevenlabs_layout.addWidget(self.elevenlabs_info_label)

        elevenlabs_key_row = QHBoxLayout()
        self.elevenlabs_key_input = QLineEdit()
        self.elevenlabs_key_input.setEchoMode(QLineEdit.Password)
        self.elevenlabs_key_input.setPlaceholderText("xi_...")
        self.elevenlabs_key_input.textChanged.connect(self._on_elevenlabs_key_changed)
        elevenlabs_key_row.addWidget(self.elevenlabs_key_input, 1)

        self.show_elevenlabs_key_btn = QPushButton("Show")
        self.show_elevenlabs_key_btn.setObjectName("secondary_btn")
        self.show_elevenlabs_key_btn.setFixedWidth(80)
        self.show_elevenlabs_key_btn.clicked.connect(self._toggle_elevenlabs_key_visibility)
        elevenlabs_key_row.addWidget(self.show_elevenlabs_key_btn)

        elevenlabs_layout.addLayout(elevenlabs_key_row)

        elevenlabs_model_row = QHBoxLayout()
        elevenlabs_model_row.addWidget(QLabel("TTS model:"))
        self.elevenlabs_model_combo = QComboBox()
        self.elevenlabs_model_combo.addItems(ELEVENLABS_TTS_MODEL_OPTIONS)
        self.elevenlabs_model_combo.setToolTip(
            "eleven_flash_v2_5: 32 languages, ~half the credit cost (recommended).\n"
            "eleven_turbo_v2_5: low latency, similar coverage.\n"
            "eleven_multilingual_v2: highest quality, 29 languages, full cost.")
        self.elevenlabs_model_combo.currentTextChanged.connect(set_elevenlabs_tts_model)
        elevenlabs_model_row.addWidget(self.elevenlabs_model_combo, 1)
        elevenlabs_layout.addLayout(elevenlabs_model_row)
        keys_section.addWidget(elevenlabs_group)

        # Soniox
        soniox_group = QGroupBox("Soniox")
        soniox_layout = QVBoxLayout(soniox_group)

        self.soniox_info_label = QLabel()
        self.soniox_info_label.setOpenExternalLinks(True)
        self.soniox_info_label.setWordWrap(True)
        soniox_layout.addWidget(self.soniox_info_label)

        soniox_key_row = QHBoxLayout()
        self.soniox_key_input = QLineEdit()
        self.soniox_key_input.setEchoMode(QLineEdit.Password)
        self.soniox_key_input.setPlaceholderText("Soniox API key")
        self.soniox_key_input.textChanged.connect(self._on_soniox_key_changed)
        soniox_key_row.addWidget(self.soniox_key_input, 1)

        self.show_soniox_key_btn = QPushButton("Show")
        self.show_soniox_key_btn.setObjectName("secondary_btn")
        self.show_soniox_key_btn.setFixedWidth(80)
        self.show_soniox_key_btn.clicked.connect(self._toggle_soniox_key_visibility)
        soniox_key_row.addWidget(self.show_soniox_key_btn)

        soniox_layout.addLayout(soniox_key_row)
        keys_section.addWidget(soniox_group)

        # Azure Speech (TTS)
        azure_group = QGroupBox("Azure Speech (TTS)")
        azure_layout = QVBoxLayout(azure_group)

        azure_info = QLabel(
            'Widest language coverage (100+ locales). '
            '<a href="https://portal.azure.com/#create/Microsoft.CognitiveServicesSpeechServices">'
            'Create a Speech resource</a> and paste its key and region.')
        azure_info.setOpenExternalLinks(True)
        azure_info.setWordWrap(True)
        azure_layout.addWidget(azure_info)

        azure_key_row = QHBoxLayout()
        self.azure_key_input = QLineEdit()
        self.azure_key_input.setEchoMode(QLineEdit.Password)
        self.azure_key_input.setPlaceholderText("Azure Speech key")
        self.azure_key_input.textChanged.connect(self._on_azure_key_changed)
        azure_key_row.addWidget(self.azure_key_input, 1)

        self.show_azure_key_btn = QPushButton("Show")
        self.show_azure_key_btn.setObjectName("secondary_btn")
        self.show_azure_key_btn.setFixedWidth(80)
        self.show_azure_key_btn.clicked.connect(self._toggle_azure_key_visibility)
        azure_key_row.addWidget(self.show_azure_key_btn)
        azure_layout.addLayout(azure_key_row)

        azure_region_row = QHBoxLayout()
        azure_region_row.addWidget(QLabel("Region:"))
        self.azure_region_combo = QComboBox()
        self.azure_region_combo.setEditable(True)
        self.azure_region_combo.addItems(AZURE_REGIONS)
        self.azure_region_combo.currentTextChanged.connect(self._on_azure_region_changed)
        azure_region_row.addWidget(self.azure_region_combo, 1)
        azure_layout.addLayout(azure_region_row)
        keys_section.addWidget(azure_group)

        # Google Cloud (TTS)
        google_group = QGroupBox("Google Cloud (TTS)")
        google_layout = QVBoxLayout(google_group)

        google_info = QLabel(
            'Cheapest cloud TTS, with a free monthly allowance. Enable the '
            '<a href="https://console.cloud.google.com/apis/library/texttospeech.googleapis.com">'
            'Text-to-Speech API</a> and create an API key.')
        google_info.setOpenExternalLinks(True)
        google_info.setWordWrap(True)
        google_layout.addWidget(google_info)

        google_key_row = QHBoxLayout()
        self.google_key_input = QLineEdit()
        self.google_key_input.setEchoMode(QLineEdit.Password)
        self.google_key_input.setPlaceholderText("Google Cloud API key")
        self.google_key_input.textChanged.connect(self._on_google_key_changed)
        google_key_row.addWidget(self.google_key_input, 1)

        self.show_google_key_btn = QPushButton("Show")
        self.show_google_key_btn.setObjectName("secondary_btn")
        self.show_google_key_btn.setFixedWidth(80)
        self.show_google_key_btn.clicked.connect(self._toggle_google_key_visibility)
        google_key_row.addWidget(self.show_google_key_btn)
        google_layout.addLayout(google_key_row)
        keys_section.addWidget(google_group)

        # Anthropic
        anthropic_group = QGroupBox("Anthropic")
        anthropic_layout = QVBoxLayout(anthropic_group)

        self.anthropic_info_label = QLabel()
        self.anthropic_info_label.setOpenExternalLinks(True)
        self.anthropic_info_label.setWordWrap(True)
        anthropic_layout.addWidget(self.anthropic_info_label)

        anthropic_key_row = QHBoxLayout()
        self.anthropic_key_input = QLineEdit()
        self.anthropic_key_input.setEchoMode(QLineEdit.Password)
        self.anthropic_key_input.setPlaceholderText("sk-ant-...")
        self.anthropic_key_input.textChanged.connect(self._on_anthropic_key_changed)
        anthropic_key_row.addWidget(self.anthropic_key_input, 1)

        self.show_anthropic_key_btn = QPushButton("Show")
        self.show_anthropic_key_btn.setObjectName("secondary_btn")
        self.show_anthropic_key_btn.setFixedWidth(80)
        self.show_anthropic_key_btn.clicked.connect(self._toggle_anthropic_key_visibility)
        anthropic_key_row.addWidget(self.show_anthropic_key_btn)

        anthropic_layout.addLayout(anthropic_key_row)
        keys_section.addWidget(anthropic_group)

        layout.addWidget(keys_section)

        # ── AI Prompts section ───────────────────────────────────────────
        prompts_section = CollapsibleSection("AI Prompts", expanded=False)

        self.settings_instructions_label = QLabel(
            "Customize translation and punctuation prompts. "
            "Changes are saved automatically. Use the Source language selector on the Process tab "
            "to choose which language to customize.\n\n"
            "Tip: Use {LANGUAGE} in your prompts as a placeholder for the source language name "
            "(e.g., 'Japanese') and {TARGET_LANGUAGE} for the translation output language "
            "(e.g., 'English', 'Spanish')."
        )
        self.settings_instructions_label.setWordWrap(True)
        prompts_section.addWidget(self.settings_instructions_label)

        self.current_language_label = QLabel("")
        prompts_section.addWidget(self.current_language_label)

        # Model list refresh (queries OpenAI/Anthropic for current models)
        refresh_models_row = QHBoxLayout()
        self.model_list_status_label = QLabel("")
        refresh_models_row.addWidget(self.model_list_status_label, 1)
        self.refresh_models_btn = QPushButton("Refresh Model List")
        self.refresh_models_btn.setObjectName("secondary_btn")
        self.refresh_models_btn.setFixedWidth(180)
        self.refresh_models_btn.setToolTip(
            "Query OpenAI and Anthropic for the current list of available models"
        )
        self.refresh_models_btn.clicked.connect(lambda: self._start_model_fetch(silent=False))
        refresh_models_row.addWidget(self.refresh_models_btn)
        prompts_section.addLayout(refresh_models_row)

        # Translation Prompt
        translation_group = QGroupBox("Translation Prompt")
        translation_layout = QVBoxLayout(translation_group)

        model_options = get_ai_model_options()

        trans_model_row = QHBoxLayout()
        trans_model_row.addWidget(QLabel("AI Model:"))
        self.translation_model_combo = QComboBox()
        self.translation_model_combo.addItems(model_options)
        self._disable_separator_items(self.translation_model_combo)
        self.translation_model_combo.currentTextChanged.connect(self._on_translation_model_changed)
        trans_model_row.addWidget(self.translation_model_combo, 1)
        translation_layout.addLayout(trans_model_row)

        trans_header = QHBoxLayout()
        self.trans_info_label = QLabel("Guides how the AI translates sentences to English (use {LANGUAGE} for dynamic language name)")
        trans_header.addWidget(self.trans_info_label, 1)
        self.translation_reset_btn = QPushButton("Reset to Default")
        self.translation_reset_btn.setObjectName("reset_inactive")
        self.translation_reset_btn.clicked.connect(self._on_reset_translation_prompt)
        trans_header.addWidget(self.translation_reset_btn)
        translation_layout.addLayout(trans_header)

        self.translation_prompt_edit = QTextEdit()
        self.translation_prompt_edit.textChanged.connect(self._on_translation_prompt_changed)
        translation_layout.addWidget(self.translation_prompt_edit)

        prompts_section.addWidget(translation_group)

        # Punctuation Prompt
        punctuation_group = QGroupBox("Punctuation Prompt")
        punctuation_layout = QVBoxLayout(punctuation_group)

        punct_model_row = QHBoxLayout()
        punct_model_row.addWidget(QLabel("AI Model:"))
        self.punctuation_model_combo = QComboBox()
        self.punctuation_model_combo.addItems(model_options)
        self._disable_separator_items(self.punctuation_model_combo)
        self.punctuation_model_combo.currentTextChanged.connect(self._on_punctuation_model_changed)
        punct_model_row.addWidget(self.punctuation_model_combo, 1)
        punctuation_layout.addLayout(punct_model_row)

        punct_header = QHBoxLayout()
        self.punct_info_label = QLabel("Guides how the AI inserts sentence-ending punctuation (use {LANGUAGE} for dynamic language name)")
        punct_header.addWidget(self.punct_info_label, 1)
        self.punctuation_reset_btn = QPushButton("Reset to Default")
        self.punctuation_reset_btn.setObjectName("reset_inactive")
        self.punctuation_reset_btn.clicked.connect(self._on_reset_punctuation_prompt)
        punct_header.addWidget(self.punctuation_reset_btn)
        punctuation_layout.addLayout(punct_header)

        self.punctuation_prompt_edit = QTextEdit()
        self.punctuation_prompt_edit.textChanged.connect(self._on_punctuation_prompt_changed)
        punctuation_layout.addWidget(self.punctuation_prompt_edit)

        prompts_section.addWidget(punctuation_group)

        # Summary Prompt
        summary_group = QGroupBox("Summary Prompt")
        summary_layout = QVBoxLayout(summary_group)

        sum_model_row = QHBoxLayout()
        sum_model_row.addWidget(QLabel("AI Model:"))
        self.summary_model_combo = QComboBox()
        self.summary_model_combo.addItems(model_options)
        self._disable_separator_items(self.summary_model_combo)
        self.summary_model_combo.currentTextChanged.connect(self._on_summary_model_changed)
        sum_model_row.addWidget(self.summary_model_combo, 1)
        summary_layout.addLayout(sum_model_row)

        sum_header = QHBoxLayout()
        self.sum_info_label = QLabel("Guides how the AI groups and summarizes sentence chunks (use {LANGUAGE} for dynamic language name)")
        sum_header.addWidget(self.sum_info_label, 1)
        self.summary_reset_btn = QPushButton("Reset to Default")
        self.summary_reset_btn.setObjectName("reset_inactive")
        self.summary_reset_btn.clicked.connect(self._on_reset_summary_prompt)
        sum_header.addWidget(self.summary_reset_btn)
        summary_layout.addLayout(sum_header)

        self.summary_prompt_edit = QTextEdit()
        self.summary_prompt_edit.textChanged.connect(self._on_summary_prompt_changed)
        summary_layout.addWidget(self.summary_prompt_edit)

        prompts_section.addWidget(summary_group)

        layout.addWidget(prompts_section)

        layout.addStretch()

        # Utility buttons
        utility_row = QHBoxLayout()
        self.ytdlp_version_label = QLabel("yt-dlp: ...")
        self.ytdlp_version_label.setObjectName("ytdlp_version_label")
        utility_row.addWidget(self.ytdlp_version_label)
        utility_row.addStretch()
        self.update_btn = QPushButton("Check for Updates")
        self.update_btn.setObjectName("secondary_btn")
        self.update_btn.setFixedWidth(180)
        self.update_btn.clicked.connect(self._on_check_updates)
        utility_row.addWidget(self.update_btn)
        layout.addLayout(utility_row)

        scroll_area.setWidget(settings_widget)
        self.tabs.addTab(scroll_area, "Settings")

        # Connect Process tab language selector to update Settings tab
        self.language_combo.currentTextChanged.connect(self._on_language_changed_in_settings)

        # Load initial prompts for default language
        self._on_language_changed_in_settings()

    def _apply_inline_styles(self):
        """Refresh all inline-styled widgets to match the current theme."""
        t = get_theme()
        self.output_label.setStyleSheet(f"color: {t.text_muted};")
        self.batch_label.setStyleSheet(f"color: {t.accent}; font-size: 12px; font-weight: bold;")
        self.detail_label.setStyleSheet(f"color: {t.text_muted}; font-size: 12px;")
        self.settings_instructions_label.setStyleSheet(f"color: {t.text_muted}; font-size: 12px; padding: 8px 0px;")
        self.current_language_label.setStyleSheet(f"color: {t.accent}; font-size: 13px; font-weight: bold; padding: 4px 0px;")
        self.trans_info_label.setStyleSheet(f"color: {t.text_muted}; font-size: 11px;")
        self.punct_info_label.setStyleSheet(f"color: {t.text_muted}; font-size: 11px;")
        self.sum_info_label.setStyleSheet(f"color: {t.text_muted}; font-size: 11px;")
        self.ytdlp_version_label.setStyleSheet(f"color: {t.text_muted}; font-size: 11px;")
        self.lemma_path_label.setStyleSheet(f"color: {t.text_muted}; font-size: 12px;")
        self.openai_info_label.setText(
            "Required for translation and punctuation. "
            f"Get your API key at <a href='https://platform.openai.com/api-keys' style='color: {t.link};'>platform.openai.com/api-keys</a>"
        )
        self.openai_info_label.setStyleSheet(f"color: {t.text_muted}; font-size: 11px; padding: 4px 0px;")
        self.elevenlabs_info_label.setText(
            "Used for transcription fallback and for cloud TTS voices (e.g. Spanish output voices). "
            f"Get your API key at <a href='https://elevenlabs.io/app/settings/api-keys' style='color: {t.link};'>elevenlabs.io/app/settings/api-keys</a>"
        )
        self.elevenlabs_info_label.setStyleSheet(f"color: {t.text_muted}; font-size: 11px; padding: 4px 0px;")
        self.soniox_info_label.setText(
            "Alternative transcription engine (60+ languages, incl. English and Spanish). "
            f"Get your API key at <a href='https://console.soniox.com' style='color: {t.link};'>console.soniox.com</a>"
        )
        self.soniox_info_label.setStyleSheet(f"color: {t.text_muted}; font-size: 11px; padding: 4px 0px;")
        self.model_list_status_label.setStyleSheet(f"color: {t.text_muted}; font-size: 11px;")

    def _on_theme_changed(self):
        theme_name = self.theme_combo.currentData()
        _themes_module.ACTIVE_THEME = theme_name
        QApplication.instance().setStyleSheet(generate_stylesheet())
        self._apply_inline_styles()
        self._save_settings()

    def _load_settings(self):
        config = load_config()
        self.key_input.setText(get_api_key())
        self.elevenlabs_key_input.setText(get_elevenlabs_api_key())
        self.anthropic_key_input.setText(get_anthropic_api_key())
        self.soniox_key_input.setText(get_soniox_api_key())

        # New TTS engines: keys, region, and per-engine model selections. Block
        # signals so setting text does not trigger a voice-fetch mid-load.
        for widget, value in (
            (self.azure_key_input, get_azure_api_key()),
            (self.google_key_input, get_google_api_key()),
        ):
            widget.blockSignals(True)
            widget.setText(value)
            widget.blockSignals(False)
        self.azure_region_combo.blockSignals(True)
        self.azure_region_combo.setCurrentText(get_azure_region())
        self.azure_region_combo.blockSignals(False)
        self.openai_tts_model_combo.blockSignals(True)
        self.openai_tts_model_combo.setCurrentText(get_openai_tts_model())
        self.openai_tts_model_combo.blockSignals(False)
        self.elevenlabs_model_combo.blockSignals(True)
        self.elevenlabs_model_combo.setCurrentText(get_elevenlabs_tts_model())
        self.elevenlabs_model_combo.blockSignals(False)

        output = config.get("output_dir", str(OUTPUT_DIR))
        self.output_label.setText(output)

        # Restore the target language before populating voices, since Piper,
        # Azure and Google voice lists are filtered by it.
        target_lang = get_target_language()
        idx = self.target_language_combo.findText(target_lang)
        if idx >= 0:
            self.target_language_combo.setCurrentIndex(idx)

        tts_engine = get_tts_engine()
        idx = self.tts_engine_combo.findText(tts_engine)
        if idx >= 0:
            self.tts_engine_combo.setCurrentIndex(idx)
        self.refresh_voices_btn.setVisible(
            tts_engine in ("Azure (Cloud)", "Google (Cloud)", "ElevenLabs (Cloud)"))
        self._populate_voice_combo()
        if tts_engine in ("Azure (Cloud)", "Google (Cloud)", "ElevenLabs (Cloud)"):
            self._start_voice_fetch()

        speed = config.get("speed", 100)
        self.speed_slider.setValue(speed)
        self._on_speed_changed(speed)

        cookie = config.get("cookie_browser", "None")
        idx = self.cookie_combo.findText(cookie)
        if idx >= 0:
            self.cookie_combo.setCurrentIndex(idx)

        self.anki_checkbox.setChecked(config.get("create_anki", False))
        self.anki_only_checkbox.setChecked(config.get("anki_only", False))
        self.keep_original_audio_checkbox.setChecked(config.get("keep_original_audio", True))
        self.keep_original_video_checkbox.setChecked(config.get("keep_original_video", False))
        self.transcription_checkbox.setChecked(config.get("use_transcription", False))
        self.force_transcription_checkbox.setChecked(config.get("force_transcription", False))
        self.auto_clear_checkbox.setChecked(config.get("auto_clear_cache", False))
        self.cache_threshold_spin.setValue(config.get("cache_threshold_gb", 10))

        # Load output configs (with backward migration from old keys)
        oc_dicts = migrate_output_configs(config)
        self.output_list.clear()
        for oc_dict in oc_dicts:
            self._add_output_item(OutputConfig.from_dict(oc_dict))

        self.comprehensibility_checkbox.setChecked(config.get("enable_comprehensibility", False))
        self.check_first_checkbox.setChecked(config.get("check_first", False))
        self.unlisted_spin.setValue(config.get("unlisted_knowledge", 0))
        lemma_path = get_lemma_list_path()
        if lemma_path:
            self.lemma_path_label.setText(lemma_path)

        engine = config.get("transcription_engine", DEFAULT_TRANSCRIPTION_ENGINE)
        idx = self.transcription_engine_combo.findText(engine)
        if idx >= 0:
            self.transcription_engine_combo.setCurrentIndex(idx)

        source_lang = config.get("source_language", "Japanese")
        idx = self.language_combo.findText(source_lang)
        if idx >= 0:
            self.language_combo.setCurrentIndex(idx)

        resolution = config.get("resolution", "Audio Only")
        idx = self.resolution_combo.findText(resolution)
        if idx >= 0:
            self.resolution_combo.setCurrentIndex(idx)

        # Load AI model selections
        trans_model = get_translation_model()
        idx = self.translation_model_combo.findText(trans_model)
        if idx >= 0:
            self.translation_model_combo.setCurrentIndex(idx)

        punct_model = get_punctuation_model()
        idx = self.punctuation_model_combo.findText(punct_model)
        if idx >= 0:
            self.punctuation_model_combo.setCurrentIndex(idx)

        sum_model = get_summary_model()
        idx = self.summary_model_combo.findText(sum_model)
        if idx >= 0:
            self.summary_model_combo.setCurrentIndex(idx)

        theme = config.get("theme", _themes_module.ACTIVE_THEME)
        if theme in THEMES:
            _themes_module.ACTIVE_THEME = theme
            idx = self.theme_combo.findData(theme)
            if idx >= 0:
                self.theme_combo.blockSignals(True)
                self.theme_combo.setCurrentIndex(idx)
                self.theme_combo.blockSignals(False)
            QApplication.instance().setStyleSheet(generate_stylesheet())
            self._apply_inline_styles()

    def _save_settings(self):
        # Encrypt API keys via dedicated setters (writes to config file)
        set_api_key(self.key_input.text().strip())
        set_elevenlabs_api_key(self.elevenlabs_key_input.text().strip())
        set_soniox_api_key(self.soniox_key_input.text().strip())
        set_azure_api_key(self.azure_key_input.text().strip())
        set_azure_region(self.azure_region_combo.currentText().strip())
        set_google_api_key(self.google_key_input.text().strip())
        # Persist the voice selection via each engine's own setter.
        engine = self.tts_engine_combo.currentText()
        voice_data = self.voice_combo.currentData()
        if voice_data:
            if engine == "ElevenLabs (Cloud)":
                set_elevenlabs_voice(self.voice_combo.currentText(), voice_data)
            elif engine == "OpenAI (Cloud)":
                set_openai_tts_voice(voice_data)
            elif engine == "Azure (Cloud)":
                set_azure_voice(voice_data)
            elif engine == "Google (Cloud)":
                set_google_voice(voice_data)
            elif engine == "Piper (Offline)":
                set_piper_voice(voice_data)
        # Reload config to pick up the encrypted key fields
        config = load_config()
        config["output_dir"] = self.output_label.text()
        config["tts_engine"] = engine
        config["speed"] = self.speed_slider.value()
        config["cookie_browser"] = self.cookie_combo.currentText()
        config["create_anki"] = self.anki_checkbox.isChecked()
        config["anki_only"] = self.anki_only_checkbox.isChecked()
        config["keep_original_audio"] = self.keep_original_audio_checkbox.isChecked()
        config["keep_original_video"] = self.keep_original_video_checkbox.isChecked()
        config["use_transcription"] = self.transcription_checkbox.isChecked()
        config["force_transcription"] = self.force_transcription_checkbox.isChecked()
        config["auto_clear_cache"] = self.auto_clear_checkbox.isChecked()
        config["cache_threshold_gb"] = self.cache_threshold_spin.value()
        config["output_configs"] = [oc.to_dict() for oc in self._get_output_configs()]
        # Remove legacy keys that have been migrated to output_configs
        for legacy_key in ("video_output", "summary_mode", "condense_audio", "sentences_per_group"):
            config.pop(legacy_key, None)
        config["enable_comprehensibility"] = self.comprehensibility_checkbox.isChecked()
        config["check_first"] = self.check_first_checkbox.isChecked()
        config["unlisted_knowledge"] = self.unlisted_spin.value()
        config["lemma_list_path"] = self.lemma_path_label.text() if self.lemma_path_label.text() != "No file selected" else ""
        config["transcription_engine"] = self.transcription_engine_combo.currentText()
        config["source_language"] = self.language_combo.currentText()
        config["target_language"] = self.target_language_combo.currentText()
        config["resolution"] = self.resolution_combo.currentText()
        config["theme"] = self.theme_combo.currentData()
        save_config(config)

    def _refresh_ytdlp_version_label(self):
        """Update the yt-dlp version label in the Settings tab."""
        from ..core.updater import _get_current_ytdlp_version
        version = _get_current_ytdlp_version()
        self.ytdlp_version_label.setText(f"yt-dlp: {version}")

    def _startup_checks(self):
        self._refresh_ytdlp_version_label()
        missing = [name for name in ("ffmpeg", "yt-dlp") if not check_tool(name)]
        if missing:
            names = ", ".join(missing)
            QMessageBox.critical(
                self,
                "Required tools not found",
                f"The following required tools were not found:\n\n"
                f"  {names}\n\n"
                "Run scripts/fetch_binaries.py to download bundled copies,\n"
                "or install them on your system PATH.",
            )

        # Check voices directory
        if not VOICES_DIR.exists() or not any(VOICES_DIR.glob("*.onnx")):
            QMessageBox.warning(
                self,
                "Voice models missing",
                f"No voice models found in:\n{VOICES_DIR}\n\n"
                "Copy .onnx and .onnx.json files to this directory.",
            )

    def _on_speed_changed(self, value):
        speed = value / 100.0
        self.speed_label.setText(f"{speed:.1f}x" if speed != int(speed) else f"{speed:.1f}x")

    def _populate_voice_combo(self):
        """Fill the voice combo for the currently selected TTS engine."""
        engine = self.tts_engine_combo.currentText()
        self.voice_combo.blockSignals(True)
        self.voice_combo.clear()

        if engine == "Piper (Offline)":
            self._populate_piper_voices()
        elif engine == "OpenAI (Cloud)":
            # OpenAI voices are multilingual — no per-language filtering.
            for name in OPENAI_TTS_VOICES:
                self.voice_combo.addItem(name.title(), name)
            self._select_voice_data(get_openai_tts_voice())
        elif engine == "Azure (Cloud)":
            self._populate_locale_voices(get_cached_azure_voices(), get_azure_voice())
        elif engine == "Google (Cloud)":
            self._populate_locale_voices(get_cached_google_voices(), get_google_voice())
        elif engine == "ElevenLabs (Cloud)":
            selected = get_elevenlabs_voice()
            for voice in get_cached_elevenlabs_voices():
                self.voice_combo.addItem(voice["name"], voice["voice_id"])
            idx = self.voice_combo.findData(selected.get("voice_id"))
            if idx < 0 and selected.get("voice_id"):
                self.voice_combo.addItem(selected["name"], selected["voice_id"])
                idx = self.voice_combo.count() - 1
            if idx >= 0:
                self.voice_combo.setCurrentIndex(idx)

        self.voice_combo.blockSignals(False)
        self._update_voice_status()

    def _target_language_code(self):
        """Language code the TTS engine will speak (the translation target)."""
        try:
            return get_language_config(self.target_language_combo.currentText())["code"]
        except (ValueError, AttributeError):
            return "en"

    def _populate_piper_voices(self):
        """List downloadable Piper voices for the current target language."""
        voices = voice_manager.voices_for_language(self._target_language_code())
        for voice in voices:
            label = voice_manager.display_name(voice)
            if not voice_manager.is_downloaded(voice):
                label += f" — {voice_manager.voice_size_mb(voice):.0f} MB download"
            self.voice_combo.addItem(label, voice["key"])
        self._select_voice_data(get_piper_voice())

    def _populate_locale_voices(self, cached, selected_id):
        """List cloud voices whose locale matches the target language.

        Azure and Google both expose hundreds of voices across every locale, so
        showing the full list would bury the handful that can actually speak the
        user's language.
        """
        code = self._target_language_code().split("-")[0]
        matching = [v for v in cached if v.get("locale", "").split("-")[0] == code]
        for voice in matching:
            self.voice_combo.addItem(voice["name"], voice["voice_id"])
        self._select_voice_data(selected_id)

    def _select_voice_data(self, value):
        if not value:
            return
        idx = self.voice_combo.findData(value)
        if idx >= 0:
            self.voice_combo.setCurrentIndex(idx)

    def _update_voice_status(self):
        """Explain an empty voice list, or note a pending download."""
        engine = self.tts_engine_combo.currentText()
        language = self.target_language_combo.currentText()

        if self.voice_combo.count() == 0:
            if engine == "Piper (Offline)":
                self.voice_status_label.setText(
                    f"No offline voice for {language} — choose a cloud TTS engine.")
            elif engine in ("Azure (Cloud)", "Google (Cloud)"):
                provider = engine.split(" ")[0]
                has_key = (get_azure_api_key() if engine.startswith("Azure")
                           else get_google_api_key())
                self.voice_status_label.setText(
                    f"No {provider} voices for {language} yet — "
                    + ("click Refresh to load the voice list."
                       if has_key else f"add a {provider} API key in Settings."))
            else:
                self.voice_status_label.setText("No voices available.")
            self.voice_status_label.setVisible(True)
            return

        if engine == "Piper (Offline)":
            voice = voice_manager.get_voice(self.voice_combo.currentData())
            if voice and not voice_manager.is_downloaded(voice):
                self.voice_status_label.setText(
                    f"This voice downloads once ({voice_manager.voice_size_mb(voice):.0f} MB) "
                    "when processing starts.")
                self.voice_status_label.setVisible(True)
                return

        cost = TTS_ENGINE_COST_PER_1M.get(engine, 0.0)
        if cost:
            # ~50k characters per hour of video, so this is roughly per-hour cost.
            self.voice_status_label.setText(
                f"≈ ${cost * 0.05:.2f} per hour of video (${cost:.0f} per 1M characters).")
            self.voice_status_label.setVisible(True)
        else:
            self.voice_status_label.setVisible(False)

    def _on_tts_engine_changed(self, engine):
        self._populate_voice_combo()
        self.refresh_voices_btn.setVisible(
            engine in ("Azure (Cloud)", "Google (Cloud)", "ElevenLabs (Cloud)"))
        if engine in ("Azure (Cloud)", "Google (Cloud)", "ElevenLabs (Cloud)"):
            self._start_voice_fetch()

    def _on_target_language_changed(self):
        """Piper, Azure and Google voice lists are filtered by target language."""
        self._populate_voice_combo()

    def _start_voice_fetch(self):
        """Refresh the current cloud engine's voice list in the background."""
        engine = self.tts_engine_combo.currentText()
        keys = {
            "ElevenLabs (Cloud)": get_elevenlabs_api_key,
            "Azure (Cloud)": get_azure_api_key,
            "Google (Cloud)": get_google_api_key,
        }
        if engine not in keys or not keys[engine]():
            return
        if self.voice_fetch_worker and self.voice_fetch_worker.isRunning():
            return
        self.voice_fetch_worker = VoiceFetchWorker(engine)
        self.voice_fetch_worker.fetched.connect(self._on_voices_fetched)
        self.voice_fetch_worker.error.connect(lambda msg: None)  # silent — cache/fallback in use
        self.voice_fetch_worker.start()

    def _on_voices_fetched(self, voices):
        self.voice_fetch_worker = None
        self._populate_voice_combo()

    def _on_swap_languages(self):
        """Swap source and target languages to reverse the learning flow."""
        source = self.language_combo.currentText()
        target = self.target_language_combo.currentText()
        self.language_combo.setCurrentText(target)
        self.target_language_combo.setCurrentText(source)

    def _on_anki_only_toggled(self, checked):
        if checked:
            self.anki_checkbox.setChecked(True)
            self.anki_checkbox.setEnabled(False)
            self.voice_combo.setEnabled(False)
            self.speed_slider.setEnabled(False)
            self.output_list.setEnabled(False)
            self.add_output_btn.setEnabled(False)
            self.output_format_combo.setEnabled(False)
            self.output_mode_combo.setEnabled(False)
            self.output_group_spin.setEnabled(False)
            self.output_condensed_check.setEnabled(False)
        else:
            self.anki_checkbox.setEnabled(True)
            self.voice_combo.setEnabled(True)
            self.speed_slider.setEnabled(True)
            self.output_list.setEnabled(True)
            self.add_output_btn.setEnabled(True)
            self.output_format_combo.setEnabled(True)
            self.output_mode_combo.setEnabled(True)
            self.output_group_spin.setEnabled(True)
            self.output_condensed_check.setEnabled(True)

    def _on_output_mode_changed(self, mode_text):
        """Disable Groups spinbox when Summary mode is selected."""
        if mode_text == "Summary":
            self.output_group_spin.setValue(1)
            self.output_group_spin.setEnabled(False)
        else:
            self.output_group_spin.setEnabled(True)

    def _on_add_output(self):
        """Add current output configuration to the list."""
        fmt = self.output_format_combo.currentText().lower()
        mode = self.output_mode_combo.currentText().lower()
        group_size = self.output_group_spin.value()
        condensed = self.output_condensed_check.isChecked()

        if mode == "summary":
            group_size = 1

        config = OutputConfig(format=fmt, mode=mode, group_size=group_size, condensed=condensed)

        # Check for duplicate
        for i in range(self.output_list.count()):
            existing = OutputConfig.from_dict(self.output_list.item(i).data(Qt.UserRole))
            if existing == config:
                QMessageBox.information(self, "Duplicate", "This output configuration already exists.")
                return

        self._add_output_item(config)

    def _add_output_item(self, config: OutputConfig):
        """Add an OutputConfig to the list widget."""
        item = QListWidgetItem()
        item.setData(Qt.UserRole, config.to_dict())

        widget = QWidget()
        row_layout = QHBoxLayout(widget)
        row_layout.setContentsMargins(8, 2, 4, 2)
        row_layout.setSpacing(6)

        idx = self.output_list.count() + 1
        label = QLabel(f"{idx}. {config.label()}")
        label.setObjectName("output_item_label")
        row_layout.addWidget(label, 1)

        remove_btn = QPushButton("\u2715")
        remove_btn.setFixedSize(24, 24)
        remove_btn.setToolTip("Remove this output")
        remove_btn.clicked.connect(lambda checked=False, it=item: self._on_remove_output(it))
        row_layout.addWidget(remove_btn)

        item.setSizeHint(widget.sizeHint())
        self.output_list.addItem(item)
        self.output_list.setItemWidget(item, widget)

    def _on_remove_output(self, item):
        """Remove an output config from the list."""
        row = self.output_list.row(item)
        if row >= 0:
            self.output_list.takeItem(row)
            self._renumber_output_items()

    def _renumber_output_items(self):
        """Update numbering labels after removal."""
        for i in range(self.output_list.count()):
            item = self.output_list.item(i)
            widget = self.output_list.itemWidget(item)
            if widget:
                label = widget.findChild(QLabel, "output_item_label")
                if label:
                    config = OutputConfig.from_dict(item.data(Qt.UserRole))
                    label.setText(f"{i + 1}. {config.label()}")

    def _get_output_configs(self):
        """Get all output configs from the list widget."""
        configs = []
        for i in range(self.output_list.count()):
            item = self.output_list.item(i)
            configs.append(OutputConfig.from_dict(item.data(Qt.UserRole)))
        return configs

    def _on_comprehensibility_toggled(self, checked):
        self.lemma_path_label.setVisible(checked)
        self.lemma_browse_btn.setVisible(checked)
        self.unlisted_label.setVisible(checked)
        self.unlisted_spin.setVisible(checked)
        self.check_first_checkbox.setVisible(checked)

    def _on_browse_lemma_list(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select Lemma List", "", "Word Lists (*.txt *.csv);;Text Files (*.txt);;CSV Files (*.csv);;All Files (*)"
        )
        if filepath:
            self.lemma_path_label.setText(filepath)
            set_lemma_list_path(filepath)

    def _toggle_key_visibility(self):
        if self.key_input.echoMode() == QLineEdit.Password:
            self.key_input.setEchoMode(QLineEdit.Normal)
            self.show_key_btn.setText("Hide")
        else:
            self.key_input.setEchoMode(QLineEdit.Password)
            self.show_key_btn.setText("Show")

    def _toggle_elevenlabs_key_visibility(self):
        if self.elevenlabs_key_input.echoMode() == QLineEdit.Password:
            self.elevenlabs_key_input.setEchoMode(QLineEdit.Normal)
            self.show_elevenlabs_key_btn.setText("Hide")
        else:
            self.elevenlabs_key_input.setEchoMode(QLineEdit.Password)
            self.show_elevenlabs_key_btn.setText("Show")

    def _on_openai_key_changed(self):
        """Auto-save OpenAI API key when it changes."""
        key = self.key_input.text().strip()
        set_api_key(key)

    def _on_elevenlabs_key_changed(self):
        """Auto-save ElevenLabs API key when it changes."""
        key = self.elevenlabs_key_input.text().strip()
        set_elevenlabs_api_key(key)

    def _toggle_anthropic_key_visibility(self):
        if self.anthropic_key_input.echoMode() == QLineEdit.Password:
            self.anthropic_key_input.setEchoMode(QLineEdit.Normal)
            self.show_anthropic_key_btn.setText("Hide")
        else:
            self.anthropic_key_input.setEchoMode(QLineEdit.Password)
            self.show_anthropic_key_btn.setText("Show")

    def _on_anthropic_key_changed(self):
        """Auto-save Anthropic API key when it changes."""
        key = self.anthropic_key_input.text().strip()
        set_anthropic_api_key(key)

    def _toggle_soniox_key_visibility(self):
        if self.soniox_key_input.echoMode() == QLineEdit.Password:
            self.soniox_key_input.setEchoMode(QLineEdit.Normal)
            self.show_soniox_key_btn.setText("Hide")
        else:
            self.soniox_key_input.setEchoMode(QLineEdit.Password)
            self.show_soniox_key_btn.setText("Show")

    def _on_soniox_key_changed(self):
        """Auto-save Soniox API key when it changes."""
        key = self.soniox_key_input.text().strip()
        set_soniox_api_key(key)

    def _toggle_azure_key_visibility(self):
        if self.azure_key_input.echoMode() == QLineEdit.Password:
            self.azure_key_input.setEchoMode(QLineEdit.Normal)
            self.show_azure_key_btn.setText("Hide")
        else:
            self.azure_key_input.setEchoMode(QLineEdit.Password)
            self.show_azure_key_btn.setText("Show")

    def _on_azure_key_changed(self):
        """Auto-save the Azure Speech key and refresh voices if Azure is active."""
        set_azure_api_key(self.azure_key_input.text().strip())
        if self.tts_engine_combo.currentText() == "Azure (Cloud)":
            self._start_voice_fetch()

    def _on_azure_region_changed(self, region):
        set_azure_region(region.strip())
        if self.tts_engine_combo.currentText() == "Azure (Cloud)":
            self._start_voice_fetch()

    def _toggle_google_key_visibility(self):
        if self.google_key_input.echoMode() == QLineEdit.Password:
            self.google_key_input.setEchoMode(QLineEdit.Normal)
            self.show_google_key_btn.setText("Hide")
        else:
            self.google_key_input.setEchoMode(QLineEdit.Password)
            self.show_google_key_btn.setText("Show")

    def _on_google_key_changed(self):
        """Auto-save the Google Cloud key and refresh voices if Google is active."""
        set_google_api_key(self.google_key_input.text().strip())
        if self.tts_engine_combo.currentText() == "Google (Cloud)":
            self._start_voice_fetch()

    def _start_model_fetch(self, silent=True):
        """Fetch current model lists from OpenAI/Anthropic in the background.

        silent=True (startup) refreshes quietly; silent=False (button) reports
        the result to the user.
        """
        if not get_api_key() and not get_anthropic_api_key():
            if not silent:
                QMessageBox.information(
                    self, "No API Keys",
                    "Add an OpenAI or Anthropic API key in the Settings tab first —\n"
                    "model lists are fetched from the providers using your keys.")
            return
        if self.model_fetch_worker and self.model_fetch_worker.isRunning():
            return
        self._model_fetch_silent = silent
        self.refresh_models_btn.setEnabled(False)
        self.refresh_models_btn.setText("Refreshing...")
        self.model_fetch_worker = ModelFetchWorker()
        self.model_fetch_worker.fetched.connect(self._on_models_fetched)
        self.model_fetch_worker.start()

    def _on_models_fetched(self, options, errors):
        self.model_fetch_worker = None
        self.refresh_models_btn.setEnabled(True)
        self.refresh_models_btn.setText("Refresh Model List")
        self._repopulate_model_combos(options)
        if errors:
            self.model_list_status_label.setText("Model list refresh had errors")
            if not self._model_fetch_silent:
                QMessageBox.warning(self, "Model List Refresh",
                                    "Some model lists could not be fetched:\n\n"
                                    + "\n".join(f"  - {e}" for e in errors))
        else:
            self.model_list_status_label.setText("Model lists updated from providers")
            if not self._model_fetch_silent:
                QMessageBox.information(self, "Model List Refresh",
                                        "Model lists updated from OpenAI/Anthropic.")

    def _repopulate_model_combos(self, options):
        """Reload the three model combos, preserving current selections."""
        combos = (
            self.translation_model_combo,
            self.punctuation_model_combo,
            self.summary_model_combo,
        )
        for combo in combos:
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            items = list(options)
            if current and current != AI_MODEL_SEPARATOR and current not in items:
                items.insert(0, current)
            combo.addItems(items)
            self._disable_separator_items(combo)
            idx = combo.findText(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.blockSignals(False)

    @staticmethod
    def _disable_separator_items(combo):
        """Disable separator items in a combo box so they can't be selected."""
        for i in range(combo.count()):
            if combo.itemText(i) == AI_MODEL_SEPARATOR:
                model = combo.model()
                item = model.item(i)
                item.setEnabled(False)

    def _change_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Output Directory", self.output_label.text())
        if d:
            self.output_label.setText(d)

    def _on_import_files(self):
        """Open a file dialog to select local audio/video files."""
        ext_filter = " ".join(f"*{e}" for e in sorted(SUPPORTED_EXTENSIONS))
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Audio/Video Files",
            "",
            f"Media Files ({ext_filter});;All Files (*)",
        )
        if files:
            existing = self.url_input.toPlainText()
            separator = "\n" if existing.strip() else ""
            self.url_input.setPlainText(existing + separator + "\n".join(files))

    def _on_process(self):
        if self.worker and self.worker.isRunning():
            # Cancel mode
            self.worker.cancel()
            self.process_btn.setEnabled(False)
            self.status_label.setText("Cancelling...")
            return

        # Parse URLs / file paths from text area
        raw_text = self.url_input.toPlainText().strip()
        if not raw_text:
            QMessageBox.warning(self, "Missing Input", "Please enter at least one URL or file path.")
            return

        urls = [line.strip() for line in raw_text.splitlines() if line.strip()]
        if not urls:
            QMessageBox.warning(self, "Missing Input", "Please enter at least one URL or file path.")
            return

        # Validate local file entries
        for entry in urls:
            if not re.match(r"https?://", entry, re.IGNORECASE):
                p = Path(entry)
                if not p.exists():
                    QMessageBox.warning(
                        self, "File Not Found",
                        f"Local file not found:\n{entry}")
                    return
                if not p.is_file():
                    QMessageBox.warning(
                        self, "Not a File",
                        f"Path is not a file:\n{entry}")
                    return
                if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    QMessageBox.warning(
                        self, "Unsupported Format",
                        f"Unsupported file type '{p.suffix}'.\n"
                        f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
                    return

        # Validate output configs
        output_configs = self._get_output_configs()
        anki_only = self.anki_only_checkbox.isChecked()
        if not anki_only and not output_configs:
            QMessageBox.warning(self, "No Outputs", "Add at least one output configuration.")
            return

        # Language direction sanity check
        if self.language_combo.currentText() == self.target_language_combo.currentText():
            QMessageBox.warning(self, "Same Language",
                "Source and 'Translate to' languages are the same.\n\n"
                "Pick the video's language as Source and your native language "
                "as 'Translate to' (use the ⇄ Swap button to reverse the flow).")
            return

        # TTS engine checks: each cloud engine needs its own key, and every
        # engine needs a selected voice for the target language.
        engine = self.tts_engine_combo.currentText()
        target = self.target_language_combo.currentText()
        anki_only = self.anki_only_checkbox.isChecked()
        if not anki_only:
            key_checks = {
                "ElevenLabs (Cloud)": (get_elevenlabs_api_key, "ElevenLabs"),
                "OpenAI (Cloud)": (get_api_key, "OpenAI"),
                "Azure (Cloud)": (get_azure_api_key, "Azure Speech"),
                "Google (Cloud)": (get_google_api_key, "Google Cloud"),
            }
            if engine in key_checks:
                getter, label = key_checks[engine]
                if not getter():
                    QMessageBox.warning(self, f"Missing {label} API Key",
                        f"{engine} TTS is selected but no {label} API key is provided.\n\n"
                        f"Add your {label} API key in the Settings tab, or switch the "
                        "TTS engine to Piper (Offline).")
                    return

            if self.voice_combo.count() == 0:
                if engine == "Piper (Offline)":
                    QMessageBox.warning(self, "No Offline Voice",
                        f"There is no offline Piper voice for {target}.\n\n"
                        "Switch the TTS engine to a cloud provider (Azure has the "
                        "widest language coverage), or change 'Translate to'.")
                else:
                    QMessageBox.warning(self, "No Voice Selected",
                        f"No {engine.split(' ')[0]} voice is available for {target}.\n\n"
                        "Click Refresh next to the voice list, or pick a different "
                        "TTS engine or target language.")
                return

        api_key = self.key_input.text().strip()
        trans_model = self.translation_model_combo.currentText()
        punct_model = self.punctuation_model_combo.currentText()
        sum_model = self.summary_model_combo.currentText()

        # Determine which models are active based on output configs
        needs_sentence = any(c.mode == "sentence" for c in output_configs)
        needs_summary = any(c.mode == "summary" for c in output_configs)
        active_models = [punct_model]
        if needs_summary:
            active_models.append(sum_model)
        if needs_sentence:
            active_models.append(trans_model)

        # Check if OpenAI key is needed (any OpenAI model selected)
        needs_openai = any(not is_anthropic_model(m) for m in active_models)
        if needs_openai and not api_key:
            QMessageBox.warning(self, "Missing OpenAI API Key",
                "An OpenAI model is selected but no API key is provided.\n\n"
                "Please enter your OpenAI API key in the Settings tab,\n"
                "or switch both models to Claude.")
            return

        # Check if Anthropic key is needed (any Claude model selected)
        needs_anthropic = any(is_anthropic_model(m) for m in active_models)
        anthropic_key = self.anthropic_key_input.text().strip()
        if needs_anthropic and not anthropic_key:
            QMessageBox.warning(self, "Missing Anthropic API Key",
                "A Claude model is selected but no Anthropic API key is provided.\n\n"
                "Please enter your Anthropic API key in the Settings tab,\n"
                "or switch to an OpenAI model.")
            return

        # Check if transcription is enabled but no usable engine is configured
        if self.transcription_checkbox.isChecked() or self.force_transcription_checkbox.isChecked():
            elevenlabs_key = self.elevenlabs_key_input.text().strip()
            soniox_key = self.soniox_key_input.text().strip()
            engine = self.transcription_engine_combo.currentText()
            source_lang = self.language_combo.currentText()
            lang_code = LANGUAGE_REGISTRY.get(source_lang, {}).get("code", "")
            feature = "Force Transcription" if self.force_transcription_checkbox.isChecked() else "Transcription fallback"

            if engine == "Soniox (Cloud)" and not soniox_key:
                QMessageBox.warning(
                    self,
                    "Missing Soniox API Key",
                    f"{feature} is enabled with the Soniox engine but no Soniox API key provided.\n\n"
                    "Please add your Soniox API key in the Settings tab."
                )
                return
            if engine == "ElevenLabs (Cloud)" and not elevenlabs_key:
                QMessageBox.warning(
                    self,
                    "Missing ElevenLabs API Key",
                    f"{feature} is enabled with the ElevenLabs engine but no ElevenLabs API key provided.\n\n"
                    "Please add your ElevenLabs API key in the Settings tab."
                )
                return
            if engine == "Auto" and not elevenlabs_key and not soniox_key and lang_code != "ja":
                QMessageBox.warning(
                    self,
                    "Missing Transcription API Key",
                    f"{feature} is enabled but no ElevenLabs or Soniox API key provided.\n\n"
                    "Please add an API key in the Settings tab,\n"
                    "or select ReazonSpeech (Offline, Japanese) for Japanese audio."
                )
                return
            if engine == "ReazonSpeech (Offline, Japanese)" and lang_code != "ja" and not elevenlabs_key and not soniox_key:
                QMessageBox.warning(
                    self,
                    "Missing Transcription API Key",
                    "ReazonSpeech only supports Japanese; other languages fall back to a cloud engine,\n"
                    "but no ElevenLabs or Soniox API key is provided.\n\n"
                    "Please add an API key in the Settings tab."
                )
                return

        # Save settings before starting
        self._save_settings()

        voice = self.voice_combo.currentText()
        speed = self.speed_slider.value() / 100.0
        output_dir = self.output_label.text()

        # Switch to cancel mode
        self.process_btn.setText("Cancel")
        self.process_btn.setObjectName("cancel_btn")
        self.process_btn.style().unpolish(self.process_btn)
        self.process_btn.style().polish(self.process_btn)
        self.url_input.setEnabled(False)
        self.import_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.batch_label.setText("")

        cookie = self.cookie_combo.currentText()
        cookie_browser = cookie.lower() if cookie != "None" else None

        create_anki = self.anki_checkbox.isChecked()
        force_transcription = self.force_transcription_checkbox.isChecked()
        source_language = self.language_combo.currentText()

        lemma_list_path = ""
        if self.comprehensibility_checkbox.isChecked():
            path_text = self.lemma_path_label.text()
            if path_text and path_text != "No file selected" and Path(path_text).is_file():
                lemma_list_path = path_text

        unlisted_knowledge = self.unlisted_spin.value() if self.comprehensibility_checkbox.isChecked() else 0

        check_first = self.check_first_checkbox.isChecked() if self.comprehensibility_checkbox.isChecked() else False

        resolution = self.resolution_combo.currentText()

        keep_original_audio = self.keep_original_audio_checkbox.isChecked()
        keep_original_video = self.keep_original_video_checkbox.isChecked()

        self.worker = BatchWorker(urls, api_key, voice, speed, output_dir,
                                  cookie_browser=cookie_browser, create_anki=create_anki,
                                  source_language=source_language,
                                  force_transcription=force_transcription,
                                  anki_only=anki_only,
                                  output_configs=output_configs,
                                  resolution=resolution,
                                  lemma_list_path=lemma_list_path,
                                  unlisted_knowledge=unlisted_knowledge,
                                  check_first=check_first,
                                  keep_original_audio=keep_original_audio,
                                  keep_original_video=keep_original_video,
                                  auto_clear_cache=self.auto_clear_checkbox.isChecked(),
                                  cache_threshold_gb=self.cache_threshold_spin.value())
        self.worker.step_changed.connect(self._on_step_changed)
        self.worker.progress.connect(self._on_progress)
        self.worker.batch_progress.connect(self._on_batch_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.comprehensibility_result.connect(self._on_comprehensibility_result)
        self.worker.start()

    def _on_step_changed(self, label):
        self._estimated_timer.stop()
        self.status_label.setText(label)

    def _on_progress(self, current, total, message):
        self._estimated_timer.stop()
        if total > 0:
            s = self._progress_scale
            scaled_max = total * s
            scaled_value = current * s
            self.progress_bar.setMaximum(scaled_max)
            self.progress_bar.setValue(scaled_value)
            # Animate toward next milestone (but never reach it)
            self._progress_cap = min((current + 1) * s, scaled_max) - 1
            if scaled_value < scaled_max:
                self._estimated_timer.start(200)
        else:
            self.progress_bar.setMaximum(0)  # Indeterminate
        self.detail_label.setText(message)

    def _tick_estimated_progress(self):
        current = self.progress_bar.value()
        remaining = self._progress_cap - current
        if remaining <= 1:
            self._estimated_timer.stop()
            return
        increment = max(1, int(remaining * 0.03))
        self.progress_bar.setValue(current + increment)

    def _on_batch_progress(self, current, total, video_url):
        if total > 1:
            self.batch_label.setText(f"Video {current} of {total}")
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(1)

    def _on_comprehensibility_result(self, message):
        """Show comprehensibility score dialog and let user Continue or Skip."""
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Comprehensibility Check")
        dialog.setIcon(QMessageBox.Information)
        dialog.setText(message)
        continue_btn = dialog.addButton("Continue", QMessageBox.AcceptRole)
        dialog.addButton("Skip", QMessageBox.RejectRole)
        dialog.exec()
        user_chose_continue = dialog.clickedButton() == continue_btn
        if self.worker:
            self.worker.set_check_response(user_chose_continue)

    def _on_finished(self, summary):
        self._estimated_timer.stop()
        self._reset_ui()
        self.progress_bar.setMaximum(1)
        self.progress_bar.setValue(1)

        # Extract comprehensibility info if present
        comp_lines = [l for l in summary.split("\n") if "Comprehensibility:" in l]
        if comp_lines:
            self.status_label.setText("Done! " + comp_lines[0])
        else:
            self.status_label.setText("Done!")

        if "failed" in summary and "0 failed" not in summary:
            self.detail_label.setText(summary.split("\n")[0])
            QMessageBox.warning(self, "Batch Complete", summary)
        else:
            self.detail_label.setText(summary.split("\n")[0])

    def _on_error(self, message):
        self._estimated_timer.stop()
        self._reset_ui()
        self.status_label.setText("Error")
        self.detail_label.setText(message)
        self.progress_bar.setValue(0)

        if "yt-dlp appears to be outdated" in message:
            from ..core.updater import _get_current_ytdlp_version
            current_ver = _get_current_ytdlp_version()
            dialog = QMessageBox(self)
            dialog.setWindowTitle("yt-dlp Outdated")
            dialog.setIcon(QMessageBox.Warning)
            dialog.setText(
                "yt-dlp is outdated and YouTube is rejecting requests.\n\n"
                f"Current version: {current_ver}\n\n"
                "Update yt-dlp to fix YouTube download errors."
            )
            update_btn = dialog.addButton("Update yt-dlp", QMessageBox.AcceptRole)
            dialog.addButton("Dismiss", QMessageBox.RejectRole)
            dialog.exec()
            if dialog.clickedButton() == update_btn:
                self._on_check_updates()
        else:
            QMessageBox.critical(self, "Pipeline Error", message)

    def _reset_ui(self):
        self.process_btn.setText("Process")
        self.process_btn.setObjectName("")
        self.process_btn.style().unpolish(self.process_btn)
        self.process_btn.style().polish(self.process_btn)
        self.process_btn.setEnabled(True)
        self.url_input.setEnabled(True)
        self.import_btn.setEnabled(True)
        self.batch_label.setText("")
        if self.worker:
            self.worker.wait()  # Ensure OS thread has fully exited before Python GC can destroy it
        self.worker = None

    def _on_check_updates(self):
        """Check for available updates."""
        # Prevent concurrent operations
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "Processing",
                "Please wait for video processing to complete.")
            return

        if self.update_worker and self.update_worker.isRunning():
            return

        # Disable button, show checking state
        self.update_btn.setEnabled(False)
        self.update_btn.setText("Checking...")

        # Import and create worker
        from ..core.updater import UpdateWorker
        self.update_worker = UpdateWorker(mode="check")
        self.update_worker.updates_found.connect(self._on_updates_found)
        self.update_worker.error.connect(self._on_update_error)
        self.update_worker.start()

    def _on_updates_found(self, updates_dict):
        """Handle updates found signal."""
        app_update = updates_dict.get("app", {})
        ytdlp_update = updates_dict.get("ytdlp", {})
        warnings = updates_dict.get("warnings", [])

        # Re-enable button
        self.update_btn.setEnabled(True)
        self.update_btn.setText("Check for Updates")

        # Refresh version label with latest info
        self._refresh_ytdlp_version_label()

        app_available = app_update.get("update_available", False) and not app_update.get("error")
        ytdlp_available = ytdlp_update.get("update_available", False) and not ytdlp_update.get("error")

        if not app_available and not ytdlp_available:
            msg = "No updates are currently available."
            if warnings:
                msg += "\n\nWarnings:\n" + "\n".join(f"  - {w}" for w in warnings)
            QMessageBox.information(self, "No Updates", msg)
            return

        msg = "Update actions available:\n\n"
        if app_available:
            msg += "App Release:\n"
            msg += f"  - {app_update.get('current', 'unknown')} \u2192 {app_update.get('latest', 'unknown')}\n"
            msg += "  - Action: open latest GitHub release page in browser\n\n"

        if ytdlp_available:
            msg += "yt-dlp Update:\n"
            msg += (
                f"  - {ytdlp_update.get('current', 'unknown')} \u2192 {ytdlp_update.get('latest', 'unknown')}"
                " (fixes YouTube download errors)\n"
            )
            msg += "  - Action: download and install with SHA-256 verification\n\n"

        if warnings:
            msg += "Warnings:\n"
            msg += "\n".join(f"  - {w}" for w in warnings)
            msg += "\n\n"

        msg += "Apply these update actions now?"

        reply = QMessageBox.question(self, "Updates Available", msg,
            QMessageBox.Yes | QMessageBox.No)

        if reply == QMessageBox.Yes:
            self._install_updates(updates_dict)

    def _install_updates(self, updates_dict):
        """Install approved updates."""
        self.update_btn.setEnabled(False)
        self.update_btn.setText("Updating...")

        from ..core.updater import UpdateWorker
        self.update_worker = UpdateWorker(mode="install", updates=updates_dict)
        self.update_worker.step_changed.connect(lambda msg: self.detail_label.setText(msg))
        self.update_worker.progress.connect(self._on_update_progress)
        self.update_worker.finished.connect(self._on_update_complete)
        self.update_worker.error.connect(self._on_update_error)
        self.update_worker.start()

    def _on_update_progress(self, current, total, message):
        """Update progress bar during installation."""
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
        self.detail_label.setText(message)

    def _on_update_complete(self, summary):
        """Handle update completion."""
        self.update_btn.setEnabled(True)
        self.update_btn.setText("Check for Updates")
        self.progress_bar.setValue(0)
        self.detail_label.setText("")
        self._refresh_ytdlp_version_label()
        QMessageBox.information(self, "Update Actions Complete", summary)
        self.update_worker = None

    def _on_update_error(self, error_msg):
        """Handle update error."""
        self.update_btn.setEnabled(True)
        self.update_btn.setText("Check for Updates")
        self.progress_bar.setValue(0)
        self.detail_label.setText("")
        QMessageBox.critical(self, "Update Error", error_msg)
        self.update_worker = None

    def _check_cache_size_warning(self):
        """Check cache size on startup and highlight button red if >= 10 GB."""
        from ..core.cache_manager import CacheWorker
        self._cache_size_checker = CacheWorker(mode="calculate")
        self._cache_size_checker.size_calculated.connect(self._on_cache_size_warning)
        self._cache_size_checker.start()

    def _on_cache_size_warning(self, total_bytes, breakdown):
        """Style the Clear Cache button red if cache is >= 10 GB."""
        from ..core.cache_manager import format_size
        self._cache_size_checker = None
        TEN_GB = 10 * 1024 * 1024 * 1024
        if total_bytes >= TEN_GB:
            self.cache_btn.setText(f"Clear Cache ({format_size(total_bytes)})")
            self.cache_btn.setStyleSheet(
                "QPushButton { background-color: #b03a2e; color: white; font-weight: bold; }"
                "QPushButton:hover { background-color: #922b21; }"
            )
        else:
            self.cache_btn.setText("Clear Cache")
            self.cache_btn.setStyleSheet("")

    def _on_clear_cache(self):
        """Entry point for cache clearing - starts size calculation."""
        # Prevent concurrent operations
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "Processing",
                "Please wait for video processing to complete before clearing cache.")
            return

        if self.cache_worker and self.cache_worker.isRunning():
            return

        # Disable button, show calculating state
        self.cache_btn.setEnabled(False)
        self.cache_btn.setText("Calculating...")

        # Import and create worker for size calculation
        from ..core.cache_manager import CacheWorker
        self.cache_worker = CacheWorker(mode="calculate")
        self.cache_worker.size_calculated.connect(self._on_cache_size_calculated)
        self.cache_worker.error.connect(self._on_cache_error)
        self.cache_worker.start()

    def _on_cache_size_calculated(self, total_bytes, breakdown):
        """Handle cache size calculation result - show confirmation dialog."""
        from ..core.cache_manager import format_size

        # Re-enable button
        self.cache_btn.setEnabled(True)
        self.cache_btn.setText("Clear Cache")

        if total_bytes == 0:
            QMessageBox.information(self, "Cache Empty",
                "Cache directory is empty (0 B).")
            self.cache_worker = None
            return

        # Build confirmation message with breakdown
        msg = f"Clear cache ({format_size(total_bytes)})?\n\nBreakdown:\n"
        for subdir_name, size in breakdown.items():
            if size > 0:
                msg += f"  • {subdir_name}: {format_size(size)}\n"

        msg += "\nThis will free up disk space. Files will be regenerated as needed."

        reply = QMessageBox.question(self, "Clear Cache", msg,
            QMessageBox.Yes | QMessageBox.No)

        if reply == QMessageBox.Yes:
            self._start_cache_clear()
        else:
            self.cache_worker = None

    def _start_cache_clear(self):
        """Initiate cache deletion after user confirms."""
        self.cache_btn.setEnabled(False)
        self.cache_btn.setText("Clearing...")

        from ..core.cache_manager import CacheWorker
        self.cache_worker = CacheWorker(mode="clear")
        self.cache_worker.progress.connect(self._on_cache_progress)
        self.cache_worker.finished.connect(self._on_cache_cleared)
        self.cache_worker.error.connect(self._on_cache_error)
        self.cache_worker.start()

    def _on_cache_progress(self, current, total, message):
        """Update progress bar during cache deletion."""
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
        self.detail_label.setText(message)

    def _on_cache_cleared(self, summary, stats):
        """Show cache clearing results."""
        self.cache_btn.setEnabled(True)
        self.cache_btn.setText("Clear Cache")
        self.cache_btn.setStyleSheet("")
        self.progress_bar.setValue(0)
        self.detail_label.setText("")

        # Determine message box type based on success
        if stats.get("failed_dirs"):
            QMessageBox.warning(self, "Cache Partially Cleared", summary)
        else:
            QMessageBox.information(self, "Cache Cleared", summary)

        self.cache_worker = None

    def _on_cache_error(self, error_msg):
        """Handle cache operation error."""
        self.cache_btn.setEnabled(True)
        self.cache_btn.setText("Clear Cache")
        self.progress_bar.setValue(0)
        self.detail_label.setText("")
        QMessageBox.critical(self, "Cache Error", error_msg)
        self.cache_worker = None

    def _on_language_changed_in_settings(self):
        """Load prompts for newly selected language."""
        language = self.language_combo.currentText()

        # Update language indicator
        self.current_language_label.setText(f"Editing prompts for: {language}")

        # Block signals to prevent auto-save during load
        self.translation_prompt_edit.blockSignals(True)
        self.punctuation_prompt_edit.blockSignals(True)
        self.summary_prompt_edit.blockSignals(True)

        # Load translation prompt (custom or default) - RAW template with {LANGUAGE}
        trans_prompt = get_translation_prompt_raw(language)
        self.translation_prompt_edit.setPlainText(trans_prompt)

        # Load punctuation prompt (custom or default) - RAW template with {LANGUAGE}
        punct_prompt = get_punctuation_prompt_raw(language)
        self.punctuation_prompt_edit.setPlainText(punct_prompt)

        # Load summary prompt (custom or default) - RAW template with {LANGUAGE}
        sum_prompt = get_summary_prompt_raw(language)
        self.summary_prompt_edit.setPlainText(sum_prompt)

        # Re-enable signals
        self.translation_prompt_edit.blockSignals(False)
        self.punctuation_prompt_edit.blockSignals(False)
        self.summary_prompt_edit.blockSignals(False)

        # Update reset button states
        self._update_translation_reset_button_state()
        self._update_punctuation_reset_button_state()
        self._update_summary_reset_button_state()

    def _on_reset_translation_prompt(self):
        """Reset translation prompt to default."""
        language = self.language_combo.currentText()
        reset_translation_prompt(language)
        # Reload default
        lang_config = get_language_config(language)
        self.translation_prompt_edit.blockSignals(True)
        self.translation_prompt_edit.setPlainText(lang_config["translation_prompt"])
        self.translation_prompt_edit.blockSignals(False)
        self._update_translation_reset_button_state()

    def _on_reset_punctuation_prompt(self):
        """Reset punctuation prompt to default."""
        language = self.language_combo.currentText()
        reset_punctuation_prompt(language)
        # Reload default
        lang_config = get_language_config(language)
        self.punctuation_prompt_edit.blockSignals(True)
        self.punctuation_prompt_edit.setPlainText(lang_config["punctuation_prompt"])
        self.punctuation_prompt_edit.blockSignals(False)
        self._update_punctuation_reset_button_state()

    def _on_translation_prompt_changed(self):
        """Auto-save translation prompt when text changes."""
        language = self.language_combo.currentText()
        trans_prompt = self.translation_prompt_edit.toPlainText().strip()
        if trans_prompt:
            set_custom_translation_prompt(language, trans_prompt)
        self._update_translation_reset_button_state()

    def _on_punctuation_prompt_changed(self):
        """Auto-save punctuation prompt when text changes."""
        language = self.language_combo.currentText()
        punct_prompt = self.punctuation_prompt_edit.toPlainText().strip()
        if punct_prompt:
            set_custom_punctuation_prompt(language, punct_prompt)
        self._update_punctuation_reset_button_state()

    def _on_translation_model_changed(self, model):
        """Auto-save translation AI model when selection changes."""
        if model != AI_MODEL_SEPARATOR:
            set_translation_model(model)

    def _on_punctuation_model_changed(self, model):
        """Auto-save punctuation AI model when selection changes."""
        if model != AI_MODEL_SEPARATOR:
            set_punctuation_model(model)

    def _on_summary_prompt_changed(self):
        """Auto-save summary prompt when text changes."""
        language = self.language_combo.currentText()
        sum_prompt = self.summary_prompt_edit.toPlainText().strip()
        if sum_prompt:
            set_custom_summary_prompt(language, sum_prompt)
        self._update_summary_reset_button_state()

    def _on_summary_model_changed(self, model):
        """Auto-save summary AI model when selection changes."""
        if model != AI_MODEL_SEPARATOR:
            set_summary_model(model)

    def _on_reset_summary_prompt(self):
        """Reset summary prompt to default."""
        language = self.language_combo.currentText()
        reset_summary_prompt(language)
        self.summary_prompt_edit.blockSignals(True)
        self.summary_prompt_edit.setPlainText(DEFAULT_SUMMARY_PROMPT)
        self.summary_prompt_edit.blockSignals(False)
        self._update_summary_reset_button_state()

    def _update_summary_reset_button_state(self):
        """Update reset button style based on customization status."""
        language = self.language_combo.currentText()
        config = load_config()
        custom_prompts = config.get("custom_summary_prompts", {})
        is_customized = language in custom_prompts

        if is_customized:
            self.summary_reset_btn.setObjectName("reset_active")
        else:
            self.summary_reset_btn.setObjectName("reset_inactive")
        self.summary_reset_btn.style().unpolish(self.summary_reset_btn)
        self.summary_reset_btn.style().polish(self.summary_reset_btn)

    def _update_translation_reset_button_state(self):
        """Update reset button style based on customization status."""
        language = self.language_combo.currentText()
        config = load_config()
        custom_prompts = config.get("custom_translation_prompts", {})
        is_customized = language in custom_prompts

        if is_customized:
            self.translation_reset_btn.setObjectName("reset_active")
        else:
            self.translation_reset_btn.setObjectName("reset_inactive")
        # Refresh styling
        self.translation_reset_btn.style().unpolish(self.translation_reset_btn)
        self.translation_reset_btn.style().polish(self.translation_reset_btn)

    def _update_punctuation_reset_button_state(self):
        """Update reset button style based on customization status."""
        language = self.language_combo.currentText()
        config = load_config()
        custom_prompts = config.get("custom_punctuation_prompts", {})
        is_customized = language in custom_prompts

        if is_customized:
            self.punctuation_reset_btn.setObjectName("reset_active")
        else:
            self.punctuation_reset_btn.setObjectName("reset_inactive")
        # Refresh styling
        self.punctuation_reset_btn.style().unpolish(self.punctuation_reset_btn)
        self.punctuation_reset_btn.style().polish(self.punctuation_reset_btn)

    def _shutdown_worker(self, timeout_ms=15000):
        """Cancel and wait for worker thread to exit. Return True if stopped."""
        if not self.worker or not self.worker.isRunning():
            return True
        self._estimated_timer.stop()
        self.worker.cancel()
        return self.worker.wait(timeout_ms)

    def closeEvent(self, event):
        self._save_settings()
        # Let short-lived fetch threads finish to avoid destroying live QThreads
        for background in (self.model_fetch_worker, self.voice_fetch_worker):
            if background and background.isRunning():
                background.wait(5000)
        if self.worker and self.worker.isRunning():
            self.status_label.setText("Cancelling...")
            if not self._shutdown_worker():
                QMessageBox.warning(
                    self,
                    "Still shutting down",
                    "A background task is still running. Please wait for cancellation to complete, then close again.",
                )
                event.ignore()
                return
        event.accept()
