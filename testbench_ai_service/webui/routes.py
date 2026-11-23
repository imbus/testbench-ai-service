import asyncio
import os
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response, status
from sqlalchemy.exc import SQLAlchemyError

from testbench_ai_service.config import AppConfig
from testbench_ai_service.dependencies import get_app_config
from testbench_ai_service.jobs.models import JobDetail, JobStatus, JobSummary
from testbench_ai_service.jobs.store import JobStore, get_job_store
from testbench_ai_service.llm.base import AzureAuthMethod, LLMProvider
from testbench_ai_service.llm.factory import LLMFactory
from testbench_ai_service.log import get_log_level_int, log_context, logger
from testbench_ai_service.models.config import LLMConfig
from testbench_ai_service.models.logging import LogLevel
from testbench_ai_service.restart import get_restart_controller
from testbench_ai_service.usage import UsageRecordingClient, UsageStore, get_usage_store
from testbench_ai_service.utils.config import get_llm_config
from testbench_ai_service.utils.naming import normalize_project_name
from testbench_ai_service.webui.activity import MAX_LIMIT, read_activity
from testbench_ai_service.webui.agent_context import agent_context_sample
from testbench_ai_service.webui.atomic import write_atomic
from testbench_ai_service.webui.auth import (
    authenticate,
    bind_log_user,
    clear_session_cookies,
    current_session,
    get_session_store,
    is_admin_role,
    require_admin,
    require_csrf,
    set_session_cookies,
)
from testbench_ai_service.webui.catalogue import PROVIDER_KEY_NAMES, build_catalogue
from testbench_ai_service.webui.config_io import build_config_response, read_config_file
from testbench_ai_service.webui.fork import build_fork, rollback_fork
from testbench_ai_service.webui.inflight import TaskRegistry, get_task_registry
from testbench_ai_service.webui.models import (
    ActivityEntry,
    ApplyResponse,
    ConfigEditsRequest,
    ConfigResponse,
    LintRequest,
    LintResponse,
    LoginRequest,
    MetaResponse,
    ModelCatalogueResponse,
    PreviewResponse,
    ProjectsResponse,
    PromptDocumentResponse,
    PromptForkRequest,
    PromptForkResponse,
    PromptMetaResponse,
    PromptPlanResponse,
    PromptSaveRequest,
    PromptSaveResponse,
    PromptTestRequest,
    PromptTestResponse,
    PromptTreeResponse,
    RenderRequest,
    RenderResponse,
    ResolvedRoute,
    RestartResponse,
    SessionResponse,
    StatusResponse,
)
from testbench_ai_service.webui.multi_write import write_all
from testbench_ai_service.webui.paths import join_path
from testbench_ai_service.webui.plan import plan_change
from testbench_ai_service.webui.projects import (
    fetch_projects_with_token,
    projects_response,
    record_projects,
)
from testbench_ai_service.webui.prompt_refs import variant_references
from testbench_ai_service.webui.prompt_render import lint_template, render_messages
from testbench_ai_service.webui.prompt_test import SingleFlight, run_query, scrub_all, to_messages
from testbench_ai_service.webui.prompts import (
    build_tree,
    build_write_set,
    declared_prompt_file,
    read_prompt_document,
    read_prompt_meta,
    resolve_prompt_file,
)
from testbench_ai_service.webui.reload import hot_reload, restart_required
from testbench_ai_service.webui.security import require_loopback
from testbench_ai_service.webui.session import Session, SessionStore
from testbench_ai_service.webui.status import build_status, read_token_usage
from testbench_ai_service.webui.validate import validate_config_dict
from testbench_ai_service.webui.write_lock import hold_write_lock

#: Lets the restart response reach the browser before the server shuts down.
RESTART_DELAY_SECONDS = 0.5

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
def sign_in(
    body: LoginRequest,
    response: Response,
    config: AppConfig = Depends(get_app_config),
    store: SessionStore = Depends(get_session_store),
) -> SessionResponse:
    """Exchange TestBench credentials for a console session.

    Also caches the TestBench project list on the new session: ``authenticate``
    reads it inside the connection it already has, and a failure there is
    recorded rather than raised (design D3/D4). The payload stays identity-only
    -- the list is served by ``GET /projects`` so a stale cache can be replaced
    without signing in again.

    A sync ``def`` for the same reason ``read_projects`` is: everything it
    calls is the blocking TestBench client, and it now makes two calls
    rather than one -- the authentication and the project list. Awaiting
    nothing, it would otherwise hold the event loop for both.
    """
    login = authenticate(config, body.username, body.password)
    session = store.create(
        username=body.username,
        roles=login.roles,
        is_admin=is_admin_role(login.roles),
        tb_session_token=login.token,
        user_key=login.user_key,
    )
    record_projects(session, login.projects)
    set_session_cookies(response, session, config)
    return SessionResponse(
        username=session.username,
        roles=session.roles,
        is_admin=session.is_admin,
        tb_server_url=config.tb_server_url,
        has_user_key=bool(session.user_key),
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
        has_user_key=bool(session.user_key),
    )


@router.get("/projects", response_model=ProjectsResponse)
def read_projects(session: Session = Depends(current_session)) -> ProjectsResponse:
    """The project list cached at login. A pure read -- no outbound call.

    Open to any signed-in user, like every other read: only ``refresh`` and the
    config write routes require the admin role. ``source == "unavailable"`` is
    how the Projects screen learns that an empty list means "we could not ask",
    at which point it offers a free-text project name instead.
    """
    return projects_response(session)


@router.post("/projects/refresh", response_model=ProjectsResponse)
def refresh_projects(
    config: AppConfig = Depends(get_app_config),
    session: Session = Depends(require_admin),
    _: None = Depends(require_csrf),
    _log: Session = Depends(bind_log_user),
) -> ProjectsResponse:
    """Re-read the project list from TestBench and replace the cache.

    Admin-gated and CSRF-guarded despite writing nothing to disk: it spends the
    stored TestBench credential on an outbound call, which is not something a
    cross-site page may trigger on the operator's behalf.

    A sync ``def`` on purpose -- the vendored TestBench client is blocking, so
    this belongs in the threadpool rather than stalling the event loop for
    however long TestBench takes to answer.

    Never fails with a 5xx: a TestBench that cannot answer is reported as
    ``source == "unavailable"`` on a 200, and the previously cached list is
    kept rather than being replaced with an empty one.
    """
    record_projects(session, fetch_projects_with_token(config, session.tb_session_token))
    return projects_response(session)


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
    usage_store: UsageStore = Depends(get_usage_store),
) -> StatusResponse:
    """Service facts, TestBench reachability, credential presence, agent counts,
    in-flight runs, and whether the file on disk has changes the process has
    not taken up.

    The restart list is derived rather than remembered: an operator who edits
    config.toml by hand, or who reloads the console after an apply, must still
    see the banner, and process state would not survive either.
    """
    on_disk, _issues = validate_config_dict(read_config_file(Path(request.app.state.config_path)))
    pending = restart_required(config, on_disk) if on_disk is not None else []
    token_usage = await read_token_usage(usage_store)
    return await asyncio.to_thread(
        build_status,
        config,
        request.app.state.started_at,
        registry.count,
        pending,
        token_usage,
        can_restart=get_restart_controller(request) is not None,
    )


@router.post("/restart", response_model=RestartResponse, status_code=status.HTTP_202_ACCEPTED)
async def restart_service(
    request: Request,
    registry: TaskRegistry = Depends(get_task_registry),
    _: Session = Depends(require_admin),
    __: None = Depends(require_csrf),
    _log: Session = Depends(bind_log_user),
) -> RestartResponse:
    """Restart the service in this process with the configuration on disk.

    Refuses with 422 and the field-addressed issues, like ``apply``, if the
    file is one the service could not start with -- the serving loop would
    fall back to the running configuration, but the operator should learn why
    up front. Refuses with 409 when the service was not started by
    ``testbench-ai-service start`` (``--dev`` auto-reload, an ASGI server of
    one's own): nothing could start it again.

    The restart begins shortly after the response is sent: open requests get
    a grace period, running agent jobs end as "aborted by a service restart".
    Console sessions survive. The response says where the restarted service
    will listen, which may differ from where it does now.
    """
    controller = get_restart_controller(request)
    if controller is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This service cannot restart itself: it was not started with "
            "'testbench-ai-service start', or runs with auto-reload. Restart it by hand.",
        )

    new_config, issues = validate_config_dict(read_config_file(Path(request.app.state.config_path)))
    if new_config is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "The configuration on disk is not valid; the service was not restarted.",
                "issues": [issue.model_dump() for issue in issues],
            },
        )
    controller.apply_overrides(new_config)

    asyncio.get_running_loop().call_later(RESTART_DELAY_SECONDS, controller.request)
    return RestartResponse(
        host=new_config.host,
        port=new_config.port,
        tls=bool(new_config.ssl_cert),
        in_flight_tasks=registry.count,
    )


@router.get("/config", response_model=ConfigResponse)
async def read_config(
    request: Request,
    _: Session = Depends(current_session),
    config: AppConfig = Depends(get_app_config),
) -> ConfigResponse:
    """The service's configuration, as loaded and as stored on disk.

    Requires a session but not the admin role -- reading the configuration is
    open to everyone signed in; only ``preview``/``apply`` require the admin
    role.
    """
    return build_config_response(config, request.app.state.config_path)


@router.get("/prompts/{lang}/{agent}/meta", response_model=PromptMetaResponse)
def read_prompt_metadata(
    lang: str,
    agent: str,
    request: Request,
    file: str | None = Query(
        default=None,
        description=(
            "Read this prompt file instead of the one the agent key declares. "
            "Relative to prompts_dir/<lang>/, and still contained within prompts_dir."
        ),
    ),
    _: Session = Depends(current_session),
    config: AppConfig = Depends(get_app_config),
) -> PromptMetaResponse:
    """Variant names and variable declarations for one agent's prompt.

    A read, so a session is enough -- the form has to render for anyone signed
    in, even though only an admin can apply what they type into it.

    The route does not resolve scope itself: the caller names both segments, so
    one endpoint serves global and per-project scope alike. ``lang`` is the
    effective language for the scope being edited (a project's ``language``
    override, otherwise the global one), and ``file`` carries the prompt file
    the *draft* points at -- a project override, or a switch the operator has
    made in the form but not yet applied. Without ``file``, a project pointing
    at a different prompt would be edited against the global prompt's variants
    and variable declarations: wrong metadata, with no symptom until the agent
    runs.

    A sync ``def``: it reads and parses a YAML file plus config.toml, so it
    belongs in the threadpool.
    """
    if config.prompts_dir is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No prompts directory is configured, so prompt metadata cannot be read",
        )

    candidate: str | Path | None = file
    if candidate is None:
        candidate = declared_prompt_file(
            agent, read_config_file(Path(request.app.state.config_path)), config
        )
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No agent named {agent!r} declares a prompt file",
        )

    return read_prompt_meta(
        resolve_prompt_file(config.prompts_dir, lang, candidate), config.prompts_dir
    )


@router.get("/activity", response_model=list[ActivityEntry])
def read_activity_log(
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
    level: LogLevel = Query(default=LogLevel.INFO),
    scope: Literal["mine", "service", "all"] = Query(default="all"),
    session: Session = Depends(current_session),
    config: AppConfig = Depends(get_app_config),
) -> list[ActivityEntry]:
    """The signed-in user's own activity, plus service entries for admins.

    Never another user's entries, for admins neither, and no parameter asks
    for them (design D6). A non-admin's ``scope`` is narrowed to ``mine``.

    A sync ``def``: it reads up to four files, so it belongs in the threadpool.
    """
    if not session.is_admin:
        scope = "mine"
    return read_activity(
        config.logging.activity,
        user_key=session.user_key,
        include_own=scope in ("mine", "all"),
        include_service=scope in ("service", "all"),
        min_level=get_log_level_int(level.value),
        limit=limit,
    )


def _jobs_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Jobs are temporarily unavailable"
    )


@router.get("/jobs", response_model=list[JobSummary])
def list_jobs(
    agent: str | None = Query(default=None),
    job_status: JobStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(current_session),
    job_store: JobStore = Depends(get_job_store),
) -> list[JobSummary]:
    """The signed-in user's own agent jobs, newest first, without reports.

    Never another user's jobs, for admins neither, and no parameter asks for
    them (design D6). A session without a user key owns no jobs and the store
    is not asked.

    A sync ``def``: the read hits SQLite, so it belongs in the threadpool.
    """
    if not session.user_key:
        return []
    try:
        return job_store.list_for_user(
            session.user_key, agent_key=agent, status=job_status, limit=limit
        )
    except (SQLAlchemyError, OSError) as e:
        logger.warning("Could not list jobs: %r", e)
        raise _jobs_unavailable() from e


@router.get("/jobs/{job_id}", response_model=JobDetail)
def read_job(
    job_id: str,
    session: Session = Depends(current_session),
    job_store: JobStore = Depends(get_job_store),
) -> JobDetail:
    """One of the signed-in user's own jobs, with its report.

    A job of someone else is answered like an unknown one (404), for admins
    as well (design D6).
    """
    job = None
    if session.user_key:
        try:
            job = job_store.get(job_id, session.user_key)
        except (SQLAlchemyError, OSError) as e:
            logger.warning("Could not read job '%s': %r", job_id, e)
            raise _jobs_unavailable() from e
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    return job


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
    preview, _text, _has_write = plan_change(
        body.edits, Path(request.app.state.config_path), config
    )
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
    _log: Session = Depends(bind_log_user),
    _lock: None = Depends(hold_write_lock),
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
    raises its banner. Applying never restarts the service; the operator does,
    through :func:`restart_service`.

    ``validate_config_dict`` also refuses a ``logging.file.file_name`` (and,
    while enabled, a ``logging.activity.file_name``) the process could not
    open (see
    :func:`~testbench_ai_service.webui.validate._log_file_writability_issues`)
    -- without it, an operator could write a config the process cannot even
    boot with, since ``setup_logging`` builds the file handlers at startup.
    That check runs before any write, same as every other validation issue.

    Once the write has committed, nothing that follows may turn it back into
    a non-2xx response: re-reading the file to verify the reload can itself
    fail (``read_config_file`` raises ``HTTPException`` on a decode error),
    and that is reported through ``reload_detail`` on a normal 200, not
    raised -- the write already succeeded and the response must say so.
    """
    config_path = Path(request.app.state.config_path)
    preview, proposed_text, has_write = plan_change(body.edits, config_path, config)

    if not preview.valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "The configuration is not valid and was not written.",
                "issues": [issue.model_dump() for issue in preview.issues],
            },
        )

    if not has_write:
        return ApplyResponse(
            written=[],
            backup=None,
            restart_required=[],
            reloaded=False,
            in_flight_tasks=registry.count,
        )

    backup = write_atomic(config_path, proposed_text)

    needs_restart = preview.restart_required
    reloaded = False
    reload_detail: str | None = None
    if not needs_restart:
        try:
            on_disk = read_config_file(config_path)
        except HTTPException as e:
            logger.error(
                "Wrote %s but could not re-read it to verify the reload: %s",
                config_path,
                e.detail,
            )
            reload_detail = (
                f"Wrote the configuration, but could not re-read it to verify "
                f"the reload: {e.detail}"
            )
        else:
            reloaded_config, issues = validate_config_dict(on_disk)
            if reloaded_config is not None:
                reloaded_config.loaded_from = config_path
                reloaded = await hot_reload(request.app, reloaded_config)
                if not reloaded:
                    reload_detail = (
                        "Wrote the configuration, but the in-process reload completed "
                        "with degraded results; check the service log if it is "
                        "currently writable."
                    )
            else:
                logger.error("Wrote %s but could not reload it: %s", config_path, issues)
                reasons = "; ".join(issue.message for issue in issues)
                reload_detail = (
                    f"Wrote the configuration, but it failed re-validation before reload: {reasons}"
                )

    return ApplyResponse(
        written=[str(config_path.resolve())],
        backup=str(backup) if backup is not None else None,
        restart_required=needs_restart,
        reloaded=reloaded,
        reload_detail=reload_detail,
        in_flight_tasks=registry.count,
    )


@router.get("/prompts", response_model=PromptTreeResponse)
def read_prompt_tree(
    request: Request,
    _session: Session = Depends(current_session),
    config: AppConfig = Depends(get_app_config),
) -> PromptTreeResponse:
    """Every prompt on disk, including the ones that do not parse."""
    if config.prompts_dir is None:
        return PromptTreeResponse(languages=[])
    try:
        on_disk = read_config_file(Path(request.app.state.config_path))
    except HTTPException as e:
        logger.warning("Listing prompts without usage labels: %s", e.detail)
        on_disk = {}
    return build_tree(config.prompts_dir, on_disk)


@router.get("/prompts/{lang}/{agent}", response_model=PromptDocumentResponse)
def read_prompt_doc(
    lang: str,
    agent: str,
    _session: Session = Depends(current_session),
    config: AppConfig = Depends(get_app_config),
) -> PromptDocumentResponse:
    """The full editable document for one agent's prompt."""
    prompts_dir = _require_prompts_dir(config)
    path = resolve_prompt_file(prompts_dir, lang, Path(agent) / "prompt.yaml")
    return read_prompt_document(
        path,
        prompts_dir,
        lang,
        agent,
        agent_context_sample(config.agents, agent, config.agent_packages.dir),
    )


@router.post("/prompts/lint", response_model=LintResponse)
def lint_prompt_template(
    body: LintRequest,
    _session: Session = Depends(current_session),
    _csrf: None = Depends(require_csrf),
) -> LintResponse:
    """A real Jinja parse. Open to every signed-in user: it executes nothing."""
    return lint_template(body.content)


@router.post("/prompts/render", response_model=RenderResponse)
def render_prompt_preview(
    body: RenderRequest,
    _session: Session = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
) -> RenderResponse:
    """Render the messages against a sample context.

    Admin-only **and** sandboxed (design D3). Rendering evaluates operator
    text, and an unsandboxed environment here would be remote code execution
    against the service; admin is the second layer, not the only one.
    """
    return RenderResponse(
        messages=render_messages(body.messages, dict(body.vars), body.agent_context)
    )


def _credential_values(provider: LLMProvider, project: str | None) -> list[str]:
    """Every credential value a run for this provider could have used.

    Returned so the 502 path can mask each one (design D9). Values never leave
    this process: they are matched against an error message and discarded.
    An unknown provider (CUSTOM has no variable) yields an empty list, and
    scrub_all then leaves the message untouched.
    """
    name = PROVIDER_KEY_NAMES.get(provider)
    if name is None:
        return []
    candidates = [os.environ.get(name)]
    if project is not None:
        candidates.append(os.environ.get(f"{normalize_project_name(project)}_{name}"))
    return [value for value in candidates if value]


def _provider_error_detail(
    exc: Exception, provider: LLMProvider, llm_config: LLMConfig, secrets: list[str]
) -> str:
    """What a failed provider call may say back to the operator (design D9/§6).

    Normally the provider's own words, scrubbed by exact substring against the
    credential this run could have used -- operators need "model not found" or
    "401" to act on.

    The Entra ID path is the documented exception (§6, §9):
    ``resolve_entra_credentials`` yields a credential *object*, so there is no
    string for the scrubber to match on and ``_credential_values`` would return
    an empty list -- which would return the provider message **unscrubbed**,
    exactly the disclosure D9 exists to prevent. For that path only, the
    message is suppressed rather than scrubbed, and the operator is pointed at
    the log, where the caller has already recorded the full exception with
    ``exc_info``.
    """
    if provider is LLMProvider.AZURE_OPENAI and llm_config.auth_method == AzureAuthMethod.ENTRA_ID:
        return (
            f"{type(exc).__name__}: the provider's message was suppressed because this "
            "request authenticates via Entra ID, which yields a credential object rather "
            "than a string that could be masked. The full error is in the service log."
        )
    return scrub_all(f"{type(exc).__name__}: {exc}", secrets)


@router.post("/prompts/test", response_model=PromptTestResponse)
async def run_prompt_test(
    body: PromptTestRequest,
    request: Request,
    session: Session = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    config: AppConfig = Depends(get_app_config),
    registry: TaskRegistry = Depends(get_task_registry),
    usage_store: UsageStore = Depends(get_usage_store),
    _log: Session = Depends(bind_log_user),
) -> PromptTestResponse:
    """Run the editor's draft against a real model.

    The one console action that spends money, so the order matters: render
    first and refuse on failure BEFORE a client is created. Rendering goes
    through the same sandboxed environment as POST /prompts/render -- a test
    run is not a hole in that sandbox.
    """
    rendered = render_messages(body.messages, dict(body.vars), body.agent_context)
    failed = [item for item in rendered if item.error is not None]
    if failed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "The prompt did not render, so nothing was sent.",
                "messages": [item.model_dump() for item in rendered],
            },
        )

    llm_config = get_llm_config(config, project_name=body.project)
    factory: LLMFactory = request.app.state.llm_factory

    provider = factory.resolve_provider(llm_config, body.model)
    secrets = _credential_values(provider, body.project)

    try:
        client = factory.get_client(
            config=llm_config, prompt_model=body.model, project_name=body.project
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=scrub_all(str(e), secrets)
        ) from e

    client = UsageRecordingClient(client, usage_store, str(provider))

    scope = "global"
    if body.project is not None and factory.has_project_credential(
        body.project, provider, llm_config
    ):
        scope = "project"

    flight: SingleFlight = request.app.state.prompt_test_flight
    with (
        log_context(project_key=body.project, agent="prompt-test", run_id=uuid4().hex),
        flight.hold(session.sid),
    ):
        async with registry.track("prompt-test"):
            try:
                outcome = await run_query(client, body.model, to_messages(rendered))
            except HTTPException:
                raise
            except Exception as e:
                logger.error("Prompt test run failed: %r", e, exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=_provider_error_detail(e, provider, llm_config, secrets),
                ) from e

    return PromptTestResponse(
        text=outcome.text,
        latency_ms=outcome.latency_ms,
        usage=outcome.usage,
        resolved=ResolvedRoute(provider=provider, model=body.model, credential_scope=scope),
    )


@router.get("/models", response_model=ModelCatalogueResponse)
def read_model_catalogue(
    project: str | None = None,
    _session: Session = Depends(require_admin),
    config: AppConfig = Depends(get_app_config),
) -> ModelCatalogueResponse:
    """Every model the console can offer, grouped by provider.

    Admin-gated despite being a read: it is the catalogue for the one console
    action that spends money, and it reports which provider credentials are
    present. Presence only -- no endpoint returns a credential value.

    Admin-gated **only**, and deliberately the one route here without
    ``require_csrf``. The console's own ``apiFetch`` (``api/client.ts``)
    attaches ``X-CSRF-Token`` to unsafe methods only, so a browser GET never
    sends one and the guard would 403 every real request -- a permanently
    empty model picker. It would also defend nothing: CSRF protects
    state-changing requests, and this one returns presence booleans to a
    session that is already authenticated and already admin. ``require_admin``
    is the access control.
    """
    return build_catalogue(config, project)


@router.post("/prompts/{lang}/{agent}/plan", response_model=PromptPlanResponse)
def plan_prompt_save(
    lang: str,
    agent: str,
    body: PromptSaveRequest,
    request: Request,
    _session: Session = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    config: AppConfig = Depends(get_app_config),
) -> PromptPlanResponse:
    """What saving *body* would write and remove, without touching anything.

    Mirrors the PUT exactly, refusals included: the dialog has to show what the
    save will really do, and a plan that downgraded a 422 into a list would be
    describing a different operation from the one the operator is about to
    confirm (design D8).
    """
    prompts_dir = _require_prompts_dir(config)
    path = resolve_prompt_file(prompts_dir, lang, Path(agent) / "prompt.yaml")
    _refuse_orphaned_variants(agent, body, Path(request.app.state.config_path))

    plan = build_write_set(body, path, prompts_dir)
    return PromptPlanResponse(
        created=sorted(str(p) for p in plan.creates),
        updated=sorted(str(p) for p in plan.writes if p not in plan.creates),
        deleted=[str(p) for p in plan.deletes],
        deletions_skipped=plan.deletions_skipped,
    )


@router.put("/prompts/{lang}/{agent}", response_model=PromptSaveResponse)
def save_prompt(
    lang: str,
    agent: str,
    body: PromptSaveRequest,
    request: Request,
    _session: Session = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    config: AppConfig = Depends(get_app_config),
    _log: Session = Depends(bind_log_user),
    _lock: None = Depends(hold_write_lock),
) -> PromptSaveResponse:
    """Validate and write the prompt document and its templates."""
    prompts_dir = _require_prompts_dir(config)
    path = resolve_prompt_file(prompts_dir, lang, Path(agent) / "prompt.yaml")

    _refuse_orphaned_variants(agent, body, Path(request.app.state.config_path))

    plan = build_write_set(body, path, prompts_dir)
    result = write_all(dict(plan.writes), deletes=plan.deletes)
    return PromptSaveResponse(
        written=[str(p) for p in result.written],
        created=[str(p) for p in result.created],
        deleted=[str(p) for p in result.deleted],
        deletions_skipped=plan.deletions_skipped,
        backups=[str(p) for p in result.backups.values()],
    )


@router.post("/prompts/{lang}/{agent}/fork", response_model=PromptForkResponse)
async def fork_prompt(
    lang: str,
    agent: str,
    body: PromptForkRequest,
    request: Request,
    session: Session = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    config: AppConfig = Depends(get_app_config),
    _log: Session = Depends(bind_log_user),
    _lock: None = Depends(hold_write_lock),
) -> PromptForkResponse:
    """Copy a prompt for one project and point that project at the copy.

    The copied files land BEFORE the proposed config is validated, and that
    ordering is forced rather than chosen: ``validate_config_dict`` builds an
    ``AppConfig``, and ``validate_prompt_paths`` refuses a ``prompt.file`` that
    is not on disk -- so validating first would reject every fork, including
    the correct ones.

    What still holds, and what the rollback is for: nothing OUTSIDE the new
    fork directory is written until the configuration validates, and the
    directory is removed if either the validation or the config write fails.
    Removing it is a true undo rather than a best-effort one, because every
    file in it is new -- there is no previous content that could fail to be
    restored.

    A narrow TOCTOU sits between ``build_fork``'s own ``target_dir.exists()``
    check and the ``mkdir(exist_ok=True)`` below: if another process creates
    and populates that same directory in the interval, this request's rollback
    (on a later failure) removes files it did not create, plus their
    ``.bak`` siblings. Admin-only and extremely narrow -- documented here
    rather than locked against.
    """
    prompts_dir = _require_prompts_dir(config)

    try:
        config_key = join_path(["projects", body.project, "agents", agent, "prompt", "file"])
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid project name: {e}"
        ) from e

    known_projects = set(config.projects) | {ref.name for ref in session.projects}
    if body.project not in known_projects:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"{body.project!r} is not a known project. It must be visible in the "
                "TestBench project list or already have an entry in the configuration."
            ),
        )

    source = resolve_prompt_file(prompts_dir, lang, Path(agent) / "prompt.yaml")
    config_path = Path(request.app.state.config_path)

    plan = build_fork(prompts_dir, source, lang, agent, body.directory, body.project)
    edits = {config_key: plan.config_value}

    plan.target_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = write_all(dict(plan.files))
    except HTTPException:
        rollback_fork((), plan.target_dir)
        raise

    try:
        preview, proposed_text, _has_write = plan_change(edits, config_path, config)
        if not preview.valid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": "The fork would produce a configuration the service cannot load.",
                    "issues": [issue.model_dump() for issue in preview.issues],
                },
            )
        backup = write_atomic(config_path, proposed_text)
    except HTTPException:
        rollback_fork(result.written, plan.target_dir)
        raise

    if preview.restart_required:
        reloaded = False
        reload_detail: str | None = (
            "Forked, but the configuration on disk has changes that need a restart: "
            + ", ".join(preview.restart_required)
        )
    else:
        reloaded, reload_detail = await _reload_after_fork(request.app, config_path)

    return PromptForkResponse(
        lang=lang,
        agent=plan.agent_dir,
        file=f"{lang}/{plan.agent_dir}/prompt.yaml",
        created=[str(p) for p in result.written],
        config_backup=str(backup) if backup is not None else None,
        reloaded=reloaded,
        reload_detail=reload_detail,
    )


async def _reload_after_fork(app: FastAPI, config_path: Path) -> tuple[bool, str | None]:
    """Take up the config a fork just wrote: whether it reloaded, and why not."""
    try:
        on_disk = read_config_file(config_path)
    except HTTPException as e:
        logger.error("Forked, but could not re-read %s: %s", config_path, e.detail)
        return False, (
            f"Forked, but could not re-read the configuration to verify the reload: {e.detail}"
        )

    reloaded_config, issues = validate_config_dict(on_disk)
    if reloaded_config is None:
        logger.error("Forked and wrote %s but could not reload it: %s", config_path, issues)
        reasons = "; ".join(issue.message for issue in issues)
        return False, f"Forked, but the configuration failed re-validation before reload: {reasons}"

    reloaded_config.loaded_from = config_path
    if await hot_reload(app, reloaded_config):
        return True, None
    return False, (
        "Forked, but the in-process reload completed with degraded results; "
        "check the service log if it is currently writable."
    )


def _require_prompts_dir(config: AppConfig) -> Path:
    if config.prompts_dir is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No prompts directory is configured",
        )
    return Path(config.prompts_dir)


def _refuse_orphaned_variants(agent: str, body: PromptSaveRequest, config_path: Path) -> None:
    """Refuse a save that would leave a config key naming a variant that is gone.

    ``get_prompt_variant`` falls back to ``default_variant`` on a miss, so an
    orphaned reference is a wrong-output bug with no error anywhere. Repointing
    the agent means writing ``config.toml`` in the same transaction, which is
    phase 4b's fork work -- so 4a refuses and names what to fix.
    """
    on_disk = read_config_file(config_path)
    surviving = {variant.name for variant in body.variants}
    orphaned = [ref for ref in variant_references(agent, on_disk) if ref.variant not in surviving]
    if not orphaned:
        return

    where = "; ".join(f"{ref.variant!r} in {ref.label()}" for ref in orphaned)
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            f"This save would remove a variant that is still in use: {where}. "
            "Point the agent at a different variant first, then rename or remove this one."
        ),
    )
