import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

from testbench_ai_service.agents.test_case_set_describer.utils import (
    get_description_for_test_case_set,
    patch_description_generation_started_for_test_structure_element,
    patch_generated_description_for_test_structure_element,
    patch_previous_description_for_test_structure_element,
)
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.testbench import SpecificationDetailsForUpdate
from testbench_ai_service.utils.testbench_helpers import get_parameter_combinations_as_string


class _DummyParameter:
    def __init__(self, name: str, value: str):
        self.name = name
        self.value = value


class _DummyTestCase:
    def __init__(self, unique_id: str, parameters: list):
        self.uniqueID = unique_id
        self.parameters = parameters


class _DummyTestCaseSet:
    def __init__(self, test_cases: dict):
        self.test_cases = test_cases


class TestGetParameterCombinationsAsString(unittest.TestCase):
    """Tests for ``get_parameter_combinations_as_string``."""

    def test_single_test_case_single_param_produces_correct_headers_and_row(self):
        tc = _DummyTestCase("TC1", [_DummyParameter("ParamA", "ValueA")])
        result = get_parameter_combinations_as_string(_DummyTestCaseSet({"tc1": tc}))
        self.assertIn("| uniqueID | ParamA |", result)
        self.assertIn("| TC1 | ValueA |", result)

    def test_multiple_test_cases_multiple_params(self):
        tc1 = _DummyTestCase("TC1", [_DummyParameter("A", "1"), _DummyParameter("B", "2")])
        tc2 = _DummyTestCase("TC2", [_DummyParameter("A", "3"), _DummyParameter("B", "4")])
        result = get_parameter_combinations_as_string(_DummyTestCaseSet({"tc1": tc1, "tc2": tc2}))
        self.assertIn("| uniqueID | A | B |", result)
        self.assertIn("| TC1 | 1 | 2 |", result)
        self.assertIn("| TC2 | 3 | 4 |", result)

    def test_missing_param_in_some_test_cases_produces_empty_cell(self):
        tc1 = _DummyTestCase("TC1", [_DummyParameter("A", "1")])
        tc2 = _DummyTestCase("TC2", [_DummyParameter("B", "2")])
        result = get_parameter_combinations_as_string(_DummyTestCaseSet({"tc1": tc1, "tc2": tc2}))
        self.assertIn("| uniqueID | A | B |", result)
        self.assertIn("| TC1 | 1 |  |", result)
        self.assertIn("| TC2 |  | 2 |", result)

    def test_no_test_cases_returns_header_and_separator_only(self):
        result = get_parameter_combinations_as_string(_DummyTestCaseSet({}))
        self.assertTrue(result.startswith("| uniqueID |"))
        self.assertEqual(len(result.strip().splitlines()), 2)  # header + separator

    def test_empty_parameters_produces_id_only_columns(self):
        tc = _DummyTestCase("TC1", [])
        result = get_parameter_combinations_as_string(_DummyTestCaseSet({"tc1": tc}))
        self.assertIn("| uniqueID |", result)
        self.assertIn("| TC1 |", result)


class TestGetDescriptionForTestCaseSet(unittest.IsolatedAsyncioTestCase):
    """Tests for ``get_description_for_test_case_set``."""

    @patch(
        "testbench_ai_service.agents.test_case_set_describer.utils.strip_html_body_tags",
        return_value="Clean description",
    )
    @patch("testbench_ai_service.agents.test_case_set_describer.utils.TestCaseSetDetails")
    async def test_strips_html_from_spec_description(self, mock_tcs_class, mock_strip):
        mock_conn = MagicMock()
        mock_conn.get_project_test_case_set.return_value = {"some": "data"}
        mock_instance = MagicMock()
        mock_instance.spec.description = "<body>Hello</body>"
        mock_tcs_class.model_validate.return_value = mock_instance

        result = await get_description_for_test_case_set(mock_conn, "PROJ1", "TCS1")

        mock_tcs_class.model_validate.assert_called_once_with({"some": "data"})
        mock_strip.assert_called_once_with("<body>Hello</body>")
        self.assertEqual(result, "Clean description")

    @patch(
        "testbench_ai_service.agents.test_case_set_describer.utils.strip_html_body_tags",
        return_value="Stripped text",
    )
    @patch("testbench_ai_service.agents.test_case_set_describer.utils.TestCaseSetDetails")
    async def test_empty_description_delegates_to_strip(self, mock_tcs_class, mock_strip):
        mock_conn = MagicMock()
        mock_conn.get_project_test_case_set = AsyncMock(return_value={})
        mock_instance = MagicMock()
        mock_instance.spec.description = ""
        mock_tcs_class.model_validate.return_value = mock_instance

        result = await get_description_for_test_case_set(mock_conn, "P", "T")

        mock_strip.assert_called_once_with("")
        self.assertEqual(result, "Stripped text")


class TestPatchDescriptionGenerationStarted(unittest.IsolatedAsyncioTestCase):
    """Tests for ``patch_description_generation_started_for_test_structure_element``."""

    @patch(
        "testbench_ai_service.agents.test_case_set_describer.utils.patch_test_structure_element_spec",
        new_callable=AsyncMock,
    )
    @patch("testbench_ai_service.agents.test_case_set_describer.utils.get_translation")
    @patch("testbench_ai_service.agents.test_case_set_describer.utils.datetime")
    async def test_patches_spec_with_started_html_and_user_metadata(
        self, mock_datetime, mock_translate, mock_patch_spec
    ):
        mock_datetime.now.return_value = datetime(
            2025, 9, 16, 12, 34, 56, tzinfo=ZoneInfo("Europe/Berlin")
        )
        mock_translate.return_value = "Generation started"
        mock_patch_spec.return_value = "patched_result"
        previous_description = "<p>Old description</p>"

        result = await patch_description_generation_started_for_test_structure_element(
            MagicMock(),
            "PROJ1",
            "SPEC1",
            previous_description,
            LanguageOption.ENGLISH,
            "user123",
        )

        expected_html = (
            "<html><body>2025-09-16 12:34:56 - Generation started"
            "<br/><br/><p>Old description</p></body></html>"
        )
        called_spec: SpecificationDetailsForUpdate = mock_patch_spec.call_args[0][3]
        self.assertIsInstance(called_spec, SpecificationDetailsForUpdate)
        self.assertEqual(called_spec.description.html, expected_html)
        self.assertEqual(called_spec.reviewer.optional, "user123")
        self.assertEqual(called_spec.locker.optional, "user123")
        self.assertEqual(called_spec.description.images, [])
        self.assertEqual(result, "patched_result")


class TestPatchGeneratedDescription(unittest.IsolatedAsyncioTestCase):
    """Tests for ``patch_generated_description_for_test_structure_element``."""

    @patch(
        "testbench_ai_service.agents.test_case_set_describer.utils.patch_test_structure_element_spec",
        new_callable=AsyncMock,
    )
    @patch("testbench_ai_service.agents.test_case_set_describer.utils.get_translation")
    @patch("testbench_ai_service.agents.test_case_set_describer.utils.datetime")
    async def test_patches_spec_html_with_previous_and_generated_content(
        self, mock_datetime, mock_translate, mock_patch_spec
    ):
        mock_datetime.now.return_value = datetime(
            2025, 9, 16, 12, 34, 56, tzinfo=ZoneInfo("Europe/Berlin")
        )
        mock_translate.return_value = "Result Heading"
        await patch_generated_description_for_test_structure_element(
            MagicMock(),
            "PROJ",
            "SPEC",
            "Line1\nLine2",
            "<p>Old desc</p>",
            LanguageOption.ENGLISH,
            "user123",
        )
        expected_html = (
            "<html><body><p>Old desc</p><br/><br/>"
            "<b>Result Heading - 2025-09-16 12:34:56</b><br/>"
            "Line1<br/>Line2"
            "<div style='padding: 5px;'>"
            "<div style='border-top: 1px solid black; width: 50%; font-size: 10px;'>"
            "Result Heading</div></div></body></html>"
        )
        called_spec: SpecificationDetailsForUpdate = mock_patch_spec.call_args[0][3]
        self.assertEqual(called_spec.description.html, expected_html)
        self.assertEqual(called_spec.description.images, [])
        self.assertEqual(called_spec.reviewer.optional, "user123")
        self.assertIsNone(called_spec.locker.optional)

    @patch(
        "testbench_ai_service.agents.test_case_set_describer.utils.patch_test_structure_element_spec",
        new_callable=AsyncMock,
    )
    @patch(
        "testbench_ai_service.agents.test_case_set_describer.utils.get_translation",
    )
    @patch("testbench_ai_service.agents.test_case_set_describer.utils.datetime")
    async def test_empty_previous_description_omits_separator(
        self, mock_datetime, mock_translate, mock_patch_spec
    ):
        mock_datetime.now.return_value = datetime(
            2025, 9, 16, 12, 34, 56, tzinfo=ZoneInfo("Europe/Berlin")
        )
        mock_translate.return_value = "Result Heading"
        await patch_generated_description_for_test_structure_element(
            MagicMock(),
            "PROJ",
            "SPEC",
            "Line1\nLine2",
            "",
            LanguageOption.ENGLISH,
            "user123",
        )
        called_spec: SpecificationDetailsForUpdate = mock_patch_spec.call_args[0][3]
        expected_html = (
            "<html><body><b>Result Heading - 2025-09-16 12:34:56</b><br/>"
            "Line1<br/>Line2</body></html>"
        )
        self.assertEqual(called_spec.description.html, expected_html)


class TestPatchPreviousDescription(unittest.IsolatedAsyncioTestCase):
    """Tests for ``patch_previous_description_for_test_structure_element``."""

    @patch(
        "testbench_ai_service.agents.test_case_set_describer.utils.patch_test_structure_element_spec",
        new_callable=AsyncMock,
    )
    async def test_restores_previous_description_and_clears_locker(self, mock_patch_spec):
        mock_patch_spec.return_value = "patched_result"
        previous_description = "<p>Old description</p>"

        result = await patch_previous_description_for_test_structure_element(
            MagicMock(),
            "PROJ1",
            "SPEC1",
            previous_description,
            LanguageOption.ENGLISH,
            "user123",
        )

        self.assertEqual(result, "patched_result")
        called_spec: SpecificationDetailsForUpdate = mock_patch_spec.call_args[0][3]
        self.assertIsInstance(called_spec, SpecificationDetailsForUpdate)
        self.assertIn("<p>Old description</p>", called_spec.description.html)
        self.assertEqual(called_spec.description.images, [])
        self.assertEqual(called_spec.reviewer.optional, "user123")
        self.assertIsNone(called_spec.locker.optional)


if __name__ == "__main__":
    unittest.main()
