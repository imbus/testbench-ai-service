import requests
from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.config import AppConfig
from testbench_ai_service.log import logger

auth_header = APIKeyHeader(
    name="Authorization",
    scheme_name="SessionToken",
    description="For authentication, provide a session token.",
    auto_error=False,
)


def validate_session_token(request: Request, session_token: str = Security(auth_header)):
    if not session_token:
        logger.warning("Missing authorization token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization token"
        )

    config: AppConfig = request.app.state.config
    server_url = config.tb_server_url

    conn = TBConnection(server_url, verify=False, sessionToken=session_token)
    try:
        conn.check_is_working()
    except requests.exceptions.HTTPError as e:
        logger.warning("Invalid authorization token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization token"
        ) from e
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Could not connect to TestBench server: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not connect to TestBench server: {e!s}",
        ) from e
    finally:
        conn.close()

    return session_token
