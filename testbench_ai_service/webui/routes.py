from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from testbench_ai_service.config import AppConfig
from testbench_ai_service.dependencies import get_app_config
from testbench_ai_service.log import logger
from testbench_ai_service.webui.atomic import write_atomic
from testbench_ai_service.webui.auth import (
    authenticate,
    clear_session_cookies,
    current_session,
    get_session_store,
    is_admin_role,
    require_admin,
    require_csrf,
    set_session_cookies,
)
from testbench_ai_service.webui.config_io import (
    build_config_response,
    read_config_file,
    redact_toml_text,
)
from testbench_ai_service.webui.diff import file_diff
from testbench_ai_service.webui.document import apply_edits, load_document, render_document
from testbench_ai_service.webui.edits import merge_edits, validate_edit_paths
from testbench_ai_service.webui.inflight import TaskRegistry, get_task_registry
from testbench_ai_service.webui.logs import MAX_LIMIT, read_log
from testbench_ai_service.webui.models import (
    ApplyResponse,
    ConfigEditsRequest,
    ConfigResponse,
    LoginRequest,
    LogLine,
    MetaResponse,
    PreviewResponse,
    SessionResponse,
    StatusResponse,
)
from testbench_ai_service.webui.reload import hot_reload, restart_required
from testbench_ai_service.webui.security import require_loopback
from testbench_ai_service.webui.session import Session, SessionStore
from testbench_ai_service.webui.status import build_status
from testbench_ai_service.webui.validate import validate_config_dict

router = APIRouter(
    prefix="/admin/api",
    tags=["console"],
    dependencies=[Depends(require_loopback)],
)


def _plan_change(
    edits: dict[str, Any],
    config_path: Path,
    running: AppConfig,
) -> tuple[PreviewResponse, str]:
    """Work out what applying *edits* would do, without doing any of it.

    Returns the preview payload and the rendered TOML text, so ``apply`` can
    reuse exactly the text ``preview`` showed rather than re-deriving it and
    risking a different result.

    Everything is computed against *config_path* as it is on disk right now,
    which is what makes a second operator's diff show the first operator's
    changes instead of silently reverting them (spec 6.1).
    """
    validate_edit_paths(edits)

    document = load_document(config_path)
    current_text = render_document(document)

    merged = merge_edits(read_config_file(config_path), edits)
    candidate, issues = validate_config_dict(merged)

    if candidate is None:
        # Nothing to approve and nothing that could be written, so no diff and
        # no restart classification -- both would be claims about a config that
        # cannot exist.
        return (
            PreviewResponse(
                valid=False,
                issues=issues,
                diffs=[],
                restart_required=[],
                in_flight_tasks=0,
                toml=redact_toml_text(current_text),
            ),
            current_text,
        )

    apply_edits(document, edits)
    proposed_text = render_document(document)
    # toml/diffs are DISPLAY-ONLY and go through redact_toml_text -- the Raw
    # screen and the apply dialog's diff must hide the same credential values
    # GET /config already hides. The tuple's second element (proposed_text)
    # stays RAW: it is what apply (Task 12) writes to disk, and writing the
    # redacted text would replace the operator's real credential with the
    # literal sentinel string, destroying it.
    diff = file_diff(
        str(config_path.resolve()),
        redact_toml_text(current_text),
        redact_toml_text(proposed_text),
    )

    return (
        PreviewResponse(
            valid=True,
            issues=[],
            diffs=[diff] if diff is not None else [],
            restart_required=restart_required(running, candidate),
            in_flight_tasks=0,
            toml=redact_toml_text(proposed_text),
        ),
        proposed_text,
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


@router.post("/config/preview", response_model=PreviewResponse)
async def preview_config(
    body: ConfigEditsRequest,
    request: Request,
    config: AppConfig = Depends(get_app_config),
    registry: TaskRegistry = Depends(get_task_registry),
    _: Session = Depends(require_admin),
    __: None = Depends(require_csrf),
) -> PreviewResponse:
    """What applying the operator's edits would do -- diff, validity, restart need.

    Mutating-route guards despite reading nothing: it carries a body of
    operator edits and is only meaningful to someone who could apply them, so
    it is gated exactly like ``apply`` rather than becoming a way for a
    non-admin to explore the config surface.
    """
    preview, _text = _plan_change(body.edits, Path(request.app.state.config_path), config)
    preview.in_flight_tasks = registry.count
    return preview


@router.post("/config/apply", response_model=ApplyResponse)
async def apply_config(
    body: ConfigEditsRequest,
    request: Request,
    config: AppConfig = Depends(get_app_config),
    registry: TaskRegistry = Depends(get_task_registry),
    _: Session = Depends(require_admin),
    __: None = Depends(require_csrf),
) -> ApplyResponse:
    """Validate the operator's edits, write them atomically, then reload.

    Refuses with 422 and the field-addressed issues if the merged config is one
    the service could not boot with -- nothing is written in that case, so a
    rejected apply can never leave a config file the service will not start
    from.

    A change the running process cannot honour (see
    :func:`~testbench_ai_service.webui.reload.restart_required`) is still
    written, but the in-process swap is skipped: the file is the source of
    truth, and reporting a new port as live when the socket is still the old
    one would be a lie. The response names what needs a restart; the console
    raises its banner. Nothing here ever restarts the service (spec 7).
    """
    config_path = Path(request.app.state.config_path)
    preview, proposed_text = _plan_change(body.edits, config_path, config)

    if not preview.valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "The configuration is not valid and was not written.",
                "issues": [issue.model_dump() for issue in preview.issues],
            },
        )

    if not preview.diffs:
        # Nothing to do. Writing anyway would churn the .bak and the mtime for
        # an operator who changed their mind back.
        return ApplyResponse(
            written=[],
            backup=None,
            restart_required=[],
            reloaded=False,
            in_flight_tasks=registry.count,
        )

    # proposed_text, never preview.toml: preview.toml is REDACTED for display
    # (Task 11), so writing it would replace the operator's real credential
    # with the literal "***REDACTED***" sentinel. proposed_text is the raw
    # second element _plan_change returns specifically so apply can write it.
    backup = write_atomic(config_path, proposed_text)

    needs_restart = preview.restart_required
    reloaded = False
    if not needs_restart:
        # Re-read rather than reuse the candidate _plan_change built: what the
        # process takes up must be what is now on disk, so a discrepancy
        # between the document path and the dict path shows up here as a
        # logged error instead of as a process quietly running something the
        # file does not say.
        reloaded_config, issues = validate_config_dict(read_config_file(config_path))
        if reloaded_config is not None:
            reloaded_config.loaded_from = config_path
            reloaded = await hot_reload(request.app, reloaded_config)
        else:
            # Should be unreachable: the same dict validated moments ago. If it
            # happens, the file on disk is the one that is right and the
            # operator needs to know the process did not follow.
            logger.error("Wrote %s but could not reload it: %s", config_path, issues)

    return ApplyResponse(
        written=[str(config_path.resolve())],
        backup=str(backup) if backup is not None else None,
        restart_required=needs_restart,
        reloaded=reloaded,
        in_flight_tasks=registry.count,
    )
