import tempfile
import zipfile
from io import BytesIO

from pydantic import TypeAdapter
from testbench2robotframework.json_reader import TestBenchJsonReader, TestCaseSet
from testbench_cli_reporter.config_model import ExecutionMode, TestCycleJsonReportOptions
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.models.testbench import (
    CycleStructureOptions,
    GlobalHumanRole,
    ProjectMember,
    ProjectRole,
    SpecificationDetailsForUpdate,
    TestStructureTree,
    TovStructureOptions,
)


def get_user_key(conn: TBConnection) -> str:
    login_data = conn.session.get(f"{conn.server_url}2/login/session").json()
    return login_data["userKey"]  # type: ignore[no-any-return]


def get_project_name(conn: TBConnection, project_key: str) -> str:
    project = conn.get_project(project_key)
    return project["name"]  # type: ignore[no-any-return]


def get_json_report_data(
    conn: TBConnection, project_key: str, tov_key: str, cycle_key: str | None, root_uid: str | None
) -> bytes:
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
            filters=None,
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
    report_dir: str,
) -> TestBenchJsonReader:
    report_data = get_json_report_data(conn, project_key, tov_key, cycle_key, root_uid)
    report_zip = zipfile.ZipFile(BytesIO(report_data))
    report_zip.extractall(report_dir)
    return TestBenchJsonReader(report_dir)


def get_test_case_set_catalog(
    conn: TBConnection, project_key: str, tov_key: str, cycle_key: str | None, root_uid: str | None
) -> dict[str, TestCaseSet]:
    with tempfile.TemporaryDirectory() as report_dir:
        report_reader = get_json_report_reader(
            conn, project_key, tov_key, cycle_key, root_uid, report_dir
        )
        test_case_set_catalog: dict[str, TestCaseSet] = report_reader.get_test_case_set_catalog()
        return test_case_set_catalog


def post_project_cycle_structure(
    conn: TBConnection, project_key: str, cycle_key: str, root_uid: str | None = None
) -> TestStructureTree:
    structure_dict = conn.session.post(
        f"{conn.server_url}2/projects/{project_key}/cycles/{cycle_key}/structure",
        json=CycleStructureOptions(treeRootUID=root_uid).model_dump(exclude_unset=True),
    ).json()
    return TestStructureTree(**structure_dict)


def post_project_tov_structure(
    conn: TBConnection, project_key: str, tov_key: str, root_uid: str | None = None
) -> TestStructureTree:
    structure_dict = conn.session.post(
        f"{conn.server_url}2/projects/{project_key}/tovs/{tov_key}/structure",
        json=TovStructureOptions(treeRootUID=root_uid).model_dump(exclude_unset=True),
    ).json()
    return TestStructureTree(**structure_dict)


def get_test_structure_tree(
    conn: TBConnection,
    project_key: str,
    tov_key: str,
    cycle_key: str | None = None,
    root_uid: str | None = None,
) -> TestStructureTree:
    if cycle_key is not None:
        return post_project_cycle_structure(conn, project_key, cycle_key, root_uid)
    return post_project_tov_structure(conn, project_key, tov_key, root_uid)


async def patch_test_structure_element_spec(
    conn: TBConnection,
    project_key: str,
    spec_key: str,
    spec_update: SpecificationDetailsForUpdate,
):
    return conn.session.patch(
        f"{conn.server_url}2/projects/{project_key}/specifications/{spec_key}",
        json=spec_update.model_dump(exclude_unset=True),
    ).json()


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


def get_project_roles(conn: TBConnection, project: str) -> list[ProjectRole]:
    project_memberships = get_own_project_memberships(conn)
    membership = next(
        (membership for membership in project_memberships if membership.projectKey == project),
        None,
    )
    return membership.roles if membership else []


def has_any_required_role(
    conn: TBConnection, project: str, required_roles: list[GlobalHumanRole | ProjectRole]
) -> bool:
    """
    Checks if user in connection has any of the required roles for a project.

    Returns: `True` if the user has at least one required role, else `False`.
    """
    global_roles = get_own_global_roles(conn)
    project_roles = get_project_roles(conn, project)
    all_roles = global_roles + project_roles
    return bool(set(all_roles) & set(required_roles))
