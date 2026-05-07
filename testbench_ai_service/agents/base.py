from abc import ABC, abstractmethod
from typing import ClassVar

from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.llm.base import LLMClient
from testbench_ai_service.models.agent import ExecutionContext, PrecheckResult


class Agent(ABC):
    GENERATED_PLACEHOLDERS: ClassVar[frozenset[str]] = frozenset()

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
            PrecheckResult containing the passed status, validated items, and warnings.
        """

    @abstractmethod
    async def run(
        self,
        context: ExecutionContext,
        conn: TBConnection,
        llm_client: LLMClient,
        precheck_results: list[str],
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
            items:      The validated items returned by ``precheck()``.
        """
