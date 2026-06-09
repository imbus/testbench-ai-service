import asyncio

import requests
from testbench2robotframework.json_reader import TestCaseSet
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.agents.base import Agent
from testbench_ai_service.agents.test_case_set_describer.utils import (
    patch_description_generation_started_for_test_structure_element,
    patch_generated_description_for_test_structure_element,
    patch_previous_description_for_test_structure_element,
)
from testbench_ai_service.exceptions import handle_requests_http_error
from testbench_ai_service.llm.base import LLMClient
from testbench_ai_service.log import logger
from testbench_ai_service.models.agent import (
    AgentData,
    ExecutionContext,
    PrecheckResult,
)
from testbench_ai_service.models.testbench import (
    PermissionWithCode,
    ProjectRole,
)
from testbench_ai_service.utils.html_utils import strip_html_body_tags
from testbench_ai_service.utils.i18n import get_translation
from testbench_ai_service.utils.testbench import (
    get_test_case_set_catalog,
    get_test_case_set_nodes,
)
from testbench_ai_service.utils.testbench_helpers import (
    parameter_combinations_as_str,
    test_case_set_as_str,
)


class TestCaseSetDescriberAgentData(AgentData):
    test_case_set: str
    parameter_combinations: str | None
    test_case_set_obj: TestCaseSet


class TestCaseSetDescriber(Agent):
    AGENT_DATA_CLASS = TestCaseSetDescriberAgentData
    REQUIRED_PERMISSIONS = frozenset(
        {
            PermissionWithCode.ReadOwnUserDetails,
            PermissionWithCode.ReadProjectDetails,
            PermissionWithCode.ReadTovReport,
            PermissionWithCode.ReadCycleReport,
            PermissionWithCode.ReadReportingJobDetails,
            PermissionWithCode.DownloadReportFile,
            PermissionWithCode.ReadTestThemeTree,
            PermissionWithCode.ReadTestCaseSetDetails,
            PermissionWithCode.ModifySpecifications,
            PermissionWithCode.ModifySpecManagementInfo,
        }
    )
    ALLOWED_ROLES = frozenset(
        {
            ProjectRole.TestManager,
            ProjectRole.TestDesigner,
        }
    )

    async def precheck(
        self,
        context: ExecutionContext,
        conn: TBConnection,
    ) -> PrecheckResult:
        """
        Precheck to determine which test case sets the agent should describe, based on the user's permissions and roles.
        """
        warnings = []

        if not context.tov_key:
            msg = get_translation("shared.precheck.missing_tov_key", context.language)
            warnings.append(msg)
            return PrecheckResult(passed=False, warnings=warnings)

        tcs_nodes = get_test_case_set_nodes(conn, context)

        items = []
        for node in tcs_nodes:
            locked_by_other_user = (
                node.spec is not None
                and node.spec.locker is not None
                and node.spec.locker.key != context.user_key
            )
            if locked_by_other_user:
                msg = get_translation(
                    "shared.precheck.spec_locked", context.language, uid=node.base.uniqueID
                )
                warnings.append(msg)
                continue

            items.append(node.base.uniqueID)

        if items:
            return PrecheckResult(passed=True, warnings=warnings, items=items)

        return PrecheckResult(passed=False, warnings=warnings)

    async def run(
        self,
        context: ExecutionContext,
        conn: TBConnection,
        llm_client: LLMClient,
        item_ids: list[str],
    ) -> None:
        """Generates descriptions for all test case sets concurrently."""
        if not item_ids:
            logger.debug("No test case sets to describe, skipping run execution.")
            return
        if not context.tov_key:
            logger.debug("Missing tov_key in context, skipping run execution.")
            return

        test_case_set_catalog = {}
        try:
            test_case_set_catalog = get_test_case_set_catalog(
                conn=conn,
                project_key=context.project_key,
                tov_key=context.tov_key,
                cycle_key=context.cycle_key,
                root_uid=context.root_uid,
                filtering=context.filtering,
            )
            logger.debug("Retrieved test case sets: %s", list(test_case_set_catalog.keys()))
        except requests.exceptions.HTTPError as e:
            handle_requests_http_error(e)

        tasks = []
        for tcs in test_case_set_catalog.values():
            if tcs.details.uniqueID in item_ids:
                task = asyncio.create_task(
                    self._generate_test_case_set_description(tcs, context, conn, llm_client)
                )
                logger.debug("Scheduled task for test_case_set '%s'", tcs.details.uniqueID)
                tasks.append(task)

        logger.debug("Awaiting completion of %d description generation task(s)", len(tasks))
        await asyncio.gather(*tasks)

    async def _generate_test_case_set_description(
        self,
        test_case_set: TestCaseSet,
        context: ExecutionContext,
        conn: TBConnection,
        llm_client: LLMClient,
    ) -> None:
        """Generates a description for a single test case set."""
        try:
            previous_description = strip_html_body_tags(test_case_set.details.spec.description)
            try:
                logger.debug(
                    "Sending PATCH request to mark description generation started for test case set '%s'",
                    test_case_set.details.uniqueID,
                )
                await patch_description_generation_started_for_test_structure_element(
                    conn=conn,
                    project_key=context.project_key,
                    spec_key=test_case_set.details.spec.key,
                    previous_description=previous_description,
                    language=context.language,
                    user_key=context.user_key,
                )
                logger.debug(
                    "Patched description generation started for test case set '%s'",
                    test_case_set.details.uniqueID,
                )

                agent_data = self._build_agent_data(test_case_set=test_case_set)
                logger.debug(
                    "Built agent data for test case set '%s': %s",
                    test_case_set.details.uniqueID,
                    list(agent_data.keys()),
                )

                description_response = await self.get_ai_response(
                    llm_client, context.llm_config, context.prompt_config, agent_data
                )
                logger.debug(
                    "AI description response for test case set '%s':\n\t%s",
                    test_case_set.details.uniqueID,
                    description_response.result,
                )

                logger.debug(
                    "Sending PATCH request to add generated description for test case set '%s'",
                    test_case_set.details.uniqueID,
                )
                await patch_generated_description_for_test_structure_element(
                    conn=conn,
                    project_key=context.project_key,
                    spec_key=test_case_set.details.spec.key,
                    description=description_response.result,
                    previous_description=previous_description,
                    language=context.language,
                    user_key=context.user_key,
                )
                logger.debug(
                    "Patched generated description for test case set '%s'",
                    test_case_set.details.uniqueID,
                )
            except Exception as e:
                logger.debug(
                    "Execution of description generation failed for test case set '%s': %s",
                    test_case_set.details.uniqueID,
                    str(e),
                )

                logger.debug(
                    "Sending PATCH request to restore previous description for test case set '%s'",
                    test_case_set.details.uniqueID,
                )
                await patch_previous_description_for_test_structure_element(
                    conn=conn,
                    project_key=context.project_key,
                    spec_key=test_case_set.details.spec.key,
                    previous_description=previous_description,
                    language=context.language,
                    user_key=context.user_key,
                )
                logger.debug(
                    "Patched previous description for test case set '%s'",
                    test_case_set.details.uniqueID,
                )

                raise e

        except Exception as e:
            logger.error(
                "generate_test_case_set_description_task failed | test_case_set='%s' | data=%s | error=%r",
                test_case_set.details.uniqueID,
                context.model_dump_json(),
                str(e),
            )
            raise e

    def _build_agent_data(self, test_case_set: TestCaseSet) -> TestCaseSetDescriberAgentData:
        return {
            "test_case_set": test_case_set_as_str(test_case_set),
            "parameter_combinations": parameter_combinations_as_str(test_case_set),
            "test_case_set_obj": test_case_set,
        }
