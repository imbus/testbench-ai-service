from dataclasses import dataclass
from enum import Enum

import requests
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
from jwt import DecodeError, decode
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.config import AppConfig
from testbench_ai_service.log import logger
from testbench_ai_service.utils.testbench import get_user_key


class AuthType(str, Enum):
    JWT_TOKEN = "jwt_token"
    SESSION_TOKEN = "session_token"


@dataclass(frozen=True)
class AuthInfo:
    """Validated authentication state for a single request."""

    auth_type: AuthType
    token: str
    user_key: str


_session_token_scheme = APIKeyHeader(
    name="Authorization",
    scheme_name="SessionToken",
    description="Authenticate using a session token.",
    auto_error=False,
)

_jwt_token_scheme = APIKeyHeader(
    name="Authorization",
    scheme_name="JWTToken",
    description="Authenticate using a JWT token.",
    auto_error=False,
)


def _is_jwt(token: str) -> bool:
    """Return True if *token* is a syntactically valid JWT.

    A JWT always consists of exactly three base64url-encoded segments separated
    by dots.  Signature verification is intentionally skipped here; the only
    purpose of this function is to distinguish JWT tokens from opaque session
    tokens so the correct execution-context builder is used.
    """
    if token.count(".") != 2:  # noqa: PLR2004
        return False
    try:
        decode(token, options={"verify_signature": False})
        return True
    except DecodeError:
        return False


def _validate_token(server_url: str, token: str) -> str:
    """Validate *token* against TestBench and return the authenticated user key.

    Opens a short-lived connection exclusively for validation so that the
    result (the user key) can be cached in ``AuthInfo`` and reused by
    downstream code without making a second API call.

    Raises:
        HTTPException 401: Token is rejected by TestBench.
        HTTPException 502: TestBench server is unreachable.
    """
    conn: TBConnection | None = None
    try:
        conn = TBConnection(server_url, verify=False, sessionToken=token)
        return get_user_key(conn)
    except requests.exceptions.HTTPError as e:
        logger.warning("Invalid authorization token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization token"
        ) from e
    except requests.exceptions.ConnectionError as e:
        logger.error("Could not connect to TestBench server: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not connect to TestBench server: {e!s}",
        ) from e
    finally:
        if conn is not None:
            conn.close()


def get_auth_info(
    request: Request,
    session_token: str = Security(_session_token_scheme),
    jwt_token: str = Security(_jwt_token_scheme),
) -> AuthInfo:
    """FastAPI dependency: validate the Authorization header and return auth context.

    Both ``session_token`` and ``jwt_token`` read the same ``Authorization`` header; the
    different scheme names exist only for OpenAPI documentation.  Token type is
    auto-detected by inspecting whether the value is a well-formed JWT.

    FastAPI caches this dependency's result for the entire request scope, so
    every other dependency that declares ``Depends(get_auth_info)`` — including
    the router-level ``validate_auth_token`` wrapper — receives the same
    ``AuthInfo`` object with no additional TestBench round-trips.

    Raises:
        HTTPException 401: Token is missing or rejected.
        HTTPException 502: TestBench server is unreachable.
    """
    token = jwt_token or session_token
    if not token:
        logger.warning("Missing authorization token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization token"
        )

    config: AppConfig = request.app.state.config
    auth_type = AuthType.JWT_TOKEN if _is_jwt(token) else AuthType.SESSION_TOKEN
    logger.debug("Authenticating via %s", auth_type.value)

    user_key = _validate_token(config.tb_server_url, token)
    return AuthInfo(auth_type=auth_type, token=token, user_key=user_key)


def validate_auth_token(auth_info: AuthInfo = Depends(get_auth_info)) -> AuthInfo:
    """Router-level authentication enforcement dependency."""
    return auth_info
