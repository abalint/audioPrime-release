"""Paths, API key storage, voice registry, and ffmpeg check."""

import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

VERSION = "1.0.0"

from .bin_paths import check_tool, ffmpeg_path
from .keystore import DecryptionError, decrypt, encrypt

if getattr(sys, "frozen", False) or "__compiled__" in globals():
    # Nuitka standalone or PyInstaller: bundled data lives inside the app
    _BUNDLE_DIR = Path(__file__).resolve().parent.parent
    APP_DIR = Path(sys.executable).resolve().parent
    if sys.platform == "darwin":
        # macOS .app: executable is at audioPrime.app/Contents/MacOS/audioPrime
        # Go up to the directory containing the .app
        APP_DIR = APP_DIR.parent.parent.parent
else:
    _BUNDLE_DIR = Path(__file__).resolve().parent.parent
    APP_DIR = _BUNDLE_DIR

VOICES_DIR = _BUNDLE_DIR / "voices"
# Piper voices downloaded on demand. Separate from VOICES_DIR because the
# bundle directory is read-only in frozen builds.
USER_VOICES_DIR = APP_DIR / "voices-downloaded"
CATALOG_FILE = _BUNDLE_DIR / "data" / "piper_voices.json"
OUTPUT_DIR = APP_DIR / "output"
WORK_DIR = APP_DIR / ".work"
LOGS_DIR = APP_DIR / "logs"
CONFIG_FILE = Path.home() / ".audioPrimeProd.json"

AI_MODEL_OPTIONS = [
    "gpt-5.2",
    "gpt-5.1",
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-nano",
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-4.5-preview",
    "gpt-4-turbo",
    "o3-mini",
    "───── Anthropic ─────",
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-haiku-4-5",
]

AI_MODEL_SEPARATOR = "───── Anthropic ─────"

DEFAULT_AI_MODEL = "gpt-4o-mini"

TRANSCRIPTION_ENGINE_OPTIONS = [
    "Auto",
    "ElevenLabs (Cloud)",
    "Soniox (Cloud)",
    "ReazonSpeech (Offline, Japanese)",
]
DEFAULT_TRANSCRIPTION_ENGINE = "Auto"

TTS_ENGINE_OPTIONS = [
    "Piper (Offline)",
    "OpenAI (Cloud)",
    "Azure (Cloud)",
    "Google (Cloud)",
    "ElevenLabs (Cloud)",
]
DEFAULT_TTS_ENGINE = "Piper (Offline)"

# Approximate USD per 1M characters, shown in the UI so users can weigh cost
# against quality. Piper is free; cloud figures are list price as of 2026-07.
TTS_ENGINE_COST_PER_1M = {
    "Piper (Offline)": 0.0,
    "OpenAI (Cloud)": 15.0,
    "Azure (Cloud)": 15.0,
    "Google (Cloud)": 4.0,
    "ElevenLabs (Cloud)": 165.0,
}

# The only voice shipped in the installer. Every other Piper voice is listed in
# data/piper_voices.json and downloaded on demand — see core/voice_manager.py.
BUNDLED_PIPER_VOICE = "en_US-amy-medium"
DEFAULT_PIPER_VOICE = BUNDLED_PIPER_VOICE

# Voice names used before the catalog existed, so an upgraded config keeps
# working instead of silently resetting to the default voice.
LEGACY_VOICE_NAMES = {
    "Amy (US, Medium)": "en_US-amy-medium",
    "Lessac (US, High)": "en_US-lessac-high",
    "LJSpeech (US, High)": "en_US-ljspeech-high",
    "Ryan (US, High)": "en_US-ryan-high",
    "Jenny (GB, Medium)": "en_GB-jenny_dioco-medium",
}

# OpenAI TTS — reuses the OpenAI key already configured for translation, so it
# needs no extra onboarding.
OPENAI_TTS_MODELS = ["gpt-4o-mini-tts", "tts-1", "tts-1-hd"]
DEFAULT_OPENAI_TTS_MODEL = "gpt-4o-mini-tts"
OPENAI_TTS_VOICES = [
    "alloy", "ash", "ballad", "coral", "echo",
    "fable", "nova", "onyx", "sage", "shimmer", "verse",
]
DEFAULT_OPENAI_TTS_VOICE = "alloy"

AZURE_REGIONS = [
    "eastus", "eastus2", "westus", "westus2", "westus3", "centralus",
    "northeurope", "westeurope", "uksouth", "francecentral", "germanywestcentral",
    "swedencentral", "switzerlandnorth", "japaneast", "japanwest", "koreacentral",
    "southeastasia", "eastasia", "australiaeast", "centralindia", "brazilsouth",
    "canadacentral", "southafricanorth", "uaenorth",
]
DEFAULT_AZURE_REGION = "eastus"

# Fallback ElevenLabs voices (premade, work with the multilingual model in any
# language including Spanish). The live list is fetched from /v1/voices and
# cached in the config file.
ELEVENLABS_DEFAULT_VOICES = [
    {"name": "Rachel", "voice_id": "21m00Tcm4TlvDq8ikWAM"},
    {"name": "Domi", "voice_id": "AZnzlk1XvdvUeBnXmlld"},
    {"name": "Bella", "voice_id": "EXAVITQu4vr4xnSDxMaL"},
    {"name": "Antoni", "voice_id": "ErXwobaYiN019PkySvjV"},
    {"name": "Josh", "voice_id": "TxGEqnHWrfWFTfGW9XjX"},
]

ELEVENLABS_TTS_MODEL = "eleven_multilingual_v2"

# Flash v2.5 covers more languages than Multilingual v2 (it adds Vietnamese,
# Hungarian and Norwegian) at roughly half the credit cost, so it is the default.
ELEVENLABS_TTS_MODEL_OPTIONS = [
    "eleven_flash_v2_5",
    "eleven_turbo_v2_5",
    "eleven_multilingual_v2",
]
DEFAULT_ELEVENLABS_TTS_MODEL = "eleven_flash_v2_5"


def _make_language_config(code, name, cjk=False):
    """Build a language configuration entry."""
    if cjk:
        sentence_enders = r'[。！？.!?」]\s*$'
        sentence_punct = r'[。！？.!?」]'
        punct_chars = set('。！？.!?')
        punct_marks = (
            "prefer Japanese punctuation: 。at the end of declarative sentences, "
            "？ after questions, ！ after exclamations. ASCII . ? ! are also allowed"
        )
        comma_note = "commas 、, existing punctuation, etc."
    else:
        sentence_enders = r'[.!?]\s*$'
        sentence_punct = r'[.!?]'
        punct_chars = set('.!?')
        punct_marks = ". at the end of declarative sentences, ? after questions, ! after exclamations"
        comma_note = "commas, existing punctuation, etc."

    if cjk:
        punctuation_prompt = (
            "You are a {LANGUAGE} punctuation engine.\n\n"
            "Task:\n"
            "You will receive unpunctuated {LANGUAGE} text from speech transcripts.\n"
            "Insert sentence-ending punctuation to restore natural sentence boundaries.\n\n"
            "Allowed insertions only:\n"
            "- CJK punctuation: 。 ？ ！\n"
            "- ASCII fallback: . ? !\n\n"
            "Critical rules:\n"
            "- Preserve all original characters and all line breaks exactly\n"
            "- Do NOT rewrite, delete, reorder, or replace any words\n"
            "- Only INSERT punctuation from the allowed list\n"
            "- Sentence boundaries may occur anywhere, including mid-line\n"
            "- If a boundary is uncertain, prefer inserting 。 rather than leaving long run-on text\n"
            f"- Do NOT remove any existing punctuation ({comma_note})\n"
            "- Return only the punctuated text, nothing else\n\n"
            "Output quality target:\n"
            "- Add enough sentence boundaries to avoid long run-ons\n"
            "- Aim for frequent natural sentence endings in spoken style"
        )
    else:
        punctuation_prompt = (
            "You are a {LANGUAGE} punctuation engine.\n\n"
            "Task:\n"
            "You will receive unpunctuated {LANGUAGE} text from speech transcripts.\n"
            "Insert sentence-ending punctuation to restore natural sentence boundaries.\n\n"
            "Allowed insertions only:\n"
            f"- {punct_marks}\n\n"
            "Critical rules:\n"
            "- Preserve all original characters and all line breaks exactly\n"
            "- Do NOT rewrite, delete, reorder, or replace any words\n"
            "- Only INSERT punctuation from the allowed list\n"
            "- Sentence boundaries may occur anywhere, including mid-line\n"
            "- If a boundary is uncertain, prefer inserting . rather than leaving long run-on text\n"
            f"- Do NOT remove any existing punctuation ({comma_note})\n"
            "- Return only the punctuated text, nothing else\n\n"
            "Output quality target:\n"
            "- Add enough sentence boundaries to avoid long run-ons\n"
            "- Aim for frequent natural sentence endings in spoken style"
        )

    translation_prompt = (
        "Translate the [Translate this] {LANGUAGE} sentence to {TARGET_LANGUAGE}. "
        "Context sentences are provided for reference only — do NOT translate them.\n\n"
        "Rules:\n"
        "- ONLY translate the text under [Translate this] — ignore [Previous context] and [Next context]\n"
        "- Literal translations — direct {LANGUAGE}-to-{TARGET_LANGUAGE}, NOT {TARGET_LANGUAGE} equivalent idioms\n"
        "- Natural {TARGET_LANGUAGE} grammar\n"
        "- Preserve tone and register (casual stays casual, formal stays formal)\n"
        "- When speakers discuss or reference a specific {LANGUAGE} word or phrase, "
        "preserve the {LANGUAGE} term in quotes with a brief gloss if needed, "
        "written phonetically in {TARGET_LANGUAGE} characters\n"
        "- Output ONLY the {TARGET_LANGUAGE} translation of the target sentence, nothing else"
    )

    return {
        "code": code,
        "sentence_enders": sentence_enders,
        "sentence_punct": sentence_punct,
        "punct_chars": punct_chars,
        "punctuation_prompt": punctuation_prompt,
        "translation_prompt": translation_prompt,
    }


LANGUAGE_REGISTRY = {
    "Arabic": _make_language_config("ar", "Arabic"),
    "Bengali": _make_language_config("bn", "Bengali"),
    "Cantonese": _make_language_config("yue", "Cantonese", cjk=True),
    "Chinese (Simplified)": _make_language_config("zh-Hans", "Chinese", cjk=True),
    "Chinese (Traditional)": _make_language_config("zh-Hant", "Chinese", cjk=True),
    "Chinese (Taiwanese)": _make_language_config("zh-TW", "Taiwanese Chinese", cjk=True),
    "Czech": _make_language_config("cs", "Czech"),
    "Danish": _make_language_config("da", "Danish"),
    "Dutch": _make_language_config("nl", "Dutch"),
    "English": _make_language_config("en", "English"),
    "Finnish": _make_language_config("fi", "Finnish"),
    "French": _make_language_config("fr", "French"),
    "German": _make_language_config("de", "German"),
    "Greek": _make_language_config("el", "Greek"),
    "Hebrew": _make_language_config("he", "Hebrew"),
    "Hindi": _make_language_config("hi", "Hindi"),
    "Hungarian": _make_language_config("hu", "Hungarian"),
    "Indonesian": _make_language_config("id", "Indonesian"),
    "Italian": _make_language_config("it", "Italian"),
    "Japanese": _make_language_config("ja", "Japanese", cjk=True),
    "Korean": _make_language_config("ko", "Korean"),
    "Malay": _make_language_config("ms", "Malay"),
    "Norwegian": _make_language_config("no", "Norwegian"),
    "Polish": _make_language_config("pl", "Polish"),
    "Portuguese": _make_language_config("pt", "Portuguese"),
    "Romanian": _make_language_config("ro", "Romanian"),
    "Russian": _make_language_config("ru", "Russian"),
    "Spanish": _make_language_config("es", "Spanish"),
    "Swedish": _make_language_config("sv", "Swedish"),
    "Thai": _make_language_config("th", "Thai"),
    "Turkish": _make_language_config("tr", "Turkish"),
    "Ukrainian": _make_language_config("uk", "Ukrainian"),
    "Vietnamese": _make_language_config("vi", "Vietnamese"),
}


def get_language_config(display_name):
    """Return the language configuration dict for a display name."""
    config = LANGUAGE_REGISTRY.get(display_name)
    if not config:
        raise ValueError(f"Unknown language: {display_name}")
    return config


DEFAULT_TARGET_LANGUAGE = "English"


def get_target_language() -> str:
    """Display name of the language translations are produced in (the learner's
    native language). Defaults to English for the classic flow."""
    return load_config().get("target_language", DEFAULT_TARGET_LANGUAGE)


def set_target_language(language: str):
    config = load_config()
    config["target_language"] = language
    save_config(config)


def get_target_language_code(language: str | None = None) -> str:
    """ISO code for the target language (e.g. 'en', 'es')."""
    name = language or get_target_language()
    cfg = LANGUAGE_REGISTRY.get(name)
    return cfg["code"] if cfg else "en"


def load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}


def save_config(config: dict):
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


def _migrate_key(config: dict, plain_field: str, enc_field: str) -> bool:
    """Migrate a plain-text key to encrypted storage. Returns True if config was changed."""
    plain = config.get(plain_field, "")
    if plain and enc_field not in config:
        config[enc_field] = encrypt(plain)
        del config[plain_field]
        return True
    return False


def get_api_key() -> str:
    config = load_config()
    # Try encrypted field first
    enc = config.get("api_key_enc", "")
    if enc:
        try:
            return decrypt(enc)
        except DecryptionError:
            config.pop("api_key_enc", None)
            save_config(config)
            return ""
    # Auto-migrate plain-text key
    if _migrate_key(config, "api_key", "api_key_enc"):
        save_config(config)
        return decrypt(config["api_key_enc"])
    return ""


def set_api_key(key: str):
    config = load_config()
    config.pop("api_key", None)
    config["api_key_enc"] = encrypt(key) if key else ""
    save_config(config)


def get_elevenlabs_api_key() -> str:
    config = load_config()
    enc = config.get("elevenlabs_api_key_enc", "")
    if enc:
        try:
            return decrypt(enc)
        except DecryptionError:
            config.pop("elevenlabs_api_key_enc", None)
            save_config(config)
            return ""
    if _migrate_key(config, "elevenlabs_api_key", "elevenlabs_api_key_enc"):
        save_config(config)
        return decrypt(config["elevenlabs_api_key_enc"])
    return ""


def set_elevenlabs_api_key(key: str):
    config = load_config()
    config.pop("elevenlabs_api_key", None)
    config["elevenlabs_api_key_enc"] = encrypt(key) if key else ""
    save_config(config)


def get_anthropic_api_key() -> str:
    config = load_config()
    enc = config.get("anthropic_api_key_enc", "")
    if enc:
        try:
            return decrypt(enc)
        except DecryptionError:
            config.pop("anthropic_api_key_enc", None)
            save_config(config)
            return ""
    if _migrate_key(config, "anthropic_api_key", "anthropic_api_key_enc"):
        save_config(config)
        return decrypt(config["anthropic_api_key_enc"])
    return ""


def set_anthropic_api_key(key: str):
    config = load_config()
    config.pop("anthropic_api_key", None)
    config["anthropic_api_key_enc"] = encrypt(key) if key else ""
    save_config(config)


def get_soniox_api_key() -> str:
    config = load_config()
    enc = config.get("soniox_api_key_enc", "")
    if enc:
        try:
            return decrypt(enc)
        except DecryptionError:
            config.pop("soniox_api_key_enc", None)
            save_config(config)
            return ""
    if _migrate_key(config, "soniox_api_key", "soniox_api_key_enc"):
        save_config(config)
        return decrypt(config["soniox_api_key_enc"])
    return ""


def set_soniox_api_key(key: str):
    config = load_config()
    config.pop("soniox_api_key", None)
    config["soniox_api_key_enc"] = encrypt(key) if key else ""
    save_config(config)


def get_tts_engine() -> str:
    return load_config().get("tts_engine", DEFAULT_TTS_ENGINE)


def set_tts_engine(engine: str):
    config = load_config()
    config["tts_engine"] = engine
    save_config(config)


def get_elevenlabs_voice() -> dict:
    """Selected ElevenLabs voice as {'name': ..., 'voice_id': ...}."""
    stored = load_config().get("elevenlabs_voice", {})
    if stored.get("voice_id"):
        return stored
    return dict(ELEVENLABS_DEFAULT_VOICES[0])


def set_elevenlabs_voice(name: str, voice_id: str):
    config = load_config()
    config["elevenlabs_voice"] = {"name": name, "voice_id": voice_id}
    save_config(config)


def get_elevenlabs_tts_model() -> str:
    return load_config().get("elevenlabs_tts_model", DEFAULT_ELEVENLABS_TTS_MODEL)


def set_elevenlabs_tts_model(model: str):
    config = load_config()
    config["elevenlabs_tts_model"] = model
    save_config(config)


def get_cached_azure_voices() -> list:
    return load_config().get("azure_voices", [])


def set_cached_azure_voices(voices: list):
    config = load_config()
    config["azure_voices"] = voices
    save_config(config)


def get_cached_google_voices() -> list:
    return load_config().get("google_voices", [])


def set_cached_google_voices(voices: list):
    config = load_config()
    config["google_voices"] = voices
    save_config(config)


def get_cached_elevenlabs_voices() -> list:
    """Last fetched ElevenLabs voice list, or the built-in fallback."""
    cached = load_config().get("elevenlabs_voices", [])
    return cached if cached else [dict(v) for v in ELEVENLABS_DEFAULT_VOICES]


def set_cached_elevenlabs_voices(voices: list):
    config = load_config()
    config["elevenlabs_voices"] = voices
    save_config(config)


def is_anthropic_model(model: str) -> bool:
    """Return True if the model name is an Anthropic/Claude model."""
    return model.startswith("claude-")


def get_use_transcription() -> bool:
    return load_config().get("use_transcription", False)


def set_use_transcription(enabled: bool):
    config = load_config()
    config["use_transcription"] = enabled
    save_config(config)


def get_transcription_engine() -> str:
    return load_config().get("transcription_engine", DEFAULT_TRANSCRIPTION_ENGINE)


def set_transcription_engine(engine: str):
    config = load_config()
    config["transcription_engine"] = engine
    save_config(config)


def get_azure_api_key() -> str:
    config = load_config()
    enc = config.get("azure_api_key_enc", "")
    if enc:
        try:
            return decrypt(enc)
        except DecryptionError:
            config.pop("azure_api_key_enc", None)
            save_config(config)
            return ""
    if _migrate_key(config, "azure_api_key", "azure_api_key_enc"):
        save_config(config)
        return decrypt(config["azure_api_key_enc"])
    return ""


def set_azure_api_key(key: str):
    config = load_config()
    config.pop("azure_api_key", None)
    config["azure_api_key_enc"] = encrypt(key) if key else ""
    save_config(config)


def get_azure_region() -> str:
    return load_config().get("azure_region", DEFAULT_AZURE_REGION)


def set_azure_region(region: str):
    config = load_config()
    config["azure_region"] = region
    save_config(config)


def get_google_api_key() -> str:
    config = load_config()
    enc = config.get("google_api_key_enc", "")
    if enc:
        try:
            return decrypt(enc)
        except DecryptionError:
            config.pop("google_api_key_enc", None)
            save_config(config)
            return ""
    if _migrate_key(config, "google_api_key", "google_api_key_enc"):
        save_config(config)
        return decrypt(config["google_api_key_enc"])
    return ""


def set_google_api_key(key: str):
    config = load_config()
    config.pop("google_api_key", None)
    config["google_api_key_enc"] = encrypt(key) if key else ""
    save_config(config)


def get_piper_voice() -> str:
    """Selected Piper voice as a catalog key, e.g. "en_US-amy-medium"."""
    config = load_config()
    stored = config.get("piper_voice", "")
    if stored:
        return stored
    # Pre-catalog configs stored a display name like "Amy (US, Medium)".
    return LEGACY_VOICE_NAMES.get(config.get("voice", ""), DEFAULT_PIPER_VOICE)


def set_piper_voice(voice_key: str):
    config = load_config()
    config["piper_voice"] = voice_key
    config.pop("voice", None)
    save_config(config)


def get_openai_tts_voice() -> str:
    return load_config().get("openai_tts_voice", DEFAULT_OPENAI_TTS_VOICE)


def set_openai_tts_voice(voice: str):
    config = load_config()
    config["openai_tts_voice"] = voice
    save_config(config)


def get_openai_tts_model() -> str:
    return load_config().get("openai_tts_model", DEFAULT_OPENAI_TTS_MODEL)


def set_openai_tts_model(model: str):
    config = load_config()
    config["openai_tts_model"] = model
    save_config(config)


def get_azure_voice() -> str:
    return load_config().get("azure_voice", "")


def set_azure_voice(voice: str):
    config = load_config()
    config["azure_voice"] = voice
    save_config(config)


def get_google_voice() -> str:
    return load_config().get("google_voice", "")


def set_google_voice(voice: str):
    config = load_config()
    config["google_voice"] = voice
    save_config(config)


def check_ffmpeg() -> bool:
    return check_tool("ffmpeg")


def get_translation_prompt_raw(language_name: str) -> str:
    """Get the raw translation prompt template (custom or default) without substitution.
    Use this for editing in the UI."""
    config = load_config()
    custom_prompts = config.get("custom_translation_prompts", {})
    if language_name in custom_prompts:
        return custom_prompts[language_name]
    lang_config = get_language_config(language_name)
    return lang_config["translation_prompt"]


def get_translation_prompt(language_name: str, target_language: str | None = None) -> str:
    """Get the effective translation prompt (custom or default) with {LANGUAGE}
    and {TARGET_LANGUAGE} substituted. Use this for actual translation API calls."""
    prompt = get_translation_prompt_raw(language_name)
    target = target_language or get_target_language()
    return prompt.replace("{LANGUAGE}", language_name).replace("{TARGET_LANGUAGE}", target)


def set_custom_translation_prompt(language_name: str, prompt: str):
    """Save a custom translation prompt for a language."""
    config = load_config()
    if "custom_translation_prompts" not in config:
        config["custom_translation_prompts"] = {}
    config["custom_translation_prompts"][language_name] = prompt
    save_config(config)


def reset_translation_prompt(language_name: str):
    """Remove custom translation prompt, reverting to default."""
    config = load_config()
    custom_prompts = config.get("custom_translation_prompts", {})
    if language_name in custom_prompts:
        del custom_prompts[language_name]
        config["custom_translation_prompts"] = custom_prompts
        save_config(config)


def get_punctuation_prompt_raw(language_name: str) -> str:
    """Get the raw punctuation prompt template (custom or default) without substitution.
    Use this for editing in the UI."""
    config = load_config()
    custom_prompts = config.get("custom_punctuation_prompts", {})
    if language_name in custom_prompts:
        return custom_prompts[language_name]
    lang_config = get_language_config(language_name)
    return lang_config["punctuation_prompt"]


def get_punctuation_prompt(language_name: str) -> str:
    """Get the effective punctuation prompt (custom or default) with {LANGUAGE} substituted.
    Use this for actual punctuation API calls."""
    prompt = get_punctuation_prompt_raw(language_name)
    # Substitute {LANGUAGE} placeholder with actual language name
    return prompt.replace("{LANGUAGE}", language_name)


def set_custom_punctuation_prompt(language_name: str, prompt: str):
    """Save a custom punctuation prompt for a language."""
    config = load_config()
    if "custom_punctuation_prompts" not in config:
        config["custom_punctuation_prompts"] = {}
    config["custom_punctuation_prompts"][language_name] = prompt
    save_config(config)


def reset_punctuation_prompt(language_name: str):
    """Remove custom punctuation prompt, reverting to default."""
    config = load_config()
    custom_prompts = config.get("custom_punctuation_prompts", {})
    if language_name in custom_prompts:
        del custom_prompts[language_name]
        config["custom_punctuation_prompts"] = custom_prompts
        save_config(config)


def get_translation_model() -> str:
    """Get the AI model used for translation."""
    return load_config().get("translation_model", DEFAULT_AI_MODEL)


def set_translation_model(model: str):
    """Set the AI model used for translation."""
    config = load_config()
    config["translation_model"] = model
    save_config(config)


def get_punctuation_model() -> str:
    """Get the AI model used for punctuation."""
    return load_config().get("punctuation_model", DEFAULT_AI_MODEL)


def set_punctuation_model(model: str):
    """Set the AI model used for punctuation."""
    config = load_config()
    config["punctuation_model"] = model
    save_config(config)


DEFAULT_SUMMARY_PROMPT = (
    "You are a content summarizer for {LANGUAGE} audio content.\n\n"
    "You will receive a numbered list of {LANGUAGE} sentences from a video transcript.\n"
    "Group them into coherent topical chunks and provide a concise {TARGET_LANGUAGE} summary for each chunk.\n\n"
    "Rules:\n"
    "- Find natural breakpoints where the topic, scene, or speaker changes\n"
    "- Each chunk should contain 3-15 sentences\n"
    "- Write a concise {TARGET_LANGUAGE} summary (1-3 sentences) capturing the key meaning\n"
    "- The summary should help a listener understand what they are about to hear\n"
    "- Every sentence must belong to exactly one chunk (no gaps, no overlaps)\n\n"
    "Return ONLY valid JSON:\n"
    "[\n"
    '  {"start": 1, "end": 5, "summary": "The speaker introduces themselves."},\n'
    '  {"start": 6, "end": 12, "summary": "Discussion of the main topic."}\n'
    "]\n\n"
    "start/end are 1-based sentence numbers (inclusive). Chunks must be contiguous."
)


def get_summary_prompt_raw(language_name: str) -> str:
    """Get the raw summary prompt template (custom or default) without substitution."""
    config = load_config()
    custom_prompts = config.get("custom_summary_prompts", {})
    if language_name in custom_prompts:
        return custom_prompts[language_name]
    return DEFAULT_SUMMARY_PROMPT


def get_summary_prompt(language_name: str, target_language: str | None = None) -> str:
    """Get the effective summary prompt with {LANGUAGE} and {TARGET_LANGUAGE} substituted."""
    prompt = get_summary_prompt_raw(language_name)
    target = target_language or get_target_language()
    return prompt.replace("{LANGUAGE}", language_name).replace("{TARGET_LANGUAGE}", target)


def set_custom_summary_prompt(language_name: str, prompt: str):
    """Save a custom summary prompt for a language."""
    config = load_config()
    if "custom_summary_prompts" not in config:
        config["custom_summary_prompts"] = {}
    config["custom_summary_prompts"][language_name] = prompt
    save_config(config)


def reset_summary_prompt(language_name: str):
    """Remove custom summary prompt, reverting to default."""
    config = load_config()
    custom_prompts = config.get("custom_summary_prompts", {})
    if language_name in custom_prompts:
        del custom_prompts[language_name]
        config["custom_summary_prompts"] = custom_prompts
        save_config(config)


def get_summary_model() -> str:
    """Get the AI model used for summarization."""
    return load_config().get("summary_model", DEFAULT_AI_MODEL)


def set_summary_model(model: str):
    """Set the AI model used for summarization."""
    config = load_config()
    config["summary_model"] = model
    save_config(config)


def get_lemma_list_path() -> str:
    """Get the path to the user's lemma list file."""
    return load_config().get("lemma_list_path", "")


def set_lemma_list_path(path: str):
    """Set the path to the user's lemma list file."""
    config = load_config()
    config["lemma_list_path"] = path
    save_config(config)


@dataclass
class OutputConfig:
    """Configuration for a single output file."""
    format: str = "mp3"       # "mp3", "mp4", or "m4b"
    mode: str = "sentence"    # "sentence" or "summary"
    group_size: int = 1       # 1-99 (forced to 1 for summary)
    condensed: bool = False

    def label(self) -> str:
        parts = [self.format.upper(), self.mode.capitalize()]
        if self.group_size > 1:
            parts.append(f"Groups: {self.group_size}")
        if self.condensed:
            parts.append("Condensed")
        return " \u2022 ".join(parts)

    def filename(self, title: str) -> str:
        mode_tag = "interleaved" if self.mode == "sentence" else "summary"
        name = f"{title}_{mode_tag}"
        if self.condensed:
            name += "_condensed"
        if self.group_size > 1:
            name += f"_g{self.group_size}"
        return f"{name}.{self.format}"

    def work_dir_tag(self) -> str:
        tag = self.mode
        if self.condensed:
            tag += "_condensed"
        if self.group_size > 1:
            tag += f"_g{self.group_size}"
        return tag

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "OutputConfig":
        return cls(
            format=d.get("format", "mp3"),
            mode=d.get("mode", "sentence"),
            group_size=d.get("group_size", 1),
            condensed=d.get("condensed", False),
        )


DEFAULT_OUTPUT_CONFIGS = [OutputConfig()]


def migrate_output_configs(config: dict) -> list[dict]:
    """Migrate old-style config keys to output_configs list.

    If output_configs already exists, return it as-is.
    Otherwise build a single-entry list from legacy keys.
    """
    if "output_configs" in config:
        return config["output_configs"]
    fmt = "mp4" if config.get("video_output", False) else "mp3"
    mode = "summary" if config.get("summary_mode", False) else "sentence"
    group_size = config.get("sentences_per_group", 1)
    condensed = config.get("condense_audio", False)
    if mode == "summary":
        group_size = 1
    return [{"format": fmt, "mode": mode, "group_size": group_size, "condensed": condensed}]
