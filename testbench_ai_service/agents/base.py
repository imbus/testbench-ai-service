from abc import ABC, abstractmethod
from typing import ClassVar

from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.llm.base import LLMClient
from testbench_ai_service.log import logger
from testbench_ai_service.models.agent import (
    AgentData,
    AgentResult,
    ExecutionContext,
    PrecheckResult,
)
from testbench_ai_service.models.config import LLMConfig, PromptConfig
from testbench_ai_service.models.testbench import GlobalHumanRole, PermissionWithCode, ProjectRole
from testbench_ai_service.utils.prompt_utils import build_prompt, pretty_messages


class Agent(ABC):
    REQUIRED_PERMISSIONS: ClassVar[frozenset[PermissionWithCode]] = frozenset()
    ALLOWED_ROLES: ClassVar[frozenset[GlobalHumanRole | ProjectRole] | None] = None

    @abstractmethod
    async def precheck(
        self,
        context: ExecutionContext,
        conn: TBConnection,
    ) -> PrecheckResult:
        """
        Validates prerequisites and collects the items ready for processing.

        Implementations fetch all domain-specific data (e.g. test case sets from
        TestBench), determine which items pass validation, and return them together
        with the aggregated summary.

        If no items pass validation, ``PrecheckResult.passed`` must be ``False``,
        which causes the router to return 409.  Per-item failure reasons should be
        collected in ``PrecheckResult.warnings``.

        Args:
            context: Fully-resolved execution context (project info, language,
                     LLM config, prompt config, …).
            conn:    TestBench connection for retrieving data.

        Returns:
            PrecheckResult containing the passed status, validated item IDs, and warnings.
        """

    @abstractmethod
    async def run(
        self,
        context: ExecutionContext,
        conn: TBConnection,
        llm_client: LLMClient,
        item_ids: list[str],
    ) -> None:
        """
        Executes the agent for all items that passed ``precheck()``.

        Implementations process each item (concurrently where appropriate).
        All domain-specific logic—prompt building, LLM calls, and TestBench
        write-back—lives here.

        Args:
            context:    Fully-resolved execution context.
            conn:       TestBench connection for retrieving and updating data.
            llm_client: Initialised LLM client ready to accept queries.
            item_ids:   The validated item IDs returned by ``precheck()``.
        """

    async def get_ai_response(
        self,
        llm_client: LLMClient,
        llm_config: LLMConfig,
        prompt_config: PromptConfig,
        agent_data: AgentData | None = None,
    ) -> AgentResult:
        """Sends the prompt to the LLM and returns the result."""
        prompt = build_prompt(prompt_config, agent_data=agent_data)

        model = llm_config.model if llm_config.model is not None else prompt.model_name
        messages = prompt.messages

        logger.debug("Using model '%s'.", model)
        logger.debug(
            "Sending the following messages to the LLM: %s",
            pretty_messages(messages),
        )
        result = await llm_client.query_llm(
            model=model, messages=messages, **(llm_config.model_extra or {})
        )

        return AgentResult(result=result)
