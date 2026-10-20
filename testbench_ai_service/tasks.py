import time
from uuid import uuid4

from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.agents.base import Agent
from testbench_ai_service.llm.factory import LLMFactory
from testbench_ai_service.log import log_context, logger
from testbench_ai_service.models.agent import ExecutionContext
from testbench_ai_service.usage import UsageRecordingClient, UsageStore
from testbench_ai_service.utils.build_prompt_utils import get_prompt_model


async def run_agent(
    agent_key: str,
    agent: Agent,
    context: ExecutionContext,
    conn: TBConnection,
    llm_factory: LLMFactory,
    item_ids: list[str],
    usage_store: UsageStore | None = None,
):
    """
    Resolves the LLM client and delegates execution to the agent.

    Args:
        agent_key: Registry key of the agent (e.g. ``"test_case_set_reviewer"``).
        agent:     Agent instance to execute.
        context:   Fully-resolved execution context (includes llm_config).
        conn:      TestBench connection.
        llm_factory: Factory used to obtain the LLM client for this project.
        item_ids:  Validated item IDs returned by ``precheck()``.
        usage_store: Where the run's token usage is counted; ``None`` counts nothing.

    Every record logged during the run carries the triggering user, the
    project, the agent and a fresh run id, which is what lets the console show
    a user their own runs and nobody else's (design 4.3).
    """
    with log_context(
        user_key=context.user_key,
        project_key=context.project_key,
        agent=agent_key,
        run_id=uuid4().hex,
    ):
        await _run_agent(agent_key, agent, context, conn, llm_factory, item_ids, usage_store)


async def _run_agent(
    agent_key: str,
    agent: Agent,
    context: ExecutionContext,
    conn: TBConnection,
    llm_factory: LLMFactory,
    item_ids: list[str],
    usage_store: UsageStore | None = None,
):
    start_time = time.time()
    logger.info(
        "Agent started | agent='%s' | project='%s'",
        agent_key,
        context.project_name,
    )
    try:
        prompt_model = get_prompt_model(context.prompt_config)
        llm_client = llm_factory.get_client(
            config=context.llm_config,
            prompt_model=prompt_model,
            project_name=context.project_name,
        )
        if usage_store is not None:
            provider = llm_factory.resolve_provider(context.llm_config, prompt_model)
            llm_client = UsageRecordingClient(llm_client, usage_store, str(provider))
        logger.debug("Initialised llm_client for agent '%s': %s", agent_key, llm_client.__class__)

        await agent.run(context=context, conn=conn, llm_client=llm_client, item_ids=item_ids)

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
