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
from testbench_ai_service.webui.catalogue import build_catalogue
from testbench_ai_service.webui.config_io import (
    build_config_response,
    read_config_file,
    redact_toml_text,
)
from testbench_ai_service.webui.diff import file_diff
from testbench_ai_service.webui.document import apply_edits, load_document, render_document
from testbench_ai_service.webui.edits import merge_edits, validate_edit_paths
from testbench_ai_service.webui.fork import build_fork, rollback_fork
from testbench_ai_service.webui.inflight import TaskRegistry, get_task_registry
from testbench_ai_service.webui.logs import MAX_LIMIT, read_log
from testbench_ai_service.webui.models import (
    ApplyResponse,
    ConfigEditsRequest,
    ConfigResponse,
    LintRequest,
    LintResponse,
    LoginRequest,
    LogLine,
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
    PromptTreeResponse,
    RenderRequest,
    RenderResponse,
    SessionResponse,
    StatusResponse,
)
from testbench_ai_service.webui.multi_write import write_all
from testbench_ai_service.webui.paths import join_path
from testbench_ai_service.webui.projects import (
    fetch_projects_with_token,
    projects_response,
    record_projects,
)
from testbench_ai_service.webui.prompt_refs import variant_references
from testbench_ai_service.webui.prompt_render import lint_template, render_messages
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
) -> tuple[PreviewResponse, str, bool]:
    """Work out what applying *edits* would do, without doing any of it.

    Returns the preview payload, the rendered TOML text, and whether there is
    anything to write, so ``apply`` can reuse exactly the text ``preview``
    showed rather than re-deriving it and risking a different result.

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
            False,
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

    # The DISPLAYED diff and the WRITE decision deliberately read different
    # texts. `diff` above is computed from the redacted before/after, because
    # that is what the operator is allowed to see. Whether there is anything
    # to write is decided from the RAW before/after instead: an overlay that
    # only changes a credential-named key (permitted -- LLMConfig declares
    # extra="allow") redacts to an identical before/after and would produce no
    # diff, which must not be read as "nothing to write" -- that would
    # silently discard the operator's change. Comparing the raw texts here
    # catches that case, and also the reverse: a mixed overlay must not be
    # treated as empty just because its *displayed* diff happens to be.
    has_write = current_text != proposed_text

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
        has_write,
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
    )
    record_projects(session, login.projects)
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
    return build_status(config, request.app.state.started_at, registry.count, pending)


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
        # There is no base directory to contain a request-supplied path
        # against, so the endpoint refuses to look rather than reading a path
        # relative to the process's working directory.
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


@router.get("/logs", response_model=list[LogLine])
async def read_logs(
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
    _: Session = Depends(current_session),
    config: AppConfig = Depends(get_app_config),
) -> list[LogLine]:
    """Tail the service log for the console's Status screen.

    Requires a session but not the admin role -- reading the log is open to
    everyone signed in; only ``preview``/``apply`` require the admin role.
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
    preview, _text, _has_write = _plan_change(
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

    ``validate_config_dict`` also refuses a ``logging.file.file_name`` the
    process could not open (see
    :func:`~testbench_ai_service.webui.validate._log_file_writability_issue`)
    -- without it, an operator could write a config the process cannot even
    boot with, since ``setup_logging`` builds the file handler at startup.
    That check runs before any write, same as every other validation issue.

    Once the write has committed, nothing that follows may turn it back into
    a non-2xx response: re-reading the file to verify the reload can itself
    fail (``read_config_file`` raises ``HTTPException`` on a decode error),
    and that is reported through ``reload_detail`` on a normal 200, not
    raised -- the write already succeeded and the response must say so.
    """
    config_path = Path(request.app.state.config_path)
    preview, proposed_text, has_write = _plan_change(body.edits, config_path, config)

    if not preview.valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "The configuration is not valid and was not written.",
                "issues": [issue.model_dump() for issue in preview.issues],
            },
        )

    if not has_write:
        # Nothing to do. Decided from the RAW texts (see `_plan_change`), not
        # from `preview.diffs`: the displayed diff is redacted and can be
        # empty while a credential-only change still needs writing. Writing
        # anyway when there is truly nothing to write would churn the .bak and
        # the mtime for an operator who changed their mind back.
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
    reload_detail: str | None = None
    if not needs_restart:
        # Re-read rather than reuse the candidate _plan_change built: what the
        # process takes up must be what is now on disk, so a discrepancy
        # between the document path and the dict path shows up here as a
        # logged error instead of as a process quietly running something the
        # file does not say.
        try:
            on_disk = read_config_file(config_path)
        except HTTPException as e:
            # The write already committed (write_atomic already returned).
            # Turning this into a raised 4xx would tell the operator the
            # apply failed when the file on disk is exactly what they asked
            # for; only the in-process verification could not complete.
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
                # Should be unreachable: the same dict validated moments ago. If it
                # happens, the file on disk is the one that is right and the
                # operator needs to know the process did not follow.
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
        # `used_by` is a labelling nicety; the tree itself is how an operator
        # reaches a broken prompt. An unreadable config must not cost them that.
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
    return read_prompt_document(path, prompts_dir, lang, agent)


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


@router.get("/models", response_model=ModelCatalogueResponse)
def read_model_catalogue(
    project: str | None = None,
    _session: Session = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    config: AppConfig = Depends(get_app_config),
) -> ModelCatalogueResponse:
    """Every model the console can offer, grouped by provider.

    Admin-gated despite being a read: it is the catalogue for the one console
    action that spends money, and it reports which provider credentials are
    present. Presence only -- no endpoint returns a credential value.
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
) -> PromptSaveResponse:
    """Validate and write the prompt document and its templates."""
    prompts_dir = _require_prompts_dir(config)
    path = resolve_prompt_file(prompts_dir, lang, Path(agent) / "prompt.yaml")

    # There is no `get_config_path` dependency: routes.py reads the path off
    # app.state, the way `read_config` and `read_prompt_metadata` already do.
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

    # The config key this fork would write, validated up front, before
    # build_fork or any existence check: join_path raises a bare ValueError
    # for a segment containing a NUL, and body.project is the only
    # unsanitised input that reaches it. Computing this AFTER mkdir/write_all
    # (as it once was) meant that ValueError propagated as a 500 with the
    # fork directory and its files already on disk and config.toml
    # untouched -- outside the rollback every later failure in this function
    # goes through. Checked before "is this project known" too: a malformed
    # name is a 400 regardless of whether it happens to also be unknown.
    try:
        config_key = join_path(["projects", body.project, "agents", agent, "prompt", "file"])
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid project name: {e}"
        ) from e

    # design 5.3 step 1 / §6: a fork naming a project neither TestBench nor
    # config.toml has ever heard of is a 404, not a config.toml write that
    # invents a brand-new [projects.<name>] section out of a typo. Checked
    # against the UNION of the session's cached TestBench project list and
    # the on-disk config's projects table -- never against config.toml alone
    # -- because a project's first-ever override is the common case, and
    # requiring it to already have a [projects.<name>] block would make a
    # fork impossible exactly when it is most wanted.
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

    # exist_ok=True: build_fork already refused an existing target_dir with a
    # 409 one line above; a fork racing in between would otherwise turn that
    # into an uncaught FileExistsError (500) instead of the same 409.
    plan.target_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = write_all(dict(plan.files))
    except HTTPException:
        # write_all rolls back the files it already staged/wrote, but the
        # directory itself is its caller's to clean up -- exactly what
        # rollback_fork's rmdir does. Without this, a write failure here
        # (disk full, a locked file) leaves an empty directory behind that
        # permanently blocks every future fork to this same target with a
        # 409, since build_fork refuses to fork into a directory that exists.
        rollback_fork((), plan.target_dir)
        raise

    try:
        preview, proposed_text, _has_write = _plan_change(edits, config_path, config)
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

    reloaded = False
    reload_detail: str | None = None
    try:
        on_disk = read_config_file(config_path)
    except HTTPException as e:
        # The write already committed (write_atomic already returned). Same
        # reasoning as apply_config: this is reported on the 200, never raised.
        logger.error("Forked, but could not re-read %s: %s", config_path, e.detail)
        reload_detail = (
            f"Forked, but could not re-read the configuration to verify the reload: {e.detail}"
        )
    else:
        reloaded_config, issues = validate_config_dict(on_disk)
        if reloaded_config is not None:
            reloaded_config.loaded_from = config_path
            reloaded = await hot_reload(request.app, reloaded_config)
            if not reloaded:
                reload_detail = (
                    "Forked, but the in-process reload completed with degraded results; "
                    "check the service log if it is currently writable."
                )
        else:
            # Should be unreachable: the same dict validated moments ago inside
            # _plan_change. If it happens, the file on disk is the one that is
            # right and the operator needs to know the process did not follow.
            logger.error("Forked and wrote %s but could not reload it: %s", config_path, issues)
            reasons = "; ".join(issue.message for issue in issues)
            reload_detail = (
                f"Forked, but the configuration failed re-validation before reload: {reasons}"
            )

    return PromptForkResponse(
        lang=lang,
        agent=plan.agent_dir,
        file=f"{lang}/{plan.agent_dir}/prompt.yaml",
        created=[str(p) for p in result.written],
        config_backup=str(backup) if backup is not None else None,
        reloaded=reloaded,
        reload_detail=reload_detail,
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
