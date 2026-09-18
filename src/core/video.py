"""ffmpeg helpers for video probing, slicing, freeze-frame clips, and concatenation."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

from ..bin_paths import ffmpeg_path, ffprobe_path, _NOWWIN

# ── Shared encoding parameters ───────────────────────────────────────
# Pinning profile, level, and GOP ensures all segments produce
# bitstream-compatible streams safe for concat-demuxer copy.
_H264_PARAMS = [
    "-c:v", "libx264",
    "-profile:v", "high",
    "-level:v", "4.1",
    "-pix_fmt", "yuv420p",
    "-g", "60",
    "-bf", "2",
]

_AAC_PARAMS = [
    "-c:a", "aac",
    "-b:a", "192k",
    "-ar", "48000",
    "-ac", "2",
]


def probe_video_info(video_path, process_tracker=None):
    """Return (width, height, fps) for the first video stream.

    Raises RuntimeError if probing fails.
    """
    cmd = [
        ffprobe_path(), "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate",
        "-of", "json",
        str(video_path),
    ]
    _run = process_tracker.run if process_tracker else subprocess.run
    result = _run(cmd, capture_output=True, text=True, timeout=15, **_NOWWIN)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe video info failed: {result.stderr.strip()}")

    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    if not streams:
        raise RuntimeError(f"No video stream found in {video_path}")

    stream = streams[0]
    width = int(stream["width"])
    height = int(stream["height"])

    # r_frame_rate is a fraction like "30000/1001"
    fps_str = stream.get("r_frame_rate", "30/1")
    num, den = fps_str.split("/")
    fps = float(num) / float(den) if float(den) != 0 else 30.0

    return width, height, fps


def probe_video_duration(video_path, process_tracker=None):
    """Return video duration in seconds, or None on failure."""
    cmd = [
        ffprobe_path(), "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    _run = process_tracker.run if process_tracker else subprocess.run
    try:
        result = _run(cmd, capture_output=True, text=True, timeout=15, **_NOWWIN)
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except (TypeError, ValueError):
        return None


def extract_frame(video_path, timestamp, output_png, process_tracker=None):
    """Extract a single frame at *timestamp* seconds to a PNG file."""
    cmd = [
        ffmpeg_path(), "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{timestamp:.3f}",
        "-i", str(video_path),
        "-frames:v", "1",
        str(output_png),
    ]
    _run = process_tracker.run if process_tracker else subprocess.run
    result = _run(cmd, capture_output=True, text=True, **_NOWWIN)
    if result.returncode != 0:
        raise RuntimeError(f"extract_frame failed at {timestamp:.3f}s: {result.stderr.strip()}")


def create_freeze_frame_clip(frame_path, audio_path, output_mp4, width, height, fps,
                             process_tracker=None):
    """Create a video clip from a still image + audio track."""
    cmd = [
        ffmpeg_path(), "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1",
        "-framerate", str(fps),
        "-i", str(frame_path),
        "-i", str(audio_path),
        *_H264_PARAMS,
        "-vf", f"scale={width}:{height}",
        "-r", str(fps),
        *_AAC_PARAMS,
        "-shortest",
        "-movflags", "+faststart",
        str(output_mp4),
    ]
    _run = process_tracker.run if process_tracker else subprocess.run
    result = _run(cmd, capture_output=True, text=True, **_NOWWIN)
    if result.returncode != 0:
        raise RuntimeError(f"create_freeze_frame_clip failed: {result.stderr.strip()}")


def slice_video(video_path, start, end, output_mp4, width, height, fps,
                process_tracker=None):
    """Re-encode a video segment to matching resolution/fps/codec."""
    duration = end - start
    cmd = [
        ffmpeg_path(), "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{start:.3f}",
        "-i", str(video_path),
        "-t", f"{duration:.3f}",
        *_H264_PARAMS,
        "-vf", f"scale={width}:{height}",
        "-r", str(fps),
        *_AAC_PARAMS,
        "-movflags", "+faststart",
        str(output_mp4),
    ]
    _run = process_tracker.run if process_tracker else subprocess.run
    result = _run(cmd, capture_output=True, text=True, **_NOWWIN)
    if result.returncode != 0:
        raise RuntimeError(
            f"slice_video failed [{start:.3f}s -> {end:.3f}s]: {result.stderr.strip()}"
        )


def concatenate_video_segments(segment_files, output_mp4, process_tracker=None):
    """Concatenate video segments using the ffmpeg concat demuxer with stream copy."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        for seg in segment_files:
            f.write(f"file '{os.path.abspath(seg)}'\n")
        concat_list = f.name

    _run = process_tracker.run if process_tracker else subprocess.run
    try:
        _run([
            ffmpeg_path(), "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-c:v", "copy",
            *_AAC_PARAMS,
            "-movflags", "+faststart",
            str(output_mp4),
        ], check=True, **_NOWWIN)
    finally:
        os.unlink(concat_list)


def validate_video_file(filepath):
    """Return True if *filepath* exists, is non-empty, and has a readable duration."""
    path = Path(filepath)
    if not path.exists() or path.stat().st_size == 0:
        return False
    return probe_video_duration(str(filepath)) is not None
