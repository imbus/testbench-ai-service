"""
This module serves as the API controller for the system.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException

from testbench_ai_service import __version__
from testbench_ai_service.config import AppConfig
from testbench_ai_service.exceptions import http_exception_handler
from testbench_ai_service.llm.factory import LLMFactory
from testbench_ai_service.middlewares import LoggingMiddleware
from testbench_ai_service.routes import router
from testbench_ai_service.usecases.routes import get_usecase_routers
from testbench_ai_service.utils.config import load_config_from_file
from testbench_ai_service.utils.i18n import load_translations


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

    usecase_routers = get_usecase_routers(app.state.config)
    for usecase_router in usecase_routers:
        app.include_router(usecase_router)


def init_exception_handlers(app: FastAPI):
    """Initialization of app exception handlers"""

    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]


def init_middlewares(app: FastAPI):
    """Initialization of app middlewares"""

    app.add_middleware(LoggingMiddleware)


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

    init_routers(app)
    init_exception_handlers(app)
    init_middlewares(app)
    init_services(app)

    return app
