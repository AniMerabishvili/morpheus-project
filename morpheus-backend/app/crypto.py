"""
Field-level encryption for sensitive dream data.

Uses Fernet (AES-128-CBC + HMAC-SHA256) from the `cryptography` package.
The key is stored only in the server environment (DREAM_ENCRYPTION_KEY env var)
and is never sent to Supabase or the frontend.

If DREAM_ENCRYPTION_KEY is not set the functions are no-ops — plaintext is
stored as-is.  This keeps local development working without a key while
production always encrypts.

Existing unencrypted rows (legacy data before the key was introduced) are
returned as-is: decrypt_field() catches InvalidToken and falls back to the
raw value, so old rows continue to display correctly after the key is added.

Generate a new key with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import logging

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None


def _get_fernet() -> Fernet | None:
    global _fernet
    if _fernet is None and settings.DREAM_ENCRYPTION_KEY:
        _fernet = Fernet(settings.DREAM_ENCRYPTION_KEY.encode())
    return _fernet


def encrypt_field(value: str) -> str:
    """Encrypt a string value.  Returns plaintext if no key is configured."""
    f = _get_fernet()
    if f is None:
        return value
    return f.encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_field(value: str | None) -> str:
    """Decrypt a string value.

    Returns:
        - Empty string if value is None or empty.
        - Decrypted plaintext when the key is set and the value is a valid
          Fernet token.
        - The raw value unchanged when no key is configured OR when the token
          is invalid (handles legacy unencrypted rows transparently).
    """
    if not value:
        return value or ""
    f = _get_fernet()
    if f is None:
        return value
    try:
        return f.decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, Exception):
        # Legacy unencrypted row — return as-is so old data still displays.
        logger.debug("decrypt_field: value is not a Fernet token, returning raw (legacy row)")
        return value


def decrypt_dream_row(row: dict) -> dict:
    """Decrypt sensitive fields in a dream row returned from Supabase.

    Operates on a copy — does not mutate the original dict.
    Only decrypts fields that are present in the row.
    """
    row = dict(row)
    for field in ("raw_text", "analysis", "title"):
        if field in row and row[field] is not None:
            row[field] = decrypt_field(str(row[field]))
    return row
