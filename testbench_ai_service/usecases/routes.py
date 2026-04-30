from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.auth import AuthInfo, get_auth_info, validate_auth_token
from testbench_ai_service.config import AppConfig, UseCaseConfig
from testbench_ai_service.dependencies import (
    get_app_config,
    get_llm_factory,
    get_tb_connection,
)
from testbench_ai_service.exceptions import HTTPError
from testbench_ai_service.llm.factory import LLMFactory
from testbench_ai_service.log import logger
from testbench_ai_service.models.testbench import GlobalHumanRole, ProjectRole
from testbench_ai_service.models.usecase import TriggerUseCaseRequest, TriggerUseCaseResponse
from testbench_ai_service.tasks import run_usecase
from testbench_ai_service.usecases.base import UseCase
from testbench_ai_service.utils.config import get_usecase_config, usecase_enabled
from testbench_ai_service.utils.import_utils import load_class_from_path
from testbench_ai_service.utils.testbench import has_any_required_role
from testbench_ai_service.utils.usecase import build_execution_context

TRIGGER_USECASE_ROUTE_KWARGS: dict = {
    "response_model": TriggerUseCaseResponse,
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
                "The action to trigger use case is not possible due to one of the following reasons:\n"
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


def create_usecase_service(config: UseCaseConfig) -> UseCase:
    """Instantiate a usecase service based on the provided configuration.

    Args:
        config: The configuration for the usecase

    Returns:
        An instance of the UseCase service

    Raises:
        HTTPException: If the usecase class cannot be imported.
    """
    try:
        usecase_class = load_class_from_path(config.class_path)
        usecase_service: UseCase = usecase_class()
        logger.debug(
            "Successfully instantiated usecase service '%s' from class path '%s'",
            usecase_class.__name__,
            config.class_path,
        )
        return usecase_service
    except ImportError as e:
        logger.error(f"Failed to import usecase class from '{config.class_path}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR) from e


async def trigger_usecase_execution(
    usecase: str,
    trigger_request: TriggerUseCaseRequest,
    background_tasks: BackgroundTasks,
    conn: TBConnection,
    llm_factory: LLMFactory,
    app_config: AppConfig,
    auth_info: AuthInfo,
) -> TriggerUseCaseResponse:
    """Execute the trigger flow shared by all usecase endpoints.

    Resolves the execution context, verifies the usecase is enabled for the project,
    checks that the caller holds at least one required role, runs the usecase-specific
    precheck, and finally enqueues the usecase as a background task.

    Args:
        usecase:          The usecase key (e.g. ``"test_case_set_reviews"``).
        trigger_request:  The incoming trigger request body.
        background_tasks: FastAPI ``BackgroundTasks`` used to schedule ``run_usecase``.
        conn:             Active TestBench connection.
        llm_factory:      Factory for obtaining the LLM client.
        app_config:       The application configuration.
        auth_info:        Validated authentication context for this request.

    Returns:
        ``TriggerUseCaseResponse`` with ``status="accepted"`` and any precheck warnings.

    Raises:
        HTTPException 404: If the usecase is disabled for the resolved project.
        HTTPException 403: If the caller lacks all required roles.
        HTTPException 409: If the usecase-specific precheck fails.
    """
    logger.debug(
        "trigger_usecase_execution called for usecase '%s', authenticated via %s",
        usecase,
        auth_info.auth_type.value,
    )

    context = build_execution_context(usecase, trigger_request, conn, app_config, auth_info)

    if not usecase_enabled(usecase, app_config, context.project_name):
        logger.debug(
            "Usecase '%s' disabled for project '%s', returning 404 Not Found",
            usecase,
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
            "Access denied: User does not have any of the required roles for the usecase '%s'",
            usecase,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You need at least one of the following roles to proceed: {', '.join([role.value for role in required_roles])}",
        )

    usecase_config = get_usecase_config(usecase, app_config, context.project_name)
    usecase_service = create_usecase_service(usecase_config)

    precheck_result = await usecase_service.precheck(context, conn)
    logger.debug("Precheck result for usecase '%s': %s", usecase, precheck_result)

    if not precheck_result.passed:
        logger.debug("Conflict: The precheck failed for usecase '%s'.", usecase)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Conflict: The precheck failed."
        )

    background_tasks.add_task(
        run_usecase,
        usecase=usecase,
        usecase_service=usecase_service,
        context=context,
        conn=conn,
        llm_factory=llm_factory,
        items=precheck_result.items,
    )
    logger.debug("Scheduled background task for usecase '%s'", usecase)

    return TriggerUseCaseResponse(status="accepted", warnings=precheck_result.warnings)


def create_usecase_router(usecase: str, config: UseCaseConfig) -> APIRouter:
    router = APIRouter(
        tags=["Usecases"],
        dependencies=[Depends(validate_auth_token)],
    )

    @router.post(
        config.endpoint_path,
        summary=config.summary,
        description=config.description,
        **TRIGGER_USECASE_ROUTE_KWARGS,
    )
    async def trigger_usecase(
        trigger_request: TriggerUseCaseRequest,
        background_tasks: BackgroundTasks,
        conn: TBConnection = Depends(get_tb_connection),
        llm_factory: LLMFactory = Depends(get_llm_factory),
        app_config: AppConfig = Depends(get_app_config),
        auth_info: AuthInfo = Depends(get_auth_info),
    ) -> TriggerUseCaseResponse:
        return await trigger_usecase_execution(
            usecase=usecase,
            trigger_request=trigger_request,
            background_tasks=background_tasks,
            conn=conn,
            llm_factory=llm_factory,
            app_config=app_config,
            auth_info=auth_info,
        )

    return router


def get_usecase_routers(app_config: AppConfig) -> list[APIRouter]:
    """Create routers for all enabled use cases based on the application configuration."""
    routers = []
    for usecase_key, usecase_config in app_config.usecases.items():
        if not usecase_config.enabled:
            logger.debug(
                "Usecase '%s' is disabled in config, skipping router creation", usecase_key
            )
            continue
        logger.debug("Creating router for enabled usecase '%s'", usecase_key)
        router = create_usecase_router(usecase_key, usecase_config)
        routers.append(router)
    return routers
