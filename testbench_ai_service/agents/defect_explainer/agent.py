import asyncio

import requests
from testbench2robotframework.json_reader import TestCaseSet
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.agents.base import Agent, AgentData
from testbench_ai_service.agents.defect_explainer.utils import (
    add_error_message,
    add_explanations_to_comment,
    clean_up_comment,
    get_error_message,
    get_test_case_set_as_string,
    update_description,
)
from testbench_ai_service.auth import AuthInfo, AuthType
from testbench_ai_service.config import LLMConfig, PromptConfig
from testbench_ai_service.exceptions import handle_requests_http_error
from testbench_ai_service.llm.base import LLMClient
from testbench_ai_service.log import logger
from testbench_ai_service.models.agent import AgentResult, ExecutionContext, PrecheckResult
from testbench_ai_service.models.testbench import (
    ActivityStatus,
    PermissionWithCode,
    ProjectRole,
    VerdictStatus,
)
from testbench_ai_service.utils.agent import (
    get_test_case_set_nodes,
    has_required_permissions,
)
from testbench_ai_service.utils.i18n import get_translation
from testbench_ai_service.utils.prompt_utils import build_prompt, pretty_messages
from testbench_ai_service.utils.testbench import (
    get_project_roles,
    get_test_case_set_catalog,
)


class DefectExplainerAgentData(AgentData):
    failed_test_case: str
    error_message: str


class DefectExplainer(Agent):
    REQUIRED_PERMISSIONS: frozenset[PermissionWithCode] = frozenset(
        {
            PermissionWithCode.ReadOwnUserDetails,
            PermissionWithCode.ReadProjectDetails,
            PermissionWithCode.ReadTovReport,
            PermissionWithCode.ReadCycleReport,
            PermissionWithCode.ReadReportingJobDetails,
            PermissionWithCode.DownloadReportFile,
            PermissionWithCode.ReadTestThemeTree,
            PermissionWithCode.ReadTestCaseSetDetails,
            PermissionWithCode.ImportExecutionResults,
            PermissionWithCode.ReadExecutionImportingJobDetails,
        }
    )
    ALLOWED_ROLES: frozenset[ProjectRole] = frozenset(
        {
            ProjectRole.TestManager,
            ProjectRole.Tester,
        }
    )

    async def precheck(
        self,
        context: ExecutionContext,
        conn: TBConnection,
        auth_info: AuthInfo,
    ) -> PrecheckResult:
        """
        Precheck to determine which test case sets the agent should explain defects for, based on the user's permissions and roles.
        """
        warnings = []

        if auth_info.auth_type == AuthType.JWT_TOKEN and not has_required_permissions(
            auth_info.token, self.REQUIRED_PERMISSIONS
        ):
            msg = get_translation(
                "defect_explainer.precheck.insufficient_permissions", context.language
            )
            warnings.append(msg)
            return PrecheckResult(passed=False, warnings=warnings)

        project_roles = set(get_project_roles(conn, context.project_key))
        if project_roles.isdisjoint(self.ALLOWED_ROLES):
            msg = get_translation("defect_explainer.precheck.insufficient_role", context.language)
            warnings.append(msg)
            return PrecheckResult(passed=False, warnings=warnings)

        tcs_nodes = get_test_case_set_nodes(conn, context)

        items = []
        for node in tcs_nodes:
            if node.exec is None:
                msg = get_translation(
                    "defect_explainer.precheck.no_execution_data",
                    context.language,
                    uid=node.base.uniqueID,
                )
                warnings.append(msg)
                continue

            if node.exec.verdict != VerdictStatus.ToVerify:
                msg = get_translation(
                    "defect_explainer.precheck.verdict_not_to_verify",
                    context.language,
                    uid=node.base.uniqueID,
                )
                warnings.append(msg)
                continue

            if node.exec.status != ActivityStatus.Performed:
                msg = get_translation(
                    "defect_explainer.precheck.execution_not_performed",
                    context.language,
                    uid=node.base.uniqueID,
                )
                warnings.append(msg)
                continue

            locked_by_other_user = (
                node.exec.locker is not None and node.exec.locker.key != context.user_key
            )
            if locked_by_other_user:
                msg = get_translation(
                    "defect_explainer.precheck.execution_locked",
                    context.language,
                    uid=node.base.uniqueID,
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
        """Generates defect explanations for all test case sets concurrently."""
        if not item_ids:
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
                    self._generate_defect_explanations(tcs, context, conn, llm_client)
                )
                logger.debug("Scheduled task for test_case_set '%s'", tcs.details.uniqueID)
                tasks.append(task)

        logger.debug("Awaiting completion of %d defect explanation generation task(s)", len(tasks))
        await asyncio.gather(*tasks)

    async def _generate_defect_explanations(
        self,
        test_case_set: TestCaseSet,
        context: ExecutionContext,
        conn: TBConnection,
        llm_client: LLMClient,
    ) -> None:
        """Generates explanations for all failed test cases in a single test case set."""
        try:
            failed_test_cases = get_error_message(test_case_set.details.exec.comments)
            logger.debug(
                "Extracted error messages of the failed test cases for test case set '%s'",
                test_case_set.details.uniqueID,
            )

            if not failed_test_cases:
                logger.debug(
                    "No failed test cases found for test case set '%s', skipping",
                    test_case_set.details.uniqueID,
                )
                return

            logger.debug(
                "Start generating a defect explanation for every failed test case of test case set '%s': %s",
                test_case_set.details.uniqueID,
                list(failed_test_cases.keys()),
            )

            tasks = []
            for failed_test_case, details in failed_test_cases.items():
                task = asyncio.create_task(
                    self._generate_explanation_for_failed_test_case(
                        test_case_set,
                        context.prompt_config,
                        details,
                        failed_test_case,
                        llm_client,
                        context.llm_config,
                    )
                )
                logger.debug(
                    "Scheduled explanation generation for failed test case '%s' of test case set '%s'",
                    failed_test_case,
                    test_case_set.details.uniqueID,
                )
                tasks.append(task)

            logger.debug(
                "Awaiting completion of explanation generation for all failed test cases of test case set '%s'",
                test_case_set.details.uniqueID,
            )
            results = list(await asyncio.gather(*tasks))

            if results:
                comment = clean_up_comment(test_case_set.details.exec.comments)
                updated_comment = add_explanations_to_comment(comment, results, context.language)
                logger.debug(
                    "Built updated comment with defect explanations for test case set '%s'",
                    test_case_set.details.uniqueID,
                )
                await update_description(updated_comment, test_case_set, conn, context)

        except Exception as e:
            comment = clean_up_comment(test_case_set.details.exec.comments)
            comment = add_error_message(comment, context.language)
            await update_description(comment, test_case_set, conn, context)
            logger.error(
                "generate_defect_explanations_task failed | test_case_set='%s' | data=%s | error=%r",
                test_case_set.details.uniqueID,
                context.model_dump_json(),
                str(e),
            )
            raise e

    def _build_agent_data(
        self, test_case_set: TestCaseSet, test_case: str, error: dict
    ) -> DefectExplainerAgentData:
        return {
            "failed_test_case": get_test_case_set_as_string(test_case_set, test_case),
            "error_message": error["error"],
        }

    async def _generate_explanation_for_failed_test_case(
        self,
        test_case_set: TestCaseSet,
        prompt_config: PromptConfig,
        details: dict,
        failed_test_case: str,
        llm_client: LLMClient,
        llm_config: LLMConfig,
    ) -> dict:
        agent_data = self._build_agent_data(
            test_case_set=test_case_set,
            test_case=failed_test_case,
            error=details,
        )
        logger.debug(
            "Built agent data for failed test case '%s' of test case set '%s': %s",
            failed_test_case,
            test_case_set.details.uniqueID,
            list(agent_data.keys()),
        )

        explanation_response = await self._get_ai_response(
            llm_client=llm_client,
            llm_config=llm_config,
            prompt_config=prompt_config,
            agent_data=agent_data,
        )
        logger.debug(
            "AI explanation response for failed test case '%s' of test case set '%s':\n\t%s",
            failed_test_case,
            test_case_set.details.uniqueID,
            explanation_response.result,
        )

        return {
            "failed_test_case": failed_test_case,
            "error": details["error"],
            "explanation": explanation_response.result,
        }

    async def _get_ai_response(
        self,
        llm_client: LLMClient,
        llm_config: LLMConfig,
        prompt_config: PromptConfig,
        agent_data: DefectExplainerAgentData | None = None,
    ) -> AgentResult:
        """Sends the prompt to the LLM and returns the defect explanation."""
        prompt = build_prompt(prompt_config=prompt_config, agent_data=agent_data)

        model = llm_config.model if llm_config.model is not None else prompt.model_name
        messages = prompt.messages

        logger.debug("Using model '%s' for the defect explanation", model)
        logger.debug(
            "Sending the following messages to the LLM for the defect explanation:\n %s",
            pretty_messages(messages),
        )

        explanation = await llm_client.query_llm(
            model=model, messages=messages, **(llm_config.model_extra or {})
        )

        return AgentResult(result=explanation)
