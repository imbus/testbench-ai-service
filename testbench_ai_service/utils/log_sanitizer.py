import json
from typing import Any

SECRET_KEY_NAMES = frozenset(
    {
        "password",
        "pwd",
        "token",
        "sessiontoken",
        "secret",
        "clientsecret",
        "apikey",
        "authorization",
        "credentials",
    }
)
REDACTED = "***"
MAX_BODY_CHARS = 2000


def _is_secret_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    return key.lower().replace("_", "").replace("-", "") in SECRET_KEY_NAMES


def redact_secrets(value: Any) -> Any:
    """
    Return a copy of `value` with secret-looking values replaced by `REDACTED`.

    Keys match case-insensitively and ignoring `_` and `-`, so `password`,
    `api_key`, `apiKey` and `API-Key` are all redacted. Dicts and lists are
    walked recursively; anything else is returned unchanged. The argument is
    never mutated, because it is the live request body.
    """
    if isinstance(value, dict):
        return {
            key: REDACTED if _is_secret_key(key) else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact_secrets(item) for item in value]
    return value


def truncate(text: str) -> str:
    """Cap `text` at `MAX_BODY_CHARS`, recording how long the original was."""
    if len(text) <= MAX_BODY_CHARS:
        return text
    return f"{text[:MAX_BODY_CHARS]}... (truncated, {len(text)} chars total)"


def format_body(value: Any) -> str:
    """
    Serialize a parsed request body as JSON for logging.

    Never raises: `default=str` degrades an unexpected non-serializable value to
    its string form, and a serialization failure yields a placeholder, so
    logging cannot break the request it describes.
    """
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return "<unserializable body>"
    return truncate(text)


def format_body_text(text: str) -> str:
    """
    Sanitize an already-serialized request body for logging.

    Valid JSON is redacted by key. Anything else is truncated as-is, because an
    unparseable body cannot be redacted structurally.
    """
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return truncate(text)
    return format_body(redact_secrets(parsed))
