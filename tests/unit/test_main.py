from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI

from testbench_ai_service import __version__
from testbench_ai_service.config import AppConfig
from testbench_ai_service.main import (
    close_services,
    create_app,
    init_middlewares,
    init_routers,
    init_services,
    lifespan,
)
from testbench_ai_service.middlewares import LoggingMiddleware


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


class TestInitMiddlewares:
    """The logging middleware is handed the payload limit from the app config."""

    def test_max_payload_length_is_taken_from_the_config(self):
        app = FastAPI()
        app.state.config = _make_app_config()
        app.state.config.logging.max_payload_length = 123

        init_middlewares(app)

        middleware = next(m for m in app.user_middleware if m.cls is LoggingMiddleware)
        assert middleware.kwargs["max_payload_length"] == 123

    def test_outbound_logging_is_installed_for_the_testbench_server(self):
        app = FastAPI()
        app.state.config = _make_app_config()

        with patch(
            "testbench_ai_service.main.OutboundRequestLoggingMiddleware.install"
        ) as mock_install:
            init_middlewares(app)

        mock_install.assert_called_once_with(app.state.config.tb_server_url)
