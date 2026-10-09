import asyncio
import re
import tempfile
import zipfile
from io import BytesIO

from pydantic import TypeAdapter
from testbench2robotframework.json_reader import TestBenchJsonReader, TestCaseSet
from testbench_cli_reporter.config_model import (
    ExecutionMode,
    FilterInfo,
    TestCycleJsonReportOptions,
)
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.models.agent import ElementType, ExecutionContext
from testbench_ai_service.models.testbench import (
    CycleStructureOptions,
    FilteringOptions,
    GlobalHumanRole,
    ProjectDetails,
    ProjectExchangeFormat,
    ProjectMember,
    ProjectRole,
    SpecificationDetailsForUpdate,
    TestCaseSetDetails,
    TestCaseSetNode,
    TestStructureTree,
    TOVDetails,
    TOVExchangeFormat,
    TovStructureOptions,
)

TEST_CASE_SET_UID = re.compile(r"-TC-\d+$")


def get_user_key(conn: TBConnection) -> str:
    login_data = conn.session.get(f"{conn.server_url}2/users/self").json()
    return login_data["key"]  # type: ignore[no-any-return]


def get_project_name(conn: TBConnection, project_key: str) -> str:
    project = conn.get_project(project_key)
    return project["name"]  # type: ignore[no-any-return]


def get_test_case_set_details(
    conn: TBConnection, project_key: str, test_case_set_key: str
) -> TestCaseSetDetails:
    tcs_dict = conn.get_project_test_case_set(project_key, test_case_set_key)
    return TestCaseSetDetails.model_validate(tcs_dict)


def get_json_report_data(
    conn: TBConnection,
    project_key: str,
    tov_key: str,
    cycle_key: str | None,
    root_uid: str | None,
    filtering: FilteringOptions | None = None,
) -> bytes:
    if filtering and filtering.appliedFilters:
        filters = [FilterInfo.from_dict(f.model_dump()) for f in filtering.appliedFilters]
    else:
        filters = None

    job_id = conn.trigger_json_report_generation(
        project_key,
        tov_key,
        cycle_key,
        report_config=TestCycleJsonReportOptions(
            treeRootUID=root_uid,
            basedOnExecution=True,
            suppressEmptyTestThemes=True,
            suppressFilteredData=True,
            suppressNotExecutable=False,
            executionMode=ExecutionMode.VIEW,
            filters=filters,
        ),
    )
    temp_name = conn.wait_for_tmp_json_report_name(project_key, job_id)
    return conn.get_json_report_data(project_key, temp_name)  # type: ignore[no-any-return]


def get_json_report_reader(
    conn: TBConnection,
    project_key: str,
    tov_key: str,
    cycle_key: str | None,
    root_uid: str | None,
    filtering: FilteringOptions | None,
    report_dir: str,
) -> TestBenchJsonReader:
    report_data = get_json_report_data(
        conn=conn,
        project_key=project_key,
        tov_key=tov_key,
        cycle_key=cycle_key,
        root_uid=root_uid,
        filtering=filtering,
    )
    report_zip = zipfile.ZipFile(BytesIO(report_data))
    report_zip.extractall(report_dir)
    return TestBenchJsonReader(report_dir)


def get_test_case_set_catalog(
    conn: TBConnection,
    project_key: str,
    tov_key: str,
    cycle_key: str | None,
    root_uid: str | None,
    filtering: FilteringOptions | None,
) -> dict[str, TestCaseSet]:
    with tempfile.TemporaryDirectory() as report_dir:
        report_reader = get_json_report_reader(
            conn=conn,
            project_key=project_key,
            tov_key=tov_key,
            cycle_key=cycle_key,
            root_uid=root_uid,
            filtering=filtering,
            report_dir=report_dir,
        )
        test_case_set_catalog: dict[str, TestCaseSet] = report_reader.get_test_case_set_catalog()
        return test_case_set_catalog


def post_project_cycle_structure(
    conn: TBConnection,
    project_key: str,
    cycle_key: str,
    root_uid: str | None = None,
    based_on_execution: bool = False,
    filtering: FilteringOptions | None = None,
) -> TestStructureTree:
    filters = filtering.appliedFilters if filtering else None
    structure_dict = conn.session.post(
        f"{conn.server_url}2/projects/{project_key}/cycles/{cycle_key}/structure",
        json=CycleStructureOptions(
            treeRootUID=root_uid, basedOnExecution=based_on_execution, filters=filters
        ).model_dump(exclude_unset=True),
    ).json()
    return TestStructureTree(**structure_dict)


def get_tov_details(conn: TBConnection, project_key: str, tov_key: str) -> TOVDetails:
    tov_details = conn.session.get(
        f"{conn.server_url}2/projects/{project_key}/tovs/{tov_key}",
    ).json()
    return TOVDetails(**tov_details)


def get_project_details(conn: TBConnection, project_key: str) -> ProjectDetails:
    project_details = conn.session.get(
        f"{conn.server_url}2/projects/{project_key}",
    ).json()
    return ProjectDetails(**project_details)


def post_project_tov_structure(
    conn: TBConnection,
    project_key: str,
    tov_key: str,
    root_uid: str | None = None,
    filtering: FilteringOptions | None = None,
) -> TestStructureTree:
    filters = filtering.appliedFilters if filtering else None
    structure_dict = conn.session.post(
        f"{conn.server_url}2/projects/{project_key}/tovs/{tov_key}/structure",
        json=TovStructureOptions(treeRootUID=root_uid, filters=filters).model_dump(
            exclude_unset=True
        ),
    ).json()
    return TestStructureTree(**structure_dict)


def get_test_structure_tree(
    conn: TBConnection,
    project_key: str,
    tov_key: str,
    cycle_key: str | None = None,
    root_uid: str | None = None,
    filtering: FilteringOptions | None = None,
) -> TestStructureTree:
    if cycle_key is not None:
        return post_project_cycle_structure(
            conn, project_key, cycle_key, root_uid=root_uid, filtering=filtering
        )
    return post_project_tov_structure(conn, project_key, tov_key, root_uid, filtering)


async def patch_test_structure_element_spec(
    conn: TBConnection,
    project_key: str,
    spec_key: str,
    spec_update: SpecificationDetailsForUpdate,
):
    url = f"{conn.server_url}2/projects/{project_key}/specifications/{spec_key}"
    body = spec_update.model_dump(exclude_unset=True)
    response = await asyncio.to_thread(conn.session.patch, url, json=body)
    return response.json()


def get_own_global_roles(conn: TBConnection) -> list[GlobalHumanRole]:
    global_roles = conn.session.get(
        f"{conn.server_url}2/users/self/globalRoles",
    ).json()
    return TypeAdapter(list[GlobalHumanRole]).validate_python(global_roles)


def get_own_project_memberships(conn: TBConnection) -> list[ProjectMember]:
    project_memberships = conn.session.get(
        f"{conn.server_url}2/users/self/projectRoles",
    ).json()
    return TypeAdapter(list[ProjectMember]).validate_python(project_memberships)


def get_project_roles(conn: TBConnection, project_key: str) -> list[ProjectRole]:
    project_memberships = get_own_project_memberships(conn)
    membership = next(
        (membership for membership in project_memberships if membership.projectKey == project_key),
        None,
    )
    return membership.roles if membership else []


def has_any_allowed_role(
    conn: TBConnection, project: str, allowed_roles: list[GlobalHumanRole | ProjectRole]
) -> bool:
    """
    Checks if user in connection has any of the allowed roles for a project.

    Returns: `True` if the user has at least one allowed role, else `False`.
    """
    global_roles = get_own_global_roles(conn)
    project_roles = get_project_roles(conn, project)
    all_roles = global_roles + project_roles
    return bool(set(all_roles) & set(allowed_roles))


def get_test_case_set_nodes(conn: TBConnection, context: ExecutionContext) -> list[TestCaseSetNode]:
    """Return the TestCaseSetNodes to process for the given execution context."""
    if not context.tov_key or context.element_type not in {
        ElementType.TESTCASESET,
        ElementType.TESTTHEME,
    }:
        return []

    structure = get_test_structure_tree(
        conn=conn,
        project_key=context.project_key,
        tov_key=context.tov_key,
        cycle_key=context.cycle_key,
        root_uid=context.root_uid,
        filtering=context.filtering,
    )

    if context.element_type == ElementType.TESTCASESET:
        return [structure.root] if isinstance(structure.root, TestCaseSetNode) else []

    return [
        node
        for node in structure.nodes
        if isinstance(node, TestCaseSetNode) and TEST_CASE_SET_UID.search(node.base.uniqueID)
    ]


def is_json_based_tov(conn: TBConnection, project_key: str, tov_key: str) -> bool:
    fetch_test_object_versions = get_tov_details(conn, project_key, tov_key)
    if fetch_test_object_versions.exchangeFormat == TOVExchangeFormat.json:
        return True
    return bool(
        fetch_test_object_versions.exchangeFormat == TOVExchangeFormat.inherited
        and get_project_details(conn, project_key).exchangeFormat
        == ProjectExchangeFormat.default_json
    )
