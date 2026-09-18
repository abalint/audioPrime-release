"""Audio interleaving: alternate English TTS with Japanese audio segments."""

from pathlib import Path

from .process_tracker import CancelledError

from .audio import (
    adjust_speed,
    adjust_speed_and_normalize,
    concatenate_segments,
    match_loudness,
    probe_audio_duration,
    measure_loudness,
    slice_audio,
    text_hash,
    validate_audio_file,
    _next_version,
    MIN_SLICE_DURATION,
)
from .srt_parser import _is_non_speech, parse_srt
from .translator import is_unclear_placeholder
from .video import (
    concatenate_video_segments,
    create_freeze_frame_clip,
    extract_frame,
    probe_video_duration,
    probe_video_info,
    slice_video,
    validate_video_file,
)

MIN_JAPANESE_DURATION = 2.0  # Minimum seconds of Japanese audio to play at a time


def _should_synthesize_tts(text: str) -> bool:
    """Return True when text has spoken content worth synthesizing.

    Skip placeholders, punctuation-only artifacts like "?" that can
    produce empty/broken TTS audio files, and non-speech annotations
    like [Music] or (singing) that may survive through translation.
    """
    stripped = text.strip()
    if not stripped or is_unclear_placeholder(stripped):
        return False
    if _is_non_speech(stripped):
        return False
    return any(ch.isalnum() for ch in stripped)


def _collapse_short_segments(en_subs, total_duration):
    """Collapse consecutive English subtitles to ensure minimum Japanese audio duration.

    Args:
        en_subs: List of (start, end, text) tuples from English SRT
        total_duration: Total duration of source audio in seconds

    Returns:
        List of collapsed (start, end, text) tuples where each segment corresponds
        to at least MIN_JAPANESE_DURATION seconds of Japanese audio
    """
    if not en_subs:
        return []

    collapsed = []
    i = 0

    while i < len(en_subs):
        # Start a new collapsed segment
        group_start, _, group_text = en_subs[i]
        group_texts = [group_text]

        # Calculate Japanese audio duration for current segment
        # (from this subtitle's start to the next subtitle's start, or to end of audio)
        next_start = en_subs[i + 1][0] if i + 1 < len(en_subs) else total_duration
        jp_duration = next_start - group_start

        # Keep merging with next subtitles until we have at least MIN_JAPANESE_DURATION
        j = i + 1
        while jp_duration < MIN_JAPANESE_DURATION and j < len(en_subs):
            _, _, next_text = en_subs[j]
            group_texts.append(next_text)

            # Recalculate Japanese duration with this subtitle included
            next_start = en_subs[j + 1][0] if j + 1 < len(en_subs) else total_duration
            jp_duration = next_start - group_start
            j += 1

        # Combine all texts in the group with a space
        combined_text = " ".join(group_texts)

        # Use the original end time of the last subtitle in the group
        # (though this isn't used in interleaving, keeping for consistency)
        group_end = en_subs[j - 1][1] if j > i else en_subs[i][1]

        collapsed.append((group_start, group_end, combined_text))
        i = j

    return collapsed


def interleave(src_audio, src_srt, en_srt, output, tts, speed, work_dir,
               sentence_punct, progress_callback=None, group_size=1,
               condense=False, return_segments=False, logger=None,
               cancelled_check=None, process_tracker=None):
    """Run the interleave pipeline for a single file set.

    Preserves ALL source audio by emitting EN TTS at subtitle timestamps
    interleaved with JP audio segments that tile [0, total_duration].

    When *condense* is True, gaps ≥ 2.0s between subtitles are trimmed from
    the JP audio slices, keeping 250ms padding on each side (500ms total)
    for smooth transitions.

    Output pattern:
        JP[0→s0], EN_0, JP[s0→s1], EN_1, ..., EN_n, JP[sn→end]

    Args:
        src_audio: Path to source language audio mp3
        src_srt: Path to source language SRT file (not used, kept for compatibility)
        en_srt: Path to English SRT file
        output: Path for output mp3
        tts: PiperTTS instance
        speed: English TTS playback speed (1.0 = normal)
        work_dir: Directory for cached intermediate files
        sentence_punct: Regex pattern string (not used, kept for compatibility)
        progress_callback: Optional callable(current, total, message)
        condense: If True, trim long gaps (≥2s) from JP audio slices
        return_segments: If True, return list of segment metadata dicts

    Returns:
        None normally, or list of segment metadata dicts when return_segments=True.
        Each dict has: type ("en"|"jp"), src_start, src_end, path.
    """
    src_audio = str(src_audio)
    en_srt = str(en_srt)
    output = str(output)
    work_dir = Path(work_dir)

    en_parts_dir = work_dir / "en_tts"
    src_parts_dir = work_dir / "src_slices"
    en_parts_dir.mkdir(parents=True, exist_ok=True)
    src_parts_dir.mkdir(parents=True, exist_ok=True)

    tts_id = tts.tts_id

    # Parse English subtitles only
    if progress_callback:
        progress_callback(0, 1, "Parsing subtitles...")

    en_subs = parse_srt(en_srt)
    if not en_subs:
        raise ValueError("No English subtitles found")

    # Measure source audio loudness
    if progress_callback:
        progress_callback(0, len(en_subs), "Measuring loudness...")

    target_lufs = measure_loudness(src_audio, process_tracker=process_tracker)

    # Get total audio duration (needed for last segment and assertions)
    total_duration = probe_audio_duration(src_audio, process_tracker=process_tracker)
    if total_duration is None:
        raise RuntimeError(f"Could not determine source audio duration: {src_audio}")

    # Collapse short English subtitles to ensure minimum Japanese audio duration
    if progress_callback:
        progress_callback(0, len(en_subs), "Collapsing short segments...")

    original_count = len(en_subs)
    en_subs = _collapse_short_segments(en_subs, total_duration)
    if logger:
        logger.debug("Interleave setup", original_segments=original_count,
                      collapsed_segments=len(en_subs), source_duration_sec=round(total_duration, 2),
                      condense=condense, group_size=group_size)

    if progress_callback:
        progress_callback(0, len(en_subs), f"Collapsed {original_count} segments into {len(en_subs)}")

    segment_files = []
    segment_meta = []  # parallel list: {"type": "en"|"jp", "src_start": float, "src_end": float, "path": str}
    jp_segments = []  # list of {"start": float, "end": float, "seg_index": int, "path": str}

    # Pre-roll: JP audio before first subtitle (if any)
    first_start = en_subs[0][0]
    pending_start = None

    CONDENSE_MIN_GAP = 2.0    # seconds — gaps shorter than this are kept
    CONDENSE_PADDING = 0.250  # seconds — padding kept on each side of a gap

    # When condensing, trim a long pre-roll down to just the lead-in padding
    effective_preroll_start = 0.0
    if condense and first_start > CONDENSE_MIN_GAP:
        effective_preroll_start = first_start - CONDENSE_PADDING

    preroll_duration = first_start - effective_preroll_start
    if preroll_duration >= MIN_SLICE_DURATION:
        preroll_key = text_hash(f"{src_audio}|{effective_preroll_start}|{first_start}")
        preroll_mp3 = src_parts_dir / f"preroll_{preroll_key}.mp3"
        if not validate_audio_file(preroll_mp3):
            if preroll_mp3.exists():
                preroll_mp3 = _next_version(preroll_mp3)
            slice_audio(src_audio, effective_preroll_start, first_start, str(preroll_mp3),
                       process_tracker=process_tracker)
        segment_files.append(str(preroll_mp3))
        segment_meta.append({"type": "jp", "src_start": effective_preroll_start, "src_end": first_start, "path": str(preroll_mp3)})
        jp_segments.append({
            "start": effective_preroll_start,
            "end": first_start,
            "seg_index": len(segment_files) - 1,
            "path": str(preroll_mp3),
        })
    elif first_start > 0.001:
        # Pre-roll too small — carry 0.0 forward so first main segment starts at 0
        pending_start = effective_preroll_start
    # else: first subtitle starts at ~0, no pre-roll needed

    # Main loop: every subtitle treated the same — EN then JP
    for i, (start, end, en_text) in enumerate(en_subs):
        if cancelled_check and cancelled_check():
            raise CancelledError("Operation cancelled")
        if progress_callback:
            progress_callback(i + 1, len(en_subs), f"Processing segment {i + 1}/{len(en_subs)}")

        # Step 1: English TTS
        if _should_synthesize_tts(en_text):
            cache_key = text_hash(f"{en_text}|{tts_id}")
            en_mp3 = en_parts_dir / f"{i:04d}_{cache_key}.mp3"

            if not validate_audio_file(en_mp3):
                if en_mp3.exists():
                    en_mp3 = _next_version(en_mp3)
                tts.synthesize_to_mp3(en_text, str(en_mp3),
                                     process_tracker=process_tracker)

            process_suffix = ""
            if speed != 1.0:
                process_suffix += f"_speed{speed}"
            process_suffix += f"_norm{target_lufs:.0f}"

            en_final = en_parts_dir / f"{i:04d}_{cache_key}{process_suffix}.mp3"
            if not validate_audio_file(en_final):
                if en_final.exists():
                    en_final = _next_version(en_final)
                adjust_speed_and_normalize(str(en_mp3), str(en_final), speed, target_lufs,
                                           process_tracker=process_tracker)

            segment_files.append(str(en_final))
            segment_meta.append({"type": "en", "src_start": start, "src_end": None, "path": str(en_final)})

        # Step 2: JP audio from this subtitle's start to next subtitle's start (or end)
        next_start = en_subs[i + 1][0] if i + 1 < len(en_subs) else total_duration
        jp_start = pending_start if pending_start is not None else start
        pending_start = None  # reset

        # When condensing, check for a long gap between this subtitle's end
        # and the next subtitle's start.  If found, emit two trimmed slices:
        #   1) speech region + 250ms tail padding
        #   2) 250ms lead-in before the next subtitle
        gap = next_start - end if i + 1 < len(en_subs) else 0.0
        if condense and gap >= CONDENSE_MIN_GAP:
            # Slice 1: speech region → subtitle end + padding
            trim_end = min(end + CONDENSE_PADDING, next_start)
            trim_duration = trim_end - jp_start
            if trim_duration >= MIN_SLICE_DURATION:
                key1 = text_hash(f"{src_audio}|{jp_start}|{trim_end}")
                mp3_1 = src_parts_dir / f"{i:04d}a_{key1}.mp3"
                if not validate_audio_file(mp3_1):
                    if mp3_1.exists():
                        mp3_1 = _next_version(mp3_1)
                    slice_audio(src_audio, jp_start, trim_end, str(mp3_1),
                               process_tracker=process_tracker)
                segment_files.append(str(mp3_1))
                segment_meta.append({"type": "jp", "src_start": jp_start, "src_end": trim_end, "path": str(mp3_1)})
                jp_segments.append({
                    "start": jp_start,
                    "end": trim_end,
                    "seg_index": len(segment_files) - 1,
                    "path": str(mp3_1),
                })
            else:
                pending_start = jp_start

            # Slice 2: lead-in padding before next subtitle
            leadin_start = max(next_start - CONDENSE_PADDING, trim_end if trim_duration >= MIN_SLICE_DURATION else jp_start)
            leadin_duration = next_start - leadin_start
            if leadin_duration >= MIN_SLICE_DURATION:
                key2 = text_hash(f"{src_audio}|{leadin_start}|{next_start}")
                mp3_2 = src_parts_dir / f"{i:04d}b_{key2}.mp3"
                if not validate_audio_file(mp3_2):
                    if mp3_2.exists():
                        mp3_2 = _next_version(mp3_2)
                    slice_audio(src_audio, leadin_start, next_start, str(mp3_2),
                               process_tracker=process_tracker)
                segment_files.append(str(mp3_2))
                segment_meta.append({"type": "jp", "src_start": leadin_start, "src_end": next_start, "path": str(mp3_2)})
                jp_segments.append({
                    "start": leadin_start,
                    "end": next_start,
                    "seg_index": len(segment_files) - 1,
                    "path": str(mp3_2),
                })
            # If lead-in is too small, next iteration will pick up from next_start normally
        else:
            # Normal path: no condensing or gap too small
            jp_duration = next_start - jp_start
            if jp_duration < MIN_SLICE_DURATION:
                # Near-zero interval — carry start forward to merge with next segment
                pending_start = jp_start
                continue

            src_cache_key = text_hash(f"{src_audio}|{jp_start}|{next_start}")
            src_mp3 = src_parts_dir / f"{i:04d}_{src_cache_key}.mp3"

            if not validate_audio_file(src_mp3):
                if src_mp3.exists():
                    src_mp3 = _next_version(src_mp3)
                slice_audio(src_audio, jp_start, next_start, str(src_mp3),
                           process_tracker=process_tracker)

            segment_files.append(str(src_mp3))
            segment_meta.append({"type": "jp", "src_start": jp_start, "src_end": next_start, "path": str(src_mp3)})
            jp_segments.append({
                "start": jp_start,
                "end": next_start,
                "seg_index": len(segment_files) - 1,
                "path": str(src_mp3),
            })

    # After loop: backward-merge if last interval was tiny
    if pending_start is not None:
        # Last JP interval was too small to emit on its own.
        # Extend the last emitted JP segment's end to total_duration.
        if not jp_segments:
            raise RuntimeError(
                "No JP segments emitted — all subtitle intervals are < MIN_SLICE_DURATION. "
                "This file cannot be processed."
            )

        last = jp_segments[-1]
        extended_start = last["start"]
        extended_key = text_hash(f"{src_audio}|{extended_start}|{total_duration}")
        extended_mp3 = src_parts_dir / f"extended_{extended_key}.mp3"
        if not validate_audio_file(extended_mp3):
            if extended_mp3.exists():
                extended_mp3 = _next_version(extended_mp3)
            slice_audio(src_audio, extended_start, total_duration, str(extended_mp3),
                       process_tracker=process_tracker)

        # Replace JP segment in-place using JP metadata index (never remove EN segments)
        segment_files[last["seg_index"]] = str(extended_mp3)
        segment_meta[last["seg_index"]] = {"type": "jp", "src_start": extended_start, "src_end": total_duration, "path": str(extended_mp3)}
        last["end"] = total_duration
        last["path"] = str(extended_mp3)

    # JP continuity assertion
    if not jp_segments:
        raise RuntimeError(
            "No JP segments emitted — all subtitle intervals are < MIN_SLICE_DURATION. "
            "This file cannot be processed."
        )

    if not condense:
        for j in range(1, len(jp_segments)):
            prev_end = jp_segments[j - 1]["end"]
            curr_start = jp_segments[j]["start"]
            if abs(prev_end - curr_start) > 0.001:
                raise RuntimeError(
                    f"JP continuity break: segment {j-1} ends at {prev_end:.3f}s "
                    f"but segment {j} starts at {curr_start:.3f}s"
                )

    if not condense and jp_segments[0]["start"] != 0.0:
        raise RuntimeError(f"JP timeline does not start at 0: starts at {jp_segments[0]['start']:.3f}s")
    if abs(jp_segments[-1]["end"] - total_duration) > 0.5:
        raise RuntimeError(
            f"JP timeline does not reach end: last segment ends at {jp_segments[-1]['end']:.3f}s "
            f"but total duration is {total_duration:.3f}s"
        )

    # Heal any stale/corrupt JP slice cache entries before concatenation.
    for seg in jp_segments:
        seg_path = Path(seg["path"])
        if validate_audio_file(seg_path):
            continue
        if seg_path.exists():
            seg_path = _next_version(seg_path)
        slice_audio(src_audio, seg["start"], seg["end"], str(seg_path),
                   process_tracker=process_tracker)
        seg["path"] = str(seg_path)
        segment_files[seg["seg_index"]] = str(seg_path)
        segment_meta[seg["seg_index"]]["path"] = str(seg_path)

    # Reorder segments for sentence grouping (group_size > 1)
    if group_size > 1:
        # Build parallel lists: en_indices[i] and jp_indices[i] hold the
        # segment_files index for subtitle i's EN TTS and JP slice respectively.
        # A value of None means the segment was skipped (empty TTS or merged JP).
        en_indices = []
        jp_indices = []

        # Rebuild index mapping by replaying the loop logic
        seg_idx = 0
        preroll_file = None
        if first_start >= MIN_SLICE_DURATION:
            preroll_file = segment_files[0]
            seg_idx = 1

        replay_pending_start = None
        for i, (start, end, en_text) in enumerate(en_subs):
            # EN TTS
            if _should_synthesize_tts(en_text):
                en_indices.append(seg_idx)
                seg_idx += 1
            else:
                en_indices.append(None)

            # JP slice (mirrors pending_start logic from main loop)
            next_start = en_subs[i + 1][0] if i + 1 < len(en_subs) else total_duration
            jp_start = replay_pending_start if replay_pending_start is not None else start
            replay_pending_start = None
            jp_duration = next_start - jp_start

            if jp_duration < MIN_SLICE_DURATION:
                replay_pending_start = jp_start
                jp_indices.append(None)
            else:
                jp_indices.append(seg_idx)
                seg_idx += 1

        num_subs = len(en_subs)
        new_files = []
        new_meta = []
        if preroll_file is not None:
            new_files.append(preroll_file)
            new_meta.append(segment_meta[0])

        for g in range(0, num_subs, group_size):
            chunk_end = min(g + group_size, num_subs)
            for k in range(g, chunk_end):
                if en_indices[k] is not None:
                    new_files.append(segment_files[en_indices[k]])
                    new_meta.append(segment_meta[en_indices[k]])
            for k in range(g, chunk_end):
                if jp_indices[k] is not None:
                    new_files.append(segment_files[jp_indices[k]])
                    new_meta.append(segment_meta[jp_indices[k]])

        segment_files = new_files
        segment_meta = new_meta

    # Concatenate all segments
    if progress_callback:
        progress_callback(len(en_subs), len(en_subs), "Concatenating final audio...")

    concatenate_segments(segment_files, output, process_tracker=process_tracker)

    # Output duration integrity check
    expected_duration = 0.0
    for seg in segment_files:
        seg_duration = probe_audio_duration(seg)
        if seg_duration is None:
            raise RuntimeError(f"Could not determine segment duration (ffprobe returned non-numeric): {seg}")
        expected_duration += seg_duration

    actual_duration = probe_audio_duration(output)
    if actual_duration is None:
        raise RuntimeError(f"Could not determine output duration: {output}")

    if abs(actual_duration - expected_duration) > 1.0:
        raise RuntimeError(
            f"Output duration mismatch: expected {expected_duration:.1f}s, "
            f"got {actual_duration:.1f}s. Segment manifest in {work_dir}"
        )

    if logger:
        tts_count = sum(1 for m in segment_meta if m["type"] == "en")
        jp_count = sum(1 for m in segment_meta if m["type"] == "jp")
        logger.debug("Interleave complete", total_segments=len(segment_files),
                      en_tts_segments=tts_count, jp_segments=jp_count,
                      output_duration_sec=round(actual_duration, 2))

    if return_segments:
        return segment_meta
    return None


def interleave_video(src_video, en_srt, output, tts, speed, work_dir,
                     sentence_punct, progress_callback=None, group_size=1,
                     condense=False, logger=None,
                     cancelled_check=None, process_tracker=None):
    """Create an interleaved video: freeze-frame during EN TTS, normal video during JP audio.

    Single-pass architecture — constructs video clips directly from SRT subtitles
    without dependency on the audio-only interleave() function.

    Output pattern per subtitle:
        [EN TTS over freeze-frame] → [Original video with native audio]

    Args:
        src_video: Path to source video file (mp4)
        en_srt: Path to English SRT file
        output: Path for output mp4
        tts: PiperTTS instance
        speed: English TTS playback speed
        work_dir: Directory for cached intermediate files
        sentence_punct: Regex pattern string (unused, kept for compatibility)
        progress_callback: Optional callable(current, total, message)
        group_size: Number of sentences to group (default 1)
        condense: If True, trim long gaps from video segments
    """
    src_video = str(src_video)
    output = str(output)
    work_dir = Path(work_dir)

    vid_parts_dir = work_dir / "vid_slices"
    frames_dir = work_dir / "frames"
    en_tts_dir = work_dir / "en_tts"
    vid_parts_dir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)
    en_tts_dir.mkdir(parents=True, exist_ok=True)

    tts_id = tts.tts_id

    # ── Phase 0: Setup ──────────────────────────────────────────────────
    if progress_callback:
        progress_callback(0, 1, "Parsing subtitles...")

    en_subs = parse_srt(en_srt)
    if not en_subs:
        raise ValueError("No English subtitles found")

    width, height, fps = probe_video_info(src_video, process_tracker=process_tracker)

    total_duration = probe_video_duration(src_video, process_tracker=process_tracker)
    if total_duration is None:
        raise RuntimeError(f"Could not determine video duration: {src_video}")

    target_lufs = measure_loudness(src_video, process_tracker=process_tracker)

    original_count = len(en_subs)
    en_subs = _collapse_short_segments(en_subs, total_duration)
    if progress_callback:
        progress_callback(0, len(en_subs),
                          f"Collapsed {original_count} segments into {len(en_subs)}")

    CONDENSE_MIN_GAP = 2.0
    CONDENSE_PADDING = 0.250

    # ── Phase 1: Generate all TTS audio (cached) ────────────────────────
    tts_paths = {}  # i → path (or absent if skipped)
    for i, (start, end, en_text) in enumerate(en_subs):
        if cancelled_check and cancelled_check():
            raise CancelledError("Operation cancelled")
        if progress_callback:
            progress_callback(i + 1, len(en_subs),
                              f"Generating TTS {i + 1}/{len(en_subs)}")

        if not _should_synthesize_tts(en_text):
            continue

        cache_key = text_hash(f"{en_text}|{tts_id}")
        raw_mp3 = en_tts_dir / f"{i:04d}_{cache_key}.mp3"
        if not validate_audio_file(raw_mp3):
            if raw_mp3.exists():
                raw_mp3 = _next_version(raw_mp3)
            tts.synthesize_to_mp3(en_text, str(raw_mp3),
                                  process_tracker=process_tracker)

        # Build processed filename suffix
        process_suffix = ""
        if speed != 1.0:
            process_suffix += f"_speed{speed}"
        process_suffix += f"_norm{target_lufs:.0f}"

        final_mp3 = en_tts_dir / f"{i:04d}_{cache_key}{process_suffix}.mp3"
        if not validate_audio_file(final_mp3):
            if final_mp3.exists():
                final_mp3 = _next_version(final_mp3)
            adjust_speed_and_normalize(str(raw_mp3), str(final_mp3), speed, target_lufs,
                                       process_tracker=process_tracker)

        tts_paths[i] = str(final_mp3)

    # ── Phase 2: Build clip list (single pass) ──────────────────────────
    # Each entry is a dict: {"type": "en"|"jp", "path": str}
    # We build parallel lists per subtitle for group reordering.
    # subtitle_groups[i] = {"en_clip": path|None, "jp_clips": [path, ...]}
    subtitle_groups = []

    first_start = en_subs[0][0]
    pending_start = None

    # Pre-roll: video before first subtitle
    effective_preroll_start = 0.0
    if condense and first_start > CONDENSE_MIN_GAP:
        effective_preroll_start = first_start - CONDENSE_PADDING

    preroll_clip = None
    preroll_duration = first_start - effective_preroll_start
    if preroll_duration >= MIN_SLICE_DURATION:
        clip_key = text_hash(f"{src_video}|preroll|{effective_preroll_start}|{first_start}")
        preroll_mp4 = vid_parts_dir / f"preroll_{clip_key}.mp4"
        if not validate_video_file(preroll_mp4):
            if preroll_mp4.exists():
                preroll_mp4 = _next_version(preroll_mp4)
            slice_video(src_video, effective_preroll_start, first_start,
                        str(preroll_mp4), width, height, fps,
                        process_tracker=process_tracker)
        preroll_clip = str(preroll_mp4)
    elif first_start > 0.001:
        pending_start = effective_preroll_start

    # Track JP segments for continuity checks and backward-merge
    jp_segments = []  # {"start", "end", "group_idx", "clip_idx"}

    for i, (start, end, en_text) in enumerate(en_subs):
        if cancelled_check and cancelled_check():
            raise CancelledError("Operation cancelled")
        if progress_callback:
            progress_callback(i + 1, len(en_subs),
                              f"Building video clip {i + 1}/{len(en_subs)}")

        group = {"en_clip": None, "jp_clips": []}

        # ── EN clip: freeze-frame with TTS audio ──
        if i in tts_paths:
            # Clamp timestamp to just before video end to avoid extraction failure
            safe_ts = min(start, max(total_duration - 0.1, 0.0))
            frame_key = text_hash(f"{src_video}|frame|{start}")
            frame_png = frames_dir / f"{i:04d}_{frame_key}.png"
            if not frame_png.exists():
                try:
                    extract_frame(src_video, safe_ts, str(frame_png),
                                  process_tracker=process_tracker)
                except RuntimeError:
                    # Fallback: try 1 second before video end
                    fallback_ts = max(total_duration - 1.0, 0.0)
                    extract_frame(src_video, fallback_ts, str(frame_png),
                                  process_tracker=process_tracker)

            clip_key = text_hash(f"{src_video}|en_av|{i}|{start}|{tts_paths[i]}")
            en_mp4 = vid_parts_dir / f"{i:04d}_en_av_{clip_key}.mp4"
            if not validate_video_file(en_mp4):
                if en_mp4.exists():
                    en_mp4 = _next_version(en_mp4)
                create_freeze_frame_clip(str(frame_png), tts_paths[i],
                                         str(en_mp4), width, height, fps,
                                         process_tracker=process_tracker)
            group["en_clip"] = str(en_mp4)

        # ── JP clip(s): video slice with native audio ──
        next_start = en_subs[i + 1][0] if i + 1 < len(en_subs) else total_duration
        jp_start = pending_start if pending_start is not None else start
        pending_start = None

        gap = next_start - end if i + 1 < len(en_subs) else 0.0

        if condense and gap >= CONDENSE_MIN_GAP:
            # Slice 1: speech region + tail padding
            trim_end = min(end + CONDENSE_PADDING, next_start)
            trim_duration = trim_end - jp_start
            if trim_duration >= MIN_SLICE_DURATION:
                key1 = text_hash(f"{src_video}|jp_av|{jp_start}|{trim_end}")
                mp4_1 = vid_parts_dir / f"{i:04d}a_jp_{key1}.mp4"
                if not validate_video_file(mp4_1):
                    if mp4_1.exists():
                        mp4_1 = _next_version(mp4_1)
                    slice_video(src_video, jp_start, trim_end,
                                str(mp4_1), width, height, fps,
                                process_tracker=process_tracker)
                group["jp_clips"].append(str(mp4_1))
                jp_segments.append({
                    "start": jp_start, "end": trim_end,
                    "group_idx": i, "clip_idx": len(group["jp_clips"]) - 1,
                })
            else:
                pending_start = jp_start

            # Slice 2: lead-in before next subtitle
            leadin_start = max(next_start - CONDENSE_PADDING,
                               trim_end if trim_duration >= MIN_SLICE_DURATION else jp_start)
            leadin_duration = next_start - leadin_start
            if leadin_duration >= MIN_SLICE_DURATION:
                key2 = text_hash(f"{src_video}|jp_av|{leadin_start}|{next_start}")
                mp4_2 = vid_parts_dir / f"{i:04d}b_jp_{key2}.mp4"
                if not validate_video_file(mp4_2):
                    if mp4_2.exists():
                        mp4_2 = _next_version(mp4_2)
                    slice_video(src_video, leadin_start, next_start,
                                str(mp4_2), width, height, fps,
                                process_tracker=process_tracker)
                group["jp_clips"].append(str(mp4_2))
                jp_segments.append({
                    "start": leadin_start, "end": next_start,
                    "group_idx": i, "clip_idx": len(group["jp_clips"]) - 1,
                })
        else:
            # Normal path
            jp_duration = next_start - jp_start
            if jp_duration < MIN_SLICE_DURATION:
                pending_start = jp_start
                subtitle_groups.append(group)
                continue

            clip_key = text_hash(f"{src_video}|jp_av|{jp_start}|{next_start}")
            jp_mp4 = vid_parts_dir / f"{i:04d}_jp_av_{clip_key}.mp4"
            if not validate_video_file(jp_mp4):
                if jp_mp4.exists():
                    jp_mp4 = _next_version(jp_mp4)
                slice_video(src_video, jp_start, next_start,
                            str(jp_mp4), width, height, fps,
                            process_tracker=process_tracker)
            group["jp_clips"].append(str(jp_mp4))
            jp_segments.append({
                "start": jp_start, "end": next_start,
                "group_idx": i, "clip_idx": 0,
            })

        subtitle_groups.append(group)

    # After loop: backward-merge if last interval was tiny
    if pending_start is not None:
        if not jp_segments:
            raise RuntimeError(
                "No JP segments emitted — all subtitle intervals are < MIN_SLICE_DURATION. "
                "This file cannot be processed."
            )
        last = jp_segments[-1]
        extended_key = text_hash(f"{src_video}|jp_av|{last['start']}|{total_duration}")
        extended_mp4 = vid_parts_dir / f"extended_{extended_key}.mp4"
        if not validate_video_file(extended_mp4):
            if extended_mp4.exists():
                extended_mp4 = _next_version(extended_mp4)
            slice_video(src_video, last["start"], total_duration,
                        str(extended_mp4), width, height, fps,
                        process_tracker=process_tracker)
        # Replace in-place
        subtitle_groups[last["group_idx"]]["jp_clips"][last["clip_idx"]] = str(extended_mp4)
        last["end"] = total_duration

    if not jp_segments:
        raise RuntimeError(
            "No JP segments emitted — all subtitle intervals are < MIN_SLICE_DURATION. "
            "This file cannot be processed."
        )

    # ── Phase 3: Group reordering (if group_size > 1) & flatten ─────────
    final_clips = []
    if preroll_clip:
        final_clips.append(preroll_clip)

    if group_size > 1:
        num_subs = len(subtitle_groups)
        for g in range(0, num_subs, group_size):
            chunk_end = min(g + group_size, num_subs)
            # All EN clips first
            for k in range(g, chunk_end):
                if subtitle_groups[k]["en_clip"]:
                    final_clips.append(subtitle_groups[k]["en_clip"])
            # Then all JP clips
            for k in range(g, chunk_end):
                final_clips.extend(subtitle_groups[k]["jp_clips"])
    else:
        for group in subtitle_groups:
            if group["en_clip"]:
                final_clips.append(group["en_clip"])
            final_clips.extend(group["jp_clips"])

    # ── Phase 4: Concatenate ────────────────────────────────────────────
    if progress_callback:
        progress_callback(len(en_subs), len(en_subs), "Concatenating final video...")

    concatenate_video_segments(final_clips, output, process_tracker=process_tracker)
