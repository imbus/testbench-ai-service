import requests
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Path,
    Query,
    Request,
    status,
)
from fastapi.responses import RedirectResponse
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.agents.routes import (
    TRIGGER_AGENT_ROUTE_KWARGS,
    trigger_agent_execution,
)
from testbench_ai_service.auth import AuthInfo, validate_auth_token
from testbench_ai_service.config import AppConfig
from testbench_ai_service.dependencies import get_app_config, get_llm_factory, get_tb_connection
from testbench_ai_service.exceptions import handle_requests_http_error
from testbench_ai_service.llm.factory import LLMFactory
from testbench_ai_service.models.agent import (
    AgentDetailsResponse,
    TriggerAgentRequest,
    TriggerAgentResponse,
)
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.prompt import PromptDetailsResponse, PromptVariantResponse
from testbench_ai_service.utils.config import get_agent_config, get_prompt_config
from testbench_ai_service.utils.prompt_utils import get_prompt_definition
from testbench_ai_service.utils.testbench import get_project_name

router = APIRouter()


def _resolve_project_name(conn: TBConnection, project_key: str | None) -> str | None:  # type: ignore[return]
    """Resolve a project key to a project name.

    Returns ``None`` only when no project key was provided.
    """
    if project_key is None:
        return None
    try:
        return get_project_name(conn, project_key)
    except requests.exceptions.HTTPError as e:
        handle_requests_http_error(e)
    except requests.exceptions.ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not connect to TestBench server: {e!s}",
        ) from e


@router.get("/", include_in_schema=False)
async def redirect_to_docs(request: Request):
    return RedirectResponse(url=request.app.docs_url)


@router.get(
    "/agents",
    dependencies=[Depends(validate_auth_token)],
    response_model=list[AgentDetailsResponse],
)
async def get_agents(
    app_config: AppConfig = Depends(get_app_config),
    conn: TBConnection = Depends(get_tb_connection),
    keys: list[str] | None = Query(None, description="Filter by agent keys"),
    project_key: str | None = Query(None, description="Filter by project key"),
    language: LanguageOption | None = Query(None, description="Override language"),
    enabled: bool | None = Query(None, description="Filter by enabled status"),
) -> list[AgentDetailsResponse]:
    project_name = _resolve_project_name(conn, project_key)

    agents = []
    agent_keys = keys if keys is not None else app_config.agents.keys()
    for key in agent_keys:
        if key not in app_config.agents:
            continue
        config = get_agent_config(key, app_config, project_name)
        if enabled is not None and config.enabled != enabled:
            continue

        prompt_config = get_prompt_config(
            agent_key=key,
            config=app_config,
            project_name=project_name,
            language=language,
        )
        prompt_definition = get_prompt_definition(prompt_config.file)

        agents.append(
            AgentDetailsResponse(
                key=key,
                enabled=config.enabled,
                name=prompt_definition.name,
                summary=prompt_definition.summary,
                description=prompt_definition.description,
            )
        )

    return agents


@router.get(
    "/agents/{agent_key}",
    dependencies=[Depends(validate_auth_token)],
    response_model=AgentDetailsResponse,
)
async def get_agent_details(
    agent_key: str = Path(description="The agent key (e.g. 'test_case_set_reviewer')"),
    app_config: AppConfig = Depends(get_app_config),
    conn: TBConnection = Depends(get_tb_connection),
    project_key: str | None = Query(None, description="Filter by project key"),
    language: LanguageOption | None = Query(None, description="Override language"),
) -> AgentDetailsResponse:
    if agent_key not in app_config.agents:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_key}' not found")

    project_name = _resolve_project_name(conn, project_key)
    config = get_agent_config(agent_key, app_config, project_name)
    prompt_config = get_prompt_config(
        agent_key=agent_key,
        config=app_config,
        project_name=project_name,
        language=language,
    )
    prompt_definition = get_prompt_definition(prompt_config.file)

    return AgentDetailsResponse(
        key=agent_key,
        enabled=config.enabled,
        name=prompt_definition.name,
        summary=prompt_definition.summary,
        description=prompt_definition.description,
    )


@router.get(
    "/agents/{agent_key}/prompt",
    dependencies=[Depends(validate_auth_token)],
    response_model=PromptDetailsResponse,
)
async def get_prompt_details(
    agent_key: str = Path(description="The agent key (e.g. 'test_case_set_reviewer')"),
    app_config: AppConfig = Depends(get_app_config),
    conn: TBConnection = Depends(get_tb_connection),
    project_key: str | None = Query(None, description="Filter by project key"),
    language: LanguageOption | None = Query(None, description="Override language"),
) -> PromptDetailsResponse:
    """Returns available variants and their prompt variables."""
    if agent_key not in app_config.agents:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_key}' not found")

    project_name = _resolve_project_name(conn, project_key)
    prompt_config = get_prompt_config(
        agent_key=agent_key,
        config=app_config,
        project_name=project_name,
        language=language,
    )
    prompt_definition = get_prompt_definition(prompt_config.file)

    variants = [
        PromptVariantResponse(
            name=variant.name,
            description=variant.description,
            model=variant.model or prompt_definition.default_model,
            vars=variant.vars,
        )
        for variant in prompt_definition.variants
    ]

    return PromptDetailsResponse(
        name=prompt_definition.name,
        summary=prompt_definition.summary,
        description=prompt_definition.description,
        file=prompt_config.file,
        default_variant=prompt_config.variant or prompt_definition.default_variant,
        variants=variants,
    )


@router.post(
    "/agents/{agent_key}/trigger",
    dependencies=[Depends(validate_auth_token)],
    summary="Trigger an agent by key",
    description="Trigger an agent execution by providing the agent key and necessary parameters.",
    **TRIGGER_AGENT_ROUTE_KWARGS,
)
async def trigger_agent(
    trigger_request: TriggerAgentRequest,
    background_tasks: BackgroundTasks,
    agent_key: str = Path(description="The agent key (e.g. 'test_case_set_reviewer')"),
    conn: TBConnection = Depends(get_tb_connection),
    llm_factory: LLMFactory = Depends(get_llm_factory),
    app_config: AppConfig = Depends(get_app_config),
    auth_info: AuthInfo = Depends(validate_auth_token),
) -> TriggerAgentResponse:
    return await trigger_agent_execution(
        agent_key=agent_key,
        trigger_request=trigger_request,
        background_tasks=background_tasks,
        conn=conn,
        llm_factory=llm_factory,
        app_config=app_config,
        auth_info=auth_info,
    )
