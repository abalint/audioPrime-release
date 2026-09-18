"""Transcription engines for videos without subtitles.

Supports:
- ElevenLabs Scribe V2 (cloud API, all languages)
- Soniox stt-async (cloud API, 60+ languages)
- ReazonSpeech k2-v2 (offline, Japanese only)
"""

import json
import time
from pathlib import Path
from typing import Callable, Optional

import requests


class TranscriptionError(Exception):
    """Raised when transcription fails."""
    pass


# Map audioPrime language codes to ElevenLabs ISO-639-3 codes
LANGUAGE_CODE_MAP = {
    "ar": "ara",      # Arabic
    "bn": "ben",      # Bengali
    "yue": "yue",     # Cantonese
    "zh-Hans": "zho", # Chinese (Simplified)
    "zh-Hant": "zho", # Chinese (Traditional)
    "zh-TW": "zho",   # Chinese (Taiwanese)
    "cs": "ces",      # Czech
    "da": "dan",      # Danish
    "nl": "nld",      # Dutch
    "en": "eng",      # English
    "fi": "fin",      # Finnish
    "fr": "fra",      # French
    "de": "deu",      # German
    "el": "ell",      # Greek
    "he": "heb",      # Hebrew
    "hi": "hin",      # Hindi
    "hu": "hun",      # Hungarian
    "id": "ind",      # Indonesian
    "it": "ita",      # Italian
    "ja": "jpn",      # Japanese
    "ko": "kor",      # Korean
    "ms": "msa",      # Malay
    "no": "nor",      # Norwegian
    "pl": "pol",      # Polish
    "pt": "por",      # Portuguese
    "ro": "ron",      # Romanian
    "ru": "rus",      # Russian
    "es": "spa",      # Spanish
    "sv": "swe",      # Swedish
    "th": "tha",      # Thai
    "tr": "tur",      # Turkish
    "uk": "ukr",      # Ukrainian
    "vi": "vie",      # Vietnamese
}


class ElevenLabsTranscriber:
    """Transcribe audio using ElevenLabs Scribe V2 API."""

    API_URL = "https://api.elevenlabs.io/v1/speech-to-text"
    TIMEOUT = 600  # 10 minutes for long videos
    MAX_RETRIES = 3
    RETRY_DELAYS = [2, 5, 10]  # Exponential backoff in seconds

    def __init__(self, api_key: str):
        """Initialize transcriber with API key.

        Args:
            api_key: ElevenLabs API key (starts with 'xi_')
        """
        if not api_key:
            raise ValueError("ElevenLabs API key is required")
        self.api_key = api_key

    def transcribe(
        self,
        audio_path: Path,
        language_code: str,
        progress_callback: Optional[Callable[[str], None]] = None,
        cancelled_check=None,
    ) -> dict:
        """Transcribe audio file using ElevenLabs Scribe V2.

        Args:
            audio_path: Path to audio file (mp3, m4a, wav, etc.)
            language_code: audioPrime language code (e.g., 'ja', 'ko', 'es')
            progress_callback: Optional callback for progress updates

        Returns:
            API response dict with word-level transcription

        Raises:
            TranscriptionError: If transcription fails after retries
        """
        # Map language code
        elevenlabs_lang = LANGUAGE_CODE_MAP.get(language_code)
        if not elevenlabs_lang:
            raise TranscriptionError(
                f"Unsupported language code: {language_code}. "
                f"Supported codes: {', '.join(LANGUAGE_CODE_MAP.keys())}"
            )

        if progress_callback:
            progress_callback(f"Transcribing audio (language: {elevenlabs_lang})...")

        # Prepare request
        headers = {"xi-api-key": self.api_key}
        data = {"model_id": "scribe_v2", "language": elevenlabs_lang}

        # Open audio file
        if not audio_path.exists():
            raise TranscriptionError(f"Audio file not found: {audio_path}")

        from .process_tracker import CancelledError, interruptible_sleep

        # Retry logic
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            if cancelled_check and cancelled_check():
                raise CancelledError("Operation cancelled")
            try:
                with open(audio_path, "rb") as audio_file:
                    files = {"file": (audio_path.name, audio_file, "audio/mpeg")}

                    if attempt > 0 and progress_callback:
                        progress_callback(
                            f"Retrying transcription (attempt {attempt + 1}/{self.MAX_RETRIES})..."
                        )

                    response = requests.post(
                        self.API_URL,
                        headers=headers,
                        data=data,
                        files=files,
                        timeout=self.TIMEOUT
                    )

                    # Handle response
                    if response.status_code == 200:
                        if progress_callback:
                            progress_callback("Transcription successful")
                        return response.json()

                    # Handle errors
                    error_msg = self._parse_error(response)

                    # Retry on transient errors
                    if response.status_code in [429, 500, 502, 503, 504]:
                        last_error = TranscriptionError(error_msg)
                        if attempt < self.MAX_RETRIES - 1:
                            delay = self.RETRY_DELAYS[attempt]
                            if progress_callback:
                                progress_callback(
                                    f"Transient error, retrying in {delay}s: {error_msg}"
                                )
                            interruptible_sleep(delay, cancelled_check)
                            continue

                    # Don't retry on permanent errors
                    raise TranscriptionError(error_msg)

            except requests.Timeout:
                last_error = TranscriptionError(
                    f"Transcription timed out after {self.TIMEOUT}s. "
                    "The audio file may be too long. Try a shorter video."
                )
                if attempt < self.MAX_RETRIES - 1:
                    if progress_callback:
                        progress_callback(f"Timeout, retrying...")
                    interruptible_sleep(self.RETRY_DELAYS[attempt], cancelled_check)
                    continue

            except requests.RequestException as e:
                last_error = TranscriptionError(f"Network error: {e}")
                if attempt < self.MAX_RETRIES - 1:
                    if progress_callback:
                        progress_callback(f"Network error, retrying...")
                    interruptible_sleep(self.RETRY_DELAYS[attempt], cancelled_check)
                    continue

        # All retries exhausted
        raise last_error

    def _parse_error(self, response: requests.Response) -> str:
        """Parse error message from API response."""
        try:
            error_data = response.json()
            error_detail = error_data.get("detail", {})

            if isinstance(error_detail, dict):
                message = error_detail.get("message", str(error_detail))
            else:
                message = str(error_detail)
        except:
            message = response.text or f"HTTP {response.status_code}"

        # Add helpful context for common errors
        if response.status_code == 401:
            return (
                "Invalid ElevenLabs API key. "
                "Check your API key in Settings tab. "
                f"Details: {message}"
            )
        elif response.status_code == 402:
            return (
                "Insufficient ElevenLabs credits. "
                "Add credits at https://elevenlabs.io/app/credits "
                f"Details: {message}"
            )
        elif response.status_code == 413:
            return (
                "Audio file too large (max 3GB). "
                "Try a shorter video. "
                f"Details: {message}"
            )
        elif response.status_code == 429:
            return f"Rate limit exceeded. Retrying... Details: {message}"
        else:
            return f"API error (HTTP {response.status_code}): {message}"


def words_to_srt(words: list[dict], max_duration: float = 5.0, separator: str = " ") -> str:
    """Convert word-level timestamps to SRT format.

    Groups words into subtitle blocks with max duration to avoid
    one-word-per-line subtitles.

    Args:
        words: List of word dicts with 'text', 'start', 'end' keys
        max_duration: Maximum duration per subtitle block (seconds)
        separator: String used to join words in each block (use "" for Japanese)

    Returns:
        SRT formatted string
    """
    if not words:
        return ""

    srt_lines = []
    subtitle_index = 1

    current_block = []
    block_start = None
    block_end = None

    for word in words:
        word_text = word.get("text", "")
        word_start = word.get("start", 0.0)
        word_end = word.get("end", 0.0)

        if not word_text.strip():
            continue

        # Start new block
        if not current_block:
            current_block = [word_text]
            block_start = word_start
            block_end = word_end
        # Check if adding this word exceeds max duration
        elif (word_end - block_start) > max_duration:
            # Write current block
            srt_lines.append(_format_srt_block(subtitle_index, block_start, block_end, current_block, separator))
            subtitle_index += 1

            # Start new block with this word
            current_block = [word_text]
            block_start = word_start
            block_end = word_end
        else:
            # Add to current block
            current_block.append(word_text)
            block_end = word_end

    # Write final block
    if current_block:
        srt_lines.append(_format_srt_block(subtitle_index, block_start, block_end, current_block, separator))

    return "\n".join(srt_lines)


def _format_srt_block(index: int, start: float, end: float, words: list[str], separator: str = " ") -> str:
    """Format a single SRT subtitle block."""
    text = separator.join(words)
    start_time = _seconds_to_srt_time(start)
    end_time = _seconds_to_srt_time(end)
    return f"{index}\n{start_time} --> {end_time}\n{text}\n"


def _seconds_to_srt_time(seconds: float) -> str:
    """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def transcribe_audio_to_srt(
    audio_path: Path,
    output_srt_path: Path,
    language_code: str,
    api_key: str,
    progress_callback: Optional[Callable[[str], None]] = None,
    logger=None,
    cancelled_check=None,
) -> None:
    """Transcribe audio file to SRT subtitle file.

    Convenience function that handles the full transcription workflow.

    Args:
        audio_path: Path to audio file
        output_srt_path: Path where SRT file should be saved
        language_code: audioPrime language code (e.g., 'ja', 'ko', 'es')
        api_key: ElevenLabs API key
        progress_callback: Optional callback for progress updates

    Raises:
        TranscriptionError: If transcription fails
    """
    # Initialize transcriber
    transcriber = ElevenLabsTranscriber(api_key)

    # Transcribe
    response = transcriber.transcribe(audio_path, language_code, progress_callback,
                                      cancelled_check=cancelled_check)

    # Extract words from response
    words = response.get("words", [])
    if not words:
        raise TranscriptionError("No transcription data returned from API")

    if logger:
        logger.debug("ElevenLabs transcription complete", word_count=len(words),
                      language_code=language_code)

    # Convert to SRT
    if progress_callback:
        progress_callback("Converting transcription to SRT format...")

    srt_content = words_to_srt(words)

    # Write to file
    output_srt_path.parent.mkdir(parents=True, exist_ok=True)
    output_srt_path.write_text(srt_content, encoding="utf-8")

    if progress_callback:
        progress_callback(f"Transcription saved to {output_srt_path.name}")


# ---------------------------------------------------------------------------
# Soniox async file transcription (cloud, 60+ languages)
# ---------------------------------------------------------------------------

# Languages Soniox accepts as ISO 639-1 hints. audioPrime codes like
# "zh-Hans" / "zh-TW" map to their base code.
_SONIOX_LANG_OVERRIDES = {
    "zh-Hans": "zh",
    "zh-Hant": "zh",
    "zh-TW": "zh",
    "yue": "zh",
}

# CJK languages have no whitespace between words, so token grouping falls
# back to time-gap splitting for these.
_CJK_LANG_CODES = {"ja", "zh", "yue", "ko"}


def _soniox_language_hint(language_code: str) -> str:
    return _SONIOX_LANG_OVERRIDES.get(language_code, language_code)


def _soniox_tokens_to_words(tokens, cjk=False, gap_threshold=0.5, max_word_sec=2.0):
    """Group Soniox subword tokens into word dicts for words_to_srt().

    Soniox tokens are subwords whose text carries its own leading whitespace.
    A new word starts when a token begins with whitespace, or (for CJK text
    without spaces) when there is a time gap or the group grows too long.
    """
    words = []
    current_text = ""
    current_start = None
    current_end = None

    def _flush():
        nonlocal current_text, current_start, current_end
        if current_text.strip():
            words.append({
                "text": current_text.strip(),
                "start": current_start,
                "end": current_end,
            })
        current_text = ""
        current_start = None
        current_end = None

    for tok in tokens:
        text = tok.get("text", "")
        if not text:
            continue
        start = tok.get("start_ms", 0) / 1000.0
        end = tok.get("end_ms", 0) / 1000.0

        boundary = False
        if current_text:
            if text[0].isspace():
                boundary = True
            elif cjk:
                gap = start - (current_end if current_end is not None else start)
                if gap > gap_threshold or (end - current_start) > max_word_sec:
                    boundary = True
        if boundary:
            _flush()

        if not current_text:
            current_start = start
        current_text += text
        current_end = end

    _flush()
    return words


class SonioxTranscriber:
    """Transcribe audio using the Soniox async speech-to-text API."""

    API_BASE = "https://api.soniox.com"
    MODEL = "stt-async-v5"
    UPLOAD_TIMEOUT = 600
    REQUEST_TIMEOUT = 30
    POLL_INTERVAL = 3
    MAX_WAIT = 1800  # 30 minutes for very long files

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("Soniox API key is required")
        self.api_key = api_key
        self._headers = {"Authorization": f"Bearer {api_key}"}

    def _parse_error(self, response) -> str:
        try:
            data = response.json()
            message = data.get("message") or data.get("error_message") or str(data)
            error_type = data.get("error_type", "")
        except Exception:
            message = response.text[:300] or f"HTTP {response.status_code}"
            error_type = ""

        if response.status_code == 401:
            return f"Invalid Soniox API key. Check your API key in the Settings tab. Details: {message}"
        if response.status_code == 402:
            return f"Soniox balance exhausted. Add credits at https://console.soniox.com Details: {message}"
        if response.status_code == 429:
            return f"Soniox rate/storage limit exceeded ({error_type}): {message}"
        return f"Soniox API error (HTTP {response.status_code}): {message}"

    def _request(self, method, path, cancelled_check=None, **kwargs):
        """HTTP request with retries on transient failures."""
        from .process_tracker import CancelledError, interruptible_sleep

        timeout = kwargs.pop("timeout", self.REQUEST_TIMEOUT)
        last_error = None
        for delay in (0, 2, 5, 10):
            if cancelled_check and cancelled_check():
                raise CancelledError("Operation cancelled")
            if delay:
                interruptible_sleep(delay, cancelled_check)
            # Rewind file handles consumed by a failed upload attempt
            for value in (kwargs.get("files") or {}).values():
                fileobj = value[1] if isinstance(value, tuple) else value
                if hasattr(fileobj, "seek"):
                    fileobj.seek(0)
            try:
                response = requests.request(
                    method, f"{self.API_BASE}{path}", headers=self._headers,
                    timeout=timeout, **kwargs)
            except requests.RequestException as e:
                last_error = TranscriptionError(f"Soniox network error: {e}")
                continue
            if response.status_code in (500, 502, 503, 504):
                last_error = TranscriptionError(self._parse_error(response))
                continue
            if response.status_code >= 400:
                raise TranscriptionError(self._parse_error(response))
            return response
        raise last_error

    def transcribe(
        self,
        audio_path: Path,
        language_code: str,
        progress_callback: Optional[Callable[[str], None]] = None,
        cancelled_check=None,
    ) -> list[dict]:
        """Transcribe an audio file. Returns tokens with start_ms/end_ms.

        Flow: upload file -> create transcription -> poll -> fetch transcript
        -> delete transcription + file (Soniox does not auto-delete).
        """
        from .process_tracker import CancelledError, interruptible_sleep

        if not audio_path.exists():
            raise TranscriptionError(f"Audio file not found: {audio_path}")

        hint = _soniox_language_hint(language_code)

        if progress_callback:
            progress_callback("Uploading audio to Soniox...")
        with open(audio_path, "rb") as f:
            upload = self._request(
                "POST", "/v1/files",
                cancelled_check=cancelled_check,
                files={"file": (audio_path.name, f)},
                timeout=self.UPLOAD_TIMEOUT,
            )
        file_id = upload.json()["id"]

        transcription_id = None
        try:
            if progress_callback:
                progress_callback(f"Starting Soniox transcription (language hint: {hint})...")
            job = self._request(
                "POST", "/v1/transcriptions",
                cancelled_check=cancelled_check,
                json={
                    "model": self.MODEL,
                    "file_id": file_id,
                    "language_hints": [hint],
                },
            ).json()
            transcription_id = job["id"]

            waited = 0
            while True:
                if cancelled_check and cancelled_check():
                    raise CancelledError("Operation cancelled")
                status = self._request(
                    "GET", f"/v1/transcriptions/{transcription_id}",
                    cancelled_check=cancelled_check,
                ).json()
                state = status.get("status")
                if state == "completed":
                    break
                if state == "error":
                    raise TranscriptionError(
                        f"Soniox transcription failed ({status.get('error_type')}): "
                        f"{status.get('error_message')}"
                    )
                if waited >= self.MAX_WAIT:
                    raise TranscriptionError(
                        f"Soniox transcription timed out after {self.MAX_WAIT}s"
                    )
                if progress_callback:
                    progress_callback(f"Soniox transcription {state}...")
                interruptible_sleep(self.POLL_INTERVAL, cancelled_check)
                waited += self.POLL_INTERVAL

            transcript = self._request(
                "GET", f"/v1/transcriptions/{transcription_id}/transcript",
                cancelled_check=cancelled_check,
            ).json()
            tokens = transcript.get("tokens", [])
            if not tokens:
                raise TranscriptionError("No transcription data returned from Soniox")
            if progress_callback:
                progress_callback("Soniox transcription successful")
            return tokens
        finally:
            # Best-effort cleanup — stored files/transcriptions count against quota
            for method, path in (
                ("DELETE", f"/v1/transcriptions/{transcription_id}" if transcription_id else None),
                ("DELETE", f"/v1/files/{file_id}"),
            ):
                if path is None:
                    continue
                try:
                    requests.request(method, f"{self.API_BASE}{path}",
                                     headers=self._headers, timeout=self.REQUEST_TIMEOUT)
                except Exception:
                    pass


def soniox_transcribe_to_srt(
    audio_path: Path,
    output_srt_path: Path,
    language_code: str,
    api_key: str,
    progress_callback: Optional[Callable[[str], None]] = None,
    logger=None,
    cancelled_check=None,
) -> None:
    """Transcribe audio to an SRT file using Soniox.

    Convenience function parallel to transcribe_audio_to_srt().
    """
    transcriber = SonioxTranscriber(api_key)
    tokens = transcriber.transcribe(audio_path, language_code, progress_callback,
                                    cancelled_check=cancelled_check)

    cjk = _soniox_language_hint(language_code) in _CJK_LANG_CODES
    words = _soniox_tokens_to_words(tokens, cjk=cjk)
    if not words:
        raise TranscriptionError("No speech detected in audio")

    if logger:
        logger.debug("Soniox transcription complete", token_count=len(tokens),
                      word_count=len(words), language_code=language_code)

    if progress_callback:
        progress_callback("Converting transcription to SRT format...")

    srt_content = words_to_srt(words, separator="" if cjk else " ")

    output_srt_path.parent.mkdir(parents=True, exist_ok=True)
    output_srt_path.write_text(srt_content, encoding="utf-8")

    if progress_callback:
        progress_callback(f"Transcription saved to {output_srt_path.name}")


def resolve_transcription_engine(lang_code: str) -> str:
    """Determine which transcription engine to use for a language.

    Returns "elevenlabs", "soniox", or "reazonspeech". Shared by the
    downloader (URLs) and local-file paths.
    """
    from ..config import get_elevenlabs_api_key, get_soniox_api_key, get_transcription_engine

    pref = get_transcription_engine()
    if pref == "ReazonSpeech (Offline, Japanese)":
        if lang_code == "ja":
            return "reazonspeech"
        # Non-Japanese: fall back to a cloud engine
        return "elevenlabs" if get_elevenlabs_api_key() or not get_soniox_api_key() else "soniox"
    if pref == "Soniox (Cloud)":
        return "soniox"
    if pref == "ElevenLabs (Cloud)":
        return "elevenlabs"
    # "Auto": prefer whichever cloud key exists (ElevenLabs first for
    # backward compatibility); offline ReazonSpeech for Japanese when no
    # cloud key is available.
    if get_elevenlabs_api_key():
        return "elevenlabs"
    if get_soniox_api_key():
        return "soniox"
    if lang_code == "ja":
        return "reazonspeech"
    return "elevenlabs"


def cloud_transcribe_to_srt(
    engine: str,
    audio_path: Path,
    output_srt_path: Path,
    language_code: str,
    progress_callback: Optional[Callable[[str], None]] = None,
    logger=None,
    cancelled_check=None,
) -> None:
    """Dispatch to the selected cloud transcription engine ("elevenlabs"/"soniox").

    Raises TranscriptionError when the engine's API key is missing.
    """
    from ..config import get_elevenlabs_api_key, get_soniox_api_key

    if engine == "soniox":
        api_key = get_soniox_api_key()
        if not api_key:
            raise TranscriptionError(
                "Soniox transcription selected but no Soniox API key provided. "
                "Add your Soniox API key in the Settings tab."
            )
        soniox_transcribe_to_srt(
            audio_path=audio_path,
            output_srt_path=output_srt_path,
            language_code=language_code,
            api_key=api_key,
            progress_callback=progress_callback,
            logger=logger,
            cancelled_check=cancelled_check,
        )
        return

    api_key = get_elevenlabs_api_key()
    if not api_key:
        raise TranscriptionError(
            "Transcription is enabled but no ElevenLabs API key provided. "
            "Add your ElevenLabs or Soniox API key in the Settings tab, or select "
            "ReazonSpeech (Offline, Japanese) as the transcription engine for Japanese audio."
        )
    transcribe_audio_to_srt(
        audio_path=audio_path,
        output_srt_path=output_srt_path,
        language_code=language_code,
        api_key=api_key,
        progress_callback=progress_callback,
        logger=logger,
        cancelled_check=cancelled_check,
    )


# ---------------------------------------------------------------------------
# ReazonSpeech k2-v2 offline transcription (Japanese only)
# ---------------------------------------------------------------------------

# Module-level model cache — loaded once, reused across all transcriptions
_RS_MODEL_CACHE = None


def _get_reazonspeech_model():
    """Load (or return cached) ReazonSpeech k2-v2 model from bundled files.

    Creates a sherpa_onnx OfflineRecognizer directly from the bundled model
    files in models/reazonspeech-k2-v2/, bypassing HuggingFace download.
    """
    global _RS_MODEL_CACHE
    if _RS_MODEL_CACHE is not None:
        return _RS_MODEL_CACHE

    import sherpa_onnx
    from ..config import _BUNDLE_DIR

    model_dir = _BUNDLE_DIR / "models" / "reazonspeech-k2-v2"

    encoder = model_dir / "encoder-epoch-99-avg-1.int8.onnx"
    decoder = model_dir / "decoder-epoch-99-avg-1.int8.onnx"
    joiner = model_dir / "joiner-epoch-99-avg-1.int8.onnx"
    tokens = model_dir / "tokens.txt"

    for path in (encoder, decoder, joiner, tokens):
        if not path.exists():
            raise TranscriptionError(
                f"ReazonSpeech model file missing: {path.name}\n"
                "Run: python scripts/fetch_models.py"
            )

    _RS_MODEL_CACHE = sherpa_onnx.OfflineRecognizer.from_transducer(
        tokens=str(tokens),
        encoder=str(encoder),
        decoder=str(decoder),
        joiner=str(joiner),
        num_threads=1,
        sample_rate=16000,
        feature_dim=80,
        decoding_method="greedy_search",
        provider="cpu",
    )
    return _RS_MODEL_CACHE


def _load_audio_as_float32(audio_path: Path, target_sr: int = 16000, process_tracker=None):
    """Load an audio file and return mono float32 numpy array at target_sr.

    Uses soundfile for wav/flac, falls back to ffmpeg + raw PCM for mp3/m4a.
    """
    import numpy as np
    import soundfile as sf

    suffix = audio_path.suffix.lower()
    if suffix in (".wav", ".flac", ".ogg"):
        data, sr = sf.read(str(audio_path), dtype="float32", always_2d=True)
        # Mix to mono
        audio = data.mean(axis=1)
        if sr != target_sr:
            audio = _resample(audio, sr, target_sr)
        return audio

    # For mp3/m4a/etc. use ffmpeg to decode to raw PCM
    import subprocess
    from ..bin_paths import ffmpeg_path, _NOWWIN

    cmd = [
        ffmpeg_path(),
        "-i", str(audio_path),
        "-f", "f32le",        # raw 32-bit float little-endian
        "-acodec", "pcm_f32le",
        "-ac", "1",           # mono
        "-ar", str(target_sr),
        "-",                  # pipe to stdout
    ]
    _run = process_tracker.run if process_tracker else subprocess.run
    result = _run(cmd, capture_output=True, **_NOWWIN)
    if result.returncode != 0:
        raise TranscriptionError(f"ffmpeg audio decode failed: {result.stderr.decode()[:300]}")

    import numpy as np
    return np.frombuffer(result.stdout, dtype=np.float32)


def _resample(audio, orig_sr: int, target_sr: int):
    """Simple linear-interpolation resampling."""
    import numpy as np
    if orig_sr == target_sr:
        return audio
    ratio = target_sr / orig_sr
    new_len = int(len(audio) * ratio)
    indices = np.linspace(0, len(audio) - 1, new_len)
    return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)


def _split_audio_on_silence(
    audio,
    sr: int = 16000,
    max_chunk_sec: float = 20.0,
    min_silence_sec: float = 0.3,
    silence_threshold: float = 0.01,
):
    """Split audio into chunks at silence boundaries.

    Returns list of (start_sample, chunk_array) tuples.
    Each chunk is at most max_chunk_sec long, split at the quietest point.
    """
    import numpy as np
    max_samples = int(max_chunk_sec * sr)
    min_silence_samples = int(min_silence_sec * sr)
    total = len(audio)

    if total <= max_samples:
        return [(0, audio)]

    chunks = []
    pos = 0

    while pos < total:
        end = min(pos + max_samples, total)

        if end >= total:
            # Last chunk
            chunks.append((pos, audio[pos:end]))
            break

        # Find the quietest region in the last 40% of the chunk for splitting
        search_start = pos + int(max_samples * 0.6)
        search_end = end

        # Compute energy in sliding windows
        window = min_silence_samples
        best_energy = float("inf")
        best_pos = end

        for i in range(search_start, search_end - window, window // 4):
            segment = audio[i : i + window]
            energy = float(np.mean(segment ** 2))
            if energy < best_energy:
                best_energy = energy
                best_pos = i + window // 2

        # If we found a quiet spot, split there; otherwise split at max_samples
        if best_energy < silence_threshold:
            split_at = best_pos
        else:
            split_at = end

        chunks.append((pos, audio[pos:split_at]))
        pos = split_at

    return chunks


def _subwords_to_words(
    subwords: list[dict],
    gap_threshold: float = 0.3,
    start_offset: float = 0.75,
) -> list[dict]:
    """Convert ReazonSpeech subwords (single-point timestamps) to word dicts.

    ReazonSpeech outputs subwords with a single `.seconds` timestamp each.
    This estimates start/end times and groups consecutive subwords into
    word-like chunks by detecting time gaps > gap_threshold seconds.

    The transducer model emits token timestamps with inherent latency —
    tokens are labeled when recognized, not when the audio actually began.
    ``start_offset`` shifts start times earlier to compensate.

    Each subword dict has keys: text, seconds.
    Returns list of dicts with text, start, end — compatible with words_to_srt().
    """
    if not subwords:
        return []

    words = []
    current_text = subwords[0]["text"]
    current_start = subwords[0]["seconds"]
    current_end = subwords[0]["seconds"]

    for sw in subwords[1:]:
        gap = sw["seconds"] - current_end
        if gap > gap_threshold:
            words.append({
                "text": current_text,
                "start": current_start,
                "end": current_end,
            })
            current_text = sw["text"]
            current_start = sw["seconds"]
            current_end = sw["seconds"]
        else:
            current_text += sw["text"]
            current_end = sw["seconds"]

    # Final word — estimate end as start + 0.5s
    words.append({
        "text": current_text,
        "start": current_start,
        "end": current_end + 0.5,
    })

    # For all but last word, set end to midpoint between it and next word start
    for i in range(len(words) - 1):
        words[i]["end"] = max(
            words[i]["end"],
            (words[i]["end"] + words[i + 1]["start"]) / 2,
        )

    # Compensate for transducer emission latency by shifting starts earlier
    if start_offset:
        for w in words:
            w["start"] = max(0.0, w["start"] - start_offset)

    return words


class ReazonSpeechTranscriber:
    """Transcribe Japanese audio offline using ReazonSpeech k2-v2."""

    SAMPLE_RATE = 16000

    def __init__(self):
        pass

    def transcribe(
        self,
        audio_path: Path,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> list[dict]:
        """Transcribe a Japanese audio file.

        Handles long audio by splitting at silence boundaries (~20s chunks),
        transcribing each, then merging with correct time offsets.

        Args:
            audio_path: Path to audio file
            progress_callback: Optional callback for progress updates

        Returns:
            List of word dicts with 'text', 'start', 'end' keys

        Raises:
            TranscriptionError: If transcription fails
        """
        from reazonspeech.k2.asr import transcribe, audio_from_numpy

        if not audio_path.exists():
            raise TranscriptionError(f"Audio file not found: {audio_path}")

        # Load model (cached)
        if progress_callback:
            progress_callback("Loading ReazonSpeech model...")
        model = _get_reazonspeech_model()

        # Load audio
        if progress_callback:
            progress_callback("Loading audio...")
        audio = _load_audio_as_float32(audio_path, self.SAMPLE_RATE)

        # Split into manageable chunks
        chunks = _split_audio_on_silence(audio, self.SAMPLE_RATE)
        total_chunks = len(chunks)

        if progress_callback:
            progress_callback(f"Transcribing {total_chunks} audio segment(s)...")

        all_subwords = []

        for i, (start_sample, chunk) in enumerate(chunks):
            if progress_callback and total_chunks > 1:
                progress_callback(
                    f"Transcribing segment {i + 1}/{total_chunks}..."
                )

            offset_sec = start_sample / self.SAMPLE_RATE
            audio_obj = audio_from_numpy(chunk, self.SAMPLE_RATE)

            try:
                result = transcribe(model, audio_obj)
            except Exception as e:
                raise TranscriptionError(
                    f"ReazonSpeech transcription failed on segment {i + 1}: {e}"
                )

            # result.subwords: list of Subword(seconds=float, token=str)
            # Each has a single-point timestamp; estimate end from next subword
            for sw in result.subwords:
                if sw.token.strip():
                    all_subwords.append({
                        "text": sw.token,
                        "seconds": sw.seconds + offset_sec,
                    })

        if not all_subwords:
            raise TranscriptionError("No speech detected in audio")

        # Convert single-point timestamps to start/end pairs,
        # then group into word-like chunks
        words = _subwords_to_words(all_subwords)

        if progress_callback:
            progress_callback("ReazonSpeech transcription complete")

        return words


def reazonspeech_transcribe_to_srt(
    audio_path: Path,
    output_srt_path: Path,
    progress_callback: Optional[Callable[[str], None]] = None,
    logger=None,
) -> None:
    """Transcribe Japanese audio to SRT using ReazonSpeech (offline).

    Convenience function parallel to transcribe_audio_to_srt().

    Args:
        audio_path: Path to audio file
        output_srt_path: Path where SRT file should be saved
        progress_callback: Optional callback for progress updates

    Raises:
        TranscriptionError: If transcription fails
    """
    transcriber = ReazonSpeechTranscriber()
    words = transcriber.transcribe(audio_path, progress_callback)

    if logger:
        logger.debug("ReazonSpeech transcription complete", word_count=len(words))

    if progress_callback:
        progress_callback("Converting transcription to SRT format...")

    srt_content = words_to_srt(words, separator="")

    output_srt_path.parent.mkdir(parents=True, exist_ok=True)
    output_srt_path.write_text(srt_content, encoding="utf-8")

    if progress_callback:
        progress_callback(f"Transcription saved to {output_srt_path.name}")
