import time

from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.llm.factory import LLMFactory
from testbench_ai_service.log import logger
from testbench_ai_service.models.usecase import ExecutionContext
from testbench_ai_service.usecases.base import UseCase


async def run_usecase(
    usecase: str,
    usecase_service: UseCase,
    context: ExecutionContext,
    conn: TBConnection,
    llm_factory: LLMFactory,
    items: list,
):
    """
    Resolves the LLM client and delegates execution to the usecase service.

    Args:
        usecase:         Name of the usecase (e.g. ``"test_case_set_reviews"``).
        usecase_service: UseCase service to execute.
        context:         Fully-resolved execution context (includes llm_config).
        conn:            TestBench connection.
        llm_factory:     Factory used to obtain the LLM client for this project.
        items:           Validated items returned by ``precheck()``.
    """
    start_time = time.time()
    logger.info(
        "Usecase started | usecase='%s' | project='%s'",
        usecase,
        context.project_name,
    )
    try:
        llm_client = llm_factory.get_client(
            config=context.llm_config,
            project_name=context.project_name,
        )
        logger.debug("Initialised llm_client for usecase '%s': %s", usecase, llm_client.__class__)

        await usecase_service.run(
            context=context,
            conn=conn,
            llm_client=llm_client,
            items=items,
        )

        duration = time.time() - start_time
        logger.info(
            "Usecase completed | usecase='%s' | project='%s' | duration=%.2fs",
            usecase,
            context.project_name,
            duration,
        )
    except Exception as e:
        logger.error(
            "Usecase failed | usecase='%s' | project='%s' | error=%r",
            usecase,
            context.project_name,
            e,
            exc_info=True,
        )
