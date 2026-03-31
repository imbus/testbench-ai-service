import asyncio
from typing import Any

import requests
from testbench2robotframework.json_reader import TestCaseSet
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.config import LLMConfig, PromptConfig
from testbench_ai_service.exceptions import handle_requests_http_error
from testbench_ai_service.llm.base import LLMClient
from testbench_ai_service.log import logger
from testbench_ai_service.models.usecase import ExecutionContext, PrecheckResult, UseCaseResult
from testbench_ai_service.usecases.base import UseCase
from testbench_ai_service.usecases.defect_explanations.utils import (
    add_error_message,
    add_explanations_to_comment,
    clean_up_comment,
    get_error_message,
    get_test_case_set_as_string,
    update_description,
)
from testbench_ai_service.utils.prompt_utils import build_prompt, pretty_messages
from testbench_ai_service.utils.testbench import get_test_case_set_catalog
from testbench_ai_service.utils.usecase import check_test_case_set_is_locked


class DefectExplainer(UseCase):
    async def precheck(
        self,
        context: ExecutionContext,
        conn: TBConnection,
    ) -> PrecheckResult[TestCaseSet]:
        """
        Fetches the TCS catalog and checks that exec is unlocked and cycle_key is set.
        """
        warnings = []
        items: list[TestCaseSet] = []

        if context.cycle_key is None:
            return PrecheckResult(
                passed=False,
                warnings=["Defect explanations require a cycle_key to be set."],
            )

        test_case_set_catalog = {}
        try:
            test_case_set_catalog = get_test_case_set_catalog(
                conn=conn,
                project_key=context.project_key,
                tov_key=context.tov_key,
                cycle_key=context.cycle_key,
                root_uid=context.root_uid,
            )
            logger.debug("Retrieved test case sets: %s", list(test_case_set_catalog.keys()))
        except requests.exceptions.HTTPError as e:
            handle_requests_http_error(e)

        for tcs_uid, tcs in test_case_set_catalog.items():
            if not check_test_case_set_is_locked(conn, context, tcs.details.uniqueID, "exec"):
                items.append(tcs)
            else:
                warning = f"The Test Structure Element with UID '{tcs.details.uniqueID}' could not be locked."
                warnings.append(warning)
                logger.debug("Precheck failed for '%s': %s", tcs_uid, warning)

        logger.debug(
            "Precheck completed: %d/%d test case sets are ready for defect explanation generation",
            len(items),
            len(test_case_set_catalog),
        )
        return PrecheckResult(passed=bool(items), items=items, warnings=warnings)

    async def run(
        self,
        context: ExecutionContext,
        conn: TBConnection,
        llm_client: LLMClient,
        items: list[TestCaseSet],
    ) -> None:
        """Generates defect explanations for all test case sets concurrently."""
        tasks = []
        for tcs in items:
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
            results = {}

            failed_test_cases = get_error_message(test_case_set.details.exec.comments)
            logger.debug(
                "Extracted error messages of the failed test cases for test case set '%s'",
                test_case_set.details.uniqueID,
            )

            logger.debug(
                "Start generating a defect explanation for every failed test case of test case set '%s': %s",
                test_case_set.details.uniqueID,
                list(failed_test_cases.keys()),
            )
            results = []
            queue = asyncio.Queue()

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
                        queue,
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
            await asyncio.gather(*tasks)

            while not queue.empty():
                results.append(await queue.get())

            if results != {}:
                comment = clean_up_comment(test_case_set.details.exec.comments)
                updated_comment = add_explanations_to_comment(comment, results, context.language)
                logger.debug(
                    "Built updated comment with defect explanations for test case set '%s'",
                    test_case_set.details.uniqueID,
                )

                update_description(updated_comment, test_case_set, conn, context)

        except Exception as e:
            comment = clean_up_comment(test_case_set.details.exec.comments)
            comment = add_error_message(comment, context.language)
            update_description(comment, test_case_set, conn, context)
            logger.error(
                "generate_defect_explanations_task failed | test_case_set='%s' | data=%s | error=%r",
                test_case_set.details.uniqueID,
                context.model_dump_json(),
                str(e),
            )
            raise e

    def _build_placeholder_data(
        self, test_case_set: TestCaseSet, test_case: str, error: dict
    ) -> dict[str, Any]:
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
        queue: asyncio.Queue,
    ) -> None:
        placeholder_data = prompt_config.placeholder_data or {}
        built_placeholder_data = self._build_placeholder_data(
            test_case_set=test_case_set,
            test_case=failed_test_case,
            error=details,
        )
        placeholder_data = built_placeholder_data | placeholder_data
        prompt_config = prompt_config.model_copy(update={"placeholder_data": placeholder_data})
        logger.debug(
            "Built placeholder data for failed test case '%s' of test case set '%s': %s",
            failed_test_case,
            test_case_set.details.uniqueID,
            prompt_config.placeholder_data,
        )

        explanation_response = await self._get_ai_response(
            llm_client=llm_client, llm_config=llm_config, prompt_config=prompt_config
        )
        logger.debug(
            "AI explanation response for failed test case '%s' of test case set '%s':\n\t%s",
            failed_test_case,
            test_case_set.details.uniqueID,
            explanation_response.result,
        )

        result = {
            "failed_test_case": failed_test_case,
            "error": details["error"],
            "explanation": explanation_response.result,
        }
        await queue.put(result)

    async def _get_ai_response(
        self,
        llm_client: LLMClient,
        llm_config: LLMConfig,
        prompt_config: PromptConfig,
    ) -> UseCaseResult:
        """Sends the prompt to the LLM and returns the defect explanation."""
        prompt = build_prompt(prompt_config=prompt_config)

        model = llm_config.model if llm_config.model is not None else prompt.model_name
        messages = prompt.messages

        logger.debug("Using model '%s' for the defect explanation", model)
        logger.debug(
            "Sending the following messages to the LLM for the defect explanation:\n %s",
            pretty_messages(messages),
        )

        explanation = await llm_client.query_llm(
            model=model, messages=messages, **llm_config.model_extra
        )

        return UseCaseResult(result=explanation)
