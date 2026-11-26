from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from testbench_ai_service.agents.test_case_set_describer.utils import (
    patch_description_generation_started_for_test_structure_element,
    patch_generated_description_for_test_structure_element,
    patch_previous_description_for_test_structure_element,
)
from testbench_ai_service.config import TEMPLATES_DIR
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.testbench import SpecificationDetailsForUpdate
from testbench_ai_service.utils.testbench_helpers import parameter_combinations_as_str


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


class TestParameterCombinationsAsStr:
    """Tests for ``parameter_combinations_as_str``."""

    def test_single_test_case_single_param_produces_correct_headers_and_row(self):
        tc = _DummyTestCase("TC1", [_DummyParameter("ParamA", "ValueA")])
        result = parameter_combinations_as_str(_DummyTestCaseSet({"tc1": tc}))
        assert "| uniqueID | ${ParamA} |" in result
        assert "| TC1 | ValueA |" in result

    def test_multiple_test_cases_multiple_params(self):
        tc1 = _DummyTestCase("TC1", [_DummyParameter("A", "1"), _DummyParameter("B", "2")])
        tc2 = _DummyTestCase("TC2", [_DummyParameter("A", "3"), _DummyParameter("B", "4")])
        result = parameter_combinations_as_str(_DummyTestCaseSet({"tc1": tc1, "tc2": tc2}))
        assert "| uniqueID | ${A} | ${B} |" in result
        assert "| TC1 | 1 | 2 |" in result
        assert "| TC2 | 3 | 4 |" in result

    def test_missing_param_in_some_test_cases_produces_empty_cell(self):
        tc1 = _DummyTestCase("TC1", [_DummyParameter("A", "1")])
        tc2 = _DummyTestCase("TC2", [_DummyParameter("B", "2")])
        result = parameter_combinations_as_str(_DummyTestCaseSet({"tc1": tc1, "tc2": tc2}))
        assert "| uniqueID | ${A} | ${B} |" in result
        assert "| TC1 | 1 |  |" in result
        assert "| TC2 |  | 2 |" in result

    def test_no_test_cases_returns_header_and_separator_only(self):
        result = parameter_combinations_as_str(_DummyTestCaseSet({}))
        assert result.startswith("| uniqueID |")
        assert len(result.strip().splitlines()) == 2  # header + separator

    def test_empty_parameters_produces_id_only_columns(self):
        tc = _DummyTestCase("TC1", [])
        result = parameter_combinations_as_str(_DummyTestCaseSet({"tc1": tc}))
        assert "| uniqueID |" in result
        assert "| TC1 |" in result


FROZEN_NOW = datetime(2025, 9, 16, 12, 34, 56, tzinfo=ZoneInfo("Europe/Berlin"))
DISCLAIMER_HTML = (
    "<div style='padding-top: 5px;'>"
    "<div style='border-top: 1px solid black; width: 218px; font-size: 10px;'>"
    "AI-generated responses may be inaccurate.</div></div>"
)


def _compact(html: str) -> str:
    """Drop the indentation and line breaks the jinja templates put around the markup."""
    return "".join(line.strip() for line in html.splitlines())


@pytest.fixture
def mock_patch_spec():
    with patch(
        "testbench_ai_service.agents.test_case_set_describer.utils.patch_test_structure_element_spec",
        new_callable=AsyncMock,
    ) as mock_patch:
        yield mock_patch


@pytest.fixture
def frozen_time():
    with patch("testbench_ai_service.utils.time_utils.datetime") as mock_datetime:
        mock_datetime.now.return_value = FROZEN_NOW
        yield


def _description_html(mock_patch_spec) -> str:
    called_spec: SpecificationDetailsForUpdate = mock_patch_spec.call_args[0][3]
    return _compact(called_spec.description.html)


class TestPatchDescriptionGenerationStarted:
    """Tests for ``patch_description_generation_started_for_test_structure_element``."""

    async def test_patches_spec_with_started_html_and_user_metadata(
        self, mock_patch_spec, frozen_time
    ):
        mock_patch_spec.return_value = "patched_result"

        result = await patch_description_generation_started_for_test_structure_element(
            MagicMock(),
            "PROJ1",
            "SPEC1",
            "<p>Old description</p>",
            LanguageOption.ENGLISH,
            "user123",
            TEMPLATES_DIR,
        )

        expected_html = (
            "<html><body>2025-09-16 12:34:56 - AI description generation started ..."
            "<br/><br/><p>Old description</p></body></html>"
        )
        called_spec: SpecificationDetailsForUpdate = mock_patch_spec.call_args[0][3]
        assert isinstance(called_spec, SpecificationDetailsForUpdate)
        assert _description_html(mock_patch_spec) == expected_html
        assert called_spec.reviewer.optional == "user123"
        assert called_spec.locker.optional == "user123"
        assert called_spec.description.images == []
        assert result == "patched_result"

    async def test_empty_previous_description_omits_separator(self, mock_patch_spec, frozen_time):
        await patch_description_generation_started_for_test_structure_element(
            MagicMock(),
            "PROJ1",
            "SPEC1",
            "",
            LanguageOption.ENGLISH,
            "user123",
            TEMPLATES_DIR,
        )

        expected_html = (
            "<html><body>2025-09-16 12:34:56 - AI description generation started ...</body></html>"
        )
        assert _description_html(mock_patch_spec) == expected_html

    async def test_uses_template_of_requested_language(self, mock_patch_spec, frozen_time):
        await patch_description_generation_started_for_test_structure_element(
            MagicMock(),
            "PROJ1",
            "SPEC1",
            "",
            LanguageOption.GERMAN,
            "user123",
            TEMPLATES_DIR,
        )

        html = _description_html(mock_patch_spec)
        assert "AI description generation started" not in html
        assert html.startswith("<html><body>2025-09-16 12:34:56 - ")

    async def test_missing_template_raises(self, mock_patch_spec, tmp_path):
        with pytest.raises(FileNotFoundError, match=r"started\.jinja"):
            await patch_description_generation_started_for_test_structure_element(
                MagicMock(), "PROJ1", "SPEC1", "", LanguageOption.ENGLISH, "user123", tmp_path
            )

        mock_patch_spec.assert_not_awaited()


class TestPatchGeneratedDescription:
    """Tests for ``patch_generated_description_for_test_structure_element``."""

    async def test_patches_spec_html_with_previous_and_generated_content(
        self, mock_patch_spec, frozen_time
    ):
        await patch_generated_description_for_test_structure_element(
            MagicMock(),
            "PROJ",
            "SPEC",
            "Line1\nLine2",
            "<p>Old desc</p>",
            LanguageOption.ENGLISH,
            "user123",
            TEMPLATES_DIR,
        )

        expected_html = (
            "<html><body><p>Old desc</p><br/><br/>"
            "<b>AI Description - 2025-09-16 12:34:56</b><br/>"
            "Line1<br/>Line2" + DISCLAIMER_HTML + "</body></html>"
        )
        called_spec: SpecificationDetailsForUpdate = mock_patch_spec.call_args[0][3]
        assert _description_html(mock_patch_spec) == expected_html
        assert called_spec.description.images == []
        assert called_spec.reviewer.optional == "user123"
        assert called_spec.locker.optional is None

    async def test_empty_previous_description_omits_separator(self, mock_patch_spec, frozen_time):
        await patch_generated_description_for_test_structure_element(
            MagicMock(),
            "PROJ",
            "SPEC",
            "Line1\nLine2",
            "",
            LanguageOption.ENGLISH,
            "user123",
            TEMPLATES_DIR,
        )

        expected_html = (
            "<html><body><b>AI Description - 2025-09-16 12:34:56</b><br/>"
            "Line1<br/>Line2" + DISCLAIMER_HTML + "</body></html>"
        )
        assert _description_html(mock_patch_spec) == expected_html

    async def test_html_special_characters_in_description_are_escaped(self, mock_patch_spec):
        await patch_generated_description_for_test_structure_element(
            MagicMock(),
            "PROJ",
            "SPEC",
            "<script>alert('xss')</script> & safer",
            "",
            LanguageOption.ENGLISH,
            "user123",
            TEMPLATES_DIR,
        )

        html = _description_html(mock_patch_spec)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "&amp;" in html


class TestPatchPreviousDescription:
    """Tests for ``patch_previous_description_for_test_structure_element``."""

    async def test_restores_previous_description_and_clears_locker(self, mock_patch_spec):
        mock_patch_spec.return_value = "patched_result"

        result = await patch_previous_description_for_test_structure_element(
            MagicMock(),
            "PROJ1",
            "SPEC1",
            "<p>Old description</p>",
            LanguageOption.ENGLISH,
            "user123",
            TEMPLATES_DIR,
        )

        assert result == "patched_result"
        called_spec: SpecificationDetailsForUpdate = mock_patch_spec.call_args[0][3]
        assert isinstance(called_spec, SpecificationDetailsForUpdate)
        assert "<p>Old description</p>" in called_spec.description.html
        assert called_spec.description.images == []
        assert called_spec.reviewer.optional == "user123"
        assert called_spec.locker.optional is None

    async def test_full_html_structure_with_previous_content(self, mock_patch_spec, frozen_time):
        await patch_previous_description_for_test_structure_element(
            MagicMock(),
            "PROJ1",
            "SPEC1",
            "<p>Old desc</p>",
            LanguageOption.ENGLISH,
            "user123",
            TEMPLATES_DIR,
        )

        expected_html = (
            "<html><body><p>Old desc</p><br/><br/>"
            "<b>AI Description failed - 2025-09-16 12:34:56</b>"
            "<br/>Please contact the system administrator for further details.</body></html>"
        )
        assert _description_html(mock_patch_spec) == expected_html

    async def test_empty_previous_description_omits_separator(self, mock_patch_spec):
        await patch_previous_description_for_test_structure_element(
            MagicMock(),
            "PROJ1",
            "SPEC1",
            "",
            LanguageOption.ENGLISH,
            "user123",
            TEMPLATES_DIR,
        )

        assert "<br/><br/>" not in _description_html(mock_patch_spec)


class TestKeepLockedOnFinalPatch:
    """The lock held before the run must survive the final patch."""

    @patch(
        "testbench_ai_service.agents.test_case_set_describer.utils.patch_test_structure_element_spec",
        new_callable=AsyncMock,
    )
    async def test_generated_description_keeps_lock_when_locked_before_run(self, mock_patch_spec):
        await patch_generated_description_for_test_structure_element(
            MagicMock(),
            "PROJ1",
            "SPEC1",
            "New description",
            "",
            LanguageOption.ENGLISH,
            "user123",
            TEMPLATES_DIR,
            keep_locked=True,
        )
        called_spec: SpecificationDetailsForUpdate = mock_patch_spec.call_args[0][3]
        assert called_spec.locker.optional == "user123"

    @patch(
        "testbench_ai_service.agents.test_case_set_describer.utils.patch_test_structure_element_spec",
        new_callable=AsyncMock,
    )
    async def test_generated_description_unlocks_by_default(self, mock_patch_spec):
        await patch_generated_description_for_test_structure_element(
            MagicMock(),
            "PROJ1",
            "SPEC1",
            "New description",
            "",
            LanguageOption.ENGLISH,
            "user123",
            TEMPLATES_DIR,
        )
        called_spec: SpecificationDetailsForUpdate = mock_patch_spec.call_args[0][3]
        assert called_spec.locker.optional is None

    @patch(
        "testbench_ai_service.agents.test_case_set_describer.utils.patch_test_structure_element_spec",
        new_callable=AsyncMock,
    )
    async def test_failed_run_keeps_lock_when_locked_before_run(self, mock_patch_spec):
        await patch_previous_description_for_test_structure_element(
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
        "testbench_ai_service.agents.test_case_set_describer.utils.patch_test_structure_element_spec",
        new_callable=AsyncMock,
    )
    async def test_failed_run_unlocks_by_default(self, mock_patch_spec):
        await patch_previous_description_for_test_structure_element(
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
