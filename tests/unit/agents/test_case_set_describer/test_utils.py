from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

from testbench_ai_service.agents.test_case_set_describer.utils import (
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


class TestGetParameterCombinationsAsString:
    """Tests for ``get_parameter_combinations_as_string``."""

    def test_single_test_case_single_param_produces_correct_headers_and_row(self):
        tc = _DummyTestCase("TC1", [_DummyParameter("ParamA", "ValueA")])
        result = get_parameter_combinations_as_string(_DummyTestCaseSet({"tc1": tc}))
        assert "| uniqueID | ParamA |" in result
        assert "| TC1 | ValueA |" in result

    def test_multiple_test_cases_multiple_params(self):
        tc1 = _DummyTestCase("TC1", [_DummyParameter("A", "1"), _DummyParameter("B", "2")])
        tc2 = _DummyTestCase("TC2", [_DummyParameter("A", "3"), _DummyParameter("B", "4")])
        result = get_parameter_combinations_as_string(_DummyTestCaseSet({"tc1": tc1, "tc2": tc2}))
        assert "| uniqueID | A | B |" in result
        assert "| TC1 | 1 | 2 |" in result
        assert "| TC2 | 3 | 4 |" in result

    def test_missing_param_in_some_test_cases_produces_empty_cell(self):
        tc1 = _DummyTestCase("TC1", [_DummyParameter("A", "1")])
        tc2 = _DummyTestCase("TC2", [_DummyParameter("B", "2")])
        result = get_parameter_combinations_as_string(_DummyTestCaseSet({"tc1": tc1, "tc2": tc2}))
        assert "| uniqueID | A | B |" in result
        assert "| TC1 | 1 |  |" in result
        assert "| TC2 |  | 2 |" in result

    def test_no_test_cases_returns_header_and_separator_only(self):
        result = get_parameter_combinations_as_string(_DummyTestCaseSet({}))
        assert result.startswith("| uniqueID |")
        assert len(result.strip().splitlines()) == 2  # header + separator

    def test_empty_parameters_produces_id_only_columns(self):
        tc = _DummyTestCase("TC1", [])
        result = get_parameter_combinations_as_string(_DummyTestCaseSet({"tc1": tc}))
        assert "| uniqueID |" in result
        assert "| TC1 |" in result


class TestPatchDescriptionGenerationStarted:
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
        assert isinstance(called_spec, SpecificationDetailsForUpdate)
        assert called_spec.description.html == expected_html
        assert called_spec.reviewer.optional == "user123"
        assert called_spec.locker.optional == "user123"
        assert called_spec.description.images == []
        assert result == "patched_result"


class TestPatchGeneratedDescription:
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
            "<div style='padding-top: 5px;'>"
            "<div style='border-top: 1px solid black; width: 218px; font-size: 10px;'>"
            "Result Heading</div></div></body></html>"
        )
        called_spec: SpecificationDetailsForUpdate = mock_patch_spec.call_args[0][3]
        assert called_spec.description.html == expected_html
        assert called_spec.description.images == []
        assert called_spec.reviewer.optional == "user123"
        assert called_spec.locker.optional is None

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
        assert called_spec.description.html == expected_html


class TestPatchPreviousDescription:
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

        assert result == "patched_result"
        called_spec: SpecificationDetailsForUpdate = mock_patch_spec.call_args[0][3]
        assert isinstance(called_spec, SpecificationDetailsForUpdate)
        assert "<p>Old description</p>" in called_spec.description.html
        assert called_spec.description.images == []
        assert called_spec.reviewer.optional == "user123"
        assert called_spec.locker.optional is None
