from fastapi import APIRouter, Depends, Response, status

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
from testbench_ai_service.webui.models import (
    LoginRequest,
    MetaResponse,
    SessionResponse,
)
from testbench_ai_service.webui.security import require_loopback
from testbench_ai_service.webui.session import Session, SessionStore

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
    _: None = Depends(require_csrf),
) -> Response:
    store.revoke(session.sid)
    clear_session_cookies(response)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
