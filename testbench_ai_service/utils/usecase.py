from fastapi import HTTPException, status
from jwt import decode
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.config import AppConfig
from testbench_ai_service.log import logger
from testbench_ai_service.models.testbench import (
    TestStructureItemExecution,
    TestStructureItemSpecification,
)
from testbench_ai_service.models.usecase import ExecutionContext, TriggerUseCaseRequest
from testbench_ai_service.utils.config import (
    get_language_from_config,
    get_llm_config,
    get_prompt_config,
)
from testbench_ai_service.utils.testbench import (
    get_project_name,
    get_test_structure_tree,
    get_user_key,
)


def build_execution_context_session_token(
    usecase: str,
    trigger_request: TriggerUseCaseRequest,
    conn: TBConnection,
    app_config: AppConfig,
) -> ExecutionContext:
    """
    Builds a fully-resolved ExecutionContext from a trigger request and app config.

    Resolves project info, language, LLM config and prompt config so that all
    downstream code (usecase service, tasks) operates on plain data without
    knowing about the request or the global config.
    """
    user_key = get_user_key(conn)

    try:
        project_name = get_project_name(conn, trigger_request.project_key)
    except Exception as e:
        logger.info(f"Resource not found in TestBench Server: {e!s}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    language, llm_config, prompt_config = build_usecase_execution_configs(
        usecase, trigger_request, app_config, project_name
    )

    return ExecutionContext(
        user_key=user_key,
        project_name=project_name,
        project_key=trigger_request.project_key,
        tov_key=trigger_request.tov_key,
        cycle_key=trigger_request.cycle_key,
        root_uid=trigger_request.root_uid,
        language=language,
        llm_config=llm_config,
        prompt_config=prompt_config,
    )


def build_usecase_execution_configs(usecase, trigger_request, app_config, project_name):
    language = trigger_request.language or get_language_from_config(app_config, project_name)

    llm_config = get_llm_config(
        config=app_config,
        project_name=project_name,
        request_config=trigger_request.llm_config,
    )
    prompt_config = get_prompt_config(
        usecase=usecase,
        config=app_config,
        project_name=project_name,
        request_config=trigger_request.prompt_config,  # type: ignore[arg-type]
        language=language,
    )

    return language, llm_config, prompt_config


def build_execution_context_jwt_token(
    usecase: str,
    trigger_request: TriggerUseCaseRequest,
    conn: TBConnection,
    app_config: AppConfig,
    token: str,
) -> ExecutionContext:
    """
    Builds a fully-resolved ExecutionContext from a trigger request and app config.

    Resolves project info, language, LLM config and prompt config so that all
    downstream code (usecase service, tasks) operates on plain data without
    knowing about the request or the global config.
    """
    user_key = get_user_key(conn)

    try:
        token_info = decode(token, options={"verify_signature": False})
    except Exception as e:
        logger.warning(f"Invalid JWT token: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization token",
        ) from e

    scope = token_info.get("scope")
    if not isinstance(scope, dict):
        logger.warning("Invalid JWT token scope: missing or malformed scope payload")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization token",
        )

    project_key = scope.get("proj")
    tov_key = scope.get("tov")
    cycle_key = scope.get("ccl")

    if not project_key or not tov_key:
        logger.warning("Invalid JWT token scope: missing required project or test object keys")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization token",
        )

    try:
        project_name = get_project_name(conn, project_key)
    except Exception as e:
        logger.info(f"Resource not found in TestBench Server: {e!s}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    language, llm_config, prompt_config = build_usecase_execution_configs(
        usecase, trigger_request, app_config, project_name
    )

    return ExecutionContext(
        user_key=user_key,
        project_name=project_name,
        project_key=project_key,
        tov_key=tov_key,
        cycle_key=cycle_key,
        root_uid=trigger_request.root_uid,
        language=language,
        llm_config=llm_config,
        prompt_config=prompt_config,
    )


def check_test_case_set_is_locked(
    conn: TBConnection, context: ExecutionContext, uniqueID: str, tab: str
) -> bool:
    """
    Returns True if the given test structure element tab is locked by a *different* user.
    Returns False if it is free or locked by the current user.
    """
    test_structure_tree = get_test_structure_tree(
        conn, context.project_key, context.tov_key, context.cycle_key, uniqueID
    )

    tab_object: TestStructureItemSpecification | TestStructureItemExecution = getattr(  # type: ignore[assignment]
        test_structure_tree.root, tab, None
    )
    if tab_object is not None and tab_object.locker is not None:
        return tab_object.locker.key != context.user_key
    return False
