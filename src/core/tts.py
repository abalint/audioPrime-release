"""TTS engines.

One offline engine (Piper, via the piper-tts package) and four cloud engines
(OpenAI, Azure, Google, ElevenLabs). All present the same interface — ``tts_id``,
``cache_key``, ``synthesize_to_mp3`` — so they are drop-in replacements for each
other in the pipeline. Pick one with ``create_tts_engine``.
"""

import base64
import hashlib
import subprocess
import time
import wave
import xml.sax.saxutils as saxutils
from pathlib import Path

import requests
from piper import PiperVoice

from ..bin_paths import ffmpeg_path, _NOWWIN


class PiperTTS:
    """Wraps the piper-tts Python package for TTS synthesis."""

    def __init__(self, model_path):
        self.model_path = Path(model_path)
        self.model_name = self.model_path.stem
        self._voice = PiperVoice.load(str(self.model_path))

    @property
    def tts_id(self):
        """Stable identifier used in audio cache keys."""
        return f"piper|{self.model_name}"

    def cache_key(self, text):
        """MD5 hash including model name for unique caching."""
        key_input = f"{text}|piper|{self.model_name}"
        return hashlib.md5(key_input.encode()).hexdigest()[:10]

    def synthesize_to_mp3(self, text, output_path, logger=None, process_tracker=None):
        """Synthesize text to an mp3 file via piper Python API + ffmpeg convert."""
        t0 = time.monotonic()
        output_path = Path(output_path)
        wav_path = output_path.with_suffix(".wav")

        try:
            with wave.open(str(wav_path), "wb") as wav_file:
                self._voice.synthesize_wav(text, wav_file)
        except Exception as e:
            wav_path.unlink(missing_ok=True)
            raise RuntimeError(
                f"Piper synthesis failed for text {text[:80]!r}: {e}"
            ) from e

        if not wav_path.exists() or wav_path.stat().st_size == 0:
            wav_path.unlink(missing_ok=True)
            raise RuntimeError(f"Piper produced empty audio for text: {text[:80]!r}")

        _run = process_tracker.run if process_tracker else subprocess.run
        _run([
            ffmpeg_path(), "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(wav_path),
            "-acodec", "libmp3lame", "-q:a", "2",
            str(output_path),
        ], check=True, **_NOWWIN)

        wav_path.unlink(missing_ok=True)
        if logger:
            mp3_size = output_path.stat().st_size if output_path.exists() else 0
            logger.debug("TTS synthesized", chars=len(text), mp3_size_bytes=mp3_size,
                          elapsed_sec=round(time.monotonic() - t0, 3))


class _CloudTTS:
    """Shared retry and error handling for HTTP-based TTS engines.

    Subclasses supply ``_request_spec`` (what to POST) and, if the response is
    not raw audio bytes, ``_decode``. Everything else — retries with backoff on
    transient failures, empty-response detection, logging — is handled here.
    """

    TIMEOUT = 120
    MAX_RETRIES = 3
    RETRY_DELAYS = [2, 5, 10]
    RETRYABLE_STATUS = (429, 500, 502, 503, 504)
    provider = "cloud"

    def cache_key(self, text):
        key_input = f"{text}|{self.tts_id}"
        return hashlib.md5(key_input.encode()).hexdigest()[:10]

    def _request_spec(self, text):
        """Return kwargs for requests.post — url, headers, json/data, params."""
        raise NotImplementedError

    def _decode(self, response):
        """Extract mp3 bytes from a successful response. Default: raw body."""
        return response.content

    def _error_hint(self, status, detail):
        """Provider-specific guidance for a non-retryable error status."""
        return None

    def synthesize_to_mp3(self, text, output_path, logger=None, process_tracker=None):
        """Synthesize text directly to an mp3 file via the provider's API."""
        t0 = time.monotonic()
        output_path = Path(output_path)
        spec = self._request_spec(text)

        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                response = requests.post(timeout=self.TIMEOUT, **spec)
            except requests.RequestException as e:
                last_error = RuntimeError(f"{self.provider} TTS network error: {e}")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAYS[attempt])
                    continue
                raise last_error

            if response.status_code == 200:
                audio = self._decode(response)
                if not audio:
                    raise RuntimeError(
                        f"{self.provider} produced empty audio for text: {text[:80]!r}")
                output_path.write_bytes(audio)
                if logger:
                    logger.debug(f"TTS synthesized ({self.provider})", chars=len(text),
                                  mp3_size_bytes=len(audio),
                                  elapsed_sec=round(time.monotonic() - t0, 3))
                return

            if response.status_code in self.RETRYABLE_STATUS and attempt < self.MAX_RETRIES - 1:
                last_error = RuntimeError(
                    f"{self.provider} TTS transient error (HTTP {response.status_code})")
                time.sleep(self.RETRY_DELAYS[attempt])
                continue

            try:
                detail = str(response.json().get("detail", ""))[:200] or response.text[:200]
            except Exception:
                detail = response.text[:200]
            hint = self._error_hint(response.status_code, detail)
            if hint:
                raise RuntimeError(hint)
            raise RuntimeError(
                f"{self.provider} TTS failed (HTTP {response.status_code}): {detail}")

        raise last_error


class OpenAITTS(_CloudTTS):
    """Cloud TTS via the OpenAI speech API.

    Reuses the OpenAI key already configured for translation, so it is the
    lowest-friction multilingual option — no extra signup. The models are
    multilingual by default; voice choice does not restrict language.
    """

    API_URL = "https://api.openai.com/v1/audio/speech"
    provider = "OpenAI"

    def __init__(self, api_key, voice, model=None):
        if not api_key:
            raise ValueError("OpenAI API key is required for OpenAI TTS")
        from ..config import DEFAULT_OPENAI_TTS_MODEL
        self.api_key = api_key
        self.voice = voice
        self.model = model or DEFAULT_OPENAI_TTS_MODEL
        self.model_name = f"{self.voice}/{self.model}"

    @property
    def tts_id(self):
        return f"openai|{self.voice}|{self.model}"

    def _request_spec(self, text):
        return {
            "url": self.API_URL,
            "headers": {"Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"},
            "json": {"model": self.model, "voice": self.voice,
                     "input": text, "response_format": "mp3"},
        }

    def _error_hint(self, status, detail):
        if status == 401:
            return ("Invalid OpenAI API key. Check your API key in the Settings tab. "
                    f"Details: {detail}")
        if status == 429:
            return ("OpenAI rate limit or quota exceeded. Check your billing at "
                    f"https://platform.openai.com/usage Details: {detail}")
        return None


class AzureTTS(_CloudTTS):
    """Cloud TTS via the Azure AI Speech API.

    Broadest language coverage of the options here (100+ locales, including the
    Japanese, Korean, Thai, Hebrew, Malay and Cantonese that Piper lacks) at
    roughly a tenth of ElevenLabs' cost.
    """

    API_URL = "https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
    provider = "Azure"

    def __init__(self, api_key, region, voice):
        if not api_key:
            raise ValueError("Azure Speech API key is required for Azure TTS")
        if not voice:
            raise ValueError("An Azure voice must be selected")
        self.api_key = api_key
        self.region = region
        self.voice = voice
        self.model_name = voice

    @property
    def tts_id(self):
        return f"azure|{self.voice}"

    def _request_spec(self, text):
        # Azure derives the speaking language from the voice's locale, so the
        # xml:lang here must match the voice or it falls back to en-US.
        locale = "-".join(self.voice.split("-")[:2])
        ssml = (
            f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xml:lang="{locale}">'
            f'<voice name="{self.voice}">{saxutils.escape(text)}</voice>'
            f'</speak>'
        )
        return {
            "url": self.API_URL.format(region=self.region),
            "headers": {
                "Ocp-Apim-Subscription-Key": self.api_key,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3",
                "User-Agent": "audioPrime",
            },
            "data": ssml.encode("utf-8"),
        }

    def _error_hint(self, status, detail):
        if status == 401:
            return ("Invalid Azure Speech API key. Check the key and region in the "
                    f"Settings tab. Details: {detail}")
        if status == 403:
            return ("Azure Speech rejected the request — this usually means the key "
                    f"does not match the selected region ({self.region}). Details: {detail}")
        return None


class GoogleTTS(_CloudTTS):
    """Cloud TTS via the Google Cloud Text-to-Speech API.

    Cheapest cloud option by a wide margin, with an ongoing free monthly tier.
    Authenticated with a plain API key rather than a service-account JSON.
    """

    API_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
    provider = "Google"

    def __init__(self, api_key, voice):
        if not api_key:
            raise ValueError("Google Cloud API key is required for Google TTS")
        if not voice:
            raise ValueError("A Google voice must be selected")
        self.api_key = api_key
        self.voice = voice
        self.model_name = voice

    @property
    def tts_id(self):
        return f"google|{self.voice}"

    def _request_spec(self, text):
        language_code = "-".join(self.voice.split("-")[:2])
        return {
            "url": self.API_URL,
            "params": {"key": self.api_key},
            "headers": {"Content-Type": "application/json"},
            "json": {
                "input": {"text": text},
                "voice": {"languageCode": language_code, "name": self.voice},
                "audioConfig": {"audioEncoding": "MP3"},
            },
        }

    def _decode(self, response):
        # Google returns base64-encoded audio inside a JSON envelope.
        encoded = response.json().get("audioContent", "")
        return base64.b64decode(encoded) if encoded else b""

    def _error_hint(self, status, detail):
        if status in (401, 403):
            return ("Google Cloud rejected the API key. Check that the key is valid "
                    "and that the Text-to-Speech API is enabled for your project. "
                    f"Details: {detail}")
        return None


class ElevenLabsTTS(_CloudTTS):
    """Cloud TTS via the ElevenLabs text-to-speech API.

    Highest quality and highest cost. Uses a multilingual model so any voice can
    speak any supported language.
    """

    API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    provider = "ElevenLabs"

    def __init__(self, api_key, voice_id, voice_name="", model_id=None):
        if not api_key:
            raise ValueError("ElevenLabs API key is required for ElevenLabs TTS")
        if not voice_id:
            raise ValueError("An ElevenLabs voice must be selected")
        from ..config import get_elevenlabs_tts_model
        self.api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id or get_elevenlabs_tts_model()
        # model_name mirrors PiperTTS for logging/labels
        self.model_name = voice_name or voice_id

    @property
    def tts_id(self):
        return f"elevenlabs|{self.voice_id}|{self.model_id}"

    def _request_spec(self, text):
        return {
            "url": self.API_URL.format(voice_id=self.voice_id),
            "headers": {"xi-api-key": self.api_key, "Content-Type": "application/json"},
            "json": {"text": text, "model_id": self.model_id},
            "params": {"output_format": "mp3_44100_128"},
        }

    def _error_hint(self, status, detail):
        if status == 401:
            return ("Invalid ElevenLabs API key. Check your API key in the Settings tab. "
                    f"Details: {detail}")
        if status == 402:
            return ("Insufficient ElevenLabs credits for TTS. "
                    f"Add credits at https://elevenlabs.io/app/credits Details: {detail}")
        return None


def fetch_elevenlabs_voices(api_key, timeout=15):
    """Fetch the account's voice list from the ElevenLabs API.

    Returns a list of {"name": ..., "voice_id": ...} dicts.
    Raises RuntimeError on failure — callers fall back to cached/default voices.
    """
    response = requests.get(
        "https://api.elevenlabs.io/v1/voices",
        headers={"xi-api-key": api_key},
        timeout=timeout,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Could not fetch ElevenLabs voices (HTTP {response.status_code})")
    voices = []
    for v in response.json().get("voices", []):
        name = v.get("name")
        voice_id = v.get("voice_id")
        if name and voice_id:
            labels = v.get("labels") or {}
            lang = labels.get("language") or labels.get("accent") or ""
            display = f"{name} ({lang})" if lang else name
            voices.append({"name": display, "voice_id": voice_id})
    if not voices:
        raise RuntimeError("ElevenLabs returned no voices")
    return voices


def fetch_azure_voices(api_key, region, timeout=15):
    """Fetch the Azure voice catalog for a region.

    Returns [{"name": display, "voice_id": short_name, "locale": locale}, ...].
    """
    response = requests.get(
        f"https://{region}.tts.speech.microsoft.com/cognitiveservices/voices/list",
        headers={"Ocp-Apim-Subscription-Key": api_key},
        timeout=timeout,
    )
    if response.status_code == 401:
        raise RuntimeError("Invalid Azure Speech API key")
    if response.status_code != 200:
        raise RuntimeError(f"Could not fetch Azure voices (HTTP {response.status_code})")

    voices = []
    for v in response.json():
        short_name = v.get("ShortName")
        if not short_name:
            continue
        label = v.get("LocalName") or v.get("DisplayName") or short_name
        gender = v.get("Gender", "")
        locale_name = v.get("LocaleName", v.get("Locale", ""))
        display = f"{label} ({locale_name}{', ' + gender if gender else ''})"
        voices.append({"name": display, "voice_id": short_name,
                       "locale": v.get("Locale", "")})
    if not voices:
        raise RuntimeError("Azure returned no voices")
    return voices


def fetch_google_voices(api_key, timeout=15):
    """Fetch the Google Cloud TTS voice catalog.

    Returns [{"name": display, "voice_id": name, "locale": locale}, ...].
    """
    response = requests.get(
        "https://texttospeech.googleapis.com/v1/voices",
        params={"key": api_key},
        timeout=timeout,
    )
    if response.status_code in (401, 403):
        raise RuntimeError(
            "Google Cloud rejected the API key — check that it is valid and that "
            "the Text-to-Speech API is enabled")
    if response.status_code != 200:
        raise RuntimeError(f"Could not fetch Google voices (HTTP {response.status_code})")

    voices = []
    for v in response.json().get("voices", []):
        name = v.get("name")
        locales = v.get("languageCodes") or []
        if not name or not locales:
            continue
        gender = (v.get("ssmlGender") or "").title()
        # Strip the locale prefix from the name to keep the label readable:
        # "en-US-Neural2-A" -> "Neural2-A".
        short = name[len(locales[0]) + 1:] if name.startswith(locales[0]) else name
        display = f"{short} ({locales[0]}{', ' + gender if gender else ''})"
        voices.append({"name": display, "voice_id": name, "locale": locales[0]})
    if not voices:
        raise RuntimeError("Google returned no voices")
    return voices


def create_tts_engine(voice_name=None, status_cb=None):
    """Create the configured TTS engine.

    Reads the TTS engine preference from config (mirrors how AI model
    selections are read inside the pipeline). ``voice_name`` is accepted for
    backward compatibility but each engine now stores its own voice selection.

    Piper voices other than the bundled default are downloaded on first use;
    ``status_cb(message)`` reports progress while that happens.
    """
    from ..config import (
        get_azure_api_key,
        get_azure_region,
        get_azure_voice,
        get_elevenlabs_api_key,
        get_elevenlabs_voice,
        get_google_api_key,
        get_google_voice,
        get_openai_tts_model,
        get_openai_tts_voice,
        get_api_key,
        get_piper_voice,
        get_tts_engine,
    )

    engine = get_tts_engine()

    if engine == "ElevenLabs (Cloud)":
        api_key = get_elevenlabs_api_key()
        if not api_key:
            raise RuntimeError(
                "ElevenLabs TTS is selected but no ElevenLabs API key is provided. "
                "Add your API key in the Settings tab, or switch the TTS engine "
                "back to Piper (Offline).")
        voice = get_elevenlabs_voice()
        return ElevenLabsTTS(api_key, voice["voice_id"], voice_name=voice["name"])

    if engine == "OpenAI (Cloud)":
        api_key = get_api_key()
        if not api_key:
            raise RuntimeError(
                "OpenAI TTS is selected but no OpenAI API key is provided. "
                "Add your API key in the Settings tab, or switch the TTS engine "
                "back to Piper (Offline).")
        return OpenAITTS(api_key, get_openai_tts_voice(), get_openai_tts_model())

    if engine == "Azure (Cloud)":
        api_key = get_azure_api_key()
        if not api_key:
            raise RuntimeError(
                "Azure TTS is selected but no Azure Speech API key is provided. "
                "Add your API key and region in the Settings tab, or switch the "
                "TTS engine back to Piper (Offline).")
        voice = get_azure_voice()
        if not voice:
            raise RuntimeError(
                "Azure TTS is selected but no voice has been chosen. Pick a voice "
                "next to the TTS engine on the Process tab.")
        return AzureTTS(api_key, get_azure_region(), voice)

    if engine == "Google (Cloud)":
        api_key = get_google_api_key()
        if not api_key:
            raise RuntimeError(
                "Google TTS is selected but no Google Cloud API key is provided. "
                "Add your API key in the Settings tab, or switch the TTS engine "
                "back to Piper (Offline).")
        voice = get_google_voice()
        if not voice:
            raise RuntimeError(
                "Google TTS is selected but no voice has been chosen. Pick a voice "
                "next to the TTS engine on the Process tab.")
        return GoogleTTS(api_key, voice)

    return _create_piper_engine(get_piper_voice(), status_cb)


def _create_piper_engine(voice_key, status_cb=None):
    """Load a Piper voice, downloading it from the catalog if not present."""
    from . import voice_manager

    voice = voice_manager.get_voice(voice_key)
    if voice is None:
        raise RuntimeError(
            f"Unknown Piper voice: {voice_key}. Pick a voice on the Process tab.")

    if not voice_manager.is_downloaded(voice):
        size_mb = voice_manager.voice_size_mb(voice)
        label = voice_manager.display_name(voice)

        def on_progress(done, total):
            if status_cb and total:
                status_cb(f"Downloading voice {label} — "
                          f"{done / (1024 * 1024):.0f}/{size_mb:.0f} MB")

        if status_cb:
            status_cb(f"Downloading voice {label} ({size_mb:.0f} MB)...")
        voice_manager.ensure_voice(voice, progress_cb=on_progress)

    return PiperTTS(str(voice_manager.local_path(voice)))
