"""One marked block per requirement in a test case set's review comment.

The block is recognised by its structure and its bold heading ``<heading> <ref> - <time>``,
tolerant of the quoting and whitespace TestBench normalises stored HTML to. A run for
one requirement replaces only its own block, so blocks of other requirements and of
the review agent stay where they are; without a block yet, it goes on top.
"""

import asyncio
import re
from collections.abc import Callable, Iterable
from enum import Enum
from html import escape

from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.log import logger
from testbench_ai_service.models.testbench import RichTextInfo, SpecificationDetailsForUpdate
from testbench_ai_service.utils.html_utils import (
    add_html_body_tags,
    build_disclaimer_html,
    has_visible_text,
    strip_html_body_tags,
)
from testbench_ai_service.utils.testbench import (
    get_test_case_set_details,
    post_project_tov_structure,
)
from testbench_ai_service.utils.traceability.models import TestCaseSetDetail


class WriteOutcome(str, Enum):
    WRITTEN = "written"
    LOCKED = "locked"
    FAILED = "failed"


def block_pattern(headings: Iterable[str], requirement_ref: str) -> re.Pattern[str]:
    """Match the block of *requirement_ref* under any of *headings*, and nothing else.

    The ref must be followed by whitespace and ``-``, so ``REQ-4`` never matches the
    block of ``REQ-42``.
    """
    heading = "|".join(re.escape(escape(text)) for text in headings)
    return re.compile(
        rf"<b>\s*(?:{heading})\s+{re.escape(escape(requirement_ref))}\s+-[^<]*</b>\s*<br\s*/?>\s*"
        r"<div style=[\"']white-space:\s*pre-wrap;?[\"']>.*?</div>\s*"
        r"<div style=[\"']padding-top:\s*5px;?[\"']>\s*<div[^>]*>.*?</div>\s*</div>",
        re.DOTALL | re.IGNORECASE,
    )


def render_block(
    heading: str, requirement_ref: str, body: str, disclaimer: str, timestamp: str
) -> str:
    """The block's HTML; *body* is plain text and keeps its line breaks."""
    return (
        f"<b>{escape(heading)} {escape(requirement_ref)} - {escape(timestamp)}</b><br/>"
        f"<div style='white-space: pre-wrap;'>{escape(body)}</div>"
        f"{build_disclaimer_html(escape(disclaimer))}"
    )


def replace_block(comment_html: str, pattern: re.Pattern[str], block: str) -> str:
    """The comment with its block for this requirement replaced, or *block* put on top.

    Returns the inner HTML, without ``<html>``/``<body>`` wrapper.
    """
    inner = strip_html_body_tags(comment_html or "").strip()
    if pattern.search(inner):
        return pattern.sub(lambda _match: block, inner, count=1)
    if not has_visible_text(inner):
        return block
    return f"{block}<br/>{inner}"


def remove_block(comment_html: str, pattern: re.Pattern[str]) -> str | None:
    """The comment without its block for this requirement, or ``None`` if it has none.

    The ``<br/>`` that separated the block from the rest of the comment goes with it.
    Returns the inner HTML, without ``<html>``/``<body>`` wrapper.
    """
    inner = strip_html_body_tags(comment_html or "").strip()
    separated = re.compile(rf"(?:{pattern.pattern})(?:\s*<br\s*/?>)?", pattern.flags)
    if not separated.search(inner):
        return None
    return separated.sub("", inner, count=1).strip()


async def _patch_review_comment(
    conn: TBConnection, project_key: str, spec_key: str, html: str
) -> None:
    """PATCH only the review comment; the lock and every other field stay as they are."""
    url = f"{conn.server_url}2/projects/{project_key}/specifications/{spec_key}"
    body = SpecificationDetailsForUpdate(
        reviewComment=RichTextInfo(html=html, images=[])
    ).model_dump(exclude_unset=True)
    response = await asyncio.to_thread(conn.session.patch, url, json=body)
    response.raise_for_status()


async def write_review_block(
    conn: TBConnection,
    project_key: str,
    tov_key: str,
    user_key: str,
    test_case_set: TestCaseSetDetail,
    pattern: re.Pattern[str],
    block: str,
) -> WriteOutcome:
    """Put *block* into the set's review comment, read fresh right before writing.

    A set locked by another user is skipped. Never raises: a failure is logged and
    reported, so one set cannot stop the others.
    """
    return await _update_review_comment(
        conn,
        project_key,
        tov_key,
        user_key,
        test_case_set,
        lambda comment: replace_block(comment, pattern, block),
    )


async def remove_review_block(
    conn: TBConnection,
    project_key: str,
    tov_key: str,
    user_key: str,
    test_case_set: TestCaseSetDetail,
    pattern: re.Pattern[str],
) -> WriteOutcome:
    """Remove the block *pattern* matches from the set's review comment, if it is there.

    Same locking and error handling as :func:`write_review_block`; a comment without
    the block is left as it is and reported as written.
    """
    return await _update_review_comment(
        conn,
        project_key,
        tov_key,
        user_key,
        test_case_set,
        lambda comment: remove_block(comment, pattern),
    )


async def _update_review_comment(
    conn: TBConnection,
    project_key: str,
    tov_key: str,
    user_key: str,
    test_case_set: TestCaseSetDetail,
    update: Callable[[str], str | None],
) -> WriteOutcome:
    """Apply *update* to the set's fresh review comment; ``None`` means nothing to write."""
    try:
        tree = await asyncio.to_thread(
            post_project_tov_structure, conn, project_key, tov_key, test_case_set.unique_id
        )
        spec = getattr(tree.root, "spec", None)
        if spec is None:
            logger.warning(
                "The lock state of test case set '%s' is unknown; its review comment is not "
                "written",
                test_case_set.path,
            )
            return WriteOutcome.FAILED
        locker = getattr(spec, "locker", None)
        if locker is not None and locker.key != user_key:
            logger.warning(
                "Test case set '%s' is locked by another user; its review comment is not written",
                test_case_set.path,
            )
            return WriteOutcome.LOCKED
        details = await asyncio.to_thread(
            get_test_case_set_details, conn, project_key, test_case_set.key
        )
        inner = update(details.spec.reviewComment)
        if inner is None:
            return WriteOutcome.WRITTEN
        await _patch_review_comment(conn, project_key, details.spec.key, add_html_body_tags(inner))
    except Exception as error:
        logger.error(
            "Writing the review comment of test case set '%s' failed: %r",
            test_case_set.path,
            error,
        )
        return WriteOutcome.FAILED
    return WriteOutcome.WRITTEN
