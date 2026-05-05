from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.agents.base import Agent
from testbench_ai_service.auth import AuthInfo, get_auth_info, validate_auth_token
from testbench_ai_service.config import AgentConfig, AppConfig
from testbench_ai_service.dependencies import (
    get_app_config,
    get_llm_factory,
    get_tb_connection,
)
from testbench_ai_service.exceptions import HTTPError
from testbench_ai_service.llm.factory import LLMFactory
from testbench_ai_service.log import logger
from testbench_ai_service.models.agent import TriggerAgentRequest, TriggerAgentResponse
from testbench_ai_service.models.testbench import GlobalHumanRole, ProjectRole
from testbench_ai_service.tasks import run_agent
from testbench_ai_service.utils.agent import build_execution_context
from testbench_ai_service.utils.config import agent_enabled, get_agent_config
from testbench_ai_service.utils.import_utils import load_class_from_path
from testbench_ai_service.utils.testbench import has_any_required_role

TRIGGER_AGENT_ROUTE_KWARGS: dict = {
    "response_model": TriggerAgentResponse,
    "status_code": status.HTTP_202_ACCEPTED,
    "responses": {
        403: {
            "model": HTTPError,
            "description": (
                "Forbidden\n\n"
                "You need at least one of the following roles to proceed:\n"
                "- Administrator\n"
                "- TestManager\n"
                "- TestDesigner"
            ),
        },
        404: {
            "model": HTTPError,
            "description": (
                "Not Found\n\n"
                "The action to trigger agent is not possible due to one of the following reasons:\n"
                "- Project with `project_name` not found.\n"
                "- Feature is disabled for project with `project_name`."
            ),
        },
        409: {
            "model": HTTPError,
            "description": "Conflict: The precheck failed.",
        },
    },
}


def load_agent(config: AgentConfig) -> Agent:
    """Instantiate an agent from the provided configuration.

    Args:
        config: The configuration for the agent.

    Returns:
        An instance of the agent.

    Raises:
        HTTPException: If the agent class cannot be imported.
    """
    try:
        agent_class = load_class_from_path(config.class_path)
        agent: Agent = agent_class()
        logger.debug(
            "Successfully loaded agent '%s' from class path '%s'",
            agent_class.__name__,
            config.class_path,
        )
        return agent
    except ImportError as e:
        logger.error(f"Failed to import agent class from '{config.class_path}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR) from e


async def trigger_agent_execution(
    agent_key: str,
    trigger_request: TriggerAgentRequest,
    background_tasks: BackgroundTasks,
    conn: TBConnection,
    llm_factory: LLMFactory,
    app_config: AppConfig,
    auth_info: AuthInfo,
) -> TriggerAgentResponse:
    """Execute the trigger flow shared by all agent endpoints.

    Resolves the execution context, verifies the agent is enabled for the project,
    checks that the caller holds at least one required role, runs the agent-specific
    precheck, and finally enqueues the agent as a background task.

    Args:
        agent_key:        The agent key (e.g. ``"test_case_set_reviewer"``).
        trigger_request:  The incoming trigger request body.
        background_tasks: FastAPI ``BackgroundTasks`` used to schedule ``run_agent``.
        conn:             Active TestBench connection.
        llm_factory:      Factory for obtaining the LLM client.
        app_config:       The application configuration.
        auth_info:        Validated authentication context for this request.

    Returns:
        ``TriggerAgentResponse`` with ``status="accepted"`` and any precheck warnings.

    Raises:
        HTTPException 404: If the agent is disabled for the resolved project.
        HTTPException 403: If the caller lacks all required roles.
        HTTPException 409: If the agent-specific precheck fails.
    """
    logger.debug(
        "trigger_agent_execution called for agent '%s', authenticated via %s",
        agent_key,
        auth_info.auth_type.value,
    )

    context = build_execution_context(agent_key, trigger_request, conn, app_config, auth_info)

    if not agent_enabled(agent_key, app_config, context.project_name):
        logger.debug(
            "Agent '%s' disabled for project '%s', returning 404 Not Found",
            agent_key,
            context.project_name,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    required_roles: list[GlobalHumanRole | ProjectRole] = [
        GlobalHumanRole.Administrator,
        ProjectRole.TestManager,
        ProjectRole.TestDesigner,
    ]
    if not has_any_required_role(conn, context.project_key, required_roles):
        logger.warning(
            "Access denied: User does not have any of the required roles for the agent '%s'",
            agent_key,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You need at least one of the following roles to proceed: {', '.join([role.value for role in required_roles])}",
        )

    agent_config = get_agent_config(agent_key, app_config, context.project_name)
    agent = load_agent(agent_config)

    precheck_result = await agent.precheck(context, conn)
    logger.debug("Precheck result for agent '%s': %s", agent_key, precheck_result)

    if not precheck_result.passed:
        logger.debug("Conflict: The precheck failed for agent '%s'.", agent_key)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Conflict: The precheck failed."
        )

    background_tasks.add_task(
        run_agent,
        agent_key=agent_key,
        agent=agent,
        context=context,
        conn=conn,
        llm_factory=llm_factory,
    )
    logger.debug("Scheduled background task for agent '%s'", agent_key)

    return TriggerAgentResponse(status="accepted", warnings=precheck_result.warnings)


def create_agent_router(agent_key: str, config: AgentConfig) -> APIRouter:
    router = APIRouter(
        tags=["Agents"],
        dependencies=[Depends(validate_auth_token)],
    )

    @router.post(
        config.endpoint_path,
        summary=config.summary,
        description=config.description,
        **TRIGGER_AGENT_ROUTE_KWARGS,
    )
    async def trigger_agent(
        trigger_request: TriggerAgentRequest,
        background_tasks: BackgroundTasks,
        conn: TBConnection = Depends(get_tb_connection),
        llm_factory: LLMFactory = Depends(get_llm_factory),
        app_config: AppConfig = Depends(get_app_config),
        auth_info: AuthInfo = Depends(get_auth_info),
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

    return router


def get_agent_routers(app_config: AppConfig) -> list[APIRouter]:
    """Create routers for all enabled agents based on the application configuration."""
    routers = []
    for agent_key, agent_config in app_config.agents.items():
        if not agent_config.enabled:
            logger.debug("Agent '%s' is disabled in config, skipping router creation", agent_key)
            continue
        logger.debug("Creating router for enabled agent '%s'", agent_key)
        router = create_agent_router(agent_key, agent_config)
        routers.append(router)
    return routers
