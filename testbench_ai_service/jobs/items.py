"""Run the items of a multi-item agent so that one failing item does not fail the job."""

import asyncio
from collections.abc import Awaitable, Sequence

from testbench_ai_service.jobs.handle import current_job
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.utils.i18n import get_translation

_ERROR_LIMIT = 200


async def gather_items(
    items: Sequence[tuple[str, Awaitable[object]]], language: LanguageOption
) -> None:
    """Await all *items* ``(label, awaitable)``; report failures on the current job.

    Each failed item adds a warning to the job. Only when every item failed
    is the job ended as failed. The run itself returns normally in both cases,
    the agents have logged the details of each failure already.
    """
    if not items:
        return
    results = await asyncio.gather(*(awaitable for _, awaitable in items), return_exceptions=True)
    failures = 0
    for (label, _), result in zip(items, results, strict=True):
        if isinstance(result, BaseException):
            if not isinstance(result, Exception):
                raise result
            failures += 1
            message = get_translation(
                "jobs.item_failed",
                language,
                item=label,
                error=repr(result)[:_ERROR_LIMIT],
            )
            await current_job().warn(message)
    if failures == len(items):
        message = get_translation("jobs.all_items_failed", language, count=len(items))
        await current_job().fail(message)
