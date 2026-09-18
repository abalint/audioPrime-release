"""QThread pipeline orchestrator connecting download, parse, translate, TTS, and interleave."""

import json
import queue
import re
import shutil
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Optional

from PySide6.QtCore import QThread, Signal

from ..config import LOGS_DIR, WORK_DIR, OutputConfig, get_anthropic_api_key, get_language_config, get_punctuation_model, get_summary_model, get_target_language, get_target_language_code, get_translation_model, is_anthropic_model
from .audio import _next_version, extract_audio_to_mp3, probe_audio_duration, validate_audio_file
from .downloader import download_youtube, fetch_video_metadata, resolve_urls
from .interleaver import interleave, interleave_video
from .local_file import is_local_file, is_m4b, generate_local_file_id, get_local_file_metadata, get_video_path, prepare_local_file
from .srt_parser import deduplicate_scrolling_subs, filter_non_speech, has_good_punctuation, merge_to_sentences, parse_srt, write_srt
from .translator import _REFUSAL_PATTERNS, is_unclear_placeholder, punctuate_subs, summarize_srt_content, translate_srt_content


from .anki import create_anki_deck
from .process_tracker import CancelledError, ProcessTracker
from .tts import create_tts_engine


class RunLogger:
    """Append-only file logger with timing, metrics accumulation, and JSON summary."""

    def __init__(self, prefix):
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = LOGS_DIR / f"{prefix}_{stamp}.log"
        self._lock = Lock()
        self._metrics = {}
        self._start_time = time.monotonic()
        self.info("Run started", logger_file=str(self.path))

    def _write(self, level, message, **context):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.") + f"{datetime.now().microsecond // 1000:03d}"
        line = f"{ts} [{level}] {message}"
        if context:
            line += " | " + json.dumps(context, ensure_ascii=False, sort_keys=True)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def info(self, message, **context):
        self._write("INFO", message, **context)

    def warn(self, message, **context):
        self._write("WARN", message, **context)

    def debug(self, message, **context):
        self._write("DEBUG", message, **context)

    def error(self, message, **context):
        self._write("ERROR", message, **context)

    @contextmanager
    def timer(self, stage_name):
        """Context manager that logs stage start/end with elapsed time and records the metric."""
        t0 = time.monotonic()
        self.info(f"{stage_name} started")
        try:
            yield
        finally:
            elapsed = round(time.monotonic() - t0, 3)
            self.info(f"{stage_name} completed", elapsed_sec=elapsed)
            self._record_metric(f"timing.{stage_name}", elapsed)

    def _record_metric(self, key, value):
        with self._lock:
            self._metrics[key] = value

    def record(self, key, value):
        """Record an arbitrary metric."""
        self._record_metric(key, value)

    def increment(self, key, amount=1):
        """Thread-safe counter increment."""
        with self._lock:
            self._metrics[key] = self._metrics.get(key, 0) + amount

    def finalize(self):
        """Write JSON metrics summary and final log entry."""
        elapsed = round(time.monotonic() - self._start_time, 3)
        self._record_metric("total_wall_time_sec", elapsed)
        self.info("Run completed", total_wall_time_sec=elapsed)
        metrics_path = self.path.with_suffix(".metrics.json")
        with self._lock:
            with metrics_path.open("w", encoding="utf-8") as f:
                json.dump(self._metrics, f, indent=2, ensure_ascii=False, sort_keys=True)


def _is_valid_srt_cache(filepath, allow_long_blocks=False):
    """Validate cached SRT file structurally (source-language SRTs).
    No refusal check — source-language text can legitimately contain
    English-like phrases that match refusal patterns.

    allow_long_blocks: skip per-block duration/length caps. Used for
    summary-mode SRTs where each entry spans a full topical chunk.
    """
    path = Path(filepath)
    if not path.exists() or path.stat().st_size == 0:
        return False

    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return False

    if "-->" not in content:
        return False

    subs = parse_srt(str(path))
    if not subs:
        return False

    if not allow_long_blocks:
        for start, end, text in subs:
            if (end - start) > 60.0:
                return False
            if len(text) > 500:
                return False

    return True


def _is_valid_en_srt_cache(filepath, allow_long_blocks=False):
    """Validate cached English SRT — structural + refusal + quality."""
    if not _is_valid_srt_cache(filepath, allow_long_blocks=allow_long_blocks):
        return False

    subs = parse_srt(str(filepath))
    if not subs:
        return False

    # Refusal check — only applies to English translations
    for _, _, text in subs:
        for pat in _REFUSAL_PATTERNS:
            if pat.search(text):
                return False

    # Quality: reject if >25% of blocks are empty or placeholder
    bad_count = sum(
        1 for _, _, text in subs
        if not text.strip() or is_unclear_placeholder(text)
    )
    if bad_count / len(subs) > 0.25:
        return False

    return True


def _sanitize_filename(name):
    """Remove characters that are invalid in file/directory names."""
    sanitized = re.sub(r'[<>:"/\\|?*]', '', name)
    sanitized = sanitized.strip('. ')
    return sanitized or "Unknown"


# ── Data classes for producer-consumer pipeline ────────────────────────

@dataclass
class DownloadResult:
    """Result of a successful download phase for one video."""
    url: str
    video_id: str
    channel_name: str
    video_title: str
    mp3_path: Path
    srt_path: Path
    video_path: Optional[str]
    index: int
    skipped: bool = False  # True if all outputs already cached
    m4b_path: Optional[str] = None  # Original M4B path for chapter-aware processing


@dataclass
class DownloadError:
    """Represents a download failure for one video."""
    url: str
    index: int
    error: str


# ── Download phase (extracted for producer-consumer reuse) ─────────────

def download_phase(url, output_dir, cookie_browser, source_language,
                   force_transcription, output_configs, anki_only,
                   cancelled_check, step_cb, progress_cb,
                   batch_mode=False, index=0, logger=None, resolution="",
                   keep_original_video=False, process_tracker=None):
    """Download media and subtitles for a single video.

    Extracts video ID, fetches metadata, checks cache, and downloads
    audio/video + subtitles as needed.

    Args:
        url: Video URL or local file path
        output_dir: Path to output directory
        cookie_browser: Browser name for cookies, or None
        source_language: Display name of source language
        force_transcription: If True, skip subtitles and always transcribe
        output_configs: List of OutputConfig defining desired outputs
        anki_only: If True, only check for Anki deck cache
        cancelled_check: Callable returning True if cancelled
        step_cb: Callable(str) for step label updates
        progress_cb: Callable(int, int, str) for progress updates
        batch_mode: If True, add yt-dlp sleep flags to avoid rate limiting
        index: Video index in batch (for DownloadResult)

    Returns:
        DownloadResult on success, None if cancelled.

    Raises:
        ValueError: If video ID cannot be extracted
        RuntimeError: If download fails
    """
    lang = get_language_config(source_language)
    lang_code = lang["code"]

    needs_video = any(c.format == "mp4" for c in output_configs) or keep_original_video

    output_dir = Path(output_dir)
    work_dir = WORK_DIR
    download_dir = work_dir / "download"
    download_dir.mkdir(parents=True, exist_ok=True)

    _is_local = is_local_file(url)

    if _is_local:
        video_id = generate_local_file_id(url)
        channel_name, video_title = get_local_file_metadata(url)
    else:
        from .downloader import _extract_video_id, _fetch_video_id_from_ytdlp

        # Extract video ID - try YouTube-specific extraction first, then fallback to yt-dlp
        video_id = _extract_video_id(url)
        if not video_id:
            try:
                video_id = _fetch_video_id_from_ytdlp(url, cookie_browser)
            except RuntimeError as e:
                raise ValueError(f"Could not extract video ID from URL: {url}. Error: {e}")

        if not video_id:
            raise ValueError(f"Could not extract video ID from URL: {url}")

        # Fetch video metadata
        step_cb("Fetching video metadata...")
        channel_name, video_title = fetch_video_metadata(url, cookie_browser=cookie_browser,
                                                          logger=logger,
                                                          process_tracker=process_tracker)

    safe_channel = _sanitize_filename(channel_name)
    safe_title = _sanitize_filename(video_title)
    channel_dir = output_dir / safe_channel

    # Skip fully processed videos when all outputs already exist
    mp3_path = download_dir / f"{video_id}.mp3"
    srt_path = download_dir / f"{video_id}.{lang_code}.srt"

    if anki_only:
        apkg_cache = channel_dir / f"{safe_title}.apkg"
        if apkg_cache.exists():
            step_cb("Anki deck cached, skipping video...")
            progress_cb(1, 1, f"Using cached output: {apkg_cache.name}")
            return DownloadResult(
                url=url, video_id=video_id, channel_name=channel_name,
                video_title=video_title, mp3_path=mp3_path, srt_path=srt_path,
                video_path=None, index=index, skipped=True,
            )
    elif output_configs:
        all_exist = True
        for oc in output_configs:
            op = channel_dir / oc.filename(safe_title)
            if oc.format == "mp4":
                if not op.exists():
                    all_exist = False
                    break
            else:
                if not validate_audio_file(op):
                    all_exist = False
                    break
        if all_exist:
            step_cb("All outputs cached, skipping video...")
            progress_cb(1, 1, "Using cached outputs")
            return DownloadResult(
                url=url, video_id=video_id, channel_name=channel_name,
                video_title=video_title, mp3_path=mp3_path, srt_path=srt_path,
                video_path=None, index=index, skipped=True,
            )

    if cancelled_check():
        return None

    # Step 1: Download media + subtitles
    # When any output needs video, download video first and extract mp3
    video_path = None
    if needs_video and not _is_local:
        from .downloader import download_video

        if not (mp3_path.exists() and srt_path.exists()):
            step_cb("Downloading video...")
            video_path = str(download_video(
                url, download_dir,
                progress_callback=lambda msg: progress_cb(0, 0, msg),
                cookie_browser=cookie_browser,
                batch_mode=batch_mode,
                logger=logger,
                resolution=resolution,
                process_tracker=process_tracker,
            ))

            if cancelled_check():
                return None

            # Extract mp3 from the video so the rest of the pipeline can use it
            if not mp3_path.exists():
                step_cb("Extracting audio from video...")
                extract_audio_to_mp3(video_path, str(mp3_path),
                                     process_tracker=process_tracker)

            # Get subtitles (download_youtube will skip audio since mp3 exists)
            if not srt_path.exists():
                step_cb("Fetching subtitles...")
                mp3_path, srt_path = download_youtube(
                    url, download_dir,
                    progress_callback=lambda msg: progress_cb(0, 0, msg),
                    cookie_browser=cookie_browser,
                    sub_lang=lang_code,
                    force_transcription=force_transcription,
                    batch_mode=batch_mode,
                    logger=logger,
                    process_tracker=process_tracker,
                )
        else:
            step_cb("Download and subtitles cached, skipping...")
            progress_cb(1, 1, "Using cached download and subtitles")
            if logger:
                logger.debug("Download cache hit", video_id=video_id)
            # Still need the video path
            video_path = str(download_video(
                url, download_dir,
                progress_callback=lambda msg: progress_cb(0, 0, msg),
                cookie_browser=cookie_browser,
                batch_mode=batch_mode,
                logger=logger,
                resolution=resolution,
                process_tracker=process_tracker,
            ))
    elif _is_local:
        if mp3_path.exists() and srt_path.exists():
            step_cb("Download and subtitles cached, skipping...")
            progress_cb(1, 1, "Using cached download and subtitles")
        else:
            step_cb("Preparing local file...")
            mp3_path, srt_path = prepare_local_file(
                url, download_dir,
                lang_code=lang_code,
                progress_callback=lambda msg: progress_cb(0, 0, msg),
                force_transcription=force_transcription,
                process_tracker=process_tracker,
            )

        if needs_video:
            video_path = get_video_path(url)
            if video_path is None:
                raise RuntimeError(
                    f"Video output mode requires a video file, but '{Path(url).name}' "
                    "is audio-only. Use a video file (.mp4, .mkv, etc.) or remove MP4 outputs."
                )
    else:
        # Audio-only mode (no video download needed)
        if mp3_path.exists() and srt_path.exists():
            step_cb("Download and subtitles cached, skipping...")
            progress_cb(1, 1, "Using cached download and subtitles")
        elif mp3_path.exists() and not srt_path.exists():
            step_cb("Audio cached, checking for subtitles...")
            progress_cb(1, 1, "Using cached audio")
            mp3_path, srt_path = download_youtube(
                url, download_dir,
                progress_callback=lambda msg: progress_cb(0, 0, msg),
                cookie_browser=cookie_browser,
                sub_lang=lang_code,
                force_transcription=force_transcription,
                batch_mode=batch_mode,
                logger=logger,
                process_tracker=process_tracker,
            )
        else:
            step_cb("Downloading audio...")
            mp3_path, srt_path = download_youtube(
                url, download_dir,
                progress_callback=lambda msg: progress_cb(0, 0, msg),
                cookie_browser=cookie_browser,
                sub_lang=lang_code,
                force_transcription=force_transcription,
                batch_mode=batch_mode,
                logger=logger,
                process_tracker=process_tracker,
            )

    if cancelled_check():
        return None

    m4b_path = str(Path(url).resolve()) if _is_local and is_m4b(url) else None

    return DownloadResult(
        url=url, video_id=video_id, channel_name=channel_name,
        video_title=video_title, mp3_path=mp3_path, srt_path=srt_path,
        video_path=video_path, index=index, m4b_path=m4b_path,
    )


def _run_m4b_chapter_pipeline(
    m4b_path, mp3_path, srt_path, video_id, api_key, voice_name, speed,
    channel_dir, safe_title, output_configs, source_language,
    force_transcription, cancelled_check, step_cb, progress_cb,
    tts=None, logger=None, process_tracker=None,
):
    """Process an M4B file chapter-by-chapter and reassemble as M4B with chapters.

    Each chapter is processed independently through the standard pipeline
    (parse → translate → TTS → interleave), then all chapters are assembled
    into a single M4B with recalculated chapter timestamps.
    """
    from .m4b import (
        assemble_m4b,
        extract_chapters,
        extract_metadata,
        filter_srt_to_chapter,
        generate_ffmetadata,
        split_chapter_audio,
    )

    lang = get_language_config(source_language)
    lang_code = lang["code"]
    target_language = get_target_language()
    target_code = get_target_language_code(target_language)

    work_dir = WORK_DIR
    download_dir = work_dir / "download"
    m4b_work = work_dir / "m4b" / Path(mp3_path).stem
    m4b_work.mkdir(parents=True, exist_ok=True)

    # Extract chapters and metadata from original M4B
    step_cb("Extracting M4B chapters...")
    chapters = extract_chapters(m4b_path, process_tracker=process_tracker)
    metadata = extract_metadata(m4b_path, process_tracker=process_tracker)

    if not chapters:
        # No chapters — treat the whole file as a single chapter
        total_dur = probe_audio_duration(str(mp3_path))
        if total_dur is None:
            raise RuntimeError(f"Could not determine M4B duration: {m4b_path}")
        chapters = [{"id": 0, "title": "Chapter 1", "start_time": 0.0, "end_time": total_dur}]

    progress_cb(0, len(chapters), f"Found {len(chapters)} chapters")

    # Parse the full SRT once (will be filtered per chapter)
    full_subs = parse_srt(str(srt_path), logger=logger)

    # Load TTS model once for all chapters
    if tts is None:
        step_cb("Loading TTS model...")
        tts = create_tts_engine(voice_name, status_cb=step_cb)

    # Process each output config that is m4b format
    for oc in output_configs:
        if oc.format != "m4b":
            continue

        output_path = channel_dir / oc.filename(safe_title)
        if output_path.exists():
            step_cb("M4B output cached, skipping...")
            continue

        en_srt_mode = oc.mode  # "sentence" or "summary"
        group_size = 1 if oc.mode == "summary" else oc.group_size

        chapter_interleaved_mp3s = []
        chapters_with_durations = []

        for ch_idx, chapter in enumerate(chapters):
            ch_label = f"Chapter {ch_idx + 1}/{len(chapters)}: {chapter['title']}"

            if cancelled_check():
                return None

            ch_start = chapter["start_time"]
            ch_end = chapter["end_time"]
            ch_work = m4b_work / f"ch{ch_idx:04d}_{oc.work_dir_tag()}"
            ch_work.mkdir(parents=True, exist_ok=True)

            # Split chapter audio from original M4B
            ch_mp3 = ch_work / "chapter_audio.mp3"
            if not validate_audio_file(ch_mp3):
                step_cb(f"{ch_label} — Extracting audio...")
                split_chapter_audio(m4b_path, ch_start, ch_end, str(ch_mp3),
                                    process_tracker=process_tracker)

            # Filter SRT to this chapter's time range
            ch_subs = filter_srt_to_chapter(full_subs, ch_start, ch_end)

            if not ch_subs:
                # No subtitles for this chapter — transcribe the chapter audio
                step_cb(f"{ch_label} — Transcribing...")
                ch_srt = ch_work / f"chapter.{lang_code}.srt"
                if not _is_valid_srt_cache(ch_srt):
                    from .local_file import _transcribe_local
                    _transcribe_local(
                        ch_mp3, ch_srt, lang_code,
                        progress_callback=lambda msg: progress_cb(ch_idx, len(chapters), f"{ch_label} — {msg}"),
                        label="Transcribing chapter audio...",
                    )
                ch_subs = parse_srt(str(ch_srt))

            if not ch_subs:
                # Still no content — skip this chapter (output raw audio)
                chapter_interleaved_mp3s.append(str(ch_mp3))
                ch_dur = probe_audio_duration(str(ch_mp3))
                chapters_with_durations.append({"title": chapter["title"], "duration": ch_dur or 0.0})
                progress_cb(ch_idx + 1, len(chapters), f"{ch_label} — No speech content, using original audio")
                continue

            # Write chapter SRT
            ch_srt = ch_work / f"chapter.{lang_code}.srt"
            if not _is_valid_srt_cache(ch_srt):
                write_srt(ch_subs, str(ch_srt))

            # Parse sentences
            step_cb(f"{ch_label} — Parsing sentences...")
            ch_sentences_srt = ch_work / f"chapter.{lang_code}_sentences.srt"
            if not _is_valid_srt_cache(ch_sentences_srt):
                subs = ch_subs
                subs = deduplicate_scrolling_subs(subs, logger=logger)
                subs = filter_non_speech(subs, logger=logger)
                if not subs:
                    # No speech content in this chapter
                    chapter_interleaved_mp3s.append(str(ch_mp3))
                    ch_dur = probe_audio_duration(str(ch_mp3))
                    chapters_with_durations.append({"title": chapter["title"], "duration": ch_dur or 0.0})
                    progress_cb(ch_idx + 1, len(chapters), f"{ch_label} — No speech, using original")
                    continue

                if not has_good_punctuation(subs, lang["sentence_punct"], logger=logger):
                    punct_model = get_punctuation_model()
                    punct_api_key = get_anthropic_api_key() if is_anthropic_model(punct_model) else api_key
                    step_cb(f"{ch_label} — Punctuating...")
                    subs = punctuate_subs(
                        punct_api_key, subs,
                        source_language=source_language,
                        progress_callback=lambda cur, total: progress_cb(
                            ch_idx, len(chapters), f"{ch_label} — Punctuating {cur + 1}/{total}"),
                        model=punct_model,
                        cache_tag=f"{video_id}_ch{ch_idx}",
                        logger=logger,
                        cancelled_check=cancelled_check,
                    )

                sentences = merge_to_sentences(subs, lang["sentence_enders"], logger=logger)
                write_srt(sentences, str(ch_sentences_srt))

            if cancelled_check():
                return None

            # Translate
            ch_en_srt = ch_work / f"chapter.{target_code}.srt"
            if en_srt_mode == "summary":
                if not _is_valid_en_srt_cache(ch_en_srt, allow_long_blocks=True):
                    step_cb(f"{ch_label} — Summarizing...")
                    sum_model = get_summary_model()
                    sum_api_key = get_anthropic_api_key() if is_anthropic_model(sum_model) else api_key
                    srt_content = Path(ch_sentences_srt).read_text(encoding="utf-8")
                    en_content = summarize_srt_content(
                        sum_api_key, srt_content,
                        source_language=source_language,
                        progress_callback=lambda cur, total: progress_cb(
                            ch_idx, len(chapters), f"{ch_label} — Summarizing {cur + 1}/{total}"),
                        model=sum_model,
                        logger=logger,
                        cancelled_check=cancelled_check,
                        target_language=target_language,
                    )
                    ch_en_srt.write_text(en_content, encoding="utf-8")
            else:
                if not _is_valid_en_srt_cache(ch_en_srt):
                    step_cb(f"{ch_label} — Translating...")
                    trans_model = get_translation_model()
                    trans_api_key = get_anthropic_api_key() if is_anthropic_model(trans_model) else api_key
                    srt_content = Path(ch_sentences_srt).read_text(encoding="utf-8")
                    en_content = translate_srt_content(
                        trans_api_key, srt_content,
                        source_language=source_language,
                        progress_callback=lambda cur, total: progress_cb(
                            ch_idx, len(chapters), f"{ch_label} — Translating {cur + 1}/{total}"),
                        model=trans_model,
                        logger=logger,
                        cancelled_check=cancelled_check,
                        target_language=target_language,
                    )
                    ch_en_srt.write_text(en_content, encoding="utf-8")

            if cancelled_check():
                return None

            # Interleave
            step_cb(f"{ch_label} — Interleaving...")
            ch_interleaved = ch_work / "chapter_interleaved.mp3"
            if not validate_audio_file(ch_interleaved):
                interleave_work = ch_work / "interleave"
                interleave_work.mkdir(parents=True, exist_ok=True)

                interleave(
                    src_audio=ch_mp3,
                    src_srt=str(ch_sentences_srt),
                    en_srt=str(ch_en_srt),
                    output=str(ch_interleaved),
                    tts=tts,
                    speed=speed,
                    work_dir=interleave_work,
                    sentence_punct=lang["sentence_punct"],
                    progress_callback=lambda cur, total, msg: progress_cb(
                        ch_idx, len(chapters), f"{ch_label} — {msg}"),
                    group_size=group_size,
                    condense=oc.condensed,
                    logger=logger,
                    cancelled_check=cancelled_check,
                    process_tracker=process_tracker,
                )

            chapter_interleaved_mp3s.append(str(ch_interleaved))
            ch_dur = probe_audio_duration(str(ch_interleaved))
            chapters_with_durations.append({"title": chapter["title"], "duration": ch_dur or 0.0})
            progress_cb(ch_idx + 1, len(chapters), f"{ch_label} — Done")

        if cancelled_check():
            return None

        # Assemble final M4B
        step_cb("Assembling M4B with chapters...")
        metadata_text = generate_ffmetadata(chapters_with_durations, metadata)
        channel_dir.mkdir(parents=True, exist_ok=True)
        assemble_m4b(chapter_interleaved_mp3s, metadata_text, str(output_path),
                     process_tracker=process_tracker)
        progress_cb(len(chapters), len(chapters), "M4B assembly complete")

    return tts


def run_single_pipeline(url, api_key, voice_name, speed, output_dir, cookie_browser,
                        cancelled_check, step_cb, progress_cb, tts=None,
                        create_anki=False, source_language="Japanese",
                        force_transcription=False, anki_only=False,
                        output_configs=None,
                        lemma_list_path="", unlisted_knowledge=0,
                        check_callback=None,
                        download_result=None,
                        logger=None, resolution="",
                        keep_original_audio=True, keep_original_video=False,
                        process_tracker=None):
    """Run the full pipeline for a single video URL.

    Two-phase architecture:
      Phase A — Shared processing (download, parse, translate/summarize)
      Phase B — Output generation (interleave per OutputConfig)

    Args:
        url: Video URL or local file path
        api_key: OpenAI API key
        voice_name: Piper catalog voice key (unused by cloud engines)
        speed: TTS speed multiplier
        output_dir: Path to output directory
        cookie_browser: Browser name for cookies, or None
        cancelled_check: Callable returning True if cancelled
        step_cb: Callable(str) for step label updates
        progress_cb: Callable(int, int, str) for progress updates
        tts: Optional pre-loaded PiperTTS instance
        create_anki: If True, also generate Anki deck
        source_language: Display name of source language (e.g. "Japanese")
        force_transcription: If True, skip subtitles and always transcribe
        anki_only: If True, skip translation/TTS/interleave and only produce Anki deck
        output_configs: List of OutputConfig defining desired outputs
        download_result: Optional pre-downloaded DownloadResult (skips download phase)

    Returns:
        str: Path to the output channel directory

    Raises:
        ValueError: If video ID cannot be extracted
        RuntimeError: If any pipeline step fails
    """
    if output_configs is None:
        output_configs = []

    lang = get_language_config(source_language)
    lang_code = lang["code"]
    target_language = get_target_language()
    target_code = get_target_language_code(target_language)

    # Derive requirements from output configs
    needs_video = any(c.format == "mp4" for c in output_configs) or keep_original_video
    needs_sentence = any(c.mode == "sentence" for c in output_configs)
    needs_summary = any(c.mode == "summary" for c in output_configs)
    any_condensed = any(c.condensed for c in output_configs)

    output_dir = Path(output_dir)

    # ── Phase A: Download (or use pre-downloaded data) ─────────────────
    if download_result is None:
        download_result = download_phase(
            url, output_dir, cookie_browser, source_language,
            force_transcription, output_configs, anki_only,
            cancelled_check, step_cb, progress_cb,
            logger=logger, resolution=resolution,
            keep_original_video=keep_original_video,
            process_tracker=process_tracker,
        )
        if download_result is None:  # cancelled
            return None

    if download_result.skipped:
        safe_channel = _sanitize_filename(download_result.channel_name)
        return str(output_dir / safe_channel)

    video_id = download_result.video_id
    channel_name = download_result.channel_name
    video_title = download_result.video_title
    mp3_path = download_result.mp3_path
    srt_path = download_result.srt_path
    video_path = download_result.video_path

    safe_channel = _sanitize_filename(channel_name)
    safe_title = _sanitize_filename(video_title)
    channel_dir = output_dir / safe_channel

    work_dir = WORK_DIR
    download_dir = work_dir / "download"

    if logger:
        mp3_size = mp3_path.stat().st_size if mp3_path.exists() else 0
        logger.record("input.mp3_size_bytes", mp3_size)
        logger.record("input.video_id", video_id)
        logger.record("input.video_title", video_title)

    if cancelled_check():
        return None

    # ── M4B chapter-aware branch ──────────────────────────────────────
    m4b_configs = [c for c in output_configs if c.format == "m4b"]
    non_m4b_configs = [c for c in output_configs if c.format != "m4b"]

    if m4b_configs and download_result.m4b_path:
        _run_m4b_chapter_pipeline(
            m4b_path=download_result.m4b_path,
            mp3_path=mp3_path,
            srt_path=srt_path,
            video_id=video_id,
            api_key=api_key,
            voice_name=voice_name,
            speed=speed,
            channel_dir=channel_dir,
            safe_title=safe_title,
            output_configs=m4b_configs,
            source_language=source_language,
            force_transcription=force_transcription,
            cancelled_check=cancelled_check,
            step_cb=step_cb,
            progress_cb=progress_cb,
            tts=tts,
            logger=logger,
            process_tracker=process_tracker,
        )
        # If only M4B outputs were requested, skip the rest of the pipeline
        if not non_m4b_configs and not create_anki and not anki_only:
            channel_dir.mkdir(parents=True, exist_ok=True)
            # Copy original audio
            if keep_original_audio:
                original_dest = channel_dir / f"{safe_title}_original.mp3"
                if not original_dest.exists():
                    shutil.copy2(str(mp3_path), str(original_dest))
            # Copy original video
            if keep_original_video and video_path:
                original_video_dest = channel_dir / f"{safe_title}_original.mp4"
                if not original_video_dest.exists():
                    shutil.copy2(str(video_path), str(original_video_dest))
            if srt_path.exists():
                transcriptions_dir = channel_dir / "transcriptions"
                transcriptions_dir.mkdir(parents=True, exist_ok=True)
                srt_dest = transcriptions_dir / f"{safe_title}.srt"
                if not srt_dest.exists():
                    shutil.copy2(str(srt_path), str(srt_dest))
            return str(channel_dir)
        # Otherwise, continue with non-m4b configs
        output_configs = non_m4b_configs

    # Step 2: Parse sentences (skip if cached)
    sentences_srt = download_dir / f"{video_id}.{lang_code}_sentences.srt"
    if _is_valid_srt_cache(sentences_srt):
        step_cb("Parsed sentences cached, skipping...")
    else:
        if sentences_srt.exists():
            sentences_srt = _next_version(sentences_srt)
        step_cb("Parsing sentences...")
        subs = parse_srt(str(srt_path), logger=logger)
        subs = deduplicate_scrolling_subs(subs, logger=logger)
        subs = filter_non_speech(subs, logger=logger)

        if not subs:
            raise RuntimeError("No speech content found after filtering non-speech annotations (e.g. [Music], [Applause]).")

        # Check punctuation quality — if poor, send to GPT for punctuation
        if not has_good_punctuation(subs, lang["sentence_punct"], logger=logger):
            punct_model = get_punctuation_model()
            punct_api_key = get_anthropic_api_key() if is_anthropic_model(punct_model) else api_key
            if is_anthropic_model(punct_model) and not punct_api_key:
                raise RuntimeError(
                    f"Anthropic API key is required for punctuation model '{punct_model}'. "
                    "Please add your Anthropic API key in the Settings tab."
                )
            for attempt in range(1, 3):
                label = "Punctuating via AI..." if attempt == 1 else "Retry: punctuating via AI (attempt 2)..."
                step_cb(label)
                subs = punctuate_subs(
                    punct_api_key, subs,
                    source_language=source_language,
                    progress_callback=lambda cur, total: progress_cb(
                        cur, total, f"Punctuating chunk {cur + 1}/{total}"),
                    model=punct_model,
                    cache_tag=f"{video_id}_attempt{attempt}",
                    cjk_chunk_size=40 if attempt == 2 else None,
                    logger=logger,
                    cancelled_check=cancelled_check,
                )
                if cancelled_check():
                    return None
                if has_good_punctuation(subs, lang["sentence_punct"], logger=logger):
                    break
            else:
                raise RuntimeError(
                    "GPT failed to add adequate punctuation after 2 attempts. "
                    "The subtitle text may be too noisy for automatic processing."
                )

        sentences = merge_to_sentences(subs, lang["sentence_enders"], logger=logger)
        write_srt(sentences, str(sentences_srt))
        progress_cb(1, 1, f"Parsed {len(subs)} blocks into {len(sentences)} sentences")
        if logger:
            logger.record("sentences.count", len(sentences))

    if cancelled_check():
        return None

    # Step 2b: Comprehensibility analysis (optional)
    lemma_analysis = None
    if lemma_list_path:
        step_cb("Analyzing comprehensibility...")
        from .lemma_analyzer import load_lemma_list, analyze_video
        known_lemmas = load_lemma_list(lemma_list_path, lang_code)
        sentences_for_analysis = parse_srt(str(sentences_srt))
        lemma_analysis = analyze_video(sentences_for_analysis, known_lemmas, lang_code,
                                       unlisted_knowledge=unlisted_knowledge, logger=logger)
        adj_pct = lemma_analysis["overall_comprehensibility"] * 100
        raw_pct = lemma_analysis.get("token_comprehensibility", lemma_analysis["overall_comprehensibility"]) * 100
        i1 = lemma_analysis["i_plus_1_count"]
        if unlisted_knowledge > 0 and lemma_analysis.get("reclassified_count", 0) > 0:
            comp_msg = f"Comprehensibility: ~{adj_pct:.0f}% (raw: {raw_pct:.0f}%) | {i1} i+1 sentences"
        else:
            comp_msg = f"Comprehensibility: {raw_pct:.1f}% | {i1} i+1 sentences"
        progress_cb(1, 1, comp_msg)

        # Check-first mode: write report early and ask user whether to continue
        if check_callback:
            channel_dir.mkdir(parents=True, exist_ok=True)
            from .lemma_report import write_report
            write_report(lemma_analysis, channel_dir, safe_title)

            should_continue = check_callback(f"{video_title}\n{comp_msg}")
            if not should_continue:
                return str(channel_dir)

    if cancelled_check():
        return None

    def _safe_progress(cur, total, msg):
        if not cancelled_check():
            progress_cb(cur, total, msg)

    if not anki_only and output_configs:
        # Step 3: Translate and/or Summarize as needed by output configs
        en_sentence_srt = None
        en_summary_srt = None

        if needs_sentence:
            en_sentence_srt = download_dir / f"{video_id}.{target_code}.srt"
            if _is_valid_en_srt_cache(en_sentence_srt):
                step_cb("Translation cached, skipping...")
            else:
                if en_sentence_srt.exists():
                    en_sentence_srt = _next_version(en_sentence_srt)
                step_cb(f"Translating to {target_language}...")
                trans_model = get_translation_model()
                if logger:
                    logger.record("translation.model", trans_model)
                trans_api_key = get_anthropic_api_key() if is_anthropic_model(trans_model) else api_key
                if is_anthropic_model(trans_model) and not trans_api_key:
                    raise RuntimeError(
                        f"Anthropic API key is required for translation model '{trans_model}'. "
                        "Please add your Anthropic API key in the Settings tab."
                    )
                srt_content = sentences_srt.read_text(encoding="utf-8")
                en_srt_content = translate_srt_content(
                    trans_api_key, srt_content,
                    source_language=source_language,
                    progress_callback=lambda cur, total: progress_cb(cur, total, f"Translating sentence {cur + 1}/{total}"),
                    model=trans_model,
                    logger=logger,
                    cancelled_check=cancelled_check,
                    target_language=target_language,
                )
                en_sentence_srt.write_text(en_srt_content, encoding="utf-8")

        if cancelled_check():
            return None

        if needs_summary:
            # Keep the legacy filename for the default English target so existing
            # caches stay valid; suffix other targets with their language code.
            summary_name = f"{video_id}.summary.srt" if target_code == "en" else f"{video_id}.summary.{target_code}.srt"
            en_summary_srt = download_dir / summary_name
            if _is_valid_en_srt_cache(en_summary_srt, allow_long_blocks=True):
                step_cb("Summary cached, skipping...")
            else:
                if en_summary_srt.exists():
                    en_summary_srt = _next_version(en_summary_srt)
                step_cb(f"Summarizing to {target_language}...")
                sum_model = get_summary_model()
                sum_api_key = get_anthropic_api_key() if is_anthropic_model(sum_model) else api_key
                if is_anthropic_model(sum_model) and not sum_api_key:
                    raise RuntimeError(
                        f"Anthropic API key is required for summary model '{sum_model}'. "
                        "Please add your Anthropic API key in the Settings tab."
                    )
                srt_content = sentences_srt.read_text(encoding="utf-8")
                en_srt_content = summarize_srt_content(
                    sum_api_key, srt_content,
                    source_language=source_language,
                    progress_callback=lambda cur, total: progress_cb(cur, total, f"Summarizing batch {cur + 1}/{total}"),
                    model=sum_model,
                    logger=logger,
                    cancelled_check=cancelled_check,
                    target_language=target_language,
                )
                en_summary_srt.write_text(en_srt_content, encoding="utf-8")

        if cancelled_check():
            return None

        # Step 4: Load TTS model (if not provided)
        if tts is None:
            step_cb("Loading TTS model...")
            tts = create_tts_engine(voice_name, status_cb=step_cb)

        if cancelled_check():
            return None

        # ── Phase B: Output generation (per config) ────────────────────
        channel_dir.mkdir(parents=True, exist_ok=True)
        total_outputs = len(output_configs)

        for oc_idx, oc in enumerate(output_configs):
            output_path = channel_dir / oc.filename(safe_title)
            oc_label = f"({oc_idx + 1}/{total_outputs})" if total_outputs > 1 else ""

            # Skip if this output already exists
            if oc.format == "mp4":
                if output_path.exists():
                    step_cb(f"Output {oc_label} cached, skipping...")
                    continue
            else:
                if validate_audio_file(output_path):
                    step_cb(f"Output {oc_label} cached, skipping...")
                    continue

            if cancelled_check():
                return None

            en_srt_path = en_summary_srt if oc.mode == "summary" else en_sentence_srt
            group_size = 1 if oc.mode == "summary" else oc.group_size

            if oc.format == "mp4" and video_path:
                step_label = "Interleaving video"
                if oc.condensed:
                    step_label += " (condensed)"
                step_cb(f"{step_label}... {oc_label}")

                interleave_work = work_dir / f"interleave_video_{oc.work_dir_tag()}" / mp3_path.stem
                interleave_work.mkdir(parents=True, exist_ok=True)

                interleave_video(
                    src_video=video_path,
                    en_srt=str(en_srt_path),
                    output=str(output_path),
                    tts=tts,
                    speed=speed,
                    work_dir=interleave_work,
                    sentence_punct=lang["sentence_punct"],
                    progress_callback=_safe_progress,
                    group_size=group_size,
                    condense=oc.condensed,
                    logger=logger,
                    cancelled_check=cancelled_check,
                    process_tracker=process_tracker,
                )
            else:
                step_label = "Interleaving audio"
                if oc.condensed:
                    step_label += " (condensed)"
                step_cb(f"{step_label}... {oc_label}")

                interleave_work = work_dir / f"interleave_{oc.work_dir_tag()}" / mp3_path.stem
                interleave_work.mkdir(parents=True, exist_ok=True)

                interleave(
                    src_audio=mp3_path,
                    src_srt=str(sentences_srt),
                    en_srt=str(en_srt_path),
                    output=str(output_path),
                    tts=tts,
                    speed=speed,
                    work_dir=interleave_work,
                    sentence_punct=lang["sentence_punct"],
                    progress_callback=_safe_progress,
                    group_size=group_size,
                    condense=oc.condensed,
                    logger=logger,
                    cancelled_check=cancelled_check,
                    process_tracker=process_tracker,
                )

            if logger and output_path.exists():
                logger.record(f"output.{oc.work_dir_tag()}.size_bytes", output_path.stat().st_size)

            if cancelled_check():
                return None

    # Ensure output directory exists for file copies
    channel_dir.mkdir(parents=True, exist_ok=True)

    # Copy original audio to output folder
    if keep_original_audio:
        original_dest = channel_dir / f"{safe_title}_original.mp3"
        shutil.copy2(str(mp3_path), str(original_dest))

    # Copy original video to output folder
    if keep_original_video and video_path:
        original_video_dest = channel_dir / f"{safe_title}_original.mp4"
        shutil.copy2(str(video_path), str(original_video_dest))

    # Condense the original audio if any output config requested it
    if keep_original_audio and any_condensed and not anki_only:
        step_cb("Condensing original audio...")
        from .audio import condense_audio as do_condense
        condensed_original = channel_dir / f"{safe_title}_condensed_original.mp3"
        do_condense(str(mp3_path), str(condensed_original), srt_path=str(sentences_srt),
                    logger=logger, process_tracker=process_tracker)

    # Copy original subtitle file to transcriptions folder
    if srt_path.exists():
        transcriptions_dir = channel_dir / "transcriptions"
        transcriptions_dir.mkdir(parents=True, exist_ok=True)
        srt_dest = transcriptions_dir / f"{safe_title}.srt"
        shutil.copy2(str(srt_path), str(srt_dest))

    # Step 6: Anki deck (optional, or always when anki_only)
    if create_anki or anki_only:
        if cancelled_check():
            return None

        step_cb("Creating Anki deck...")
        anki_work = work_dir / "anki" / video_id
        anki_work.mkdir(parents=True, exist_ok=True)

        apkg_path = channel_dir / f"{safe_title}.apkg"
        create_anki_deck(
            srt_path=sentences_srt,
            audio_path=mp3_path,
            output_apkg=apkg_path,
            deck_title=video_title,
            work_dir=anki_work,
            video_id=video_id,
            progress_callback=_safe_progress,
            logger=logger,
            process_tracker=process_tracker,
        )

    # Write comprehensibility report if analysis was run
    if lemma_analysis:
        from .lemma_report import write_report
        write_report(lemma_analysis, channel_dir, safe_title)

    return str(channel_dir)


class PipelineWorker(QThread):
    """Runs the full pipeline for a single video in a background thread.

    Signals:
        progress(current, total, message): Step-level progress
        step_changed(label): Current pipeline step label
        finished(output_path): Emitted on success with output file path
        error(message): Emitted on failure
    """

    progress = Signal(int, int, str)
    step_changed = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, url, api_key, voice_name, speed, output_dir, cookie_browser=None,
                 create_anki=False, source_language="Japanese", force_transcription=False,
                 anki_only=False):
        super().__init__()
        self.url = url
        self.api_key = api_key
        self.voice_name = voice_name
        self.speed = speed
        self.output_dir = Path(output_dir)
        self.cookie_browser = cookie_browser
        self.create_anki = create_anki
        self.source_language = source_language
        self.force_transcription = force_transcription
        self.anki_only = anki_only
        self._cancelled = False
        self._tracker = ProcessTracker()

    def cancel(self):
        self._cancelled = True
        self._tracker.cancel()

    def run(self):
        logger = RunLogger("single")
        logger.info(
            "Single pipeline request received",
            url=self.url,
            voice=self.voice_name,
            speed=self.speed,
            source_language=self.source_language,
            create_anki=self.create_anki,
            anki_only=self.anki_only,
            output_dir=str(self.output_dir),
        )

        last_step = ["init"]

        def logged_step_cb(label):
            last_step[0] = label
            logger.info("Step changed", stage=label)
            self.step_changed.emit(label)

        def logged_progress_cb(current, total, message):
            logger.info("Progress", stage=last_step[0], current=current, total=total, progress_message=message)
            self.progress.emit(current, total, message)

        try:
            result = run_single_pipeline(
                self.url, self.api_key, self.voice_name, self.speed,
                self.output_dir, self.cookie_browser,
                cancelled_check=lambda: self._cancelled,
                step_cb=logged_step_cb,
                progress_cb=logged_progress_cb,
                create_anki=self.create_anki,
                source_language=self.source_language,
                force_transcription=self.force_transcription,
                anki_only=self.anki_only,
                logger=logger,
                process_tracker=self._tracker,
            )
            if result and not self._cancelled:
                logger.info("Single pipeline succeeded", stage=last_step[0], result=result)
                self.finished.emit(result)
            elif self._cancelled:
                logger.info("Single pipeline cancelled", stage=last_step[0])
        except Exception as e:
            if not self._cancelled:
                logger.error("Single pipeline failed", stage=last_step[0], error=str(e))
                self.error.emit(str(e))
        finally:
            logger.finalize()


class BatchWorker(QThread):
    """Runs the pipeline for multiple videos with parallel download and processing.

    Uses a producer-consumer pattern: a download thread fetches videos ahead
    while a processing thread works through them as they become available.

    Signals:
        batch_progress(video_index, total_videos, video_url): Current video in batch
        step_changed(label): Current pipeline step label
        progress(current, total, message): Step-level progress
        finished(summary): Emitted on completion with summary string
        error(message): Emitted on fatal failure
    """

    batch_progress = Signal(int, int, str)
    step_changed = Signal(str)
    progress = Signal(int, int, str)
    finished = Signal(str)
    error = Signal(str)
    comprehensibility_result = Signal(str)

    def __init__(self, urls, api_key, voice_name, speed, output_dir, cookie_browser=None,
                 create_anki=False, source_language="Japanese", force_transcription=False,
                 anki_only=False, output_configs=None, resolution="",
                 lemma_list_path="", unlisted_knowledge=0, check_first=False,
                 keep_original_audio=True, keep_original_video=False,
                 auto_clear_cache=False, cache_threshold_gb=10):
        super().__init__()
        self.urls = urls
        self.api_key = api_key
        self.voice_name = voice_name
        self.speed = speed
        self.output_dir = Path(output_dir)
        self.cookie_browser = cookie_browser
        self.create_anki = create_anki
        self.source_language = source_language
        self.force_transcription = force_transcription
        self.anki_only = anki_only
        self.output_configs = output_configs or []
        self.resolution = resolution
        self.lemma_list_path = lemma_list_path
        self.unlisted_knowledge = unlisted_knowledge
        self.check_first = check_first
        self.keep_original_audio = keep_original_audio
        self.keep_original_video = keep_original_video
        self.auto_clear_cache = auto_clear_cache
        self.cache_threshold_gb = cache_threshold_gb
        self._cancelled = False
        self._tracker = ProcessTracker()
        self._check_event = None
        self._check_continue = False

    def cancel(self):
        self._cancelled = True
        self._tracker.cancel()
        # Unblock the check event so the worker thread can exit
        if self._check_event is not None:
            self._check_event.set()

    def set_check_response(self, continue_: bool):
        """Called from the UI thread to respond to a comprehensibility check dialog."""
        self._check_continue = continue_
        if self._check_event is not None:
            self._check_event.set()

    def run(self):
        try:
            self._run_batch()
        except Exception as e:
            if not self._cancelled:
                self.error.emit(str(e))

    def _run_batch(self):
        logger = RunLogger("batch")
        logger.info(
            "Batch request received",
            input_url_count=len(self.urls),
            voice=self.voice_name,
            speed=self.speed,
            source_language=self.source_language,
            create_anki=self.create_anki,
            anki_only=self.anki_only,
            force_transcription=self.force_transcription,
            cookie_browser=self.cookie_browser,
            output_dir=str(self.output_dir),
        )

        # Phase 1: Resolve URLs (expand playlists/channels)
        self.step_changed.emit("Resolving URLs...")
        logger.info("Batch phase started", phase="resolve_urls")
        resolved = resolve_urls(
            self.urls,
            cookie_browser=self.cookie_browser,
            progress_callback=lambda cur, total, msg: (
                logger.info("Resolve progress", current=cur, total=total, progress_message=msg),
                self.progress.emit(cur, total, msg),
            )[-1],
            logger=logger,
            process_tracker=self._tracker,
        )

        if self._cancelled:
            logger.info("Batch cancelled during URL resolution")
            logger.finalize()
            return

        if not resolved:
            logger.error("No valid video URLs found")
            logger.finalize()
            self.error.emit("No valid video URLs found.")
            return

        total = len(resolved)
        logger.info("URL resolution complete", resolved_count=total)

        # Phase 2: Load TTS model once for all videos (skip if no interleaving needed)
        if self.anki_only or not self.output_configs:
            tts = None
            logger.info("Skipping TTS model load (no interleaved outputs)")
        else:
            self.step_changed.emit("Loading TTS model...")
            logger.info("Batch phase started", phase="load_tts")
            tts = create_tts_engine(self.voice_name, status_cb=self.step_changed.emit)
            logger.info("TTS model loaded", tts_id=tts.tts_id)

        if self._cancelled:
            logger.info("Batch cancelled after TTS load")
            logger.finalize()
            return

        # Phase 3: Producer-consumer parallel download + process
        download_q = queue.Queue(maxsize=2)
        succeeded = 0
        failures = []
        comprehensibility_summaries = []
        consumer_idle = Event()
        consumer_idle.set()  # Initially idle — producer can emit UI updates

        # ── Producer thread: download videos ahead ─────────────────────
        def producer():
            try:
                for i, url in enumerate(resolved):
                    if self._cancelled:
                        break

                    # Use batch_mode sleep for 2nd+ videos to avoid rate limiting
                    batch_mode = (i > 0)

                    def _dl_step_cb(label, _i=i):
                        logger.info("Download step", index=_i + 1, total=total, url=url, stage=label)
                        if consumer_idle.is_set():
                            self.step_changed.emit(label)

                    def _dl_progress_cb(cur, ttl, msg, _i=i):
                        logger.info("Download progress", index=_i + 1, total=total, url=url, progress_message=msg)
                        if consumer_idle.is_set():
                            self.progress.emit(cur, ttl, msg)

                    try:
                        result = download_phase(
                            url, self.output_dir, self.cookie_browser,
                            self.source_language, self.force_transcription,
                            self.output_configs, self.anki_only,
                            cancelled_check=lambda: self._cancelled,
                            step_cb=_dl_step_cb,
                            progress_cb=_dl_progress_cb,
                            batch_mode=batch_mode,
                            index=i,
                            logger=logger,
                            resolution=self.resolution,
                            keep_original_video=self.keep_original_video,
                            process_tracker=self._tracker,
                        )
                        if result is None:  # cancelled
                            break
                        download_q.put(result)
                    except CancelledError:
                        break
                    except Exception as e:
                        download_q.put(DownloadError(url=url, index=i, error=str(e)))
            finally:
                download_q.put(None)  # sentinel — always sent

        # ── Consumer thread: process downloaded videos ─────────────────
        def consumer():
            nonlocal succeeded

            while True:
                if self._cancelled:
                    break

                # Use timeout to stay responsive to cancellation
                try:
                    item = download_q.get(timeout=1)
                except queue.Empty:
                    continue

                if item is None:  # sentinel — producer is done
                    break

                consumer_idle.clear()
                i = item.index

                # Handle download errors
                if isinstance(item, DownloadError):
                    failures.append({
                        "url": item.url,
                        "video_id": "unknown",
                        "error": item.error,
                        "stage": "download",
                        "cache_dir": "unknown",
                    })
                    logger.error(
                        "Video failed during download",
                        index=i + 1, total=total, url=item.url, error=item.error,
                    )
                    consumer_idle.set()
                    continue

                # item is DownloadResult — process it
                self.batch_progress.emit(i + 1, total, item.url)
                logger.info("Video started processing", index=i + 1, total=total, url=item.url)

                last_step = ["init"]

                def tracking_step_cb(label, _i=i, _url=item.url):
                    last_step[0] = label
                    logger.info("Step changed", index=_i + 1, total=total, url=_url, stage=label)
                    self.step_changed.emit(label)

                def tracking_progress_cb(cur, ttl, msg, _i=i, _url=item.url):
                    logger.info(
                        "Progress",
                        index=_i + 1, total=total, url=_url,
                        stage=last_step[0], current=cur, total_steps=ttl,
                        progress_message=msg,
                    )
                    self.progress.emit(cur, ttl, msg)
                    # Capture comprehensibility result for the summary
                    if last_step[0] == "Analyzing comprehensibility..." and msg.startswith("Comprehensibility:"):
                        comprehensibility_summaries.append(msg)

                # Build check callback for check-first mode
                check_cb = None
                if self.check_first and self.lemma_list_path:
                    def check_cb(message):
                        self._check_event = Event()
                        self._check_continue = False
                        self.comprehensibility_result.emit(message)
                        self._check_event.wait()
                        return self._check_continue and not self._cancelled

                try:
                    run_single_pipeline(
                        item.url, self.api_key, self.voice_name, self.speed,
                        self.output_dir, self.cookie_browser,
                        cancelled_check=lambda: self._cancelled,
                        step_cb=tracking_step_cb,
                        progress_cb=tracking_progress_cb,
                        tts=tts,
                        create_anki=self.create_anki,
                        source_language=self.source_language,
                        force_transcription=self.force_transcription,
                        anki_only=self.anki_only,
                        output_configs=self.output_configs,
                        lemma_list_path=self.lemma_list_path,
                        unlisted_knowledge=self.unlisted_knowledge,
                        check_callback=check_cb,
                        download_result=item,
                        logger=logger,
                        resolution=self.resolution,
                        keep_original_audio=self.keep_original_audio,
                        keep_original_video=self.keep_original_video,
                        process_tracker=self._tracker,
                    )
                    if not self._cancelled:
                        succeeded += 1
                        outcome = "skipped" if item.skipped else "succeeded"
                        logger.info("Video complete", index=i + 1, total=total, url=item.url, outcome=outcome, stage=last_step[0])
                except CancelledError:
                    consumer_idle.set()
                    break
                except Exception as e:
                    if self._cancelled:
                        consumer_idle.set()
                        break
                    vid = item.video_id
                    work_path = str(WORK_DIR / "interleave" / vid) if vid != "unknown" else "unknown"
                    failures.append({
                        "url": item.url,
                        "video_id": vid,
                        "error": str(e),
                        "stage": last_step[0],
                        "cache_dir": work_path,
                    })
                    logger.error(
                        "Video failed",
                        index=i + 1, total=total, url=item.url,
                        video_id=vid, stage=last_step[0], error=str(e),
                        cache_dir=work_path,
                    )

                # Auto-clear cache if enabled and threshold exceeded
                if self.auto_clear_cache and not self._cancelled:
                    from .cache_manager import auto_clear_if_needed
                    threshold_bytes = self.cache_threshold_gb * 1024 * 1024 * 1024
                    auto_clear_if_needed(threshold_bytes, logger=logger)

                consumer_idle.set()

        # Launch both threads
        producer_thread = Thread(target=producer, name="batch-download", daemon=True)
        consumer_thread = Thread(target=consumer, name="batch-process", daemon=True)
        producer_thread.start()
        consumer_thread.start()

        # Wait for both to complete
        producer_thread.join()
        consumer_thread.join()

        if self._cancelled:
            logger.info("Batch cancelled during processing", succeeded=succeeded, failed=len(failures))
            logger.finalize()
            return

        # Phase 4: Build summary
        failed = len(failures)
        summary = f"Batch complete: {succeeded} succeeded, {failed} failed out of {total} videos."
        if failures:
            details = "\n".join(
                f"  - {f['url']} (stage: {f['stage']}): {f['error']}\n"
                f"    Cache: {f['cache_dir']}"
                for f in failures
            )
            summary += f"\n\nFailed videos:\n{details}"
        if comprehensibility_summaries:
            summary += "\n\n" + "\n".join(comprehensibility_summaries)
            summary += "\nSee report files in output folder."
        summary += f"\n\nLog: {logger.path}"
        logger.record("batch.succeeded", succeeded)
        logger.record("batch.failed", failed)
        logger.record("batch.total", total)
        logger.info("Batch finished", succeeded=succeeded, failed=failed, total=total, log=str(logger.path))
        logger.finalize()

        self.finished.emit(summary)
