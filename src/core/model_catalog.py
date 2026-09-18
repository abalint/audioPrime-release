"""Fetch available AI model lists from OpenAI and Anthropic.

The fetched lists are cached in the config file so the dropdowns work
offline; the hardcoded AI_MODEL_OPTIONS in config.py remain the fallback
when no key is configured or a fetch has never succeeded.
"""

import re
from datetime import datetime, timezone

import requests

from ..config import (
    AI_MODEL_OPTIONS,
    AI_MODEL_SEPARATOR,
    get_anthropic_api_key,
    get_api_key,
    load_config,
    save_config,
)

REQUEST_TIMEOUT = 15

# OpenAI /v1/models lists every model (embeddings, TTS, image, ...).
# Keep only chat-completion capable text models.
_OPENAI_CHAT_RE = re.compile(r"^(gpt-|o\d)")
_OPENAI_EXCLUDE = (
    "audio", "realtime", "tts", "whisper", "transcribe", "embed",
    "moderation", "image", "dall-e", "search", "instruct", "vision",
    "davinci", "babbage", "computer-use", "codex",
)


def fetch_openai_models(api_key):
    """Return chat-capable OpenAI model ids, newest-ish first.

    Raises RuntimeError on any failure.
    """
    try:
        response = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"OpenAI model list fetch failed: {e}")
    if response.status_code != 200:
        raise RuntimeError(f"OpenAI model list fetch failed (HTTP {response.status_code})")

    models = []
    for entry in response.json().get("data", []):
        model_id = entry.get("id", "")
        if not _OPENAI_CHAT_RE.match(model_id):
            continue
        if any(term in model_id for term in _OPENAI_EXCLUDE):
            continue
        models.append(model_id)
    if not models:
        raise RuntimeError("OpenAI returned no chat models")
    # Descending sort puts newer families (gpt-5...) above older ones (gpt-4...)
    return sorted(set(models), reverse=True)


def fetch_anthropic_models(api_key):
    """Return Anthropic model ids, newest first (API returns most recent first).

    Raises RuntimeError on any failure.
    """
    try:
        response = requests.get(
            "https://api.anthropic.com/v1/models",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            params={"limit": 100},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"Anthropic model list fetch failed: {e}")
    if response.status_code != 200:
        raise RuntimeError(f"Anthropic model list fetch failed (HTTP {response.status_code})")

    models = [entry.get("id") for entry in response.json().get("data", [])
              if entry.get("id", "").startswith("claude-")]
    if not models:
        raise RuntimeError("Anthropic returned no models")
    return models


def _fallback_segment(anthropic: bool):
    """The hardcoded options for one provider, from AI_MODEL_OPTIONS."""
    sep_idx = AI_MODEL_OPTIONS.index(AI_MODEL_SEPARATOR)
    return AI_MODEL_OPTIONS[sep_idx + 1:] if anthropic else AI_MODEL_OPTIONS[:sep_idx]


def refresh_model_catalog():
    """Query both providers (where keys exist) and cache the results.

    Returns (options, errors): the combined dropdown option list and a list
    of human-readable fetch errors (empty on full success). Providers
    without an API key are silently skipped.
    """
    errors = []
    catalog = load_config().get("model_catalog", {})

    openai_key = get_api_key()
    if openai_key:
        try:
            catalog["openai"] = fetch_openai_models(openai_key)
        except RuntimeError as e:
            errors.append(str(e))

    anthropic_key = get_anthropic_api_key()
    if anthropic_key:
        try:
            catalog["anthropic"] = fetch_anthropic_models(anthropic_key)
        except RuntimeError as e:
            errors.append(str(e))

    catalog["fetched_at"] = datetime.now(timezone.utc).isoformat()
    config = load_config()
    config["model_catalog"] = catalog
    save_config(config)

    return get_ai_model_options(), errors


def get_ai_model_options():
    """Combined model dropdown options: cached live lists, hardcoded fallback."""
    catalog = load_config().get("model_catalog", {})
    openai_models = catalog.get("openai") or _fallback_segment(anthropic=False)
    anthropic_models = catalog.get("anthropic") or _fallback_segment(anthropic=True)
    return [*openai_models, AI_MODEL_SEPARATOR, *anthropic_models]
