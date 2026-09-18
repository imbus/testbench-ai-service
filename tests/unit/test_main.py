from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

from testbench_ai_service import __version__
from testbench_ai_service.config import AppConfig
from testbench_ai_service.main import (
    close_services,
    create_app,
    init_routers,
    init_services,
    lifespan,
)


def _make_app_config():
    with (
        patch("testbench_ai_service.config.validate_tb_server_url"),
        patch("testbench_ai_service.config.AppConfig.validate_prompt_paths", return_value=None),
        patch(
            "testbench_ai_service.config.AppConfig.validate_prompts_dir_exists", return_value=None
        ),
    ):
        return AppConfig()


class TestCreateApp:
    def _create_app_with_mock_config(self):
        config = _make_app_config()
        with (
            patch("testbench_ai_service.main.load_translations"),
            patch("testbench_ai_service.main.LLMFactory") as mock_factory_cls,
        ):
            mock_factory = MagicMock()
            mock_factory.init_clients = MagicMock()
            mock_factory.close_clients = AsyncMock()
            mock_factory_cls.return_value = mock_factory
            app = create_app(config)
        return app, mock_factory

    def test_returns_fastapi_instance(self):
        app, _ = self._create_app_with_mock_config()
        assert isinstance(app, FastAPI)

    def test_app_title_is_set(self):
        app, _ = self._create_app_with_mock_config()
        assert app.title == "TestBench AI Service"

    def test_app_version_matches_package(self):
        app, _ = self._create_app_with_mock_config()
        assert app.version == __version__

    def test_config_stored_in_app_state(self):
        config = _make_app_config()
        with (
            patch("testbench_ai_service.main.load_translations"),
            patch("testbench_ai_service.main.LLMFactory") as mock_factory_cls,
        ):
            mock_factory = MagicMock()
            mock_factory.init_clients = MagicMock()
            mock_factory.close_clients = AsyncMock()
            mock_factory_cls.return_value = mock_factory
            app = create_app(config)

        assert app.state.config is config

    def test_boot_survives_a_missing_provider_credential(self):
        """A missing API key must not stop the service starting.

        The console exists partly to repair a misconfigured provider, so the
        one configuration that cannot start is the one the operator most needs
        to fix. Asserts the app is built, not that a log line was emitted.
        """
        config = _make_app_config()
        with (
            patch("testbench_ai_service.main.load_translations"),
            patch("testbench_ai_service.main.LLMFactory") as mock_factory_cls,
        ):
            mock_factory = MagicMock()
            mock_factory.init_clients.side_effect = ValueError(
                "API key for provider 'openai' not found in environment variables."
            )
            mock_factory.close_clients = AsyncMock()
            mock_factory_cls.return_value = mock_factory

            app = create_app(config)

        assert isinstance(app, FastAPI)
        # The factory is still on the app: clients are created on demand by
        # get_client, so the next agent request is where a genuinely missing
        # credential surfaces -- which is where it is actionable.
        assert app.state.llm_factory is mock_factory
        mock_factory.init_clients.assert_called_once()

    def test_boot_failure_is_logged_as_a_warning(self):
        """The operator gets told, on the one channel available at boot."""
        config = _make_app_config()
        with (
            patch("testbench_ai_service.main.load_translations"),
            patch("testbench_ai_service.main.LLMFactory") as mock_factory_cls,
            patch("testbench_ai_service.main.logger") as mock_logger,
        ):
            mock_factory = MagicMock()
            mock_factory.init_clients.side_effect = ValueError("no key")
            mock_factory.close_clients = AsyncMock()
            mock_factory_cls.return_value = mock_factory

            create_app(config)

        assert mock_logger.warning.called

    def test_keyboard_interrupt_during_boot_still_propagates(self):
        """BaseException is not swallowed: Ctrl-C must still stop the process."""
        config = _make_app_config()
        with (
            patch("testbench_ai_service.main.load_translations"),
            patch("testbench_ai_service.main.LLMFactory") as mock_factory_cls,
        ):
            mock_factory = MagicMock()
            mock_factory.init_clients.side_effect = KeyboardInterrupt()
            mock_factory.close_clients = AsyncMock()
            mock_factory_cls.return_value = mock_factory

            with pytest.raises(KeyboardInterrupt):
                create_app(config)


class TestInitServices:
    def test_creates_llm_factory_in_app_state(self):
        app = MagicMock()
        app.state.config.llm_config = MagicMock()

        with patch("testbench_ai_service.main.LLMFactory") as mock_factory_cls:
            mock_factory = MagicMock()
            mock_factory_cls.return_value = mock_factory
            init_services(app)

        assert app.state.llm_factory is mock_factory
        mock_factory.init_clients.assert_called_once()


class TestCloseServices:
    async def test_closes_all_llm_clients(self):
        app = MagicMock()
        app.state.llm_factory.close_clients = AsyncMock()

        await close_services(app)

        app.state.llm_factory.close_clients.assert_awaited_once()


class TestInitRouters:
    def test_includes_main_router(self):
        app = MagicMock()
        with patch("testbench_ai_service.main.get_agent_routers", return_value=[]):
            init_routers(app)

        app.include_router.assert_called()

    def test_includes_agent_routers(self):
        mock_agent_router = MagicMock()
        app = MagicMock()

        with patch("testbench_ai_service.main.get_agent_routers", return_value=[mock_agent_router]):
            init_routers(app)

        assert app.include_router.call_count >= 2


class TestLifespan:
    async def test_lifespan_closes_services(self):
        """lifespan context manager calls close_services on exit."""
        app = MagicMock()
        app.state.config.llm_config = MagicMock()

        with patch(
            "testbench_ai_service.main.close_services", new_callable=AsyncMock
        ) as mock_close:
            async with lifespan(app):
                pass

        mock_close.assert_awaited_once_with(app)
