import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from testbench2robotframework.model import (
    KeywordCallType,
    KeywordType,
)

from testbench_ai_service.agents.test_case_set_reviewer.utils import (
    get_review_comment_for_test_case_set,
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


class TestGetInteractionCallsForTestCase(unittest.TestCase):
    """Tests for ``get_interaction_calls_for_test_case``."""

    def test_returns_all_top_level_calls(self):
        calls = [
            _make_keyword_call("Step A", parent_id=None),
            _make_keyword_call("Step B", parent_id=None),
        ]
        tc = _make_test_case(calls)
        result = get_interaction_calls_for_test_case(tc)
        self.assertEqual(result, calls)

    def test_excludes_child_calls(self):
        parent = _make_keyword_call("Parent", parent_id=None)
        child = _make_keyword_call("Child", parent_id="some-parent-id")
        tc = _make_test_case([parent, child])
        result = get_interaction_calls_for_test_case(tc)
        self.assertEqual(result, [parent])

    def test_empty_sequence_returns_empty_list(self):
        tc = _make_test_case([])
        result = get_interaction_calls_for_test_case(tc)
        self.assertEqual(result, [])


class TestGetTestCaseSetAsString(unittest.TestCase):
    """Tests for ``get_test_case_set_as_string``."""

    def test_first_line_is_test_case_set_name(self):
        step = _make_keyword_call("My Step")
        tc = _make_test_case([step])
        tcs = _make_test_case_set("My Test Case Set", {"tc1": tc})
        result = get_test_case_set_as_string(tcs)
        self.assertTrue(result.startswith("My Test Case Set"))

    def test_includes_step_name(self):
        step = _make_keyword_call("Perform Action")
        tc = _make_test_case([step])
        tcs = _make_test_case_set("TCS", {"tc1": tc})
        result = get_test_case_set_as_string(tcs)
        self.assertIn("Perform Action", result)

    def test_flow_step_type_appended(self):
        step = _make_keyword_call(
            "Click Button", keyword_type=KeywordType.Atomic, call_type=KeywordCallType.Flow
        )
        tc = _make_test_case([step])
        tcs = _make_test_case_set("TCS", {"tc1": tc})
        result = get_test_case_set_as_string(tcs)
        self.assertIn("step_type:flow", result)

    def test_check_step_type_appended(self):
        step = _make_keyword_call(
            "Verify Result", keyword_type=KeywordType.Atomic, call_type=KeywordCallType.Check
        )
        tc = _make_test_case([step])
        tcs = _make_test_case_set("TCS", {"tc1": tc})
        result = get_test_case_set_as_string(tcs)
        self.assertIn("step_type:check", result)

    def test_textual_step_has_no_step_type(self):
        step = _make_keyword_call("Just Text", keyword_type=KeywordType.Textual)
        tc = _make_test_case([step])
        tcs = _make_test_case_set("TCS", {"tc1": tc})
        result = get_test_case_set_as_string(tcs)
        self.assertNotIn("step_type:", result)

    def test_uses_first_test_case_only(self):
        """Only the first test case determines the steps."""
        step1 = _make_keyword_call("First Case Step")
        step2 = _make_keyword_call("Second Case Step")
        tc1 = _make_test_case([step1])
        tc2 = _make_test_case([step2])
        tcs = _make_test_case_set("TCS", {"tc1": tc1, "tc2": tc2})
        result = get_test_case_set_as_string(tcs)
        self.assertIn("First Case Step", result)
        self.assertNotIn("Second Case Step", result)


class TestGetReviewCommentForTestCaseSet(unittest.IsolatedAsyncioTestCase):
    """Tests for ``get_review_comment_for_test_case_set``."""

    async def test_returns_stripped_review_comment(self):
        conn = MagicMock()
        tcs_data = MagicMock()

        with (
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.TestCaseSetDetails.model_validate"
            ) as mock_validate,
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.strip_html_body_tags",
                return_value="Stripped comment",
            ),
        ):
            mock_tcs = MagicMock()
            mock_tcs.spec.reviewComment = "<html><body>Raw comment</body></html>"
            mock_validate.return_value = mock_tcs
            conn.get_project_test_case_set.return_value = tcs_data

            result = await get_review_comment_for_test_case_set(conn, "PROJ1", "TCS1")

        self.assertEqual(result, "Stripped comment")


class TestPatchReviewStarted(unittest.IsolatedAsyncioTestCase):
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
        self.assertIsInstance(spec_update, SpecificationDetailsForUpdate)
        self.assertIn("review started", spec_update.reviewComment.html.lower())

    async def test_html_contains_previous_review_comment(self):
        conn = MagicMock()
        previous = "Old review comment"

        with (
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.patch_test_structure_element_spec",
                new_callable=AsyncMock,
            ),
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.get_translation",
                return_value="Review started",
            ),
        ):
            await patch_review_started_for_test_structure_element(
                conn, "PROJ1", "SPEC1", previous, LanguageOption.ENGLISH, "user1"
            )


class TestPatchReviewResult(unittest.IsolatedAsyncioTestCase):
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
        self.assertIn("Issue found", spec_update.reviewComment.html)

    async def test_empty_review_notes_uses_translation(self):
        conn = MagicMock()

        with (
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.patch_test_structure_element_spec",
                new_callable=AsyncMock,
            ),
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.utils.get_translation",
                return_value="No notes available",
            ),
        ):
            # no exception should be raised when review_notes is empty
            await patch_review_result_for_test_structure_element(
                conn, "PROJ1", "SPEC1", "", "prev", LanguageOption.GERMAN, "user1"
            )


class TestPatchPreviousReviewComment(unittest.IsolatedAsyncioTestCase):
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


if __name__ == "__main__":
    unittest.main()
