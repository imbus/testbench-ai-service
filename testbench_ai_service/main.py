"""
This module serves as the API controller for the system.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException

from testbench_ai_service import __version__
from testbench_ai_service.agents.routes import get_agent_routers
from testbench_ai_service.config import AppConfig
from testbench_ai_service.exceptions import http_exception_handler
from testbench_ai_service.llm.factory import LLMFactory
from testbench_ai_service.log import logger
from testbench_ai_service.middlewares import LoggingMiddleware, OutboundRequestLoggingMiddleware
from testbench_ai_service.routes import router
from testbench_ai_service.utils.config import load_config_from_file
from testbench_ai_service.utils.i18n import load_translations
from testbench_ai_service.webui.routes import router as webui_router
from testbench_ai_service.webui.security import is_loopback
from testbench_ai_service.webui.session import SessionStore
from testbench_ai_service.webui.static import STATIC_DIR, mount_spa


def init_services(app: FastAPI):
    """Initialization of app singleton services"""

    # Initialize a singleton instance of LLMFactory and add it to the application state
    app.state.llm_factory = LLMFactory()
    app.state.llm_factory.init_clients([app.state.config.llm_config])


async def close_services(app: FastAPI):
    """
    Close all services and resources that may hold open connections
    to ensure a clean application shutdown.
    """

    await app.state.llm_factory.close_clients()


def init_routers(app: FastAPI):
    """Initialization of app routers"""

    app.include_router(router)

    agent_routers = get_agent_routers(app.state.config)
    for agent_router in agent_routers:
        app.include_router(agent_router)


def init_webui(app: FastAPI):
    """Mount the browser console, unless it is disabled in config."""
    if not app.state.config.admin_ui.enabled:
        logger.info("Web console is disabled (admin_ui.enabled = false)")
        return

    if not is_loopback(app.state.config.host):
        logger.warning(
            "Web console is enabled and the service binds %s, so the console is "
            "reachable from other hosts. Restrict access or set "
            "admin_ui.require_loopback = true.",
            app.state.config.host,
        )

    app.state.webui_sessions = SessionStore()

    app.include_router(webui_router)
    mount_spa(app, STATIC_DIR)


def init_exception_handlers(app: FastAPI):
    """Initialization of app exception handlers"""

    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]


def init_middlewares(app: FastAPI):
    """Initialization of app middlewares"""

    app.add_middleware(LoggingMiddleware)
    OutboundRequestLoggingMiddleware.install(app.state.config.tb_server_url)


# Define startup and shutdown procedure
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield  # App runs here
    # Shutdown
    await close_services(app)


def create_app(config: AppConfig | None = None) -> FastAPI:
    if config is None:
        config = load_config_from_file("config.toml")

    load_translations()

    app = FastAPI(title="TestBench AI Service", version=__version__, lifespan=lifespan)

    app.state.config = config
    app.state.config_path = Path(getattr(config, "loaded_from", None) or "config.toml")
    app.state.started_at = datetime.now(timezone.utc)

    init_routers(app)
    init_webui(app)
    init_exception_handlers(app)
    init_middlewares(app)
    init_services(app)

    return app
