"""Recognising credential-named keys, shared by every place that masks them."""

_CREDENTIAL_KEY_SUBSTRINGS = (
    "secret",
    "password",
    "token",
    "credential",
    "authorization",
    "api_key",
    "apikey",
)
_SEPARATOR_TRANSLATION = str.maketrans({"-": "_", ".": "_", " ": "_"})


def looks_like_credential_key(key: str) -> bool:
    """True when *key* names a value that must not be shown or logged."""
    normalized = key.lower().translate(_SEPARATOR_TRANSLATION)
    return any(pattern in normalized for pattern in _CREDENTIAL_KEY_SUBSTRINGS)
