"""One marked block per requirement in a test case set's review comment.

The block is recognised by its structure and its bold heading ``<heading> <ref> - <time>``,
tolerant of the quoting and whitespace TestBench normalises stored HTML to. A run for
one requirement replaces only its own block, so blocks of other requirements and of
the review agent stay where they are; without a block yet, it goes on top.
"""

import asyncio
import re
from collections.abc import Iterable
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
from testbench_ai_service.utils.traceability.models import LinkedSet


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
    linked_set: LinkedSet,
    pattern: re.Pattern[str],
    block: str,
) -> WriteOutcome:
    """Put *block* into the set's review comment, read fresh right before writing.

    A set locked by another user is skipped. Never raises: a failure is logged and
    reported, so one set cannot stop the others.
    """
    try:
        tree = await asyncio.to_thread(
            post_project_tov_structure, conn, project_key, tov_key, linked_set.unique_id
        )
        locker = getattr(getattr(tree.root, "spec", None), "locker", None)
        if locker is not None and locker.key != user_key:
            logger.warning(
                "Test case set '%s' is locked by another user; its review comment is not written",
                linked_set.path,
            )
            return WriteOutcome.LOCKED
        details = await asyncio.to_thread(
            get_test_case_set_details, conn, project_key, linked_set.key
        )
        html = add_html_body_tags(replace_block(details.spec.reviewComment, pattern, block))
        await _patch_review_comment(conn, project_key, linked_set.spec_key, html)
    except Exception as error:
        logger.error(
            "Writing the review comment of test case set '%s' failed: %r", linked_set.path, error
        )
        return WriteOutcome.FAILED
    return WriteOutcome.WRITTEN
