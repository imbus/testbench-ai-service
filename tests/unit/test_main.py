import unittest
from unittest.mock import AsyncMock, MagicMock, patch

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


class TestCreateApp(unittest.TestCase):
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
        self.assertIsInstance(app, FastAPI)

    def test_app_title_is_set(self):
        app, _ = self._create_app_with_mock_config()
        self.assertEqual(app.title, "TestBench AI Service")

    def test_app_version_matches_package(self):
        app, _ = self._create_app_with_mock_config()
        self.assertEqual(app.version, __version__)

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

        self.assertIs(app.state.config, config)


class TestInitServices(unittest.TestCase):
    def test_creates_llm_factory_in_app_state(self):
        app = MagicMock()
        app.state.config.llm_config = MagicMock()

        with patch("testbench_ai_service.main.LLMFactory") as mock_factory_cls:
            mock_factory = MagicMock()
            mock_factory_cls.return_value = mock_factory
            init_services(app)

        self.assertIs(app.state.llm_factory, mock_factory)
        mock_factory.init_clients.assert_called_once()


class TestCloseServices(unittest.IsolatedAsyncioTestCase):
    async def test_closes_all_llm_clients(self):
        app = MagicMock()
        app.state.llm_factory.close_clients = AsyncMock()

        await close_services(app)

        app.state.llm_factory.close_clients.assert_awaited_once()


class TestInitRouters(unittest.TestCase):
    def test_includes_main_router(self):
        app = MagicMock()
        with patch("testbench_ai_service.main.get_usecase_routers", return_value=[]):
            init_routers(app)

        app.include_router.assert_called()

    def test_includes_usecase_routers(self):
        mock_usecase_router = MagicMock()
        app = MagicMock()

        with patch(
            "testbench_ai_service.main.get_usecase_routers", return_value=[mock_usecase_router]
        ):
            init_routers(app)

        # include_router called at least twice (main router + usecase router)
        self.assertGreaterEqual(app.include_router.call_count, 2)


class TestLifespan(unittest.IsolatedAsyncioTestCase):
    async def test_lifespan_inits_and_closes_services(self):
        """lifespan context manager calls init_services on enter and close_services on exit."""
        app = MagicMock()
        app.state.config.llm_config = MagicMock()

        with (
            patch("testbench_ai_service.main.init_services") as mock_init,
            patch("testbench_ai_service.main.close_services", new_callable=AsyncMock) as mock_close,
        ):
            async with lifespan(app):
                mock_init.assert_called_once_with(app)

        mock_close.assert_awaited_once_with(app)


if __name__ == "__main__":
    unittest.main()
