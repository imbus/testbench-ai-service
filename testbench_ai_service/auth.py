from collections.abc import Generator
from dataclasses import dataclass, field
from enum import Enum

import requests
from fastapi import HTTPException, Request, Security, status
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
    conn: TBConnection = field(hash=False, compare=False)


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


def _validate_token(server_url: str, token: str, verify: bool | str) -> tuple[str, TBConnection]:
    """Validate *token* against TestBench and return the user key and open connection.

    The returned connection is intentionally left open so it can be reused for
    the remainder of the request.  The caller is responsible for closing it.
    On error the connection is closed before re-raising.

    Raises:
        HTTPException 401: Token is rejected by TestBench.
        HTTPException 502: TestBench server is unreachable.
    """
    conn: TBConnection | None = None
    try:
        conn = TBConnection(server_url, verify=verify, sessionToken=token)
        user_key = get_user_key(conn)
        return user_key, conn
    except requests.exceptions.HTTPError as e:
        logger.warning("Invalid authorization token")
        if conn is not None:
            conn.close()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization token"
        ) from e
    except requests.exceptions.ConnectionError as e:
        logger.error("Could not connect to TestBench server: %s", e)
        if conn is not None:
            conn.close()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not connect to TestBench server: {e!s}",
        ) from e


def validate_auth_token(
    request: Request,
    session_token: str = Security(_session_token_scheme),
    jwt_token: str = Security(_jwt_token_scheme),
) -> Generator[AuthInfo, None, None]:
    """FastAPI dependency: validate the Authorization header and yield auth context.

    Both ``session_token`` and ``jwt_token`` read the same ``Authorization`` header; the
    different scheme names exist only for OpenAPI documentation.  Token type is
    auto-detected by inspecting whether the value is a well-formed JWT.

    The TestBench connection opened during token validation is kept alive and
    attached to ``AuthInfo.conn`` for the duration of the request.  It is closed
    in the ``finally`` block after the response has been sent, regardless of
    whether the request succeeded or failed.

    FastAPI caches this dependency's result for the entire request scope, so
    every other dependency that declares ``Depends(validate_auth_token)`` receives the
    same ``AuthInfo`` object with no additional TestBench round-trips.

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

    verify: bool | str = config.tb_ssl_ca_bundle or config.tb_ssl_verify
    user_key, conn = _validate_token(config.tb_server_url, token, verify)
    try:
        yield AuthInfo(auth_type=auth_type, token=token, user_key=user_key, conn=conn)
    finally:
        # NOTE: Starlette runs BackgroundTasks inside Response.__call__ before returning
        # control to the routing stack, so the connection is still open for the full
        # duration of any background task scheduled during this request.
        conn.close()
