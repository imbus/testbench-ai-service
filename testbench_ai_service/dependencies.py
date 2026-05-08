from fastapi import Depends, Request
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.auth import AuthInfo, get_auth_info
from testbench_ai_service.config import AppConfig
from testbench_ai_service.llm.factory import LLMFactory


def get_app_config(request: Request) -> AppConfig:
    config: AppConfig = request.app.state.config
    return config


def get_tb_connection(
    auth_info: AuthInfo = Depends(get_auth_info),
) -> TBConnection:
    """Return the authenticated TestBench connection for the current request.

    The connection's lifecycle is managed by :func:`get_auth_info`, which opens
    it during token validation and closes it after the request completes.
    """
    return auth_info.conn


def get_llm_factory(request: Request) -> LLMFactory:
    factory: LLMFactory = request.app.state.llm_factory
    return factory
