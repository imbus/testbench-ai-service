"""Ranking strategies for the related-requirements tier of the context.

A ranker returns an *ordering* of candidates; how many of them survive is the
budget's decision, not the ranker's. That split keeps the strategies
interchangeable and lets a tighter budget degrade the tier gracefully instead of
dropping it.
"""

import re
from collections.abc import Sequence
from typing import Protocol

from testbench_ai_service.agents.requirement.model import Requirement
from testbench_ai_service.agents.requirement.tree import render_detail, render_line
from testbench_ai_service.llm.base import LLMClient
from testbench_ai_service.log import logger
from testbench_ai_service.models.prompt import Message

#: Matches word characters, so accented UDF values such as ``Priorität`` tokenise
#: as one word rather than two.
_WORD = re.compile(r"\w+")


def _tokens(requirement: Requirement) -> set[str]:
    """Return the lowercased word set of a requirement's name and populated UDFs.

    Args:
        requirement: The requirement to tokenise.

    Returns:
        The distinct words available for comparison. Requirements carry no prose,
        so this is typically well under a dozen words.
    """
    text = " ".join([requirement.name, *(udf.value for udf in requirement.udfs if udf.value)])
    return set(_WORD.findall(text.lower()))


class Ranker(Protocol):
    """Orders candidate requirements by relevance to a target requirement."""

    async def order(
        self,
        target: Requirement,
        candidates: Sequence[Requirement],
    ) -> list[Requirement]:
        """Return the candidates worth including, most relevant first.

        Args:
            target: The requirement test ideas are being generated for.
            candidates: Every other requirement in the baseline.

        Returns:
            An ordering of the relevant candidates. Implementations must exclude the
            target itself, and may drop candidates they judge irrelevant.
        """
        ...


class LexicalRanker:
    """Orders candidates by how many words they share with the target.

    Deliberately simple, because the corpus is: a requirement's searchable text is
    a ten-word title plus a handful of UDF characters. Candidates sharing no word
    at all are dropped rather than ranked last -- filling a token budget with
    unrelated requirements costs money and teaches the model nothing.
    """

    async def order(
        self,
        target: Requirement,
        candidates: Sequence[Requirement],
    ) -> list[Requirement]:
        """Return candidates sharing at least one word with the target.

        Args:
            target: The requirement test ideas are being generated for.
            candidates: Every other requirement in the baseline.

        Returns:
            The overlapping candidates, most shared words first, ties broken by
            ``extendedID`` so the same baseline always yields the same order.
        """
        target_tokens = _tokens(target)

        scored = [
            (len(target_tokens & _tokens(candidate)), candidate)
            for candidate in candidates
            if candidate.key.serial != target.key.serial
        ]

        return [
            candidate
            for score, candidate in sorted(
                (entry for entry in scored if entry[0] > 0),
                key=lambda entry: (-entry[0], entry[1].extendedID),
            )
        ]


#: How many lexically ranked candidates the reranking model is shown.
#:
#: The prefilter is not optional: a baseline can hold thousands of requirements, so
#: the full set fits in no selector call. This bounds the reranking prompt while
#: leaving the model far more candidates than a budget will ever include.
SHORTLIST_SIZE = 80

RERANK_SYSTEM_PROMPT = (
    "You rank software requirements by how useful they are as context for writing "
    "test ideas about one target requirement. Reply with the identifiers only, most "
    "useful first, separated by commas. Include no explanation, and invent no "
    "identifier that is not in the list."
)


class LlmRerankRanker:
    """Reorders a lexically prefiltered shortlist using a cheap model.

    Reranking is an enhancement, never a dependency: if the call fails, times out,
    or answers with nothing recognisable, the lexical order stands and the run
    continues. A ranking problem must not cost the user their test ideas.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        model: str,
        base: Ranker | None = None,
        shortlist_size: int = SHORTLIST_SIZE,
    ):
        """
        Args:
            llm_client: Client used for the reranking call.
            model: Model identifier for the reranking call; a cheap model is enough.
            base: Ranker producing the shortlist. Defaults to :class:`LexicalRanker`.
            shortlist_size: How many candidates to show the model.
        """
        self._llm_client = llm_client
        self._model = model
        self._base = base if base is not None else LexicalRanker()
        self._shortlist_size = shortlist_size

    async def order(
        self,
        target: Requirement,
        candidates: Sequence[Requirement],
    ) -> list[Requirement]:
        """Return the shortlist in the model's order, then the rest.

        Args:
            target: The requirement test ideas are being generated for.
            candidates: Every other requirement in the baseline.

        Returns:
            The shortlist reordered by the model, with candidates it did not mention
            following in lexical order so a budget can still be filled. The plain
            lexical order on any failure.
        """
        shortlist = (await self._base.order(target, candidates))[: self._shortlist_size]
        if not shortlist:
            return []

        try:
            reply = await self._llm_client.query_llm(
                model=self._model,
                messages=self._messages(target, shortlist),
            )
        except Exception as error:
            logger.warning(
                "Reranking requirement '%s' failed (%r); keeping lexical order",
                target.extendedID,
                error,
            )
            return shortlist

        ranked = _mentioned_in_order(reply, shortlist)
        if not ranked:
            logger.warning(
                "Rerank reply for requirement '%s' named no known identifier; "
                "keeping lexical order",
                target.extendedID,
            )
            return shortlist

        ranked_keys = {node.key.serial for node in ranked}
        return [*ranked, *(node for node in shortlist if node.key.serial not in ranked_keys)]

    def _messages(self, target: Requirement, shortlist: Sequence[Requirement]) -> list[Message]:
        """Build the reranking conversation.

        Args:
            target: The target requirement.
            shortlist: The candidates to be ranked.

        Returns:
            A system message stating the task and a user message holding the target
            and the candidate list.
        """
        candidate_lines = "\n".join(render_line(node) for node in shortlist)
        return [
            Message(role="system", content=RERANK_SYSTEM_PROMPT),
            Message(
                role="user",
                content=(
                    f"Target requirement:\n{render_detail(target)}\n\n"
                    f"Candidates:\n{candidate_lines}"
                ),
            ),
        ]


def _mentioned_in_order(reply: str, shortlist: Sequence[Requirement]) -> list[Requirement]:
    """Return the shortlist entries named in the reply, in the order they appear.

    Matching is bounded by word edges so a reply naming ``C11`` does not also select
    ``C1``. Identifiers absent from the shortlist are ignored, which is what makes a
    hallucinated reply degrade instead of corrupting the ordering.

    Args:
        reply: The raw model reply.
        shortlist: The candidates that were offered.

    Returns:
        The matched candidates, ordered by first mention. Empty if none matched.
    """
    positions: list[tuple[int, Requirement]] = []

    for node in shortlist:
        match = re.search(rf"(?<!\w){re.escape(node.extendedID)}(?!\w)", reply)
        if match is not None:
            positions.append((match.start(), node))

    return [node for _, node in sorted(positions, key=lambda entry: entry[0])]
