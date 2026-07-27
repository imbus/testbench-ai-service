import asyncio
import html
import json
import re
import tempfile
import zipfile
from dataclasses import asdict
from enum import Enum
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag
from testbench2robotframework.json_reader import TestCaseSet, TestCaseSetDetails
from testbench2robotframework.model import KeywordType, TestCaseDetails, VerdictStatus
from testbench_cli_reporter.actions import ImportJSONExecutionResults
from testbench_cli_reporter.config_model import ImportJsonParameters
from testbench_cli_reporter.testbench import Connection as TBConnection
from testbench_cli_reporter.testbench import ConnectionLog

from testbench_ai_service.agents.defect_explainer.model import (
    Comments,
    Result,
    TestCase,
    TestCaseSetProtocol,
)
from testbench_ai_service.config import TEMPLATES_DIR
from testbench_ai_service.log import logger
from testbench_ai_service.models.agent import ExecutionContext
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.utils.i18n import get_translation
from testbench_ai_service.utils.template_utils import render_template, resolve_template_path
from testbench_ai_service.utils.time_utils import current_time

AGENT_KEY = "defect_explainer"

_SEPARATOR = "    "
_VERDICT_WIDTH = 10  # fixed width for verdict padding, e.g. "[Pass]    " or "[Fail]    "


async def update_description(
    updated_comment: str, test_case_set: TestCaseSet, conn: TBConnection, context: ExecutionContext
):
    """Write an updated HTML comment back to TestBench for a test case set.

    Creates a temporary ZIP archive containing the serialized protocol and test
    case set data, then imports it into TestBench via :func:`import_data`.

    Args:
        updated_comment: The new HTML comment string to embed in the import payload.
        test_case_set: The test case set whose execution results are being updated.
        conn: The active TestBench connection.
        context: Execution context containing project, TOV, and cycle keys.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = Path(tmpdir) / "report.zip"

        create_import_zip(updated_comment, test_case_set.details, zip_path)
        logger.debug(
            "Created an import zip file containing the results for test case set '%s'",
            test_case_set.details.uniqueID,
        )

        await import_data(conn, context, zip_path)
        logger.debug(
            "Imported the results into TestBench for test case set '%s'",
            test_case_set.details.uniqueID,
        )


def clean_up_comment(comment: str) -> str:
    pattern = "/table><div.*</div>"
    return re.sub(pattern, "/table>", comment)


async def import_data(conn: TBConnection, context: ExecutionContext, path: Path):
    """Trigger a JSON execution results import job in TestBench.

    Args:
        conn: The active TestBench connection.
        context: Execution context containing the project and cycle keys.
        path: Path to the ZIP archive to import.

    Raises:
        RuntimeError: If the import job could not be triggered (e.g. the upload
            returned no server-side filename).
    """
    connection = ConnectionLog()
    connection.add_connection(conn)

    parameters = ImportJsonParameters(
        inputPath=path, projectKey=context.project_key, cycleKey=context.cycle_key
    )  # add importConfig ?
    importer = ImportJSONExecutionResults(parameters=parameters)

    triggered = await asyncio.to_thread(importer.trigger, connection.active_connection)
    if not triggered:
        raise RuntimeError(
            f"Failed to trigger importing of execution results for test case set in cycle '{context.cycle_key}'."
        )


def create_import_zip(updated_comment: str, test_case_set_details: TestCaseSetDetails, path: Path):
    """
    Creates a ZIP file containing a test case set and its protocol JSON files.

    This function generates two JSON files from a TestCaseSetDetails object:
        1. `protocol.json`: Contains the serialized TestCaseSetProtocol object built from
           the updated comments and test case details.
        2. `<tcs.uniqueID>.json`: Contains the serialized TestCaseSetDetails object with
           updated comments, using a custom serializer for Enum values.

    Both JSON files are written into a ZIP archive at the specified `path`.

    Args:
        updated_comment (str): The updated HTML comment to embed in both the protocol and test case set.
        test_case_set_details (TestCaseSetDetails): The source test case set details object.
        path (Path): The file path where the ZIP archive will be created.

    Returns:
        None: The function writes files to disk but does not return a value.

    Example:
        >>> create_import_zip("<new comment>", test_case_set_details, Path("output.zip"))
        # Produces 'output.zip' containing 'protocol.json' and '<tcs.uniqueID>.json'
    """
    tcs = build_update_test_case_set(updated_comment, test_case_set_details)
    protocol = build_protocol_json(updated_comment, test_case_set_details)

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zipf:
        zipf.writestr(
            "protocol.json", json.dumps([item.model_dump() for item in [protocol]], indent=4)
        )
        zipf.writestr(f"{tcs.uniqueID}.json", json.dumps(asdict(tcs), default=custom_serializer))


def custom_serializer(obj):
    """
    Serializes Enum objects for JSON encoding.

    If the given object is an instance of `Enum`, its `value` is returned
    so it can be serialized into JSON. For all other object types, a
    `TypeError` is raised.

    Args:
        obj (Any): The object to serialize.

    Returns:
        Any: The underlying value of the Enum if `obj` is an Enum.

    Raises:
        TypeError: If `obj` is not an Enum.

    Example:
        >>> from enum import Enum
        >>> class Status(Enum):
        ...     PASS = "PASS"
        ...     FAIL = "FAIL"
        ...
        >>> custom_serializer(Status.PASS)
        'PASS'
        >>> custom_serializer("not enum")
        Traceback (most recent call last):
            ...
        TypeError: Type <class 'str'> not serializable
    """
    if isinstance(obj, Enum):
        return obj.value
    raise TypeError(f"Type {type(obj)} not serializable")


def build_protocol_json(
    updated_comment: str, test_case_set_details: TestCaseSetDetails
) -> TestCaseSetProtocol:
    """
    Builds a TestCaseSetProtocol object from updated comments and test case details.

    This function constructs a new `TestCaseSetProtocol` based on the provided
    `test_case_set_details`. It creates a list of `TestCase` objects by copying
    execution-related information (keys, status, verdict, etc.) from each
    test case in the set. The `comments` field of the new protocol is updated
    with the given `updated_comment`.

    Args:
        updated_comment (str): The new comment string (typically HTML) to embed in the protocol.
        test_case_set_details (TestCaseSetDetails): The source object containing test case set metadata
            and individual test case execution details.

    Returns:
        TestCaseSetProtocol: A newly built protocol object that includes:
            - The original test case set key and execution key
            - A `Comments` object with the updated HTML comment
            - A list of `TestCase` objects with their execution results

    Example:
        >>> protocol = build_protocol_json("<new comment>", test_case_set_details)
        >>> protocol.comments.html
        "<new comment>"
    """
    test_cases = []
    for test_case in test_case_set_details.testCases:
        assert test_case.exec is not None
        test_cases.append(
            TestCase(
                testCaseExecutionKey=test_case.exec.key,
                durationMillis=0,
                uniqueID=test_case.uniqueID,
                result=Result(
                    execStatus=test_case.exec.execStatus,
                    status=test_case.exec.status,
                    verdict=test_case.exec.verdict,
                ),
            )
        )

    assert test_case_set_details.exec is not None
    return TestCaseSetProtocol(
        testCaseSetKey=test_case_set_details.key,
        durationMillis=0,
        executionKey=test_case_set_details.exec.key,
        comments=Comments(html=updated_comment),
        testCases=test_cases,
    )


def build_update_test_case_set(
    updated_comment: str, test_case_set_details: TestCaseSetDetails
) -> TestCaseSetDetails:
    """
    Updates the comments field of a TestCaseSetDetails object with new content.

    This function replaces the `exec.comments` attribute of the provided
    `test_case_set_details` with the given `updated_comment`.
    The modified object is then returned.

    Args:
        updated_comment (str): The new comment string (typically HTML) to insert.
        test_case_set_details (TestCaseSetDetails): The test case set details object
            whose comments will be updated.

    Returns:
        TestCaseSetDetails: The same object with its `exec.comments` field updated.

    Example:
        >>> details = TestCaseSetDetails()
        >>> details.exec.comments = "<old comment>"
        >>> new_details = build_update_test_case_set("<new comment>", details)
        >>> new_details.exec.comments
        "<new comment>"
    """
    updated_test_case_set_details = test_case_set_details
    assert updated_test_case_set_details.exec is not None
    updated_test_case_set_details.exec.comments = updated_comment
    return updated_test_case_set_details


def add_explanations_to_comment(
    comment: str,
    errors: list[dict],
    language: LanguageOption,
    templates_dir: Path | None = None,
) -> str:
    """Insert AI-generated defect explanations into an HTML test execution comment.

    For each entry in ``errors``, the function locates the matching ``<pre>`` block
    in the HTML by test case ID and error message. If a previous AI explanation
    (``<div class='ai'>``) already exists in that block, it is replaced; otherwise
    a new one is appended.

    Args:
        comment: The original HTML comment string from the test case set execution.
        errors: List of result dicts, one per failed test case. Each dict must contain:
            - ``"failed_test_case"`` - the test case unique ID as it appears in the HTML.
            - ``"error"`` - the raw error message string used to locate the ``<pre>`` block.
            - ``"explanation"`` - the AI-generated explanation to insert.
        language: The language used for the explanation heading label.
        templates_dir: Directory to resolve the fallback template from. Defaults to the
            built-in templates directory when not provided.

    Returns:
        The updated HTML string with explanations inserted or replaced.

    Example:
        >>> errors = [
        ...     {
        ...         "failed_test_case": "iTB-TC-001",
        ...         "error": "Error: Value mismatch",
        ...         "explanation": "This happens when X is not equal to Y.",
        ...     }
        ... ]
        >>> add_explanations_to_comment(comment, errors, LanguageOption.ENGLISH)
    """
    if not comment or not comment.strip():
        return comment

    heading = get_translation("defect_explainer.run.result_heading", language)
    soup = BeautifulSoup(comment, "html.parser")

    unmatched: list[dict] = []
    matched_any = False
    for error in errors:
        message_pre = _find_message_pre(soup, error)
        if message_pre is None:
            unmatched.append(error)
            continue
        _insert_explanation_into_pre(soup, message_pre, error, heading)
        matched_any = True

    result = str(soup) if matched_any else comment

    # Errors with no matching row are rendered into the single ``ai-explainer`` block
    # instead of inline; generate_explanation_template makes that block idempotent.
    fallback_body = "".join(_render_fallback_block(error, heading) for error in unmatched)
    print(f"Fallback body for unmatched errors: {fallback_body}")
    result = generate_explanation_template(
        result, language, templates_dir, explanation=fallback_body
    )

    # BeautifulSoup (here and inside generate_explanation_template) normalizes attribute
    # quoting to double quotes on output; the rest of the tooling (and the existing
    # tests) expect the single-quoted marker.
    return result.replace('<div class="ai">', "<div class='ai'>")


def _find_message_pre(soup: BeautifulSoup, error: dict) -> Tag | None:
    """Locate the ``<pre>`` message block belonging to a failed test case.

    A row is considered a match when its ``data-tb-test-case`` attribute equals the
    error's test case ID, or when the ID appears in the row's text. Within a matching
    row the explicit ``data-tb-role="message"`` cell is preferred; otherwise any
    ``<pre>`` whose text contains the raw error message is used.
    """
    test_case_id = error.get("failed_test_case", "")
    error_message = error.get("error", "")

    for row in soup.find_all("tr"):
        if not _row_matches_test_case(row, test_case_id):
            continue
        message_pre = _message_pre_in_row(row, error_message)
        if message_pre is not None:
            return message_pre
    return None


def _row_matches_test_case(row: Tag, test_case_id: str) -> bool:
    if not test_case_id:
        return False
    if row.get("data-tb-test-case") == test_case_id:
        return True
    return test_case_id in row.get_text()


def _message_pre_in_row(row: Tag, error_message: str) -> Tag | None:
    message_cell = row.find(attrs={"data-tb-role": "message"})
    if isinstance(message_cell, Tag):
        pre = message_cell.find("pre")
        if isinstance(pre, Tag):
            return pre

    for pre in row.find_all("pre"):
        if error_message and error_message in pre.get_text():
            return pre
    return None


def _insert_explanation_into_pre(
    soup: BeautifulSoup, message_pre: Tag, error: dict, heading: str
) -> None:
    """Insert (or replace) the AI explanation inside a message ``<pre>`` block."""
    _remove_existing_explanation(message_pre, heading)
    message_pre.append(_build_explanation_div(soup, heading, error.get("explanation", "")))


def _remove_existing_explanation(message_pre: Tag, heading: str) -> None:
    """Strip any previously inserted explanation from a ``<pre>`` block.

    Both the current ``<div class='ai'>`` wrapper and the older un-wrapped
    ``<b>{heading}:</b>...`` format are removed so re-runs replace rather than
    accumulate explanations.
    """
    for ai_div in message_pre.find_all("div", class_="ai"):
        ai_div.decompose()

    for bold in message_pre.find_all("b"):
        if heading not in bold.get_text():
            continue
        for sibling in list(bold.next_siblings):
            if isinstance(sibling, Tag):
                sibling.decompose()
            else:
                sibling.extract()
        bold.decompose()


def _build_explanation_div(soup: BeautifulSoup, heading: str, explanation: str) -> Tag:
    """Build a ``<div class='ai'>`` node holding the heading and the explanation.

    The explanation text is added as a :class:`NavigableString`, so BeautifulSoup
    escapes any HTML-special characters on output.
    """
    div = soup.new_tag("div", attrs={"class": "ai"})
    bold = soup.new_tag("b")
    bold.string = f"{heading}:"
    div.append(bold)
    div.append(soup.new_tag("br"))
    div.append(NavigableString(explanation))
    return div


def _render_fallback_block(error: dict, heading: str) -> str:
    """Render a fallback explanation block for a failed test case with no matching row.

    Used when an error message cannot be located in the HTML comment. The block is
    placed inside the single ``ai-explainer`` wrapper by :func:`generate_explanation_template`
    rather than attached inline.
    """
    test_case_id = html.escape(error.get("failed_test_case", ""))
    explanation = html.escape(error.get("explanation", ""))
    return f"<div class='ai'><b>{heading} ({test_case_id}):</b><br/>{explanation}</div>"


def _remove_ai_blocks(soup: BeautifulSoup, text_anchors: list[str]) -> None:
    """Remove AI blocks a previous run inserted, so re-runs don't stack them.

    Covers both the success block (``ai-explainer``) and the failure notice
    (``ai-explainer-failed``). This is what lets a successful run overwrite a stale
    "explanation failed" notice, and a failed run overwrite a stale explanation.

    TestBench stores comments as ``<html><body>...</body></html>`` and re-serialises
    them through an HTML sanitiser that can drop ``class`` attributes. So we match on
    two kinds of anchor: the marker classes (intact within our own pipeline) and, as a
    fallback, the block's distinctive sentence (disclaimer / failure message) — plain
    text content always survives the round trip.

    The text fallback is scoped to the direct children of ``<body>`` (where blocks are
    always appended), so per-test-case explanations nested inside the result tables are
    never mistaken for a block.
    """
    for block in soup.select("div.ai-explainer, div.ai-explainer-failed"):
        block.decompose()

    anchors = [anchor for anchor in text_anchors if anchor]
    if not anchors:
        return
    container = soup.body or soup
    for child in list(container.children):
        if isinstance(child, Tag) and any(anchor in child.get_text() for anchor in anchors):
            child.decompose()


def _insert_ai_block(comment: str, block_html: str, text_anchors: list[str]) -> str:
    """Replace any prior AI block(s) in ``comment`` with ``block_html``, kept well-formed.

    The block is appended inside the comment's ``<body>`` (TestBench wraps comments in
    ``<html><body>...</body></html>``; appending after ``</html>`` is what caused earlier
    markup to be mangled on re-import).
    """
    soup = BeautifulSoup(comment or "", "html.parser")
    _remove_ai_blocks(soup, text_anchors)

    block = BeautifulSoup(block_html, "html.parser")
    container = soup.body or soup
    container.append(block)
    return str(soup)


def generate_explanation_template(
    comment: str,
    language: LanguageOption,
    templates_dir: Path | None = None,
    explanation: str | None = None,
) -> str:
    """Insert a single AI block into an HTML comment, replacing any block from a prior run.

    The block (heading, optional fallback explanation, disclaimer) is rendered from
    ``template.jinja`` and appended inside the comment's ``<body>`` so the result stays
    well-formed — TestBench wraps comments in ``<html><body>...</body></html>``, and
    appending after ``</html>`` is what caused earlier markup to be mangled on re-import.

    Re-runs stay idempotent via :func:`_remove_ai_blocks`, which strips the old block by
    class and, as a fallback, by text (robust against TestBench dropping the ``class``
    attribute). A prior "explanation failed" notice is removed as well, so a successful
    run overwrites it.

    Args:
        comment: The current HTML comment; all non-AI content is preserved.
        language: Language used to resolve the template and localized strings.
        templates_dir: Base directory for template resolution; defaults to the built-in
            templates when not provided.
        explanation: Optional extra HTML rendered inside the block, used for fallback
            explanations that could not be attached inline.

    Returns:
        The comment containing exactly one AI block.
    """
    disclaimer = get_translation("defect_explainer.run.disclaimer", language)
    failed_message = get_translation("defect_explainer.run.failed_message", language)

    template_path = resolve_template_path(
        "template.jinja",
        templates_dir=templates_dir or TEMPLATES_DIR,
        language=language,
        agent_key=AGENT_KEY,
    )
    block_html = render_template(
        template_path,
        {
            "disclaimer": disclaimer,
            "explanation": explanation or "",
        },
    )

    return _insert_ai_block(comment, block_html, text_anchors=[disclaimer, failed_message])


def generate_failed_template(
    comment: str,
    language: LanguageOption,
    templates_dir: Path | None = None,
) -> str:
    """Insert a single "explanation failed" notice, replacing any block from a prior run.

    Mirrors :func:`generate_explanation_template` for the error path: it removes both a
    prior success block and a prior failure notice before appending a fresh notice inside
    ``<body>``, so notices never stack and a new failure overwrites a stale explanation.

    Args:
        comment: The current HTML comment; all non-AI content is preserved.
        language: Language used to resolve the template and localized strings.
        templates_dir: Base directory for template resolution; defaults to the built-in
            templates when not provided.

    Returns:
        The comment containing exactly one failure notice.
    """
    heading = get_translation("defect_explainer.run.failed_heading", language)
    message = get_translation("defect_explainer.run.failed_message", language)
    disclaimer = get_translation("defect_explainer.run.disclaimer", language)

    template_path = resolve_template_path(
        "failed.jinja",
        templates_dir=templates_dir or TEMPLATES_DIR,
        language=language,
        agent_key=AGENT_KEY,
    )
    block_html = render_template(
        template_path,
        {
            "current_time": current_time(),
            "heading": heading,
            "message": message,
        },
    )

    return _insert_ai_block(comment, block_html, text_anchors=[disclaimer, message])


def extract_failed_test_cases(test_case_set):
    failed_test_cases = {}
    for test_case in test_case_set.details.testCases:
        if test_case.exec.verdict in (VerdictStatus.ToVerify, VerdictStatus.Fail):
            error_message = test_case_fail_comment(test_case_set, test_case.uniqueID)
            failed_test_cases.update(
                {
                    test_case.uniqueID: {
                        "status": test_case.exec.verdict,
                        "error": error_message,
                    }
                }
            )
    return failed_test_cases


def _strip_param_prefix(name: str) -> str:
    """Strips the leading ``*`` marker TestBench uses to denote required parameters."""
    return name.replace("*", "").strip()


def _collect_fail_levels_by_top_call(test_sequence) -> dict[int, set[int]]:
    """Map each top-level call index to nested levels that contain at least one failure."""
    fail_levels_by_top_call: dict[int, set[int]] = {}
    top_call_index: int | None = None

    for idx, call in enumerate(test_sequence):
        if call.parentID is None:
            top_call_index = idx
            continue

        if top_call_index is None or call.exec.verdict.name != "Fail":
            continue

        level = len(call.numbering.split(".")) - 1
        fail_levels_by_top_call.setdefault(top_call_index, set()).add(level)

    return fail_levels_by_top_call


def _should_render_nested_call(
    level: int,
    top_call_index: int | None,
    top_call_verdict: str,
    fail_levels_by_top_call: dict[int, set[int]],
) -> bool:
    """Return whether a nested call should be rendered in the execution tree."""
    if top_call_verdict != "Fail":
        return False
    if top_call_index is None:
        return False
    return level in fail_levels_by_top_call.get(top_call_index, set())


def test_case_fail_comment(test_case_set: TestCaseSet, test_case: str) -> str:
    test_case_details: TestCaseDetails = test_case_set.test_cases.get(test_case)
    if test_case_details is None:
        raise ValueError(
            f"Test case '{test_case}' not found in test case set '{test_case_set.details.name}'."
        )

    error_message = ""
    last_top_level_verdict = ""
    for call in test_case_details.testSequence:
        verdict = call.exec.verdict.name

        if call.parentID is None:
            last_top_level_verdict = verdict
        elif last_top_level_verdict != "Fail":
            continue

        is_compound_fail = call.spec.keywordType == KeywordType.Compound and verdict == "Fail"
        if not is_compound_fail and verdict == "Fail":
            error_message = call.exec.comments

    return error_message


def _format_html_comment(comment: str) -> str:
    """Convert HTML fragments to readable plain text for trace output."""
    if not comment:
        return ""

    text = re.sub(r"<\s*br\s*/?\s*>", "\n", comment, flags=re.IGNORECASE)
    text = re.sub(r"</\s*(p|div|li|tr|table|h[1-6])\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*li[^>]*>", "- ", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*(script|style)[^>]*>.*?<\s*/\s*\1\s*>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)

    text = html.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = [line.strip() for line in text.split("\n")]
    normalized_lines = []
    prev_empty = False
    for line in lines:
        is_empty = line == ""
        if is_empty and prev_empty:
            continue
        normalized_lines.append(line)
        prev_empty = is_empty

    return "\n".join(normalized_lines).strip()


def test_case_execution_as_str(test_case_set: TestCaseSet, test_case: str) -> str:
    """Formats the execution trace of a specific test case as a human-readable string.

    Top-level steps are rendered with their execution verdict, indented by nesting level.
    For nested steps under a failed top-level step, all calls on levels that contain
    at least one failure are included. This keeps the output focused while still
    showing sibling context around failures.

    Parameters of each step are rendered as ``param_name=param_value``.
    Leading ``*`` markers (TestBench required-parameter convention) are stripped
    from parameter names.

    Args:
        test_case_set: The test case set containing the target test case.
        test_case: The unique ID of the test case to format.

    Raises:
        ValueError: If ``test_case`` is not found in the test case set.

    Returns:
        Multi-line string with the test case set name on the first line, followed
        by one indented line per rendered step.

    ## Example output
    ```
    Login Test Set
        ►[Pass]      Open Browser
        ►[Pass]      Navigate To Login    url=https://example.com
        ▼[Fail]      Login    username=admin    password=secret
            ►[Pass]  Enter Username    username=admin
            ►[Fail]  Enter Password    password=secret
    ```
    """
    test_case_details: TestCaseDetails = test_case_set.test_cases.get(test_case)
    if test_case_details is None:
        raise ValueError(
            f"Test case '{test_case}' not found in test case set '{test_case_set.details.name}'."
        )

    lines = [test_case_set.details.name]

    fail_levels_by_top_call = _collect_fail_levels_by_top_call(test_case_details.testSequence)

    top_call_index = None
    top_call_verdict = ""
    for idx, call in enumerate(test_case_details.testSequence):
        level = len(call.numbering.split(".")) - 1
        verdict = call.exec.verdict.name

        if call.parentID is None:
            top_call_index = idx
            top_call_verdict = verdict
        elif not _should_render_nested_call(
            level=level,
            top_call_index=top_call_index,
            top_call_verdict=top_call_verdict,
            fail_levels_by_top_call=fail_levels_by_top_call,
        ):
            continue

        is_compound_fail = call.spec.keywordType == KeywordType.Compound and verdict == "Fail"
        if call.spec.keywordType == KeywordType.Compound:
            prefix = "▼" if is_compound_fail else "►"
        else:
            prefix = " "
        verdict_label = f"[{verdict}]{' ' * (_VERDICT_WIDTH - len(verdict))}"
        indent = _SEPARATOR * (level + 1)
        params = [f"{_strip_param_prefix(p.name)}={p.value}" for p in call.spec.callParameters]

        line = f"{indent}{prefix}{verdict_label}{_SEPARATOR}{call.spec.name}"
        if params:
            line += f"{_SEPARATOR}{_SEPARATOR.join(params)}"
        lines.append(line)

        if not is_compound_fail and verdict == "Fail":
            plain_comment = _format_html_comment(call.exec.comments)
            if plain_comment:
                for comment_line in plain_comment.splitlines():
                    lines.append(f"{indent} | {comment_line}")

    return "\n".join(lines)
