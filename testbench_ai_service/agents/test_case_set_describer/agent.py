import asyncio
from typing import ClassVar

import requests
from testbench2robotframework.json_reader import TestCaseSet
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.agents.base import Agent
from testbench_ai_service.agents.test_case_set_describer.utils import (
    get_description_for_test_case_set,
    get_test_case_set_as_string,
    patch_description_generation_started_for_test_structure_element,
    patch_generated_description_for_test_structure_element,
    patch_previous_description_for_test_structure_element,
)
from testbench_ai_service.config import LLMConfig, PromptConfig
from testbench_ai_service.exceptions import handle_requests_http_error
from testbench_ai_service.llm.base import LLMClient
from testbench_ai_service.log import logger
from testbench_ai_service.models.agent import (
    AgentResult,
    ExecutionContext,
    PrecheckResult,
)
from testbench_ai_service.models.testbench import ProjectRole, SpecStatus
from testbench_ai_service.utils.agent import check_test_case_set_is_locked
from testbench_ai_service.utils.prompt_utils import build_prompt, pretty_messages
from testbench_ai_service.utils.testbench import get_project_roles, get_test_case_set_catalog
from testbench_ai_service.utils.testbench_helpers import get_parameter_combinations_as_string


class TestCaseSetDescriber(Agent):
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
        project_roles = get_project_roles(conn, context.project_key)
        if context.element_type != "TESTCASESET":
            warnings.append("The selected element must be a TestCaseSet.")
            return PrecheckResult(passed=False, warnings=warnings)

        test_case_set = conn.get_project_test_case_set(context.project_key, context.tree_root_key)
        spec = test_case_set.get("spec") or {}
        _sufficient_roles = {ProjectRole.TestManager}

        if check_test_case_set_is_locked(conn, context, context.root_uid, "spec"):
            return PrecheckResult(passed=False, warnings=warnings)

        if _sufficient_roles.intersection(project_roles):
            return PrecheckResult(passed=True, warnings=warnings)

        if ProjectRole.TestDesigner in project_roles:
            responsible = (spec.get("responsible") or {}).get("key")
            if responsible == context.user_key or responsible is None:
                return PrecheckResult(passed=True, warnings=warnings)

        return PrecheckResult(passed=False, warnings=warnings)

    async def run(
        self,
        context: ExecutionContext,
        conn: TBConnection,
        llm_client: LLMClient,
    ) -> None:
        """Generates descriptions for all test case sets concurrently."""
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
    ) -> AgentResult:
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

        return AgentResult(result=description)
