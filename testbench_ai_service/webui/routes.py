from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request, Response, status

from testbench_ai_service.config import AppConfig
from testbench_ai_service.dependencies import get_app_config
from testbench_ai_service.webui.auth import (
    authenticate,
    clear_session_cookies,
    current_session,
    get_session_store,
    is_admin_role,
    require_csrf,
    set_session_cookies,
)
from testbench_ai_service.webui.config_io import build_config_response
from testbench_ai_service.webui.inflight import TaskRegistry, get_task_registry
from testbench_ai_service.webui.logs import MAX_LIMIT, read_log
from testbench_ai_service.webui.models import (
    ConfigResponse,
    LoginRequest,
    LogLine,
    MetaResponse,
    SessionResponse,
    StatusResponse,
)
from testbench_ai_service.webui.security import require_loopback
from testbench_ai_service.webui.session import Session, SessionStore
from testbench_ai_service.webui.status import build_status

router = APIRouter(
    prefix="/admin/api",
    tags=["console"],
    dependencies=[Depends(require_loopback)],
)


@router.get("/meta", response_model=MetaResponse)
async def read_meta(config: AppConfig = Depends(get_app_config)) -> MetaResponse:
    """Unauthenticated: the login screen names the server before signing in.

    Deliberately carries nothing but the URL.
    """
    return MetaResponse(tb_server_url=config.tb_server_url)


@router.post("/session", response_model=SessionResponse)
async def sign_in(
    body: LoginRequest,
    response: Response,
    config: AppConfig = Depends(get_app_config),
    store: SessionStore = Depends(get_session_store),
) -> SessionResponse:
    """Exchange TestBench credentials for a console session."""
    token, roles = authenticate(config, body.username, body.password)
    session = store.create(
        username=body.username,
        roles=roles,
        is_admin=is_admin_role(roles),
        tb_session_token=token,
    )
    set_session_cookies(response, session, config)
    return SessionResponse(
        username=session.username,
        roles=session.roles,
        is_admin=session.is_admin,
        tb_server_url=config.tb_server_url,
    )


@router.get("/session", response_model=SessionResponse)
async def read_session(
    session: Session = Depends(current_session),
    config: AppConfig = Depends(get_app_config),
) -> SessionResponse:
    """Who am I -- so a page reload does not force a new login."""
    return SessionResponse(
        username=session.username,
        roles=session.roles,
        is_admin=session.is_admin,
        tb_server_url=config.tb_server_url,
    )


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out(
    response: Response,
    session: Session = Depends(current_session),
    store: SessionStore = Depends(get_session_store),
    config: AppConfig = Depends(get_app_config),
    _: None = Depends(require_csrf),
) -> None:
    """Revoke the session and clear both cookies on the client.

    Must mutate the injected ``response`` and return ``None`` -- returning a
    fresh ``Response`` instance instead discards the Set-Cookie headers that
    :func:`clear_session_cookies` just attached.
    """
    store.revoke(session.sid)
    clear_session_cookies(response, config)


@router.get("/status", response_model=StatusResponse)
async def read_status(
    request: Request,
    _: Session = Depends(current_session),
    config: AppConfig = Depends(get_app_config),
    registry: TaskRegistry = Depends(get_task_registry),
) -> StatusResponse:
    """Service facts, TestBench reachability, credential presence, agent counts,
    and how many agent runs are in flight."""
    return build_status(config, request.app.state.started_at, registry.count)


@router.get("/config", response_model=ConfigResponse)
async def read_config(
    request: Request,
    _: Session = Depends(current_session),
    config: AppConfig = Depends(get_app_config),
) -> ConfigResponse:
    """The service's configuration, as loaded and as stored on disk.

    Requires a session but not the admin role -- Phase 1 is read-only for
    everyone signed in.
    """
    return build_config_response(config, request.app.state.config_path)


@router.get("/logs", response_model=list[LogLine])
async def read_logs(
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
    _: Session = Depends(current_session),
    config: AppConfig = Depends(get_app_config),
) -> list[LogLine]:
    """Tail the service log for the console's Status screen.

    Requires a session but not the admin role -- Phase 1 is read-only for
    everyone signed in.
    """
    return read_log(Path(config.logging.file.file_name), limit)
