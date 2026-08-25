import time
from typing import get_type_hints

import requests
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.agents.base import Agent
from testbench_ai_service.auth import AuthInfo, AuthType, validate_auth_token
from testbench_ai_service.config import AppConfig
from testbench_ai_service.dependencies import (
    get_app_config,
    get_llm_factory,
    get_tb_connection,
)
from testbench_ai_service.exceptions import (
    TRANSPORT_ERRORS,
    HTTPError,
    handle_requests_http_error,
    handle_requests_transport_error,
)
from testbench_ai_service.llm.factory import LLMFactory
from testbench_ai_service.log import logger
from testbench_ai_service.models.agent import (
    TriggerAgentRequest,
    TriggerAgentResponse,
)
from testbench_ai_service.models.config import AgentConfig
from testbench_ai_service.models.prompt import PromptDefinition
from testbench_ai_service.tasks import run_agent
from testbench_ai_service.utils.agent import build_execution_context, has_required_permissions
from testbench_ai_service.utils.config import agent_enabled, get_agent_config, get_prompt_config
from testbench_ai_service.utils.i18n import get_translation
from testbench_ai_service.utils.import_utils import load_class_from_path
from testbench_ai_service.utils.prompt_utils import (
    get_prompt_definition,
    get_prompt_variant,
    template_variables,
    validate_agent_variable,
    validate_template_placeholders,
)
from testbench_ai_service.utils.testbench import get_project_roles

TRIGGER_AGENT_ROUTE_KWARGS: dict = {
    "response_model": TriggerAgentResponse,
    "status_code": status.HTTP_202_ACCEPTED,
    "responses": {
        403: {
            "model": HTTPError,
            "description": "Forbidden",
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

    agent_config = get_agent_config(agent_key, app_config, context.project_name)
    agent = load_agent(agent_config)

    if auth_info.auth_type == AuthType.JWT_TOKEN and not has_required_permissions(
        auth_info.token, agent.REQUIRED_PERMISSIONS
    ):
        msg = get_translation("routes.error.insufficient_permissions", context.language)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg)

    if agent.ALLOWED_ROLES is not None:
        project_roles = set(get_project_roles(conn, context.project_key))
        if project_roles.isdisjoint(agent.ALLOWED_ROLES):
            sorted_roles = sorted(agent.ALLOWED_ROLES, key=lambda r: (type(r).__name__, r.value))
            translated_roles = [
                get_translation(f"roles.{role.name}", context.language) for role in sorted_roles
            ]
            msg = get_translation(
                "routes.error.insufficient_role",
                context.language,
                allowed_roles="\n".join([f"• {role}" for role in translated_roles]),
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg)

    validate_template_and_agent_vars(context, agent)
    precheck_start_time = time.perf_counter()
    try:
        precheck_result = await agent.precheck(context, conn)
    except requests.exceptions.HTTPError as e:
        handle_requests_http_error(e)
    except TRANSPORT_ERRORS as e:
        handle_requests_transport_error(e)
    precheck_duration = time.perf_counter() - precheck_start_time
    logger.debug(
        "Precheck completed for agent '%s': passed=%s, items=%d in %.3f seconds",
        agent_key,
        precheck_result.passed,
        len(precheck_result.items),
        precheck_duration,
    )
    logger.debug("Precheck result for agent '%s': %s", agent_key, precheck_result)

    if not precheck_result.passed:
        logger.debug("Conflict: The precheck failed for agent '%s'.", agent_key)
        precheck_failed_msg = get_translation("routes.error.precheck_failed", context.language)
        warnings_text = "\n".join(precheck_result.warnings)
        if warnings_text:
            detail = f"{precheck_failed_msg.removesuffix('.')}:\n{warnings_text}"
        else:
            detail = precheck_failed_msg
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )

    background_tasks.add_task(
        run_agent,
        agent_key=agent_key,
        agent=agent,
        context=context,
        conn=conn,
        llm_factory=llm_factory,
        item_ids=precheck_result.items,
    )
    logger.debug("Scheduled background task for agent '%s'", agent_key)

    return TriggerAgentResponse(status="accepted", warnings=precheck_result.warnings)


def validate_template_and_agent_vars(context, agent):
    prompt_file = context.prompt_config.file
    prompt_template_variables = template_variables(prompt_file=prompt_file)
    agent_variables = get_type_hints(agent.AGENT_DATA_CLASS).keys()
    variant = get_prompt_variant(get_prompt_definition(prompt_file), context.prompt_config.variant)

    variant_variables: set[str] = set(variant.vars.keys())
    required_variant_variables: set[str] = {
        var for var, content in variant.vars.items() if content.required
    }

    template_var_keys = set(prompt_template_variables)

    is_valid_agent = validate_agent_variable(template_var_keys, agent_variables)

    if not is_valid_agent:
        error_detail = ""
        error_msg = f"Agent variable validation failed for '{prompt_file}'. Details: {error_detail}"

        logger.error(error_msg)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=error_msg)

    is_valid_template, template_errors = validate_template_placeholders(
        template_variables=template_var_keys,
        variant_variables=variant_variables,
        required_variables=required_variant_variables,
    )

    if not is_valid_template:
        error_detail = " | ".join(template_errors)
        error_msg = (
            f"Template placeholder validation failed for '{prompt_file}'. Details: {error_detail}"
        )

        logger.error(error_msg)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=error_msg)


def create_agent_router(
    agent_key: str,
    config: AgentConfig,
    prompt_definition: PromptDefinition | None = None,
) -> APIRouter:
    router = APIRouter(
        tags=["Agents"],
        dependencies=[Depends(validate_auth_token)],
    )

    @router.post(
        config.endpoint_path,
        summary=prompt_definition.summary if prompt_definition else None,
        description=prompt_definition.description if prompt_definition else None,
        **TRIGGER_AGENT_ROUTE_KWARGS,
    )
    async def trigger_agent(
        trigger_request: TriggerAgentRequest,
        background_tasks: BackgroundTasks,
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

    return router


def get_agent_routers(app_config: AppConfig) -> list[APIRouter]:
    """Create routers for all enabled agents based on the application configuration."""
    routers = []
    for agent_key, agent_config in app_config.agents.items():
        if not agent_config.enabled:
            logger.debug("Agent '%s' is disabled in config, skipping router creation", agent_key)
            continue
        logger.debug("Creating router for enabled agent '%s'", agent_key)
        try:
            prompt_config = get_prompt_config(agent_key, app_config)
            prompt_def = get_prompt_definition(prompt_config.file)
        except Exception:
            prompt_def = None
        router = create_agent_router(agent_key, agent_config, prompt_def)
        routers.append(router)
    return routers
