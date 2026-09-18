"""Encrypt / decrypt API keys at rest using a local key file.

Uses only Python stdlib: HMAC-SHA256 in CTR mode for encryption,
HMAC-SHA256 for authentication.  The 32-byte encryption key lives in
~/.audioPrimeProd.key with mode 0600 (Unix).
"""

import base64
import hashlib
import hmac
import os
import struct
from pathlib import Path

KEY_FILE = Path.home() / ".audioPrimeProd.key"
_KEY_LEN = 32
_IV_LEN = 16
_TAG_LEN = 32  # HMAC-SHA256 digest length

_cached_key: bytes | None = None


class DecryptionError(Exception):
    """Raised when a token cannot be decrypted (bad key, tampered data, etc.)."""


# ── key management ──────────────────────────────────────────────────


def _get_or_create_key() -> bytes:
    """Return the 32-byte encryption key, creating it on first use."""
    global _cached_key
    if _cached_key is not None:
        return _cached_key

    if KEY_FILE.exists():
        raw = KEY_FILE.read_bytes()
        if len(raw) == _KEY_LEN:
            _cached_key = raw
            return _cached_key

    # Generate a fresh key and persist it with restricted permissions.
    key = os.urandom(_KEY_LEN)
    KEY_FILE.write_bytes(key)
    try:
        KEY_FILE.chmod(0o600)
    except OSError:
        pass  # Windows: permissions model differs; best-effort
    _cached_key = key
    return _cached_key


# ── CTR-mode keystream via HMAC-SHA256 ──────────────────────────────


def _keystream(key: bytes, iv: bytes, length: int) -> bytes:
    """Produce *length* bytes of keystream: HMAC-SHA256(key, iv || ctr)."""
    blocks: list[bytes] = []
    needed = length
    ctr = 0
    while needed > 0:
        block = hmac.new(
            key, iv + struct.pack(">I", ctr), hashlib.sha256
        ).digest()
        blocks.append(block)
        needed -= len(block)
        ctr += 1
    return b"".join(blocks)[:length]


def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


# ── public API ──────────────────────────────────────────────────────


def encrypt(plaintext: str) -> str:
    """Encrypt *plaintext* and return a base64-encoded token."""
    key = _get_or_create_key()
    iv = os.urandom(_IV_LEN)
    pt_bytes = plaintext.encode()
    ct = _xor(pt_bytes, _keystream(key, iv, len(pt_bytes)))
    tag = hmac.new(key, iv + ct, hashlib.sha256).digest()
    return base64.b64encode(iv + ct + tag).decode()


def decrypt(token: str) -> str:
    """Decrypt a base64 token produced by :func:`encrypt`.

    Raises :class:`DecryptionError` on any failure.
    """
    try:
        raw = base64.b64decode(token)
    except Exception as exc:
        raise DecryptionError("invalid base64") from exc

    if len(raw) < _IV_LEN + _TAG_LEN:
        raise DecryptionError("token too short")

    iv = raw[:_IV_LEN]
    tag = raw[-_TAG_LEN:]
    ct = raw[_IV_LEN:-_TAG_LEN]

    key = _get_or_create_key()
    expected_tag = hmac.new(key, iv + ct, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected_tag):
        raise DecryptionError("HMAC verification failed")

    pt_bytes = _xor(ct, _keystream(key, iv, len(ct)))
    return pt_bytes.decode()
