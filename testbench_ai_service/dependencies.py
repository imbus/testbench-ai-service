from collections.abc import Generator

import requests
from fastapi import Depends, HTTPException, Request, status
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.auth import AuthInfo, get_auth_info
from testbench_ai_service.config import AppConfig
from testbench_ai_service.llm.factory import LLMFactory
from testbench_ai_service.log import logger


def get_app_config(request: Request) -> AppConfig:
    config: AppConfig = request.app.state.config
    return config


def get_tb_connection(
    config: AppConfig = Depends(get_app_config),
    auth_info: AuthInfo = Depends(get_auth_info),
) -> Generator[TBConnection, None, None]:
    """Yield an authenticated TestBench connection for the duration of a request."""
    server_url = config.tb_server_url
    try:
        conn = TBConnection(server_url=server_url, verify=False, sessionToken=auth_info.token)
    except requests.exceptions.RequestException as e:
        logger.error("Could not connect to TestBench server: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not connect to TestBench server: {e!s}",
        ) from e

    try:
        yield conn
    finally:
        conn.close()


def get_llm_factory(request: Request) -> LLMFactory:
    factory: LLMFactory = request.app.state.llm_factory
    return factory
