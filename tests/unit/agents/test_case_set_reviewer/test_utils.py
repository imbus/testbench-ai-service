from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

from testbench2robotframework.model import (
    KeywordCallType,
    KeywordType,
)

from testbench_ai_service.agents.test_case_set_reviewer.utils import (
    patch_previous_review_comment_for_test_structure_element,
    patch_review_result_for_test_structure_element,
    patch_review_started_for_test_structure_element,
)
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


class TestPatchReviewStarted:
    """Tests for ``patch_review_started_for_test_structure_element``."""

    async def test_calls_patch_with_spec_update(self):
        conn = MagicMock()

        with (
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.patch_test_structure_element_spec",
                new_callable=AsyncMock,
            ) as mock_patch,
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.get_translation",
                return_value="Review started",
            ),
        ):
            await patch_review_started_for_test_structure_element(
                conn, "PROJ1", "SPEC1", "prev comment", LanguageOption.ENGLISH, "user1"
            )

        mock_patch.assert_awaited_once()
        call_args = mock_patch.call_args
        spec_update: SpecificationDetailsForUpdate = call_args[0][3]
        assert isinstance(spec_update, SpecificationDetailsForUpdate)
        assert "review started" in spec_update.reviewComment.html.lower()

    async def test_html_contains_previous_review_comment(self):
        conn = MagicMock()
        previous = "Old review comment"

        with (
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.patch_test_structure_element_spec",
                new_callable=AsyncMock,
            ) as mock_patch,
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.get_translation",
                return_value="Review started",
            ),
        ):
            await patch_review_started_for_test_structure_element(
                conn, "PROJ1", "SPEC1", previous, LanguageOption.ENGLISH, "user1"
            )

        spec_update: SpecificationDetailsForUpdate = mock_patch.call_args[0][3]
        assert previous in spec_update.reviewComment.html

    async def test_full_html_structure_with_previous_content(self):
        conn = MagicMock()
        with (
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.patch_test_structure_element_spec",
                new_callable=AsyncMock,
            ) as mock_patch,
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.get_translation",
                return_value="Review started",
            ),
            patch("testbench_ai_service.utils.time_utils.datetime") as mock_datetime,
        ):
            mock_datetime.now.return_value = datetime(
                2025, 9, 16, 12, 34, 56, tzinfo=ZoneInfo("Europe/Berlin")
            )
            await patch_review_started_for_test_structure_element(
                conn, "PROJ1", "SPEC1", "<p>Previous</p>", LanguageOption.ENGLISH, "user1"
            )
        expected_html = (
            "<html><body>2025-09-16 12:34:56 - Review started"
            "<br/><br/><p>Previous</p></body></html>"
        )
        spec_update: SpecificationDetailsForUpdate = mock_patch.call_args[0][3]
        assert spec_update.reviewComment.html == expected_html

    async def test_empty_previous_omits_separator(self):
        conn = MagicMock()
        with (
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.patch_test_structure_element_spec",
                new_callable=AsyncMock,
            ) as mock_patch,
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.get_translation",
                return_value="Review started",
            ),
        ):
            await patch_review_started_for_test_structure_element(
                conn, "PROJ1", "SPEC1", "", LanguageOption.ENGLISH, "user1"
            )
        spec_update: SpecificationDetailsForUpdate = mock_patch.call_args[0][3]
        assert "<br/>" not in spec_update.reviewComment.html
        assert "Review started" in spec_update.reviewComment.html

    async def test_locker_and_reviewer_metadata(self):
        conn = MagicMock()
        with (
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.patch_test_structure_element_spec",
                new_callable=AsyncMock,
            ) as mock_patch,
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.get_translation",
                return_value="Review started",
            ),
        ):
            await patch_review_started_for_test_structure_element(
                conn, "PROJ1", "SPEC1", "", LanguageOption.ENGLISH, "user42"
            )
        spec_update: SpecificationDetailsForUpdate = mock_patch.call_args[0][3]
        assert spec_update.locker.optional == "user42"
        assert spec_update.reviewer.optional == "user42"
        assert spec_update.reviewComment.images == []


class TestPatchReviewResult:
    """Tests for ``patch_review_result_for_test_structure_element``."""

    async def test_calls_patch_with_review_notes(self):
        conn = MagicMock()

        with (
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.patch_test_structure_element_spec",
                new_callable=AsyncMock,
            ) as mock_patch,
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.get_translation",
                side_effect=lambda key, lang: key,
            ),
        ):
            await patch_review_result_for_test_structure_element(
                conn, "PROJ1", "SPEC1", "- Issue found", "prev", LanguageOption.ENGLISH, "user1"
            )

        mock_patch.assert_awaited_once()
        spec_update: SpecificationDetailsForUpdate = mock_patch.call_args[0][3]
        assert "Issue found" in spec_update.reviewComment.html

    async def test_empty_review_notes_uses_translation(self):
        conn = MagicMock()

        with (
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.patch_test_structure_element_spec",
                new_callable=AsyncMock,
            ) as mock_patch,
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.get_translation",
                return_value="No notes available",
            ),
        ):
            await patch_review_result_for_test_structure_element(
                conn, "PROJ1", "SPEC1", "", "prev", LanguageOption.GERMAN, "user1"
            )

        spec_update: SpecificationDetailsForUpdate = mock_patch.call_args[0][3]
        assert "No notes available" in spec_update.reviewComment.html

    async def test_full_html_structure_with_previous_content(self):
        conn = MagicMock()
        with (
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.patch_test_structure_element_spec",
                new_callable=AsyncMock,
            ) as mock_patch,
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.get_translation",
                side_effect=lambda key, lang: key,
            ),
            patch("testbench_ai_service.utils.time_utils.datetime") as mock_datetime,
        ):
            mock_datetime.now.return_value = datetime(
                2025, 9, 16, 12, 34, 56, tzinfo=ZoneInfo("Europe/Berlin")
            )
            await patch_review_result_for_test_structure_element(
                conn, "PROJ1", "SPEC1", "Review note", "<p>Old</p>", LanguageOption.ENGLISH, "user1"
            )
        expected_html = (
            "<html><body>"
            "<b>test_case_set_reviewer.run.result_heading - 2025-09-16 12:34:56</b>"
            "<br/>Review note"
            "<div style='padding-top: 5px;'><div style='border-top: 1px solid black;"
            " width: 218px; font-size: 10px;'>shared.run.disclaimer</div></div>"
            "<br/><p>Old</p>"
            "</body></html>"
        )
        spec_update: SpecificationDetailsForUpdate = mock_patch.call_args[0][3]
        assert spec_update.reviewComment.html == expected_html

    async def test_empty_previous_omits_previous_block(self):
        conn = MagicMock()
        with (
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.patch_test_structure_element_spec",
                new_callable=AsyncMock,
            ) as mock_patch,
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.get_translation",
                side_effect=lambda key, lang: key,
            ),
        ):
            await patch_review_result_for_test_structure_element(
                conn, "PROJ1", "SPEC1", "notes", "", LanguageOption.ENGLISH, "user1"
            )
        spec_update: SpecificationDetailsForUpdate = mock_patch.call_args[0][3]
        assert spec_update.reviewComment.html.endswith("</div></div></body></html>")
        assert "notes" in spec_update.reviewComment.html

    async def test_html_escaping_in_notes(self):
        conn = MagicMock()
        with (
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.patch_test_structure_element_spec",
                new_callable=AsyncMock,
            ) as mock_patch,
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.get_translation",
                side_effect=lambda key, lang: key,
            ),
        ):
            await patch_review_result_for_test_structure_element(
                conn,
                "PROJ1",
                "SPEC1",
                "<script>alert('xss')</script> & safer",
                "",
                LanguageOption.ENGLISH,
                "user1",
            )
        html = mock_patch.call_args[0][3].reviewComment.html
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "&amp;" in html

    async def test_locker_cleared_and_reviewer_set(self):
        conn = MagicMock()
        with (
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.patch_test_structure_element_spec",
                new_callable=AsyncMock,
            ) as mock_patch,
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.get_translation",
                side_effect=lambda key, lang: key,
            ),
        ):
            await patch_review_result_for_test_structure_element(
                conn, "PROJ1", "SPEC1", "notes", "", LanguageOption.ENGLISH, "user42"
            )
        spec_update: SpecificationDetailsForUpdate = mock_patch.call_args[0][3]
        assert spec_update.locker.optional is None
        assert spec_update.reviewer.optional == "user42"
        assert spec_update.reviewComment.images == []


class TestPatchPreviousReviewComment:
    """Tests for ``patch_previous_review_comment_for_test_structure_element``."""

    async def test_calls_patch_on_failure(self):
        conn = MagicMock()

        with (
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.patch_test_structure_element_spec",
                new_callable=AsyncMock,
            ) as mock_patch,
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.get_translation",
                side_effect=lambda key, lang: key,
            ),
        ):
            await patch_previous_review_comment_for_test_structure_element(
                conn, "PROJ1", "SPEC1", "prev comment", LanguageOption.ENGLISH, "user1"
            )

        mock_patch.assert_awaited_once()

    async def test_full_html_structure_with_previous_content(self):
        conn = MagicMock()
        with (
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.patch_test_structure_element_spec",
                new_callable=AsyncMock,
            ) as mock_patch,
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.get_translation",
                side_effect=lambda key, lang: key,
            ),
            patch("testbench_ai_service.utils.time_utils.datetime") as mock_datetime,
        ):
            mock_datetime.now.return_value = datetime(
                2025, 9, 16, 12, 34, 56, tzinfo=ZoneInfo("Europe/Berlin")
            )
            await patch_previous_review_comment_for_test_structure_element(
                conn, "PROJ1", "SPEC1", "<p>Previous</p>", LanguageOption.ENGLISH, "user1"
            )
        expected_html = (
            "<html><body>"
            "<b>test_case_set_reviewer.run.failed_heading - 2025-09-16 12:34:56</b>"
            "<br/>shared.run.error_message"
            "<br/><br/><p>Previous</p>"
            "</body></html>"
        )
        spec_update: SpecificationDetailsForUpdate = mock_patch.call_args[0][3]
        assert spec_update.reviewComment.html == expected_html

    async def test_empty_previous_omits_previous_block(self):
        conn = MagicMock()
        with (
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.patch_test_structure_element_spec",
                new_callable=AsyncMock,
            ) as mock_patch,
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.get_translation",
                side_effect=lambda key, lang: key,
            ),
        ):
            await patch_previous_review_comment_for_test_structure_element(
                conn, "PROJ1", "SPEC1", "", LanguageOption.ENGLISH, "user1"
            )
        spec_update: SpecificationDetailsForUpdate = mock_patch.call_args[0][3]
        assert "<br/></body></html>" not in spec_update.reviewComment.html

    async def test_locker_cleared_and_reviewer_set(self):
        conn = MagicMock()
        with (
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.patch_test_structure_element_spec",
                new_callable=AsyncMock,
            ) as mock_patch,
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.get_translation",
                side_effect=lambda key, lang: key,
            ),
        ):
            await patch_previous_review_comment_for_test_structure_element(
                conn, "PROJ1", "SPEC1", "", LanguageOption.ENGLISH, "user42"
            )
        spec_update: SpecificationDetailsForUpdate = mock_patch.call_args[0][3]
        assert spec_update.locker.optional is None
        assert spec_update.reviewer.optional == "user42"
        assert spec_update.reviewComment.images == []
