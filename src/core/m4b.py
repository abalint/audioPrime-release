"""M4B audiobook utilities: chapter extraction, splitting, and reassembly."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

from ..bin_paths import ffmpeg_path, ffprobe_path, _NOWWIN
from .audio import probe_audio_duration


def extract_chapters(m4b_path, process_tracker=None):
    """Extract chapter metadata from an M4B file.

    Returns:
        List of dicts with keys: id, title, start_time (float), end_time (float).
        Returns empty list if no chapters found.
    """
    cmd = [
        ffprobe_path(),
        "-v", "error",
        "-show_chapters",
        "-print_format", "json",
        str(m4b_path),
    ]
    _run = process_tracker.run if process_tracker else subprocess.run
    result = _run(cmd, capture_output=True, text=True, **_NOWWIN)
    if result.returncode != 0:
        return []

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    chapters = []
    for ch in data.get("chapters", []):
        chapters.append({
            "id": ch.get("id", len(chapters)),
            "title": ch.get("tags", {}).get("title", f"Chapter {len(chapters) + 1}"),
            "start_time": float(ch["start_time"]),
            "end_time": float(ch["end_time"]),
        })
    return chapters


def extract_metadata(m4b_path, process_tracker=None):
    """Extract format-level metadata (title, artist, etc.) from an M4B file.

    Returns:
        Dict of metadata tags (lowercased keys). Empty dict on failure.
    """
    cmd = [
        ffprobe_path(),
        "-v", "error",
        "-show_format",
        "-print_format", "json",
        str(m4b_path),
    ]
    _run = process_tracker.run if process_tracker else subprocess.run
    result = _run(cmd, capture_output=True, text=True, **_NOWWIN)
    if result.returncode != 0:
        return {}

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}

    return data.get("format", {}).get("tags", {})


def split_chapter_audio(m4b_path, start, end, output_mp3, process_tracker=None):
    """Extract a chapter's audio segment from an M4B file as MP3.

    Args:
        m4b_path: Path to the M4B file
        start: Start time in seconds
        end: End time in seconds
        output_mp3: Path for output MP3 file
    """
    duration = end - start
    cmd = [
        ffmpeg_path(), "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(m4b_path),
        "-ss", f"{start:.3f}",
        "-t", f"{duration:.3f}",
        "-vn",
        "-acodec", "libmp3lame", "-q:a", "2",
        str(output_mp3),
    ]
    _run = process_tracker.run if process_tracker else subprocess.run
    result = _run(cmd, capture_output=True, text=True, **_NOWWIN)
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to extract chapter audio [{start:.1f}s-{end:.1f}s]: "
            f"{result.stderr.strip()}"
        )


def filter_srt_to_chapter(subs, chapter_start, chapter_end):
    """Filter parsed SRT entries to a chapter's time range.

    Includes subtitles that start within the chapter range.
    Timestamps are offset to be chapter-relative (start from 0).

    Args:
        subs: List of (start, end, text) tuples from parse_srt()
        chapter_start: Chapter start time in seconds
        chapter_end: Chapter end time in seconds

    Returns:
        List of (start, end, text) tuples with chapter-relative timestamps.
    """
    filtered = []
    for start, end, text in subs:
        if start >= chapter_start and start < chapter_end:
            new_start = start - chapter_start
            new_end = min(end, chapter_end) - chapter_start
            filtered.append((new_start, new_end, text))
    return filtered


def generate_ffmetadata(chapters_with_durations, metadata=None):
    """Generate FFMETADATA1 text with chapter markers and global metadata.

    Args:
        chapters_with_durations: List of dicts with "title" and "duration" (seconds).
        metadata: Optional dict of global metadata tags (title, artist, etc.)

    Returns:
        FFMETADATA1 formatted string.
    """
    lines = [";FFMETADATA1"]

    if metadata:
        for key, value in metadata.items():
            safe_value = str(value).replace("\\", "\\\\").replace("=", "\\=").replace(";", "\\;").replace("#", "\\#").replace("\n", "\\\n")
            lines.append(f"{key}={safe_value}")

    cursor_ms = 0
    for ch in chapters_with_durations:
        duration_ms = int(ch["duration"] * 1000)
        start_ms = cursor_ms
        end_ms = cursor_ms + duration_ms

        lines.append("")
        lines.append("[CHAPTER]")
        lines.append("TIMEBASE=1/1000")
        lines.append(f"START={start_ms}")
        lines.append(f"END={end_ms}")
        title = ch["title"].replace("\\", "\\\\").replace("=", "\\=").replace(";", "\\;").replace("#", "\\#").replace("\n", "\\\n")
        lines.append(f"title={title}")

        cursor_ms = end_ms

    return "\n".join(lines) + "\n"


def assemble_m4b(chapter_mp3s, metadata_text, output_path, process_tracker=None):
    """Concatenate chapter MP3s into a single M4B with chapter metadata.

    Args:
        chapter_mp3s: List of paths to per-chapter interleaved MP3 files.
        metadata_text: FFMETADATA1 formatted string with chapter markers.
        output_path: Path for the output M4B file.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Write concat list
        concat_path = os.path.join(tmp_dir, "concat.txt")
        with open(concat_path, "w") as f:
            for mp3 in chapter_mp3s:
                f.write(f"file '{os.path.abspath(mp3)}'\n")

        # Write metadata file
        meta_path = os.path.join(tmp_dir, "metadata.txt")
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write(metadata_text)

        _run = process_tracker.run if process_tracker else subprocess.run
        cmd = [
            ffmpeg_path(), "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", concat_path,
            "-i", meta_path,
            "-map_metadata", "1",
            "-codec:a", "aac", "-b:a", "128k",
            "-f", "ipod",
            str(output_path),
        ]
        result = _run(cmd, capture_output=True, text=True, **_NOWWIN)
        if result.returncode != 0:
            raise RuntimeError(
                f"M4B assembly failed: {result.stderr.strip()}"
            )
