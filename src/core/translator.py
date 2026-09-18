"""Provider-agnostic AI translation for SRT content (OpenAI + Anthropic)."""

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from difflib import SequenceMatcher

import tiktoken
from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI, RateLimitError

try:
    import anthropic as _anthropic_module
except ImportError:
    _anthropic_module = None

from ..config import WORK_DIR, get_language_config, get_translation_prompt, get_punctuation_prompt, get_summary_prompt, is_anthropic_model
from .srt_parser import parse_srt_content

DEFAULT_MODEL = "gpt-4o-mini"
MAX_OUTPUT_LIMIT = 16384
MAX_INPUT_PER_CHUNK = 10000
PUNCT_CACHE_DIR = WORK_DIR / "punctuation_cache"
CJK_PUNCT_CHUNK_SIZE = 80
CJK_PUNCT_OVERLAP = 12
API_RETRY_DELAYS = (1.0, 2.0, 4.0)

_encoder = None

# Cached API clients — both OpenAI and Anthropic clients are thread-safe
_openai_client = None
_openai_client_key = None
_anthropic_client = None
_anthropic_client_key = None


def _get_openai_client(api_key):
    global _openai_client, _openai_client_key
    if _openai_client is None or _openai_client_key != api_key:
        _openai_client = OpenAI(api_key=api_key)
        _openai_client_key = api_key
    return _openai_client


def _get_anthropic_client(api_key):
    global _anthropic_client, _anthropic_client_key
    if _anthropic_client is None or _anthropic_client_key != api_key:
        _anthropic_client = _anthropic_module.Anthropic(api_key=api_key)
        _anthropic_client_key = api_key
    return _anthropic_client


def _get_encoder():
    global _encoder
    if _encoder is None:
        _encoder = tiktoken.encoding_for_model("gpt-4o-mini")
    return _encoder


def count_tokens(text):
    return len(_get_encoder().encode(text))


CONTEXT_SENTENCES = 2  # Number of surrounding sentences to include as context

_REFUSAL_PATTERNS = [
    re.compile(r"I'?m sorry,?\s*(but\s+)?I\s*(can'?t|cannot|am unable to)", re.IGNORECASE),
    re.compile(r"As an AI", re.IGNORECASE),
    re.compile(r"I cannot (translate|assist|help|provide)", re.IGNORECASE),
    re.compile(r"I'?m unable to (translate|assist|help|provide)", re.IGNORECASE),
    re.compile(r"I (can'?t|cannot) (assist|help) with", re.IGNORECASE),
    re.compile(r"against my (guidelines|policy|programming)", re.IGNORECASE),
    re.compile(r"content policy", re.IGNORECASE),
]

UNCLEAR_PLACEHOLDER = "[Unclear segment]"


def is_unclear_placeholder(text):
    """Return True for the unclear-translation placeholder.

    Matches both the current placeholder and legacy cached variants
    like "[Unclear Japanese]".
    """
    return text.strip().startswith("[Unclear")


def _is_refusal(text):
    """Return True if text matches common LLM refusal templates."""
    return any(p.search(text) for p in _REFUSAL_PATTERNS)


def _is_retryable_api_error(exc):
    """Return True for transient API failures worth retrying."""
    if isinstance(exc, (InternalServerError, APIConnectionError, APITimeoutError, RateLimitError)):
        return True
    if _anthropic_module is not None:
        if isinstance(exc, (
            _anthropic_module.InternalServerError,
            _anthropic_module.APIConnectionError,
            _anthropic_module.APITimeoutError,
            _anthropic_module.RateLimitError,
        )):
            return True
    status_code = getattr(exc, "status_code", None)
    return status_code in {408, 409, 429, 500, 502, 503, 504}


_INVALID_JSON_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _sanitize_for_api(text):
    """Strip NUL bytes and other control chars that OpenAI's JSON parser rejects.

    Preserves \\t (\\x09), \\n (\\x0a), and \\r (\\x0d).
    """
    if not isinstance(text, str):
        return text
    return _INVALID_JSON_CHARS_RE.sub("", text)


def _chat_completion(api_key, model, messages, max_tokens, temperature, logger=None,
                     cancelled_check=None):
    """Unified chat completion for OpenAI and Anthropic models.

    Returns the text content of the response.
    """
    from .process_tracker import CancelledError, interruptible_sleep

    messages = [
        {**m, "content": _sanitize_for_api(m.get("content", ""))} for m in messages
    ]
    for i, delay in enumerate((0.0, *API_RETRY_DELAYS)):
        if cancelled_check and cancelled_check():
            raise CancelledError("Operation cancelled")
        if delay > 0:
            interruptible_sleep(delay, cancelled_check)
        t0 = time.monotonic()
        try:
            if is_anthropic_model(model):
                if _anthropic_module is None:
                    raise ImportError(
                        "The 'anthropic' package is required for Claude models. "
                        "Install it with: pip install anthropic"
                    )
                client = _get_anthropic_client(api_key)
                # Extract system message from messages list
                system_content = ""
                user_messages = []
                for msg in messages:
                    if msg["role"] == "system":
                        system_content = msg["content"]
                    else:
                        user_messages.append(msg)
                # No temperature: anthropic>=1.0 removed it from
                # messages.create() (TypeError), and Claude 4.7+ models reject
                # it server-side anyway.
                kwargs = dict(
                    model=model,
                    messages=user_messages,
                    max_tokens=max_tokens,
                )
                if system_content:
                    kwargs["system"] = system_content
                response = client.messages.create(**kwargs)
                if logger:
                    logger.debug("API call", model=model, elapsed_sec=round(time.monotonic() - t0, 3),
                                  attempt=i + 1)
                return response.content[0].text
            else:
                client = _get_openai_client(api_key)
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                if logger:
                    logger.debug("API call", model=model, elapsed_sec=round(time.monotonic() - t0, 3),
                                  attempt=i + 1)
                return response.choices[0].message.content
        except Exception as exc:
            if logger:
                logger.debug("API call failed", model=model, attempt=i + 1,
                              elapsed_sec=round(time.monotonic() - t0, 3), error=str(exc)[:100])
            if i == len(API_RETRY_DELAYS) or not _is_retryable_api_error(exc):
                raise


def _translate_sentence(api_key, sentence, prev_context, next_context, model, translation_prompt,
                        logger=None, cancelled_check=None):
    """Translate a single sentence with surrounding context. Retries on refusal."""
    user_parts = []
    if prev_context:
        user_parts.append(f"[Previous context]\n{prev_context}")
    user_parts.append(f"[Translate this]\n{sentence}")
    if next_context:
        user_parts.append(f"[Next context]\n{next_context}")
    user_msg = "\n\n".join(user_parts)

    for attempt in range(3):
        temp = 0.3 + (attempt * 0.15)
        result = _chat_completion(
            api_key,
            model=model,
            messages=[
                {"role": "system", "content": translation_prompt},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=MAX_OUTPUT_LIMIT,
            temperature=temp,
            logger=logger,
            cancelled_check=cancelled_check,
        ).strip()

        if result.startswith("```"):
            lines = result.split("\n")
            if lines[-1].strip() == "```":
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            result = "\n".join(lines).strip()

        for marker in ("[Previous context]", "[Next context]", "[Translate this]"):
            if marker in result:
                result = result[:result.index(marker)].strip()

        if not _is_refusal(result):
            return result

    return UNCLEAR_PLACEHOLDER


def reassemble_srt(blocks, translations):
    """Reassemble a valid SRT file from original metadata + translated text."""
    output_lines = []
    for block, translated_text in zip(blocks, translations):
        output_lines.append(block["seq"])
        output_lines.append(block["timestamp"])
        output_lines.append(translated_text)
        output_lines.append("")

    return "\n".join(output_lines)


def translate_srt_content(api_key, srt_content, source_language="Japanese",
                          progress_callback=None, model=DEFAULT_MODEL, logger=None,
                          cancelled_check=None, target_language=None):
    """Translate SRT content to the target language, one sentence at a time.

    Each sentence is sent individually with surrounding sentences as context
    for accuracy, but only the target sentence is translated.

    Args:
        api_key: OpenAI API key
        srt_content: Raw SRT file content string
        source_language: Display name of source language (e.g. "Japanese")
        progress_callback: Optional callable(current, total)
        model: OpenAI model to use
        target_language: Display name of translation output language
            (defaults to the configured target language, normally "English")

    Returns:
        Translated SRT content string
    """
    lang = get_language_config(source_language)
    translation_prompt = get_translation_prompt(source_language, target_language)

    blocks = parse_srt_content(srt_content)

    if not blocks:
        raise ValueError("No subtitle blocks found in SRT content")

    texts = [b["text"] for b in blocks]
    total = len(blocks)
    if logger:
        logger.info("Translation starting", sentence_count=total, model=model,
                      source_language=source_language)
    all_translations = [None] * total

    # Pre-build all task tuples
    tasks = []
    for i in range(total):
        prev_parts = texts[max(0, i - CONTEXT_SENTENCES):i]
        next_parts = texts[i + 1:i + 1 + CONTEXT_SENTENCES]
        prev_context = "\n".join(prev_parts) if prev_parts else ""
        next_context = "\n".join(next_parts) if next_parts else ""
        tasks.append((i, texts[i], prev_context, next_context))

    # Concurrent translation with progress tracking
    completed_count = 0
    progress_lock = threading.Lock()

    def _translate_task(task):
        nonlocal completed_count
        idx, sentence, prev_ctx, next_ctx = task
        result = _translate_sentence(api_key, sentence, prev_ctx, next_ctx, model, translation_prompt,
                                     logger=logger, cancelled_check=cancelled_check)
        with progress_lock:
            completed_count += 1
            if progress_callback:
                progress_callback(completed_count, total)
        return idx, result

    max_workers = min(8, total)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_translate_task, t): t for t in tasks}
        try:
            for future in as_completed(futures):
                idx, result = future.result()
                all_translations[idx] = result
        except Exception:
            executor.shutdown(wait=False, cancel_futures=True)
            raise

    if progress_callback:
        progress_callback(total, total)

    refusal_count = sum(1 for t in all_translations if t == UNCLEAR_PLACEHOLDER)
    if logger:
        logger.info("Translation complete", sentence_count=total, refusals=refusal_count,
                      model=model)

    output_content = reassemble_srt(blocks, all_translations)
    if not output_content.endswith("\n"):
        output_content += "\n"

    return output_content


def _extract_punct_insertions(original, punctuated, punct_chars):
    """Use diff to find only the punctuation marks GPT inserted.

    Compares original text against GPT output, keeping the original text
    intact but inserting any sentence-ending punctuation that GPT added.
    Discards all other changes (word rewrites, deletions, etc.).

    Returns the original text with only punctuation insertions applied.
    """
    matcher = SequenceMatcher(None, original, punctuated, autojunk=False)
    result = []

    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == 'equal':
            result.append(original[i1:i2])
        elif op == 'insert':
            # GPT inserted characters — keep only punctuation
            inserted = punctuated[j1:j2]
            punct_only = ''.join(c for c in inserted if c in punct_chars)
            if punct_only:
                result.append(punct_only)
        elif op == 'replace':
            # GPT changed text — keep original, but extract any new punct
            orig_chunk = original[i1:i2]
            new_chunk = punctuated[j1:j2]
            # Find punct in new that wasn't in old
            new_punct = ''.join(c for c in new_chunk if c in punct_chars)
            old_punct = ''.join(c for c in orig_chunk if c in punct_chars)
            result.append(orig_chunk)
            # If GPT added more punct marks than original had, append extras
            extra = len(new_punct) - len(old_punct)
            if extra > 0:
                result.append(new_punct[-extra:])
        elif op == 'delete':
            # GPT deleted characters — keep original
            result.append(original[i1:i2])

    return ''.join(result)


def _realign_to_blocks(original_texts, merged_punctuated, punct_chars):
    """Split merged punctuated text back into per-block strings.

    Walks through the merged text character by character, consuming each
    original block's characters and absorbing any punctuation GPT inserted.
    """
    result = []
    p = 0

    for orig in original_texts:
        block_chars = []
        o = 0

        while o < len(orig):
            if p >= len(merged_punctuated):
                block_chars.append(orig[o:])
                break

            pc = merged_punctuated[p]

            if pc in punct_chars and (o >= len(orig) or orig[o] not in punct_chars):
                block_chars.append(pc)
                p += 1
            elif pc == orig[o]:
                block_chars.append(pc)
                p += 1
                o += 1
            else:
                # Shouldn't happen after _extract_punct_insertions
                block_chars.append(orig[o])
                o += 1

        # Absorb trailing punctuation at block boundary
        while p < len(merged_punctuated) and merged_punctuated[p] in punct_chars:
            block_chars.append(merged_punctuated[p])
            p += 1

        # If we couldn't match any content from punctuated text but original had content,
        # preserve the original text to avoid losing blocks
        block_text = ''.join(block_chars)
        if not block_text.strip() and orig.strip():
            # Realignment failed for this block, keep original
            result.append(orig)
        else:
            result.append(block_text)

    return result


def _send_for_punctuation(api_key, text, model, punctuation_prompt, logger=None,
                          cancelled_check=None):
    """Send raw text to AI for punctuation. Returns punctuated string."""
    input_tokens = count_tokens(text)
    max_tokens = min(max(int(input_tokens * 2), 256), MAX_OUTPUT_LIMIT)

    result = _chat_completion(
        api_key,
        model=model,
        messages=[
            {"role": "system", "content": punctuation_prompt},
            {"role": "user", "content": text},
        ],
        max_tokens=max_tokens,
        temperature=0.3,
        logger=logger,
        cancelled_check=cancelled_check,
    )

    # Strip markdown code fences
    if result.startswith("```"):
        lines = result.split("\n")
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        result = "\n".join(lines)

    return result.strip()


def _write_punctuation_cache(cache_tag, chunk_number, model, source_language,
                             start_idx, end_idx, input_text, raw_output, cleaned_output):
    """Persist raw/clean punctuation outputs for postmortem debugging."""
    try:
        PUNCT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        run_dir = PUNCT_CACHE_DIR / cache_tag
        run_dir.mkdir(parents=True, exist_ok=True)

        stem = f"chunk_{chunk_number:03d}"
        (run_dir / f"{stem}_input.txt").write_text(input_text, encoding="utf-8")
        (run_dir / f"{stem}_raw_output.txt").write_text(raw_output, encoding="utf-8")
        (run_dir / f"{stem}_clean_output.txt").write_text(cleaned_output, encoding="utf-8")

        metadata = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "model": model,
            "source_language": source_language,
            "chunk_number": chunk_number,
            "start_idx": start_idx,
            "end_idx": end_idx,
            "input_chars": len(input_text),
            "raw_output_chars": len(raw_output),
            "clean_output_chars": len(cleaned_output),
        }
        (run_dir / f"{stem}_meta.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        # Debug cache should never break the pipeline.
        pass


def _split_text_into_chunks(texts, max_tokens=MAX_INPUT_PER_CHUNK):
    """Split a list of texts into chunks that fit within the token limit.

    Returns list of (start_index, end_index) ranges.
    """
    chunks = []
    start = 0
    current_tokens = 0

    for i, text in enumerate(texts):
        tokens = count_tokens(text)
        if start < i and current_tokens + tokens > max_tokens:
            chunks.append((start, i))
            start = i
            current_tokens = 0
        current_tokens += tokens

    if start < len(texts):
        chunks.append((start, len(texts)))
    return chunks


def _build_overlap_chunk_specs(total_blocks, chunk_size, overlap):
    """Build expanded chunk windows plus non-overlapping core ranges.

    Returns list of (expanded_start, expanded_end, core_start, core_end).
    """
    if total_blocks <= 0:
        return []

    specs = []
    core_start = 0
    while core_start < total_blocks:
        core_end = min(core_start + chunk_size, total_blocks)
        expanded_start = max(0, core_start - overlap)
        expanded_end = min(total_blocks, core_end + overlap)
        specs.append((expanded_start, expanded_end, core_start, core_end))
        core_start = core_end

    return specs


def punctuate_subs(api_key, subs, source_language="Japanese",
                   progress_callback=None, model=DEFAULT_MODEL, cache_tag=None,
                   cjk_chunk_size=None, logger=None, cancelled_check=None):
    """Add sentence-ending punctuation to subtitle blocks via GPT.

    Concatenates all block text, sends to GPT as raw prose, then realigns
    the punctuated result back to the original blocks and timestamps.

    Args:
        api_key: OpenAI API key
        subs: List of (start_sec, end_sec, text) tuples
        source_language: Display name of source language (e.g. "Japanese")
        progress_callback: Optional callable(current_chunk, total_chunks)
        model: OpenAI model to use
        cache_tag: Optional directory tag for saving raw punctuation outputs
        cjk_chunk_size: Optional override for CJK chunk core size

    Returns:
        List of (start_sec, end_sec, text) tuples with punctuation added
    """
    if not subs:
        return subs

    lang = get_language_config(source_language)
    punctuation_prompt = get_punctuation_prompt(source_language)
    punct_chars = lang["punct_chars"]

    texts = [text for _, _, text in subs]
    run_cache_tag = None
    if cache_tag:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_cache_tag = f"{cache_tag}_{ts}"

    # CJK punctuation benefits from smaller chunks with overlap to preserve
    # sentence context near chunk boundaries while avoiding giant prompts.
    is_cjk_language = source_language in {
        "Japanese",
        "Chinese (Simplified)",
        "Chinese (Traditional)",
        "Chinese (Taiwanese)",
        "Cantonese",
    }
    if is_cjk_language:
        effective_chunk_size = cjk_chunk_size or CJK_PUNCT_CHUNK_SIZE
        chunk_specs = _build_overlap_chunk_specs(
            total_blocks=len(texts),
            chunk_size=effective_chunk_size,
            overlap=CJK_PUNCT_OVERLAP,
        )
    else:
        chunk_specs = [(s, e, s, e) for s, e in _split_text_into_chunks(texts)]

    if logger:
        logger.info("Punctuation starting", block_count=len(subs), chunk_count=len(chunk_specs),
                      model=model, cjk=is_cjk_language)

    punctuated_texts = list(texts)

    def _punctuate_chunk(chunk_info):
        i, start_idx, end_idx, core_start, core_end = chunk_info
        chunk_texts = texts[start_idx:end_idx]
        raw_concat = ''.join(chunk_texts)
        readable = '\n'.join(chunk_texts)

        raw_punctuated = _send_for_punctuation(api_key, readable, model, punctuation_prompt,
                                                logger=logger, cancelled_check=cancelled_check)
        punctuated = raw_punctuated
        punctuated_flat = punctuated.replace('\n', '')

        safe_merged = _extract_punct_insertions(raw_concat, punctuated_flat, punct_chars)
        realigned = _realign_to_blocks(chunk_texts, safe_merged, punct_chars)

        local_core_start = core_start - start_idx
        local_core_end = local_core_start + (core_end - core_start)
        core_realigned = realigned[local_core_start:local_core_end]

        if run_cache_tag:
            _write_punctuation_cache(
                cache_tag=run_cache_tag,
                chunk_number=i + 1,
                model=model,
                source_language=source_language,
                start_idx=start_idx,
                end_idx=end_idx,
                input_text=readable,
                raw_output=raw_punctuated,
                cleaned_output=punctuated,
            )

        return core_start, core_end, core_realigned

    chunk_infos = [(i, s, e, cs, ce) for i, (s, e, cs, ce) in enumerate(chunk_specs)]
    punct_completed = 0
    punct_lock = threading.Lock()
    total_chunks = len(chunk_specs)

    max_workers = min(8, total_chunks)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_punctuate_chunk, ci): ci for ci in chunk_infos}
        try:
            for future in as_completed(futures):
                core_start, core_end, core_realigned = future.result()
                punctuated_texts[core_start:core_end] = core_realigned
                with punct_lock:
                    punct_completed += 1
                    if progress_callback:
                        progress_callback(punct_completed, total_chunks)
        except Exception:
            executor.shutdown(wait=False, cancel_futures=True)
            raise

    if progress_callback:
        progress_callback(total_chunks, total_chunks)

    # Rebuild subs with punctuated text, preserving timestamps
    result = []
    for (start, end, _), new_text in zip(subs, punctuated_texts):
        result.append((start, end, new_text))

    return result


def _parse_summary_response(text, total_sentences):
    """Parse and validate JSON summary response from AI.

    Returns list of {"start": int, "end": int, "summary": str} dicts,
    or raises ValueError on invalid structure.
    """
    # Strip markdown code fences
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        cleaned = "\n".join(lines).strip()

    chunks = json.loads(cleaned)

    if not isinstance(chunks, list) or len(chunks) == 0:
        raise ValueError("Response is not a non-empty JSON array")

    for chunk in chunks:
        if not isinstance(chunk, dict):
            raise ValueError(f"Chunk is not a dict: {chunk}")
        for key in ("start", "end", "summary"):
            if key not in chunk:
                raise ValueError(f"Missing key '{key}' in chunk: {chunk}")
        if not isinstance(chunk["start"], int) or not isinstance(chunk["end"], int):
            raise ValueError(f"start/end must be integers: {chunk}")
        if chunk["start"] > chunk["end"]:
            raise ValueError(f"start > end: {chunk}")
        if not chunk["summary"] or not chunk["summary"].strip():
            raise ValueError(f"Empty summary: {chunk}")

    # Validate and repair contiguity
    chunks.sort(key=lambda c: c["start"])
    if chunks[0]["start"] != 1:
        raise ValueError(f"First chunk starts at {chunks[0]['start']}, expected 1")
    for i in range(1, len(chunks)):
        if chunks[i]["start"] <= chunks[i - 1]["end"]:
            raise ValueError(
                f"Overlap: chunk ending at {chunks[i-1]['end']} and "
                f"chunk starting at {chunks[i]['start']}"
            )
        if chunks[i]["start"] > chunks[i - 1]["end"] + 1:
            # Gap — extend previous chunk to fill it
            chunks[i - 1]["end"] = chunks[i]["start"] - 1
    if chunks[-1]["end"] > total_sentences:
        raise ValueError(
            f"Last chunk ends at {chunks[-1]['end']}, exceeds {total_sentences}"
        )
    if chunks[-1]["end"] < total_sentences:
        # AI undershot — extend last chunk to cover remaining sentences
        chunks[-1]["end"] = total_sentences

    return chunks


def _fallback_summary_chunks(total_sentences, chunk_size=5):
    """Generate uniform fallback chunks when AI summary parsing fails."""
    chunks = []
    for start in range(1, total_sentences + 1, chunk_size):
        end = min(start + chunk_size - 1, total_sentences)
        chunks.append({
            "start": start,
            "end": end,
            "summary": "Continuing.",
        })
    return chunks


def _summarize_window(api_key, model, summary_prompt, texts, offset, logger=None,
                      cancelled_check=None):
    """Send a window of sentences to the AI for chunked summarization.

    Args:
        texts: list of sentence strings (the window)
        offset: 0-based global index of texts[0]

    Returns list of chunks with global 1-based start/end indices.
    """
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
    batch_count = len(texts)

    parsed_chunks = None
    for attempt in range(3):
        temp = 0.3 + (attempt * 0.15)
        try:
            result = _chat_completion(
                api_key,
                model=model,
                messages=[
                    {"role": "system", "content": summary_prompt},
                    {"role": "user", "content": numbered},
                ],
                max_tokens=MAX_OUTPUT_LIMIT,
                temperature=temp,
                logger=logger,
                cancelled_check=cancelled_check,
            )
            parsed_chunks = _parse_summary_response(result, batch_count)
            break
        except (json.JSONDecodeError, ValueError):
            if attempt == 2:
                parsed_chunks = _fallback_summary_chunks(batch_count)

    # Remap from 1-based window-local to 1-based global
    for chunk in parsed_chunks:
        chunk["start"] += offset
        chunk["end"] += offset
    return parsed_chunks


def summarize_srt_content(api_key, srt_content, source_language="Japanese",
                          progress_callback=None, model=DEFAULT_MODEL, logger=None,
                          cancelled_check=None, target_language=None):
    """Summarize SRT content into topical chunks with target-language summaries.

    Uses a sliding window with overlap so the AI chooses natural chunk
    boundaries — batch edges never force a split.

    Returns SRT content where each entry spans a chunk's time range
    with a target-language summary as text.
    """
    WINDOW_SIZE = 40   # sentences sent to AI per call
    CORE_SIZE = 25     # we only accept chunks that end within this prefix

    summary_prompt = get_summary_prompt(source_language, target_language)
    blocks = parse_srt_content(srt_content)

    if not blocks:
        raise ValueError("No subtitle blocks found in SRT content")

    texts = [b["text"] for b in blocks]
    total = len(blocks)
    if logger:
        logger.info("Summarization starting", sentence_count=total, model=model)

    # Estimate number of windows for progress reporting
    est_windows = max(1, (total + CORE_SIZE - 1) // CORE_SIZE)

    all_chunks = []
    cursor = 0        # 0-based index of the first unconsumed sentence
    window_num = 0

    while cursor < total:
        if progress_callback:
            progress_callback(window_num, est_windows)

        window_end = min(cursor + WINDOW_SIZE, total)
        window_texts = texts[cursor:window_end]
        is_final = (window_end == total)

        chunks = _summarize_window(api_key, model, summary_prompt, window_texts, cursor,
                                    logger=logger, cancelled_check=cancelled_check)

        if is_final:
            # Last window — accept everything
            all_chunks.extend(chunks)
            cursor = total
        else:
            # Accept chunks whose end falls within the core region.
            # Core region = sentences cursor+1 .. cursor+CORE_SIZE (1-based global).
            core_limit = cursor + CORE_SIZE  # 1-based global max end we trust
            accepted = []
            for chunk in chunks:
                if chunk["end"] <= core_limit:
                    accepted.append(chunk)
                else:
                    break  # chunks are sorted, remaining are beyond core

            if not accepted:
                # AI made one giant chunk spanning the whole window — force-accept
                # the first chunk and move on to avoid an infinite loop.
                accepted.append(chunks[0])

            all_chunks.extend(accepted)
            # Advance cursor past the last accepted sentence
            cursor = accepted[-1]["end"]  # 1-based, so this is the next 0-based index

        window_num += 1

    if progress_callback:
        progress_callback(window_num, window_num)

    # Build SRT output — map chunk ranges to original timestamps
    output_lines = []
    for seq, chunk in enumerate(all_chunks, 1):
        first_block = blocks[chunk["start"] - 1]
        last_block = blocks[chunk["end"] - 1]

        start_ts = first_block["timestamp"].split(" --> ")[0].strip()
        end_ts = last_block["timestamp"].split(" --> ")[1].strip()

        output_lines.append(str(seq))
        output_lines.append(f"{start_ts} --> {end_ts}")
        output_lines.append(chunk["summary"])
        output_lines.append("")

    output_content = "\n".join(output_lines)
    if not output_content.endswith("\n"):
        output_content += "\n"

    return output_content
