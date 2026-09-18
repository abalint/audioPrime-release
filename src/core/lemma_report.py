"""Generate comprehensibility reports from lemma analysis."""

import json
from pathlib import Path


def _format_timestamp(seconds):
    """Convert seconds to MM:SS format."""
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m:02d}:{s:02d}"


def write_report(analysis, output_dir, video_title):
    """Write JSON and human-readable comprehensibility reports.

    Args:
        analysis: dict from analyze_video()
        output_dir: Path to output directory
        video_title: sanitized video title for filenames

    Returns:
        tuple of (json_path, txt_path)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / f"{video_title}_comprehensibility.json"
    txt_path = output_dir / f"{video_title}_comprehensibility.txt"

    # JSON report (full data, but skip per-sentence details for readability)
    json_data = {
        "total_sentences": analysis["total_sentences"],
        "total_tokens": analysis["total_tokens"],
        "known_tokens": analysis["known_tokens"],
        "total_unique_lemmas": analysis["total_unique_lemmas"],
        "known_lemma_count": analysis["known_lemma_count"],
        "unknown_lemma_count": analysis["unknown_lemma_count"],
        "token_comprehensibility": round(analysis.get("token_comprehensibility", analysis["overall_comprehensibility"]), 4),
        "unlisted_knowledge": analysis.get("unlisted_knowledge", 0),
        "reclassified_count": analysis.get("reclassified_count", 0),
        "reclassified_lemmas": analysis.get("reclassified_lemmas", []),
        "adjusted_known_tokens": analysis.get("adjusted_known_tokens", analysis["known_tokens"]),
        "adjusted_comprehensibility": round(analysis.get("adjusted_comprehensibility", analysis["overall_comprehensibility"]), 4),
        "overall_comprehensibility": round(analysis["overall_comprehensibility"], 4),
        "i_plus_1_count": analysis["i_plus_1_count"],
        "i_plus_1_sentences": analysis["i_plus_1_sentences"],
        "unknown_vocabulary": analysis["unknown_vocabulary"],
    }
    json_path.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Human-readable report
    known_tok = analysis["known_tokens"]
    total_tok = analysis["total_tokens"]
    total_sent = analysis["total_sentences"]
    i1_count = analysis["i_plus_1_count"]
    i1_pct = (i1_count / total_sent * 100) if total_sent else 0
    raw_pct = analysis.get("token_comprehensibility", analysis["overall_comprehensibility"]) * 100
    unlisted = analysis.get("unlisted_knowledge", 0)
    reclassified_count = analysis.get("reclassified_count", 0)

    lines = [
        f"Comprehensibility Report: {video_title}",
        "=" * 40,
        f"Unique lemmas: {analysis['known_lemma_count']}/{analysis['total_unique_lemmas']} known "
        f"({analysis['known_lemma_count'] / analysis['total_unique_lemmas'] * 100:.1f}%)" if analysis['total_unique_lemmas'] else "Unique lemmas: 0/0",
        f"Token coverage (raw): {known_tok}/{total_tok} ({raw_pct:.1f}%)",
    ]

    if unlisted > 0 and reclassified_count > 0:
        adj_tok = analysis.get("adjusted_known_tokens", known_tok)
        adj_pct = analysis.get("adjusted_comprehensibility", analysis["overall_comprehensibility"]) * 100
        lines.append(f"Token coverage (adjusted): {adj_tok}/{total_tok} ({adj_pct:.1f}%) — unlisted knowledge {unlisted}%")
    lines.append(f"Sentences: {total_sent} total | {i1_count} i+1 ({i1_pct:.1f}%)")
    lines.append("")

    reclassified_lemmas = analysis.get("reclassified_lemmas", [])
    if reclassified_lemmas:
        lines.append(f"Reclassified as probably known ({len(reclassified_lemmas)} words):")
        lines.append(f"  {', '.join(reclassified_lemmas)}")
        lines.append("")

    if analysis["i_plus_1_sentences"]:
        lines.append("i+1 Sentences:")
        for s in analysis["i_plus_1_sentences"]:
            ts = _format_timestamp(s["start"])
            lines.append(f"  [{ts}] {s['text']} (unknown: {s['unknown_word']})")
        lines.append("")

    unknown_vocab = analysis["unknown_vocabulary"]
    if unknown_vocab:
        lines.append(f"Unknown Vocabulary ({len(unknown_vocab)} words):")
        lines.append(f"  {', '.join(unknown_vocab)}")
        lines.append("")

    txt_path.write_text("\n".join(lines), encoding="utf-8")

    return json_path, txt_path
