from unittest.mock import AsyncMock, MagicMock, patch

from testbench2robotframework.model import (
    KeywordCallType,
    KeywordType,
)

from testbench_ai_service.agents.test_case_set_reviewer.utils import (
    get_test_case_set_as_string,
    patch_previous_review_comment_for_test_structure_element,
    patch_review_result_for_test_structure_element,
    patch_review_started_for_test_structure_element,
)
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.testbench import SpecificationDetailsForUpdate
from testbench_ai_service.utils.testbench_helpers import get_interaction_calls_for_test_case


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


class TestGetInteractionCallsForTestCase:
    """Tests for ``get_interaction_calls_for_test_case``."""

    def test_returns_all_top_level_calls(self):
        calls = [
            _make_keyword_call("Step A", parent_id=None),
            _make_keyword_call("Step B", parent_id=None),
        ]
        tc = _make_test_case(calls)
        result = get_interaction_calls_for_test_case(tc)
        assert result == calls

    def test_excludes_child_calls(self):
        parent = _make_keyword_call("Parent", parent_id=None)
        child = _make_keyword_call("Child", parent_id="some-parent-id")
        tc = _make_test_case([parent, child])
        result = get_interaction_calls_for_test_case(tc)
        assert result == [parent]

    def test_empty_sequence_returns_empty_list(self):
        tc = _make_test_case([])
        result = get_interaction_calls_for_test_case(tc)
        assert result == []


class TestGetTestCaseSetAsString:
    """Tests for ``get_test_case_set_as_string``."""

    def test_first_line_is_test_case_set_name(self):
        step = _make_keyword_call("My Step")
        tc = _make_test_case([step])
        tcs = _make_test_case_set("My Test Case Set", {"tc1": tc})
        result = get_test_case_set_as_string(tcs)
        assert result.startswith("My Test Case Set")

    def test_includes_step_name(self):
        step = _make_keyword_call("Perform Action")
        tc = _make_test_case([step])
        tcs = _make_test_case_set("TCS", {"tc1": tc})
        result = get_test_case_set_as_string(tcs)
        assert "Perform Action" in result

    def test_flow_step_type_appended(self):
        step = _make_keyword_call(
            "Click Button", keyword_type=KeywordType.Atomic, call_type=KeywordCallType.Flow
        )
        tc = _make_test_case([step])
        tcs = _make_test_case_set("TCS", {"tc1": tc})
        result = get_test_case_set_as_string(tcs)
        assert "step_type:flow" in result

    def test_check_step_type_appended(self):
        step = _make_keyword_call(
            "Verify Result", keyword_type=KeywordType.Atomic, call_type=KeywordCallType.Check
        )
        tc = _make_test_case([step])
        tcs = _make_test_case_set("TCS", {"tc1": tc})
        result = get_test_case_set_as_string(tcs)
        assert "step_type:check" in result

    def test_textual_step_has_no_step_type(self):
        step = _make_keyword_call("Just Text", keyword_type=KeywordType.Textual)
        tc = _make_test_case([step])
        tcs = _make_test_case_set("TCS", {"tc1": tc})
        result = get_test_case_set_as_string(tcs)
        assert "step_type:" not in result

    def test_uses_first_test_case_only(self):
        """Only the first test case determines the steps."""
        step1 = _make_keyword_call("First Case Step")
        step2 = _make_keyword_call("Second Case Step")
        tc1 = _make_test_case([step1])
        tc2 = _make_test_case([step2])
        tcs = _make_test_case_set("TCS", {"tc1": tc1, "tc2": tc2})
        result = get_test_case_set_as_string(tcs)
        assert "First Case Step" in result
        assert "Second Case Step" not in result


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
