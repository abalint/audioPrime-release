"""Lemma-based comprehensibility analysis for language learning."""

import re
import string
from pathlib import Path


# CJK language codes that should preserve case
_CJK_CODES = {"ja", "zh-Hans", "zh-Hant", "zh-TW", "yue", "ko"}

# simplemma uses 2-letter ISO codes; map our codes to theirs
_SIMPLEMMA_CODE_MAP = {
    "zh-Hans": "zh",
    "zh-Hant": "zh",
    "zh-TW": "zh",
    "yue": "zh",
    "no": "nb",  # Norwegian Bokmål
}

# Japanese character detection (hiragana, katakana, CJK ideographs)
_JAPANESE_RE = re.compile(r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]")

# POS categories to skip — these don't carry learnable vocabulary signal.
# Matches the filtering used in the graphs project (grapher/graph.py).
#
# 名詞-固有名詞  proper nouns (character/place names, too context-specific)
# 名詞-数詞      numerals (numbers carry no learning signal)
# 記号          symbols (non-semantic)
# 補助記号       supplementary symbols / punctuation
# 感動詞        interjections (low-value emotional particles like ああ, えー)
# 助詞          particles (grammatical function words: は, が, を, etc.)
# 助動詞        auxiliary verbs (grammatical: ます, です, た, etc.)
# 空白          whitespace tokens
_SKIP_POS1 = {"記号", "補助記号", "感動詞", "助詞", "助動詞", "空白"}
_SKIP_POS1_POS2 = {("名詞", "固有名詞"), ("名詞", "数詞")}


def load_lemma_list(filepath, language_code="ja"):
    """Read a word list from a plain text or CSV file.

    Supported formats:
    - Plain text: one word per line
    - CSV: reads the first column of each row

    Automatically detects and skips header rows (containing common
    header labels like 'word', 'lemma', 'term', 'vocabulary', etc.).
    Skips empty lines and lines starting with #.
    Lowercases for non-CJK languages.
    """
    import csv

    filepath = str(filepath)
    is_csv = filepath.lower().endswith(".csv")
    known = set()

    with open(filepath, encoding="utf-8") as f:
        if is_csv:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                if not row or not row[0].strip():
                    continue
                word = row[0].strip()
                # Skip header row
                if i == 0 and _is_header(word):
                    continue
                if word.startswith("#"):
                    continue
                if language_code not in _CJK_CODES:
                    word = word.lower()
                known.add(word)
        else:
            for i, line in enumerate(f):
                word = line.strip()
                if not word or word.startswith("#"):
                    continue
                # Skip header row
                if i == 0 and _is_header(word):
                    continue
                if language_code not in _CJK_CODES:
                    word = word.lower()
                known.add(word)
    return known


_HEADER_WORDS = {
    "word", "words", "lemma", "lemmas", "term", "terms", "vocabulary",
    "vocab", "token", "tokens", "headword", "entry", "lexeme",
}


def _is_header(value):
    """Check if a value looks like a CSV/text header rather than a real word."""
    # Strip BOM if present
    clean = value.strip().lstrip("\ufeff").strip()
    return clean.lower() in _HEADER_WORDS


def tokenize_and_lemmatize(text, language_code):
    """Extract content lemmas from text.

    Japanese: uses fugashi (MeCab) for morphological analysis with POS filtering.
    All others: whitespace split + simplemma lemmatization.
    """
    if language_code == "ja":
        return _lemmatize_japanese(text)
    return _lemmatize_generic(text, language_code)


def _lemmatize_japanese(text):
    """Japanese lemmatization via fugashi/MeCab with POS-based filtering.

    Uses orthBase (base orthographic form) instead of lemma to get natural
    forms users actually know: それ instead of 其れ, する instead of 為る,
    コーヒー instead of コーヒー-coffee.

    Filters applied (matching graphs project):
    - Supplementary symbols and punctuation (補助記号, 記号)
    - Whitespace tokens (空白)
    - Particles (助詞: は, が, を, etc.)
    - Auxiliary verbs (助動詞: ます, です, た, etc.)
    - Interjections (感動詞: ああ, えー, etc.)
    - Proper nouns (名詞-固有名詞: character/place names)
    - Numerals (名詞-数詞)
    - OOV tokens (not in MeCab dictionary — garbled/non-standard)
    - Non-Japanese dictionary forms (English loanwords without kana)
    """
    import fugashi

    tagger = fugashi.Tagger()
    lemmas = []
    for word in tagger(text):
        surface = word.surface
        if not surface.strip():
            continue

        try:
            pos1 = word.feature.pos1
            pos2 = word.feature.pos2
        except (AttributeError, IndexError):
            continue

        # Skip by top-level POS
        if pos1 in _SKIP_POS1:
            continue

        # Skip by POS1+POS2 combination (proper nouns, numerals)
        if (pos1, pos2) in _SKIP_POS1_POS2:
            continue

        # Extract lemma — prefer orthBase (natural kana/surface base form)
        # over lemma (which uses archaic kanji: 其れ, 為る, コーヒー-coffee)
        try:
            base = word.feature.orthBase
        except (AttributeError, IndexError):
            base = None

        if not base or base == "*":
            try:
                base = word.feature.lemma
            except (AttributeError, IndexError):
                base = None

        # Skip OOV tokens (no base form = not in dictionary)
        if not base:
            continue

        # Skip non-Japanese base forms (catches romanized/English words)
        if not _JAPANESE_RE.search(base):
            continue

        lemmas.append(base)
    return lemmas


def _lemmatize_generic(text, language_code):
    """Lemmatization for non-Japanese languages via simplemma."""
    import simplemma

    code = _SIMPLEMMA_CODE_MAP.get(language_code, language_code)
    # Split on whitespace, strip punctuation
    tokens = text.split()
    lemmas = []
    for token in tokens:
        cleaned = token.strip(string.punctuation + "。、！？「」『』（）・…─―")
        if not cleaned:
            continue
        lemma = simplemma.lemmatize(cleaned, lang=code)
        lemmas.append(lemma.lower())
    return lemmas


def _load_frequency_ranks():
    """Load Japanese frequency list into {word: rank} dict.

    The file is one word per line, most frequent first.
    Returns empty dict if file not found.
    """
    freq_path = Path(__file__).resolve().parent.parent.parent / "data" / "ja_frequency.txt"
    if not freq_path.exists():
        return {}
    ranks = {}
    with open(freq_path, encoding="utf-8") as f:
        for rank, line in enumerate(f):
            word = line.strip()
            if word:
                ranks[word] = rank
    return ranks


def _reclassify_unknown_lemmas(unknown_unique, frequency_ranks, count, language_code):
    """Pick the top `count` unknown lemmas most likely to be known.

    For Japanese: sort by frequency rank (lower = more common = more likely known).
    For other languages: sort alphabetically (no frequency data).
    Unknown lemmas not in the frequency list get a high rank.
    """
    if count <= 0:
        return set()

    unknowns = list(unknown_unique)
    if language_code == "ja" and frequency_ranks:
        max_rank = len(frequency_ranks)
        unknowns.sort(key=lambda w: frequency_ranks.get(w, max_rank))
    else:
        unknowns.sort()

    return set(unknowns[:count])


def analyze_sentence(text, known_lemmas, language_code):
    """Analyze a single sentence for comprehensibility.

    Returns dict with lemmas, known/unknown lists, ratio, and i+1 status.
    """
    lemmas = tokenize_and_lemmatize(text, language_code)
    if not lemmas:
        return {
            "text": text,
            "lemmas": [],
            "known": [],
            "unknown": [],
            "known_ratio": 1.0,
            "is_i_plus_1": False,
            "unknown_count": 0,
        }

    known = [l for l in lemmas if l in known_lemmas]
    unknown = [l for l in lemmas if l not in known_lemmas]
    unique_unknown = set(unknown)

    return {
        "text": text,
        "lemmas": lemmas,
        "known": known,
        "unknown": unknown,
        "known_ratio": len(known) / len(lemmas) if lemmas else 1.0,
        "is_i_plus_1": len(unique_unknown) == 1,
        "unknown_count": len(unique_unknown),
    }


def analyze_video(sentences, known_lemmas, language_code, unlisted_knowledge=0, logger=None):
    """Analyze all sentences from a parsed SRT for comprehensibility.

    Args:
        sentences: list of (start, end, text) tuples from SRT parser
        known_lemmas: set of known lemma strings
        language_code: language code for tokenization
        unlisted_knowledge: 0-75 int, estimated % of known vocab NOT in the lemma list

    Returns dict with overall stats, i+1 sentences, and per-sentence details.
    """
    all_unique_lemmas = set()
    total_tokens = 0
    known_tokens = 0
    sentence_details = []
    i_plus_1_sentences = []

    for idx, (start, end, text) in enumerate(sentences):
        analysis = analyze_sentence(text, known_lemmas, language_code)
        analysis["index"] = idx
        analysis["start"] = start
        analysis["end"] = end
        sentence_details.append(analysis)

        all_unique_lemmas.update(analysis["lemmas"])
        total_tokens += len(analysis["lemmas"])
        known_tokens += len(analysis["known"])

        if analysis["is_i_plus_1"]:
            unique_unknown = set(analysis["unknown"])
            i_plus_1_sentences.append({
                "index": idx,
                "start": start,
                "end": end,
                "text": text,
                "unknown_word": list(unique_unknown)[0],
            })

    known_unique = all_unique_lemmas & known_lemmas
    unknown_unique = all_unique_lemmas - known_lemmas

    # Unlisted knowledge adjustment
    reclassified = set()
    adjusted_known_tokens = known_tokens

    if unlisted_knowledge > 0 and unknown_unique:
        list_coverage = 1.0 - (unlisted_knowledge / 100.0)
        estimated_true_known = len(known_unique) / list_coverage if list_coverage > 0 else len(known_unique)
        extra_words = round(estimated_true_known - len(known_unique))
        extra_words = min(extra_words, len(unknown_unique))

        freq_ranks = _load_frequency_ranks() if language_code == "ja" else {}
        reclassified = _reclassify_unknown_lemmas(unknown_unique, freq_ranks, extra_words, language_code)

        # Recount tokens with reclassified words treated as known
        adjusted_known_tokens = 0
        for detail in sentence_details:
            for lemma in detail["lemmas"]:
                if lemma in known_lemmas or lemma in reclassified:
                    adjusted_known_tokens += 1
    else:
        adjusted_known_tokens = known_tokens

    adjusted_comp = adjusted_known_tokens / total_tokens if total_tokens else 0.0
    remaining_unknown = sorted(unknown_unique - reclassified)

    if logger:
        logger.debug("Comprehensibility analysis", sentences=len(sentences),
                      total_tokens=total_tokens, known_tokens=adjusted_known_tokens,
                      unique_lemmas=len(all_unique_lemmas),
                      comprehensibility=round(adjusted_comp, 3),
                      i_plus_1=len(i_plus_1_sentences),
                      reclassified=len(reclassified))

    return {
        "total_sentences": len(sentences),
        "total_unique_lemmas": len(all_unique_lemmas),
        "known_lemma_count": len(known_unique),
        "unknown_lemma_count": len(unknown_unique),
        "total_tokens": total_tokens,
        "known_tokens": known_tokens,
        "unknown_tokens": total_tokens - known_tokens,
        "token_comprehensibility": known_tokens / total_tokens if total_tokens else 0.0,
        "unique_comprehensibility": len(known_unique) / len(all_unique_lemmas) if all_unique_lemmas else 0.0,
        "unlisted_knowledge": unlisted_knowledge,
        "reclassified_count": len(reclassified),
        "reclassified_lemmas": sorted(reclassified),
        "adjusted_known_tokens": adjusted_known_tokens,
        "adjusted_comprehensibility": adjusted_comp,
        "overall_comprehensibility": adjusted_comp,
        "i_plus_1_count": len(i_plus_1_sentences),
        "i_plus_1_sentences": i_plus_1_sentences,
        "sentence_details": sentence_details,
        "unknown_vocabulary": remaining_unknown,
    }
