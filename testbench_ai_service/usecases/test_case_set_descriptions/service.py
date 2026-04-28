import asyncio
from typing import ClassVar

import requests
from testbench2robotframework.json_reader import TestCaseSet
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.config import LLMConfig, PromptConfig
from testbench_ai_service.exceptions import handle_requests_http_error
from testbench_ai_service.llm.base import LLMClient
from testbench_ai_service.log import logger
from testbench_ai_service.models.usecase import (
    ExecutionContext,
    PrecheckResult,
    UseCaseResult,
)
from testbench_ai_service.usecases.base import UseCase
from testbench_ai_service.usecases.test_case_set_descriptions.utils import (
    get_description_for_test_case_set,
    get_test_case_set_as_string,
    patch_description_generation_started_for_test_structure_element,
    patch_generated_description_for_test_structure_element,
    patch_previous_description_for_test_structure_element,
)
from testbench_ai_service.utils.prompt_utils import build_prompt, pretty_messages
from testbench_ai_service.utils.testbench import get_test_case_set_catalog
from testbench_ai_service.utils.testbench_helpers import get_parameter_combinations_as_string
from testbench_ai_service.utils.usecase import check_test_case_set_is_locked


class TestCaseSetDescriber(UseCase):
    GENERATED_PLACEHOLDERS: ClassVar[frozenset[str]] = frozenset(
        {
            "parameter_combinations",
            "step_sequence",
            "test_case_set_obj",
        }
    )

    async def precheck(
        self,
        context: ExecutionContext,
        conn: TBConnection,
    ) -> PrecheckResult[TestCaseSet]:
        """
        Fetches the test case set catalog and checks that each spec tab is unlocked.
        """
        warnings = []
        items: list[TestCaseSet] = []

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
            if not check_test_case_set_is_locked(conn, context, tcs.details.uniqueID, "spec"):
                items.append(tcs)
            else:
                warning = f"The Test Structure Element with UID '{tcs.details.uniqueID}' could not be locked."
                warnings.append(warning)
                logger.debug("Precheck failed for '%s': %s", tcs_uid, warning)

        logger.debug(
            "Precheck completed: %d/%d test case sets are ready for description generation",
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
        """Generates descriptions for all test case sets concurrently."""
        tasks = []
        for tcs in items:
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
            tcs_key = test_case_set.details.key
            tcs_spec_key = test_case_set.details.spec.key

            previous_description = await get_description_for_test_case_set(
                conn=conn, project_key=context.project_key, test_case_set_key=tcs_key
            )
            try:
                logger.debug(
                    "Sending PATCH request to mark description generation started for test case set '%s'",
                    test_case_set.details.uniqueID,
                )
                await patch_description_generation_started_for_test_structure_element(
                    conn=conn,
                    project_key=context.project_key,
                    spec_key=tcs_spec_key,
                    previous_description=previous_description,
                    language=context.language,
                    user_key=context.user_key,
                )
                logger.debug(
                    "Patched description generation started for test case set '%s'",
                    test_case_set.details.uniqueID,
                )

                placeholder_data = context.prompt_config.placeholder_data or {}
                built_placeholder_data = self._build_placeholder_data(test_case_set=test_case_set)
                placeholder_data = built_placeholder_data | placeholder_data
                prompt_config = context.prompt_config.model_copy(
                    update={"placeholder_data": placeholder_data}
                )
                logger.debug(
                    "Built placeholder data for test case set '%s': %s",
                    test_case_set.details.uniqueID,
                    prompt_config.placeholder_data,
                )

                description_response = await self._get_ai_response(
                    llm_client, context.llm_config, prompt_config
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
                    spec_key=tcs_spec_key,
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
                    spec_key=tcs_spec_key,
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

    def _build_placeholder_data(self, test_case_set: TestCaseSet) -> dict[str, str]:
        return {
            "step_sequence": get_test_case_set_as_string(test_case_set),
            "parameter_combinations": get_parameter_combinations_as_string(test_case_set),
            "test_case_set_obj": test_case_set,
        }

    async def _get_ai_response(
        self,
        llm_client: LLMClient,
        llm_config: LLMConfig,
        prompt_config: PromptConfig,
    ) -> UseCaseResult:
        """Sends the prompt to the LLM and returns the generated description."""
        prompt = build_prompt(prompt_config=prompt_config)

        model = llm_config.model if llm_config.model is not None else prompt.model_name
        messages = prompt.messages

        logger.debug("Using model '%s' for the test case set description generation", model)
        logger.debug(
            "Sending the following messages to the LLM for the test case set description generation:\n%s",
            pretty_messages(messages),
        )

        description = await llm_client.query_llm(
            model=model, messages=messages, **(llm_config.model_extra or {})
        )

        return UseCaseResult(result=description)
