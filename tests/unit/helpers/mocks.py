"""
Shared mock factories for unit tests.

Use these factory functions instead of duplicating MagicMock boilerplate across
test files.  Each factory returns a pre-configured mock that covers the most
common patterns; individual test classes can still customize the result as
needed.
"""

from unittest.mock import AsyncMock, MagicMock

from testbench_ai_service.config import AppConfig


def make_app_config(**overrides) -> AppConfig:
    """Return a minimal, valid AppConfig suitable for unit tests.

    Any keyword argument accepted by AppConfig can be passed as an override,
    e.g. ``make_app_config(language="de")``.
    """
    return AppConfig(tb_server_url="https://localhost:9443/api/", **overrides)


def make_mock_tb_connection(server_url: str = "https://localhost:9443/api/") -> MagicMock:
    """Return a MagicMock that mimics the TBConnection interface.

    The ``server_url`` attribute is pre-set so callers can compose URLs without
    an additional ``configure`` call.
    """
    mock = MagicMock()
    mock.server_url = server_url
    return mock


def make_mock_llm_factory() -> MagicMock:
    """Return a MagicMock that mimics LLMFactory.

    ``get_client()`` is pre-configured to return a fresh ``AsyncMock`` so
    callers that just need the factory to *work* without real AI calls need
    no extra setup.
    """
    mock = MagicMock()
    mock.get_client.return_value = AsyncMock()
    return mock
