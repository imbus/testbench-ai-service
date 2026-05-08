import time

from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.agents.base import Agent
from testbench_ai_service.llm.factory import LLMFactory
from testbench_ai_service.log import logger
from testbench_ai_service.models.agent import ExecutionContext
from testbench_ai_service.utils.prompt_utils import get_prompt_model


async def run_agent(
    agent_key: str,
    agent: Agent,
    context: ExecutionContext,
    conn: TBConnection,
    llm_factory: LLMFactory,
    precheck_results: list[str],
):
    """
    Resolves the LLM client and delegates execution to the agent.

    Args:
        agent_key: Registry key of the agent (e.g. ``"test_case_set_reviewer"``).
        agent:     Agent instance to execute.
        context:   Fully-resolved execution context (includes llm_config).
        conn:      TestBench connection.
        llm_factory: Factory used to obtain the LLM client for this project.
        items:     Validated items returned by ``precheck()``.
    """
    start_time = time.time()
    logger.info(
        "Agent started | agent='%s' | project='%s'",
        agent_key,
        context.project_name,
    )
    try:
        llm_client = llm_factory.get_client(
            config=context.llm_config,
            prompt_model=get_prompt_model(context.prompt_config),
            project_name=context.project_name,
        )
        logger.debug("Initialised llm_client for agent '%s': %s", agent_key, llm_client.__class__)

        await agent.run(
            context=context, conn=conn, llm_client=llm_client, precheck_results=precheck_results
        )

        duration = time.time() - start_time
        logger.info(
            "Agent completed | agent='%s' | project='%s' | duration=%.2fs",
            agent_key,
            context.project_name,
            duration,
        )
    except Exception as e:
        logger.error(
            "Agent failed | agent='%s' | project='%s' | error=%r",
            agent_key,
            context.project_name,
            e,
            exc_info=True,
        )
