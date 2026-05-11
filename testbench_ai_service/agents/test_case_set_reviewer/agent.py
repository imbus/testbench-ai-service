import asyncio
from typing import ClassVar

import requests
from jwt import decode
from testbench2robotframework.json_reader import TestCaseSet
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.agents.base import Agent, AgentData
from testbench_ai_service.agents.test_case_set_reviewer.utils import (
    get_review_comment_for_test_case_set,
    get_test_case_set_as_string,
    patch_previous_review_comment_for_test_structure_element,
    patch_review_result_for_test_structure_element,
    patch_review_started_for_test_structure_element,
)
from testbench_ai_service.auth import AuthInfo, AuthType
from testbench_ai_service.config import LLMConfig, PromptConfig
from testbench_ai_service.exceptions import handle_requests_http_error
from testbench_ai_service.llm.base import LLMClient
from testbench_ai_service.log import logger
from testbench_ai_service.models.agent import (
    AgentResult,
    ExecutionContext,
    PrecheckResult,
)
from testbench_ai_service.models.testbench import PermissionWithCode, ProjectRole, SpecStatus
from testbench_ai_service.utils.agent import (
    check_test_case_set_is_locked,
    get_test_case_nodes,
    has_required_permissions,
)
from testbench_ai_service.utils.prompt_utils import build_prompt, pretty_messages
from testbench_ai_service.utils.string_processor import extract_text_from_html_body
from testbench_ai_service.utils.testbench import (
    get_project_roles,
    get_test_case_set_catalog,
)
from testbench_ai_service.utils.testbench_helpers import (
    get_parameter_combinations_as_string,
)


class TestCaseSetReviewerAgentData(AgentData, total=False):
    test_case: str
    parameter_combinations: str | None
    test_case_set_description: str | None
    test_case_set_obj: TestCaseSet


class TestCaseSetReviewer(Agent):
    GENERATED_PLACEHOLDERS: ClassVar[frozenset[str]] = frozenset(
        {
            "parameter_combinations",
            "test_case",
            "test_case_set_description",
            "test_case_set_obj",
        }
    )

    async def precheck(  # noqa: C901
        self,
        context: ExecutionContext,
        conn: TBConnection,
        auth_info: AuthInfo,
    ) -> PrecheckResult[TestCaseSet]:
        """
        Fetches the test case set catalog and checks that each spec tab is unlocked.
        """
        warnings = []
        requierd_permissions = {
            PermissionWithCode.AccessSecuredData,
            PermissionWithCode.ReadOwnUserDetails,
            PermissionWithCode.ReadProjectDetails,
            PermissionWithCode.ReadCycleReport,
            PermissionWithCode.ReadReportingJobDetails,
            PermissionWithCode.DownloadReportFile,
            PermissionWithCode.ReadTestThemeTree,
            PermissionWithCode.ReadTestCaseSetDetails,
            PermissionWithCode.ModifySpecifications,
            PermissionWithCode.ReadTestThemeDetails,
        }

        if auth_info.auth_type == AuthType.JWT_TOKEN:
            token_info = decode(auth_info.token, options={"verify_signature": False})
            token_perms = token_info.get("perms", [])
            if not has_required_permissions(requierd_permissions, token_perms):
                warnings.append("Insufficient permissions in JWT token.")
                return PrecheckResult(passed=False, warnings=warnings)

        tc_nodes = get_test_case_nodes(context, conn)

        project_roles = get_project_roles(conn, context.project_key)
        _sufficient_roles = {ProjectRole.TestManager}
        items = []

        for node in tc_nodes:
            test_case_set = conn.get_project_test_case_set(context.project_key, node.base.key)
            spec = test_case_set.get("spec") or {}

            if check_test_case_set_is_locked(conn, context, test_case_set.get("uniqueID"), "spec"):
                warnings.append(
                    f"The test case set specification is currently locked (uid='{node.base.uniqueID}')."
                )
                continue

            if _sufficient_roles.intersection(project_roles):
                items.append(node.base.uniqueID)
            elif ProjectRole.TestDesigner in project_roles:
                responsible = (spec.get("responsible") or {}).get("key")
                is_responsible = responsible == context.user_key or responsible is None
                if is_responsible:
                    items.append(node.base.uniqueID)
            elif ProjectRole.Tester in project_roles or ProjectRole.TestProgrammer in project_roles:
                is_in_review = spec.get("status", "") == SpecStatus.InReview.value
                is_current_reviewer = (spec.get("reviewer") or {}).get(
                    "key", ""
                ) == context.user_key
                if is_in_review and is_current_reviewer:
                    items.append(node.base.uniqueID)
            else:
                warnings.append("Insufficient project role to perform a review.")

        if items:
            return PrecheckResult(passed=True, warnings=warnings, items=items)

        return PrecheckResult(passed=False, warnings=warnings)

    async def run(
        self,
        context: ExecutionContext,
        conn: TBConnection,
        llm_client: LLMClient,
        precheck_results: list[str] | None,
    ) -> None:
        """Reviews all test case sets concurrently."""
        if not precheck_results:
            return
        tasks = []
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
        for tcs in test_case_set_catalog.values():
            if tcs.details.uniqueID in precheck_results:
                task = asyncio.create_task(
                    self._review_test_case_set(tcs, context, conn, llm_client)
                )
                logger.debug("Scheduled task for test_case_set '%s'", tcs.details.uniqueID)
                tasks.append(task)

        logger.debug("Awaiting completion of %d test case set review task(s)", len(tasks))
        await asyncio.gather(*tasks)

    async def _review_test_case_set(
        self,
        test_case_set: TestCaseSet,
        context: ExecutionContext,
        conn: TBConnection,
        llm_client: LLMClient,
    ) -> None:
        """Performs a review for a single test case set."""
        try:
            tcs_key = test_case_set.details.key
            tcs_spec_key = test_case_set.details.spec.key

            previous_review_comment = await get_review_comment_for_test_case_set(
                conn=conn, project_key=context.project_key, test_case_set_key=tcs_key
            )
            try:
                logger.debug(
                    "Sending PATCH request to mark review started for test case set '%s'",
                    test_case_set.details.uniqueID,
                )
                await patch_review_started_for_test_structure_element(
                    conn=conn,
                    project_key=context.project_key,
                    spec_key=tcs_spec_key,
                    previous_review_comment=previous_review_comment,
                    language=context.language,
                    user_key=context.user_key,
                )
                logger.debug(
                    "Patched review started for test case set '%s'",
                    test_case_set.details.uniqueID,
                )

                agent_data = self._build_agent_data(test_case_set=test_case_set)
                logger.debug(
                    "Built agent data for test case set '%s': %s",
                    test_case_set.details.uniqueID,
                    list(agent_data.keys()),
                )

                review_response = await self._get_ai_response(
                    llm_client, context.llm_config, context.prompt_config, agent_data
                )
                logger.debug(
                    "AI review response for test case set '%s':\n\t%s",
                    test_case_set.details.uniqueID,
                    review_response.result,
                )

                logger.debug(
                    "Sending PATCH request to add review result to review comment for test case set '%s'",
                    test_case_set.details.uniqueID,
                )
                await patch_review_result_for_test_structure_element(
                    conn=conn,
                    project_key=context.project_key,
                    spec_key=tcs_spec_key,
                    review_notes=review_response.result,
                    previous_review_comment=previous_review_comment,
                    language=context.language,
                    user_key=context.user_key,
                )
                logger.debug(
                    "Patched review result for test case set '%s'",
                    test_case_set.details.uniqueID,
                )
            except Exception as e:
                logger.debug(
                    "Execution of review failed for test case set '%s': %s",
                    test_case_set.details.uniqueID,
                    str(e),
                )

                logger.debug(
                    "Sending PATCH request to restore previous review comment for test case set '%s'",
                    test_case_set.details.uniqueID,
                )
                await patch_previous_review_comment_for_test_structure_element(
                    conn=conn,
                    project_key=context.project_key,
                    spec_key=tcs_spec_key,
                    previous_review_comment=previous_review_comment,
                    language=context.language,
                    user_key=context.user_key,
                )
                logger.debug(
                    "Patched previous review comment for test case set '%s'",
                    test_case_set.details.uniqueID,
                )

                raise e
        except Exception as e:
            logger.error(
                "review_test_case_set_task failed | test_case_set='%s' | data=%s | error=%r",
                test_case_set.details.uniqueID,
                context.model_dump_json(),
                str(e),
            )
            raise e

    def _build_agent_data(
        self,
        test_case_set: TestCaseSet,
    ) -> TestCaseSetReviewerAgentData:
        """Builds the agent-data dict (``agent.*`` namespace) for a single test case set."""
        data: TestCaseSetReviewerAgentData = {
            "test_case": get_test_case_set_as_string(test_case_set),
            "parameter_combinations": get_parameter_combinations_as_string(test_case_set),
            "test_case_set_obj": test_case_set,
        }

        if test_case_set.details.spec.description:
            data["test_case_set_description"] = extract_text_from_html_body(
                test_case_set.details.spec.description
            )

        return data

    async def _get_ai_response(
        self,
        llm_client: LLMClient,
        llm_config: LLMConfig,
        prompt_config: PromptConfig,
        agent_data: TestCaseSetReviewerAgentData | None = None,
    ) -> AgentResult:
        """Sends the prompt to the LLM and returns the review result."""
        prompt = build_prompt(prompt_config, agent_data=agent_data)

        model = llm_config.model if llm_config.model is not None else prompt.model_name
        messages = prompt.messages

        logger.debug("Using model '%s' for the test case set review", model)
        logger.debug(
            "Sending the following messages to the LLM for the test case set review: %s",
            pretty_messages(messages),
        )

        review_notes = await llm_client.query_llm(
            model=model, messages=messages, **(llm_config.model_extra or {})
        )

        return AgentResult(result=review_notes)
