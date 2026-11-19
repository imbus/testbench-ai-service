from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from testbench2robotframework.model import (
    KeywordCallType,
    KeywordType,
)

from testbench_ai_service.agents.test_case_set_reviewer.utils import (
    patch_previous_review_comment_for_test_structure_element,
    patch_review_result_for_test_structure_element,
    patch_review_started_for_test_structure_element,
)
from testbench_ai_service.config import TEMPLATES_DIR
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.testbench import SpecificationDetailsForUpdate
from testbench_ai_service.utils.testbench_helpers import (
    get_keyword_calls_for_test_case,
)


def _make_keyword_call(
    name: str,
    keyword_type=KeywordType.Textual,
    call_type=KeywordCallType.Flow,
    parent_id=None,
    call_parameters=None,
):
    call = MagicMock()
    call.spec = MagicMock()
    call.spec.name = name
    call.spec.keywordType = keyword_type
    call.spec.callType = call_type
    call.spec.callParameters = call_parameters or []
    call.parentID = parent_id
    return call


def _make_test_case(sequence: list):
    tc = MagicMock()
    tc.testSequence = sequence
    return tc


def _make_test_case_set(name: str, test_cases: dict):
    tcs = MagicMock()
    tcs.details = MagicMock()
    tcs.details.name = name
    tcs.test_cases = test_cases
    return tcs


class TestGetKeywordCallsForTestCase:
    """Tests for ``get_keyword_calls_for_test_case``."""

    def test_returns_all_top_level_calls(self):
        calls = [
            _make_keyword_call("Step A", parent_id=None),
            _make_keyword_call("Step B", parent_id=None),
        ]
        tc = _make_test_case(calls)
        result = get_keyword_calls_for_test_case(tc)
        assert result == calls

    def test_excludes_child_calls(self):
        parent = _make_keyword_call("Parent", parent_id=None)
        child = _make_keyword_call("Child", parent_id="some-parent-id")
        tc = _make_test_case([parent, child])
        result = get_keyword_calls_for_test_case(tc)
        assert result == [parent]

    def test_empty_sequence_returns_empty_list(self):
        tc = _make_test_case([])
        result = get_keyword_calls_for_test_case(tc)
        assert result == []


FROZEN_NOW = datetime(2025, 9, 16, 12, 34, 56, tzinfo=ZoneInfo("Europe/Berlin"))


def _compact(html: str) -> str:
    """Drop the indentation and line breaks the jinja templates put around the markup."""
    return "".join(line.strip() for line in html.splitlines())


@pytest.fixture
def mock_patch_spec():
    with patch(
        "testbench_ai_service.agents.test_case_set_reviewer.utils.patch_test_structure_element_spec",
        new_callable=AsyncMock,
    ) as mock_patch:
        yield mock_patch


@pytest.fixture
def frozen_time():
    with patch("testbench_ai_service.utils.time_utils.datetime") as mock_datetime:
        mock_datetime.now.return_value = FROZEN_NOW
        yield


def _review_comment_html(mock_patch_spec) -> str:
    spec_update: SpecificationDetailsForUpdate = mock_patch_spec.call_args[0][3]
    return _compact(spec_update.reviewComment.html)


class TestPatchReviewStarted:
    """Tests for ``patch_review_started_for_test_structure_element``."""

    async def test_calls_patch_with_spec_update(self, mock_patch_spec):
        await patch_review_started_for_test_structure_element(
            MagicMock(),
            "PROJ1",
            "SPEC1",
            "prev comment",
            LanguageOption.ENGLISH,
            "user1",
            TEMPLATES_DIR,
        )

        mock_patch_spec.assert_awaited_once()
        spec_update: SpecificationDetailsForUpdate = mock_patch_spec.call_args[0][3]
        assert isinstance(spec_update, SpecificationDetailsForUpdate)
        assert "review started" in spec_update.reviewComment.html.lower()

    async def test_html_contains_previous_review_comment(self, mock_patch_spec):
        previous = "Old review comment"

        await patch_review_started_for_test_structure_element(
            MagicMock(), "PROJ1", "SPEC1", previous, LanguageOption.ENGLISH, "user1", TEMPLATES_DIR
        )

        assert previous in _review_comment_html(mock_patch_spec)

    async def test_full_html_structure_with_previous_content(self, mock_patch_spec, frozen_time):
        await patch_review_started_for_test_structure_element(
            MagicMock(),
            "PROJ1",
            "SPEC1",
            "<p>Previous</p>",
            LanguageOption.ENGLISH,
            "user1",
            TEMPLATES_DIR,
        )

        expected_html = (
            "<html><body>2025-09-16 12:34:56 - AI review started ..."
            "<br/><br/><p>Previous</p></body></html>"
        )
        assert _review_comment_html(mock_patch_spec) == expected_html

    async def test_uses_template_of_requested_language(self, mock_patch_spec, frozen_time):
        await patch_review_started_for_test_structure_element(
            MagicMock(), "PROJ1", "SPEC1", "", LanguageOption.GERMAN, "user1", TEMPLATES_DIR
        )

        html = _review_comment_html(mock_patch_spec)
        assert "AI review started" not in html
        assert html.startswith("<html><body>2025-09-16 12:34:56 - ")

    async def test_empty_previous_omits_separator(self, mock_patch_spec):
        await patch_review_started_for_test_structure_element(
            MagicMock(), "PROJ1", "SPEC1", "", LanguageOption.ENGLISH, "user1", TEMPLATES_DIR
        )

        html = _review_comment_html(mock_patch_spec)
        assert "<br/>" not in html
        assert "AI review started" in html

    async def test_locker_and_reviewer_metadata(self, mock_patch_spec):
        await patch_review_started_for_test_structure_element(
            MagicMock(), "PROJ1", "SPEC1", "", LanguageOption.ENGLISH, "user42", TEMPLATES_DIR
        )

        spec_update: SpecificationDetailsForUpdate = mock_patch_spec.call_args[0][3]
        assert spec_update.locker.optional == "user42"
        assert spec_update.reviewer.optional == "user42"
        assert spec_update.reviewComment.images == []

    async def test_missing_template_raises(self, mock_patch_spec, tmp_path):
        with pytest.raises(FileNotFoundError, match=r"started\.jinja"):
            await patch_review_started_for_test_structure_element(
                MagicMock(), "PROJ1", "SPEC1", "", LanguageOption.ENGLISH, "user1", tmp_path
            )

        mock_patch_spec.assert_not_awaited()


class TestPatchReviewResult:
    """Tests for ``patch_review_result_for_test_structure_element``."""

    async def test_calls_patch_with_review_notes(self, mock_patch_spec):
        await patch_review_result_for_test_structure_element(
            MagicMock(),
            "PROJ1",
            "SPEC1",
            "- Issue found",
            "prev",
            LanguageOption.ENGLISH,
            "user1",
            TEMPLATES_DIR,
        )

        mock_patch_spec.assert_awaited_once()
        assert "Issue found" in _review_comment_html(mock_patch_spec)

    async def test_empty_review_notes_uses_translation(self, mock_patch_spec):
        with patch(
            "testbench_ai_service.agents.test_case_set_reviewer.utils.get_translation",
            return_value="No notes available",
        ) as mock_translate:
            await patch_review_result_for_test_structure_element(
                MagicMock(),
                "PROJ1",
                "SPEC1",
                "",
                "prev",
                LanguageOption.GERMAN,
                "user1",
                TEMPLATES_DIR,
            )

        mock_translate.assert_called_once_with(
            "test_case_set_reviewer.run.no_notes", LanguageOption.GERMAN
        )
        assert "No notes available" in _review_comment_html(mock_patch_spec)

    async def test_full_html_structure_with_previous_content(self, mock_patch_spec, frozen_time):
        await patch_review_result_for_test_structure_element(
            MagicMock(),
            "PROJ1",
            "SPEC1",
            "Review note",
            "<p>Old</p>",
            LanguageOption.ENGLISH,
            "user1",
            TEMPLATES_DIR,
        )

        expected_html = (
            "<html><body>"
            "<b>AI Review - 2025-09-16 12:34:56</b>"
            "<br/>Review note"
            "<div style='padding-top: 5px;'><div style='border-top: 1px solid black;"
            " width: 218px; font-size: 10px;'>AI-generated responses may be inaccurate.</div></div>"
            "<br/><p>Old</p>"
            "</body></html>"
        )
        assert _review_comment_html(mock_patch_spec) == expected_html

    async def test_empty_previous_omits_previous_block(self, mock_patch_spec):
        await patch_review_result_for_test_structure_element(
            MagicMock(),
            "PROJ1",
            "SPEC1",
            "notes",
            "",
            LanguageOption.ENGLISH,
            "user1",
            TEMPLATES_DIR,
        )

        html = _review_comment_html(mock_patch_spec)
        assert html.endswith("</div></div></body></html>")
        assert "notes" in html

    async def test_html_escaping_in_notes(self, mock_patch_spec):
        await patch_review_result_for_test_structure_element(
            MagicMock(),
            "PROJ1",
            "SPEC1",
            "<script>alert('xss')</script> & safer",
            "",
            LanguageOption.ENGLISH,
            "user1",
            TEMPLATES_DIR,
        )

        html = _review_comment_html(mock_patch_spec)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "&amp;" in html

    async def test_locker_cleared_and_reviewer_set(self, mock_patch_spec):
        await patch_review_result_for_test_structure_element(
            MagicMock(),
            "PROJ1",
            "SPEC1",
            "notes",
            "",
            LanguageOption.ENGLISH,
            "user42",
            TEMPLATES_DIR,
        )

        spec_update: SpecificationDetailsForUpdate = mock_patch_spec.call_args[0][3]
        assert spec_update.locker.optional is None
        assert spec_update.reviewer.optional == "user42"
        assert spec_update.reviewComment.images == []


class TestPatchPreviousReviewComment:
    """Tests for ``patch_previous_review_comment_for_test_structure_element``."""

    async def test_calls_patch_on_failure(self, mock_patch_spec):
        await patch_previous_review_comment_for_test_structure_element(
            MagicMock(),
            "PROJ1",
            "SPEC1",
            "prev comment",
            LanguageOption.ENGLISH,
            "user1",
            TEMPLATES_DIR,
        )

        mock_patch_spec.assert_awaited_once()

    async def test_full_html_structure_with_previous_content(self, mock_patch_spec, frozen_time):
        await patch_previous_review_comment_for_test_structure_element(
            MagicMock(),
            "PROJ1",
            "SPEC1",
            "<p>Previous</p>",
            LanguageOption.ENGLISH,
            "user1",
            TEMPLATES_DIR,
        )

        expected_html = (
            "<html><body>"
            "<b>AI Review failed - 2025-09-16 12:34:56</b>"
            "<br/>Please contact the system administrator for further details."
            "<br/><br/><p>Previous</p>"
            "</body></html>"
        )
        assert _review_comment_html(mock_patch_spec) == expected_html

    async def test_empty_previous_omits_previous_block(self, mock_patch_spec):
        await patch_previous_review_comment_for_test_structure_element(
            MagicMock(), "PROJ1", "SPEC1", "", LanguageOption.ENGLISH, "user1", TEMPLATES_DIR
        )

        html = _review_comment_html(mock_patch_spec)
        assert html.endswith("for further details.</body></html>")

    async def test_locker_cleared_and_reviewer_set(self, mock_patch_spec):
        await patch_previous_review_comment_for_test_structure_element(
            MagicMock(), "PROJ1", "SPEC1", "", LanguageOption.ENGLISH, "user42", TEMPLATES_DIR
        )

        spec_update: SpecificationDetailsForUpdate = mock_patch_spec.call_args[0][3]
        assert spec_update.locker.optional is None
        assert spec_update.reviewer.optional == "user42"
        assert spec_update.reviewComment.images == []


class TestKeepLockedOnFinalPatch:
    """The lock held before the run must survive the final patch."""

    @patch(
        "testbench_ai_service.agents.test_case_set_reviewer.utils.patch_test_structure_element_spec",
        new_callable=AsyncMock,
    )
    async def test_review_result_keeps_lock_when_locked_before_run(self, mock_patch_spec):
        await patch_review_result_for_test_structure_element(
            MagicMock(),
            "PROJ1",
            "SPEC1",
            "Review notes",
            "",
            LanguageOption.ENGLISH,
            "user123",
            TEMPLATES_DIR,
            keep_locked=True,
        )
        called_spec: SpecificationDetailsForUpdate = mock_patch_spec.call_args[0][3]
        assert called_spec.locker.optional == "user123"

    @patch(
        "testbench_ai_service.agents.test_case_set_reviewer.utils.patch_test_structure_element_spec",
        new_callable=AsyncMock,
    )
    async def test_review_result_unlocks_by_default(self, mock_patch_spec):
        await patch_review_result_for_test_structure_element(
            MagicMock(),
            "PROJ1",
            "SPEC1",
            "Review notes",
            "",
            LanguageOption.ENGLISH,
            "user123",
            TEMPLATES_DIR,
        )
        called_spec: SpecificationDetailsForUpdate = mock_patch_spec.call_args[0][3]
        assert called_spec.locker.optional is None

    @patch(
        "testbench_ai_service.agents.test_case_set_reviewer.utils.patch_test_structure_element_spec",
        new_callable=AsyncMock,
    )
    async def test_failed_run_keeps_lock_when_locked_before_run(self, mock_patch_spec):
        await patch_previous_review_comment_for_test_structure_element(
            MagicMock(),
            "PROJ1",
            "SPEC1",
            "",
            LanguageOption.ENGLISH,
            "user123",
            TEMPLATES_DIR,
            keep_locked=True,
        )
        called_spec: SpecificationDetailsForUpdate = mock_patch_spec.call_args[0][3]
        assert called_spec.locker.optional == "user123"

    @patch(
        "testbench_ai_service.agents.test_case_set_reviewer.utils.patch_test_structure_element_spec",
        new_callable=AsyncMock,
    )
    async def test_failed_run_unlocks_by_default(self, mock_patch_spec):
        await patch_previous_review_comment_for_test_structure_element(
            MagicMock(),
            "PROJ1",
            "SPEC1",
            "",
            LanguageOption.ENGLISH,
            "user123",
            TEMPLATES_DIR,
        )
        called_spec: SpecificationDetailsForUpdate = mock_patch_spec.call_args[0][3]
        assert called_spec.locker.optional is None
