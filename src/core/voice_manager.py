"""Piper voice catalog and on-demand voice downloading.

The app ships a single English voice so the installer stays small. Every other
Piper voice — 166 voices across 45 languages — is listed in
``data/piper_voices.json`` and fetched from Hugging Face the first time it is
selected, into a writable directory alongside the app's output folder.

Regenerate the catalog with ``scripts/fetch_piper_catalog.py``.
"""

import hashlib
import json
import shutil
import urllib.request
from pathlib import Path

from ..config import CATALOG_FILE, USER_VOICES_DIR, VOICES_DIR

DOWNLOAD_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/{path}"
TIMEOUT = 60
CHUNK_SIZE = 1024 * 256

# Worst -> best. "low" and "medium" are both ~63 MB and differ only in sample
# rate, so there is no size argument for preferring low.
QUALITY_ORDER = ["x_low", "low", "medium", "high"]

_catalog = None


def load_catalog():
    """Load and memoize the bundled voice catalog."""
    global _catalog
    if _catalog is None:
        with open(CATALOG_FILE, encoding="utf-8") as f:
            _catalog = json.load(f)["voices"]
    return _catalog


def get_voice(key):
    """Return the catalog entry for a voice key, or None."""
    return next((v for v in load_catalog() if v["key"] == key), None)


def voices_for_language(lang_family):
    """Return catalog entries for a language, best quality first.

    ``lang_family`` is the app's two-letter language code. Chinese variants in
    LANGUAGE_REGISTRY carry script/region suffixes (zh-Hans, zh-TW) that Piper
    does not distinguish, so only the part before the hyphen is matched.
    """
    family = lang_family.split("-")[0]
    matches = [v for v in load_catalog() if v["lang_family"] == family]
    matches.sort(key=lambda v: (
        -_quality_rank(v["quality"]),
        v["lang_code"],
        v["name"],
    ))
    return matches


def _quality_rank(quality):
    return QUALITY_ORDER.index(quality) if quality in QUALITY_ORDER else -1


def display_name(voice):
    """Human-readable label for a voice, e.g. "Thorsten (Germany, high)"."""
    country = voice.get("country") or voice["lang_code"]
    return f"{voice['name'].replace('_', ' ').title()} ({country}, {voice['quality']})"


def voice_size_mb(voice):
    """Download size in MB, for showing before a download starts."""
    return voice["onnx_size"] / (1024 * 1024)


def local_path(voice):
    """Where this voice's model lives, whether or not it exists yet.

    Bundled voices win over downloaded ones so a shipped voice is never
    re-fetched. Downloads land in USER_VOICES_DIR because the bundle directory
    is read-only in frozen builds.
    """
    filename = Path(voice["onnx_path"]).name
    bundled = VOICES_DIR / filename
    if bundled.exists():
        return bundled
    return USER_VOICES_DIR / filename


def is_downloaded(voice):
    """True if both the model and its config are present locally."""
    model = local_path(voice)
    return model.exists() and model.with_suffix(".onnx.json").exists()


def ensure_voice(voice, progress_cb=None, logger=None):
    """Return a local path to the voice model, downloading it if needed.

    ``progress_cb(downloaded_bytes, total_bytes)`` is called during the model
    download so callers can drive a progress bar. Raises RuntimeError if the
    download fails or the model fails its md5 check.
    """
    model_path = local_path(voice)
    if is_downloaded(voice):
        return model_path

    USER_VOICES_DIR.mkdir(parents=True, exist_ok=True)
    if logger:
        logger.info("Downloading Piper voice", voice=voice["key"],
                    size_mb=round(voice_size_mb(voice), 1))

    # Config first: it is tiny, and a model without its config is unusable, so
    # failing here avoids leaving a 63 MB orphan behind.
    _download(voice["config_path"], model_path.with_suffix(".onnx.json"))
    _download(voice["onnx_path"], model_path,
              expected_md5=voice["onnx_md5"],
              expected_size=voice["onnx_size"],
              progress_cb=progress_cb)

    if logger:
        logger.info("Piper voice ready", voice=voice["key"], path=str(model_path))
    return model_path


def _download(remote_path, dest, expected_md5=None, expected_size=None,
              progress_cb=None):
    """Download one file to ``dest`` via a temp file, verifying md5 if given."""
    url = DOWNLOAD_URL.format(path=remote_path)
    tmp = dest.with_suffix(dest.suffix + ".part")
    digest = hashlib.md5()
    downloaded = 0

    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
            total = expected_size or int(response.headers.get("Content-Length", 0))
            with open(tmp, "wb") as f:
                while chunk := response.read(CHUNK_SIZE):
                    f.write(chunk)
                    digest.update(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        progress_cb(downloaded, total)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"Could not download Piper voice file {Path(remote_path).name}: {e}"
        ) from e

    if expected_md5 and digest.hexdigest() != expected_md5:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"Downloaded voice {Path(remote_path).name} failed its checksum — "
            "the download was corrupted. Try again.")

    shutil.move(str(tmp), str(dest))


def downloaded_voices():
    """Catalog entries for every voice present locally, for cache reporting."""
    return [v for v in load_catalog() if is_downloaded(v)]


def remove_downloaded_voice(voice):
    """Delete a downloaded voice. Bundled voices are left alone."""
    model = local_path(voice)
    if VOICES_DIR in model.parents:
        return False
    model.unlink(missing_ok=True)
    model.with_suffix(".onnx.json").unlink(missing_ok=True)
    return True
