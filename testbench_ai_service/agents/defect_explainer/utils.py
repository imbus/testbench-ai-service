import asyncio
import html
import json
import re
import tempfile
import zipfile
from dataclasses import asdict
from enum import Enum
from pathlib import Path

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
from testbench_ai_service.log import logger
from testbench_ai_service.models.agent import ExecutionContext
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.utils.i18n import get_translation
from testbench_ai_service.utils.time_utils import current_time

_SEPARATOR = "    "
_VERDICT_WIDTH = 10  # fixed width for verdict padding, e.g. "[Pass]    " or "[Fail]    "


# --- Anchors written by testbench2robotframework -----------------------------
# tb2rf marks the interesting cells of its execution comments with 'data-tb-*'
# attributes, so they can be found without parsing the styling. The legacy
# patterns below still read comments written by tb2rf <= 1.1.
_FAIL_MESSAGE_BY_ANCHOR = re.compile(
    r"<tr[^>]*data-tb-level=['\"]FAIL['\"][^>]*>.*?"
    r"<td[^>]*data-tb-role=['\"]text['\"][^>]*>(.*?)</td>",
    re.DOTALL,
)
_FAIL_MESSAGE_LEGACY = re.compile(r"<b>FAIL</b></td><td><pre>([^<]+)</pre>")
_TAG = re.compile(r"<[^>]+>")


def extract_error_message(keyword_comment: str) -> str:
    """The failure message out of a keyword execution comment written by tb2rf.

    Prefers the 'data-tb-level=\"FAIL\"' row of the structured keyword comment
    and falls back to the flat table of older tb2rf versions.
    """
    comment = keyword_comment or ""
    match = _FAIL_MESSAGE_BY_ANCHOR.search(comment)
    if match:
        return html.unescape(_TAG.sub("", match.group(1))).strip()
    legacy = _FAIL_MESSAGE_LEGACY.search(comment)
    if legacy:
        return legacy.group(1).strip()
    # A caller may hand over the bare message instead of a comment.
    return "" if "<" in comment else comment.strip()


def message_cell_pattern(test_case_id: str, error_message: str) -> re.Pattern:
    """Matches the message cell of one test case in a test case set comment.

    Group 1 is everything up to and including the opening '<pre>', group 2 the
    current content and group 3 the closing tag, so an explanation can be put in
    place of group 2.
    """
    return re.compile(
        rf"(<tr[^>]*data-tb-test-case=['\"]{re.escape(test_case_id)}['\"][^>]*>.*?"
        rf"<td[^>]*data-tb-role=['\"]message['\"][^>]*>\s*<pre[^>]*>)(.*?)(</pre>)",
        re.DOTALL,
    )


def legacy_message_cell_pattern(test_case_id: str, error_message: str) -> re.Pattern:
    """The pre-1.2 layout, where only the test case ID and a <pre> could be matched."""
    return re.compile(
        rf"({re.escape(test_case_id)}.*?<pre[^>]*>)(.*?{re.escape(error_message)}.*?)(</pre>)",
        re.DOTALL,
    )


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


def add_explanations_to_comment(comment: str, errors: list[dict], language: LanguageOption) -> str:
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
    explainer_result_heading_message = get_translation(
        "defect_explainer.run.result_heading", language
    )
    if not comment.strip():
        # Nothing to annotate - do not turn an empty comment into a disclaimer.
        return comment
    updated_html = comment
    has_fallback_errors = False
    fallback_html_buffer = f"<div class='ai-explainer'><br/><b>{explainer_result_heading_message} - {current_time()}</b></div>"
    for details in errors:
        try:
            test_case_id = details["failed_test_case"]
            explanation = details.get("explanation", "")
            if not explanation:
                logger.warning(f"No explanation found for error ID: {test_case_id}")
                continue

            error_msg = extract_error_message(details.get("error", ""))
            pattern = message_cell_pattern(test_case_id, error_msg)
            if not pattern.search(updated_html):
                # Comments written by tb2rf <= 1.1 have no anchors; there the
                # message can only be found via the test case ID and the text.
                if not error_msg:
                    logger.warning(f"No error message found for error ID: {test_case_id}")
                    has_fallback_errors = True
                    fallback_html_buffer = add_explanation(fallback_html_buffer, details)
                    continue
                pattern = legacy_message_cell_pattern(test_case_id, error_msg)
                if not pattern.search(updated_html):
                    logger.warning(f"No matches found for error ID: {test_case_id}")
                    has_fallback_errors = True
                    fallback_html_buffer = add_explanation(fallback_html_buffer, details)
                    continue

            heading = f"<b>{explainer_result_heading_message}:</b>"
            # The explanation comes from a language model and may contain '<' or '&'.
            explanation_block = f"<div class='ai'>{heading}<br>{html.escape(explanation)}</div>"

            def insert(match: re.Match, block: str = explanation_block, mark: str = heading) -> str:
                # An explanation of an earlier run is replaced, not appended - also
                # when only its heading survived in the stored comment.
                current = match.group(2).split("<div class='ai'>", 1)[0].split(mark, 1)[0]
                return match.group(1) + current + block + match.group(3)

            updated_html = pattern.sub(insert, updated_html, count=1)
        except (KeyError, IndexError, AttributeError) as e:
            logger.error(f"Error processing error ID {details.get('failed_test_case')}: {e}")
            continue

    if has_fallback_errors:
        return add_disclaimer_no_rf_comment(updated_html, fallback_html_buffer, language)
    return add_disclaimer(updated_html, language)


def add_explanation(comment: str, error: dict) -> str:
    comment = comment.replace("\n", "<br/>")
    return f"{comment}<br/><b>{error['failed_test_case']}</b>: {error['explanation']}"


def add_disclaimer_no_rf_comment(comment: str, explanation: str, language: LanguageOption) -> str:
    ai_disclaimer = get_translation("shared.run.disclaimer", language)
    disclaimer = f"<div style='padding-top: 5px;'><div style='border-top: 1px solid black; width: 218px; font-size: 10px;'>{ai_disclaimer}</div></div>"

    content_to_insert = f'<div class="ai-explainer">\n{explanation}\n{disclaimer}\n</div>'

    if '<div class="ai-explainer">' in comment:
        if "</body>" in comment:
            return re.sub(
                r'<div class="ai-explainer">.*?(?=</body>)',
                content_to_insert + "\n",
                comment,
                flags=re.DOTALL,
            )
        return re.sub(r'<div class="ai-explainer">.*', content_to_insert, comment, flags=re.DOTALL)

    if "<body>" in comment:
        return comment.replace("</body>", f"{content_to_insert}\n</body>", 1)

    return comment + content_to_insert


def add_disclaimer(comment: str, language: LanguageOption) -> str:
    ai_disclaimer = get_translation("shared.run.disclaimer", language)
    disclaimer = f"<div style='padding-top: 5px;'><div style='border-top: 1px solid black; width: 218px; font-size: 10px;'>{ai_disclaimer}</div></div>"
    return comment.replace("</table>", "</table>" + disclaimer, 1)


def add_error_message(comment: str, language: LanguageOption) -> str:
    error_message = get_translation("shared.run.error_message", language)
    failed_heading = get_translation("defect_explainer.run.failed_heading", language)
    error_message = f"<div><b>{failed_heading}:</b><br/>{error_message}</div>"
    return comment.replace("</table>", "</table>" + error_message, 1)


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
    # A table cell ends a column, not a line - keep its content on the same line.
    text = re.sub(r"</\s*td\s*>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)

    text = html.unescape(text)
    # tb2rf indents its comment tables with '&nbsp;', which unescapes to U+00A0.
    # Turn those into ordinary spaces so the trace stays plain text.
    text = text.replace("\xa0", " ")
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
