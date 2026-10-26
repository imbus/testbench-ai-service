"""Recognising credential-named keys, shared by every place that masks them."""

# Case-insensitive substring matches against key NAMES only -- never against
# values. "api_key"/"apikey" are compound tokens deliberately: a bare "key"
# pattern would wrongly catch `ssl_key`, which is a certificate file path, not
# a secret, and the compound form leaves `api_version` alone. The key is
# normalised before matching -- "-", "." and " " are folded to "_" -- so
# separator variants of the same compound token ("api-key", "x-api-key",
# "api.key", "api key") match exactly as "api_key" does, and lower-casing
# folds camelCase "apiKey" into "apikey". The bare-substring patterns
# ("secret", "token", "credential", ...) do not need this: they match
# regardless of what surrounds them either way.
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
