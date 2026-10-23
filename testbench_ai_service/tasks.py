import time
from uuid import uuid4

from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.agents.base import Agent
from testbench_ai_service.jobs.handle import JobHandle, current_job, job_scope
from testbench_ai_service.jobs.store import JobStore
from testbench_ai_service.llm.base import LLMClient, NoLLMClient
from testbench_ai_service.llm.factory import LLMFactory
from testbench_ai_service.log import log_context, logger
from testbench_ai_service.models.agent import ExecutionContext
from testbench_ai_service.usage import UsageRecordingClient, UsageStore
from testbench_ai_service.utils.build_prompt_utils import get_prompt_model

_MAX_ERROR_LENGTH = 500


async def run_agent(
    agent_key: str,
    agent: Agent,
    context: ExecutionContext,
    conn: TBConnection,
    llm_factory: LLMFactory,
    item_ids: list[str],
    usage_store: UsageStore | None = None,
    job_id: str | None = None,
    job_store: JobStore | None = None,
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
        job_id:    Id of the job tracking this run; also the log run id. A fresh id
                   is made when ``None``.
        job_store: Where the job is kept; ``None`` tracks no job.

    Every record logged during the run carries the triggering user, the
    project, the agent and a fresh run id, which is what lets the console show
    a user their own runs and nobody else's (design 4.3).
    """
    run_id = job_id or uuid4().hex
    with log_context(
        user_key=context.user_key,
        project_key=context.project_key,
        agent=agent_key,
        run_id=run_id,
    ):
        if job_store is None:
            await _run_agent(agent_key, agent, context, conn, llm_factory, item_ids, usage_store)
            return
        with job_scope(JobHandle(run_id, job_store)):
            await _run_agent(
                agent_key,
                agent,
                context,
                conn,
                llm_factory,
                item_ids,
                usage_store,
                run_id,
                job_store,
            )


async def _run_agent(
    agent_key: str,
    agent: Agent,
    context: ExecutionContext,
    conn: TBConnection,
    llm_factory: LLMFactory,
    item_ids: list[str],
    usage_store: UsageStore | None = None,
    job_id: str | None = None,
    job_store: JobStore | None = None,
):
    start_time = time.time()
    logger.info(
        "Agent started | agent='%s' | project='%s'",
        agent_key,
        context.project_name,
    )
    try:
        llm_client: LLMClient
        if getattr(agent, "USES_LLM", True):
            prompt_model = get_prompt_model(context.prompt_config)
            llm_client = llm_factory.get_client(
                config=context.llm_config,
                prompt_model=prompt_model,
                project_name=context.project_name,
            )
            if usage_store is not None:
                provider = llm_factory.resolve_provider(context.llm_config, prompt_model)
                llm_client = UsageRecordingClient(llm_client, usage_store, str(provider))
        else:
            llm_client = NoLLMClient()
        logger.debug("Initialised llm_client for agent '%s': %s", agent_key, llm_client.__class__)

        await agent.run(context=context, conn=conn, llm_client=llm_client, item_ids=item_ids)
        if job_store is not None and job_id is not None:
            await job_store.run(job_store.finish, job_id, "succeeded")

        duration = time.time() - start_time
        logger.info(
            "Agent completed%s | agent='%s' | project='%s' | duration=%.2fs",
            ", job failed" if current_job().failed else "",
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
        if job_store is not None and job_id is not None:
            # A fail() the agent called before already ended the job; finish keeps that first outcome.
            await job_store.run(job_store.finish, job_id, "failed", repr(e)[:_MAX_ERROR_LENGTH])
