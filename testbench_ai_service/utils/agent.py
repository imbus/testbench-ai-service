import re

import requests
from fastapi import HTTPException, status
from jwt import DecodeError, decode
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.auth import AuthInfo, AuthType
from testbench_ai_service.config import AppConfig
from testbench_ai_service.exceptions import handle_requests_http_error
from testbench_ai_service.log import logger
from testbench_ai_service.models.agent import ElementType, ExecutionContext, TriggerAgentRequest
from testbench_ai_service.models.testbench import (
    PermissionWithCode,
    TestCaseSetNode,
    TestStructureItemExecution,
    TestStructureItemSpecification,
    TestStructureTree,
)
from testbench_ai_service.utils.config import (
    get_language_from_config,
    get_llm_config,
    get_prompt_config,
)
from testbench_ai_service.utils.testbench import (
    get_project_name,
    get_test_structure_tree,
    post_project_cycle_structure,
    post_project_tov_structure,
)


def _extract_jwt_scope(token: str) -> tuple[str, str, str | None]:
    """Decode a JWT and extract the TestBench project / TOV / cycle keys from its scope.

    Returns:
        A ``(project_key, tov_key, cycle_key)`` tuple where ``cycle_key`` may
        be ``None`` when the token was issued without one.

    Raises:
        HTTPException 401: If the token cannot be decoded or the scope payload
            is missing or does not contain the required keys.
    """
    try:
        token_info = decode(token, options={"verify_signature": False})
    except DecodeError as e:
        logger.warning("Invalid JWT token: %s", e)
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

    project_key: str | None = scope.get("proj")
    tov_key: str | None = scope.get("tov")
    cycle_key: str | None = scope.get("ccl")

    if not project_key or not tov_key:
        logger.warning("Invalid JWT token scope: missing required project or test object keys")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization token",
        )

    return project_key, tov_key, cycle_key


def build_execution_context(
    agent_key: str,
    trigger_request: TriggerAgentRequest,
    conn: TBConnection,
    app_config: AppConfig,
    auth_info: AuthInfo,
) -> ExecutionContext:
    """Build a fully-resolved ``ExecutionContext`` from a trigger request and auth context.

    For JWT-authenticated requests the project / TOV / cycle keys are extracted
    from the token's scope claim; for session-token requests they are taken from
    the request body.  In both cases ``filtering`` is forwarded from the request.

    The ``user_key`` is taken directly from ``auth_info`` — it was already
    fetched during token validation and cached there, so no additional
    TestBench API call is needed here.

    Args:
        agent_key:       Agent key (e.g. ``"test_case_set_reviewer"``).
        trigger_request: Incoming trigger request body.
        conn:            Active TestBench connection for project-name lookup.
        app_config:      Application configuration.
        auth_info:       Validated auth context produced by ``get_auth_info``.

    Returns:
        A fully-populated ``ExecutionContext`` ready for use by the agent
        and background tasks.

    Raises:
        HTTPException 401: JWT scope is missing or malformed.
        HTTPException 404: Project key does not resolve to a known project.
    """
    if auth_info.auth_type == AuthType.JWT_TOKEN:
        project_key, tov_key, cycle_key = _extract_jwt_scope(auth_info.token)
    else:
        project_key = trigger_request.project_key
        tov_key = trigger_request.tov_key
        cycle_key = trigger_request.cycle_key

    try:
        project_name = get_project_name(conn, project_key)
    except Exception as e:
        logger.info("Resource not found in TestBench Server: %s", e)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    language = trigger_request.language or get_language_from_config(app_config, project_name)

    llm_config = get_llm_config(
        config=app_config,
        project_name=project_name,
        request_config=trigger_request.llm_config,
    )
    prompt_config = get_prompt_config(
        agent_key=agent_key,
        config=app_config,
        project_name=project_name,
        request_config=trigger_request.prompt_config,  # type: ignore[arg-type]
        language=language,
    )

    return ExecutionContext(
        user_key=auth_info.user_key,
        project_name=project_name,
        project_key=project_key,
        tov_key=tov_key,
        cycle_key=cycle_key,
        root_uid=trigger_request.root_uid,
        root_key=trigger_request.root_key,
        element_type=trigger_request.element_type,
        tree_type=trigger_request.tree_type,
        filtering=trigger_request.filtering,
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
    test_structure_tree = fetch_test_structure_tree(conn, context, uniqueID)

    return is_test_case_locked_by_user(test_structure_tree, context, tab)


def is_test_case_locked_by_user(
    test_structure_tree: TestStructureTree, context: ExecutionContext, tab: str
):
    tab_object: TestStructureItemSpecification | TestStructureItemExecution = getattr(  # type: ignore[assignment]
        test_structure_tree.root, tab, None
    )
    if tab_object is not None and tab_object.locker is not None:
        return tab_object.locker.key != context.user_key
    return False


def has_required_permissions(
    required_permissions: set[PermissionWithCode],
    token_perms: list[int],
) -> bool:
    token_perm_set = set(token_perms)
    return all(perm.value in token_perm_set for perm in required_permissions)


def fetch_test_structure_tree(
    conn: TBConnection, context: ExecutionContext, uniqueID: str
) -> TestStructureTree:
    try:
        test_structure_tree = get_test_structure_tree(
            conn=conn,
            project_key=context.project_key,
            tov_key=context.tov_key,
            cycle_key=context.cycle_key,
            root_uid=uniqueID,
            filtering=context.filtering,
        )
    except requests.exceptions.HTTPError as e:
        handle_requests_http_error(e)
    except requests.exceptions.ConnectionError as e:
        logger.error("Could not connect to TestBench server: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not connect to TestBench server: {e!s}",
        ) from e

    return test_structure_tree


def get_test_case_nodes(context: ExecutionContext, conn: TBConnection):
    if context.element_type == ElementType.TESTCASESET:
        data = conn.get_project_test_case_set(context.project_key, context.root_key)
        exec_data = data.get("exec")
        node = TestCaseSetNode(
            base={
                "key": context.root_key,
                "numbering": "",
                "parentKey": "",
                "name": "",
                "uniqueID": data["uniqueID"],
                "matchesFilter": True,
            },
            exec={
                "key": exec_data["key"],
                "status": exec_data["status"],
                "execStatus": exec_data["execStatus"],
                "verdict": exec_data["verdict"],
            }
            if exec_data
            else None,
        )
        tc_nodes = [node]

    elif context.element_type == ElementType.TESTTHEME:
        if context.cycle_key:
            test_case = post_project_cycle_structure(
                conn,
                context.project_key,
                context.cycle_key,
                context.root_uid,
                context.filtering,
            )
        else:
            test_case = post_project_tov_structure(
                conn,
                context.project_key,
                context.cycle_key,
                context.root_uid,
                context.filtering,
            )
        tc_nodes = [
            node for node in test_case.nodes if re.match(r"^iTB-TC-\d+$", node.base.uniqueID)
        ]

    else:
        tc_nodes = []
    return tc_nodes
