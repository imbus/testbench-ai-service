"""Step ``prefilter``: which of the TOV's unlinked sets are worth reading in full.

The prefilter sees only titles, paths and short descriptions and may err on the side
of too many candidates: precision is the interpretation's job, and a set dropped here
is never looked at again. Batches run in parallel; a failing batch is logged and its
sets are lost for this run, the others still count.
"""

import asyncio
from collections.abc import Mapping
from typing import Protocol

from testbench2robotframework.json_reader import TestCaseSet

from testbench_ai_service.agents.link_finder.model import (
    CONFIDENCE_ORDER,
    PrefilterAnswer,
    PrefilterHit,
    PrefilterResult,
    TestCaseSetSummary,
)
from testbench_ai_service.log import logger
from testbench_ai_service.models.agent import AgentData
from testbench_ai_service.utils.html_utils import visible_text
from testbench_ai_service.utils.traceability.interpretation import batches, render_aspects
from testbench_ai_service.utils.traceability.models import AskStep, Aspect

STEP = "prefilter"

#: Characters of the set description the prefilter sees.
SHORT_DESCRIPTION_LENGTH = 300


class PrefilterData(AgentData):
    """Template variables of the ``prefilter`` step."""

    requirement: str
    aspects: str
    test_case_sets: str


class Prefilter(Protocol):
    async def run(
        self, requirement: str, aspects: list[Aspect], sets: list[TestCaseSetSummary]
    ) -> PrefilterResult: ...


def summarize(catalog: Mapping[str, TestCaseSet], set_keys: list[str]) -> list[TestCaseSetSummary]:
    """The given sets of the catalog as the prefilter sees them, sorted by path."""
    wanted = set(set_keys)
    summaries = []
    for test_case_set in catalog.values():
        details = test_case_set.details
        if details.key not in wanted:
            continue
        description = visible_text(details.spec.description or "")
        if len(description) > SHORT_DESCRIPTION_LENGTH:
            description = description[:SHORT_DESCRIPTION_LENGTH].rstrip() + " ..."
        summaries.append(
            TestCaseSetSummary(
                key=details.key,
                title=details.name,
                path=details.path,
                description_short=description,
                spec_status=details.spec.status.value,
            )
        )
    return sorted(summaries, key=lambda summary: summary.path)


def render_summaries(sets: list[TestCaseSetSummary]) -> str:
    return "\n".join(
        f"{summary.key} | {summary.path} | {summary.title} | {summary.description_short or '-'}"
        for summary in sets
    )


def validate_hits(
    hits: list[PrefilterHit], sets: list[TestCaseSetSummary], max_candidates: int
) -> list[PrefilterHit]:
    """Drop unknown and repeated keys; keep the most relevant, ties in path order.

    Keys are compared trimmed.
    """
    order = {summary.key: index for index, summary in enumerate(sets)}
    best: dict[str, PrefilterHit] = {}
    for hit in hits:
        key = hit.set_key.strip()
        if key not in order:
            continue
        checked = hit.model_copy(update={"set_key": key})
        current = best.get(key)
        if current is None or CONFIDENCE_ORDER.index(checked.relevance) < CONFIDENCE_ORDER.index(
            current.relevance
        ):
            best[key] = checked
    ranked = sorted(
        best.values(), key=lambda h: (CONFIDENCE_ORDER.index(h.relevance), order[h.set_key])
    )
    return ranked[:max_candidates]


class LlmPrefilter:
    """Screens the sets in batches with the model."""

    def __init__(self, ask: AskStep, batch_size: int, max_candidates: int, max_parallel: int):
        self.ask = ask
        self.batch_size = batch_size
        self.max_candidates = max_candidates
        self.max_parallel = max_parallel

    async def run(
        self, requirement: str, aspects: list[Aspect], sets: list[TestCaseSetSummary]
    ) -> PrefilterResult:
        semaphore = asyncio.Semaphore(self.max_parallel)
        rendered_aspects = render_aspects(aspects)

        async def screen(batch: list[TestCaseSetSummary]) -> list[PrefilterHit] | None:
            async with semaphore:
                try:
                    answer = await self.ask(
                        STEP,
                        PrefilterAnswer,
                        PrefilterData(
                            requirement=requirement,
                            aspects=rendered_aspects,
                            test_case_sets=render_summaries(batch),
                        ),
                    )
                except Exception as error:
                    logger.error(
                        "Prefiltering %d test case sets (%s ...) failed: %r",
                        len(batch),
                        batch[0].path,
                        error,
                    )
                    return None
            return answer.hits

        chunks = batches(sets, self.batch_size)
        answers = await asyncio.gather(*(screen(chunk) for chunk in chunks))
        hits = [hit for answer in answers if answer for hit in answer]
        unscreened = [
            summary.key
            for chunk, answer in zip(chunks, answers, strict=True)
            if answer is None
            for summary in chunk
        ]
        return PrefilterResult(
            hits=validate_hits(hits, sets, self.max_candidates),
            sets_screened=len(sets),
            incomplete=bool(unscreened),
            unscreened=unscreened,
        )
