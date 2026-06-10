import json
import tempfile
import zipfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from testbench2robotframework.model import KeywordType

from testbench_ai_service.agents.defect_explainer.model import (
    Comments,
    Result,
    TestCase,
    TestCaseSetProtocol,
)
from testbench_ai_service.agents.defect_explainer.utils import (
    add_explanations_to_comment,
    build_protocol_json,
    build_update_test_case_set,
    clean_up_comment,
    create_import_zip,
    custom_serializer,
    get_error_message,
    import_data,
)
from testbench_ai_service.agents.defect_explainer.utils import (
    test_case_execution_as_str as _tce_as_str,
)
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.testbench import (
    ActivityStatus,
    ExecStatus,
    Priority,
    SpecStatus,
    TestCaseExecutionSummary,
    TestCaseSetDetails,
    TestCaseSetExecutionSummary,
    TestCaseSetSpecificationSummary,
    TestCaseSpecificationSummary,
    TestCaseSummary,
    VerdictStatus,
)


@dataclass
class _DummyTCS:
    """Stand-in for ``TestCaseSetDetails`` used in zip-creation tests.

    Must be a dataclass so that ``dataclasses.asdict()`` can serialise it.
    """

    uniqueID: str = "TCS123"


def _make_tcs_details(key="key", test_cases=None):
    """Build a minimal ``TestCaseSetDetails`` with sensible defaults."""
    return TestCaseSetDetails(
        key=key,
        numbering="1.1",
        uniqueID="iTB-TC-001",
        name="name",
        spec=TestCaseSetSpecificationSummary(
            key="specKey",
            description="description",
            reviewComment="reviewComment",
            status=SpecStatus.InProgress,
            priority=Priority.Low,
            preConditions=[],
            postConditions=[],
            udfs=[],
            keywords=[],
            references=[],
            requirements=[],
        ),
        exec=TestCaseSetExecutionSummary(
            key="execKey",
            comments="comment",
            udfs=[],
            keywords=[],
        ),
        testCases=test_cases or [],
    )


def _make_keyword_call(
    name,
    numbering="1",
    verdict="Pass",
    keyword_type=None,
    parent_id=None,
    params=None,
):
    """Build a minimal keyword-call ``SimpleNamespace`` matching the utils API."""

    return SimpleNamespace(
        numbering=numbering,
        exec=SimpleNamespace(verdict=SimpleNamespace(name=verdict)),
        spec=SimpleNamespace(
            name=name,
            keywordType=keyword_type if keyword_type is not None else KeywordType.Atomic,
            callParameters=params or [],
        ),
        parentID=parent_id,
    )


def _make_param(name, value):
    return SimpleNamespace(name=name, value=value)


def _make_tcs_ns(set_name, test_sequence, test_case_key="tc1"):
    return SimpleNamespace(
        details=SimpleNamespace(name=set_name),
        test_cases={test_case_key: SimpleNamespace(testSequence=test_sequence)},
    )


class TestCleanUpComment:
    """Tests for ``clean_up_comment``."""

    _TABLE_ONLY = "<table><tr><td>data</td></tr></table>"
    _WITH_DISCLAIMER = (
        "<table><tr><td>data</td></tr></table>"
        "<div style='padding-top: 5px;'>"
        "<div style='border-top: 1px solid black;'>Disclaimer text</div>"
        "</div>"
    )
    _WITH_MULTILINE_DISCLAIMER = (
        "<table><tr><td>data</td></tr></table>"
        "<div style='padding-top: 5px;'>\n"
        "<div style='border-top: 1px solid black;'>\nDisclaimer text\n</div>\n"
        "</div>"
    )

    def test_no_disclaimer_returns_unchanged(self):
        assert clean_up_comment(self._TABLE_ONLY) == self._TABLE_ONLY

    def test_removes_disclaimer_div_after_table(self):
        result = clean_up_comment(self._WITH_DISCLAIMER)
        assert result == self._TABLE_ONLY

    def test_removes_multiline_disclaimer_div(self):
        result = clean_up_comment(self._WITH_MULTILINE_DISCLAIMER)
        assert result == self._TABLE_ONLY

    def test_empty_string_returns_empty(self):
        assert clean_up_comment("") == ""

    def test_plain_text_returns_unchanged(self):
        assert clean_up_comment("no html here") == "no html here"


class TestAddExplanationsToComment:
    """Tests for ``add_explanations_to_comment``."""

    _FAIL_COMMENT = (
        "<pre>Start Time:   2025-08-27 07:44:13.781 "
        "End Time:     2025-08-27 07:44:19.889 </pre>"
        "<table style='font-family: monospace; border: none; table-layout: auto;'>"
        "<tr><td>iTB-TC-20021-PC-30037</td><td></td>"
        "<td style='background-color: #ce3e01; color: #fff;'><b>FAIL</b></td>"
        "<td><pre>Example Domain != AKShgdl</pre></td></tr></table>"
    )

    _ERRORS = [  # noqa: RUF012
        {
            "failed_test_case": "iTB-TC-20021-PC-30037",
            "error": "Example Domain != AKShgdl",
            "explanation": "something went wrong",
        }
    ]

    @patch("testbench_ai_service.agents.defect_explainer.utils.get_translation")
    def test_appends_explanation_heading_and_text(self, mock_get_translation):
        mock_get_translation.return_value = "KI-Erklärung"
        result = add_explanations_to_comment(
            comment=self._FAIL_COMMENT,
            errors=self._ERRORS,
            language=LanguageOption.GERMAN,
        )
        assert "KI-Erklärung" in result
        assert "something went wrong" in result

    @patch("testbench_ai_service.agents.defect_explainer.utils.get_translation")
    def test_overrides_existing_explanation(self, mock_get_translation):
        """An existing explanation block is replaced rather than duplicated."""
        comment_with_old_explanation = (
            "<pre>Start Time:   2025-08-27 07:44:13.781"
            "End Time:     2025-08-27 07:44:19.889"
            "</pre><table style='font-family: monospace; border: none; table-layout: auto;'>"
            "<tr><td>iTB-TC-20021-PC-30037</td><td></td>"
            "<td style='background-color: #ce3e01; color: #fff;'><b>FAIL</b></td>"
            "<td><pre>Example Domain != AKShgdl"
            "<b>KI-Erklärung:</b><br>nothing went wrong</div></pre></td></tr></table>"
        )
        mock_get_translation.return_value = "KI-Erklärung"
        result = add_explanations_to_comment(
            comment=comment_with_old_explanation,
            errors=self._ERRORS,
            language=LanguageOption.GERMAN,
        )
        assert "something went wrong" in result
        assert "nothing went wrong" not in result

    @patch("testbench_ai_service.agents.defect_explainer.utils.get_translation")
    def test_replaces_existing_ai_div_on_second_run(self, mock_get_translation):
        """On a second run the <div class='ai'> wrapper produced by the first run is replaced."""
        comment_with_ai_div = (
            "<pre>Start Time:   2025-08-27 07:44:13.781 "
            "End Time:     2025-08-27 07:44:19.889 </pre>"
            "<table style='font-family: monospace; border: none; table-layout: auto;'>"
            "<tr><td>iTB-TC-20021-PC-30037</td><td></td>"
            "<td style='background-color: #ce3e01; color: #fff;'><b>FAIL</b></td>"
            "<td><pre>Example Domain != AKShgdl"
            "<div class='ai'><b>KI-Erklärung:</b><br>old explanation</div></pre></td></tr></table>"
        )
        mock_get_translation.return_value = "KI-Erklärung"
        result = add_explanations_to_comment(
            comment=comment_with_ai_div,
            errors=self._ERRORS,
            language=LanguageOption.GERMAN,
        )
        assert "something went wrong" in result
        assert "old explanation" not in result
        assert result.count("<div class='ai'>") == 1

    @patch("testbench_ai_service.agents.defect_explainer.utils.get_translation")
    def test_explanation_html_special_chars_are_escaped(self, mock_get_translation):
        """AI-generated explanation with HTML-special characters must be escaped."""
        mock_get_translation.return_value = "KI-Erklärung"
        errors_with_html = [
            {
                "failed_test_case": "iTB-TC-20021-PC-30037",
                "error": "Example Domain != AKShgdl",
                "explanation": "Got <Error> instead of <Success> & retry failed",
            }
        ]
        result = add_explanations_to_comment(
            comment=self._FAIL_COMMENT,
            errors=errors_with_html,
            language=LanguageOption.GERMAN,
        )
        assert "&lt;Error&gt;" in result
        assert "&lt;Success&gt;" in result
        assert "&amp;" in result
        assert "<Error>" not in result

    @patch("testbench_ai_service.agents.defect_explainer.utils.get_translation")
    def test_empty_comment_returns_empty_string(self, mock_get_translation):
        """An empty comment (no HTML table) should be returned unchanged."""
        mock_get_translation.return_value = "KI-Erklärung"
        result = add_explanations_to_comment(
            comment="", errors=self._ERRORS, language=LanguageOption.GERMAN
        )
        assert result == ""

    @patch("testbench_ai_service.agents.defect_explainer.utils.get_translation")
    def test_missing_error_message_adds_explanation_to_bottom_fallback(self, mock_get_translation):
        mock_get_translation.side_effect = ["KI-Erklärung", "KI-Hinweis"]
        errors_without_parseable_message = [
            {
                "failed_test_case": "iTB-TC-20021-PC-30037",
                "error": "plain text without FAIL table row",
                "explanation": "fallback explanation",
            }
        ]

        result = add_explanations_to_comment(
            comment=self._FAIL_COMMENT,
            errors=errors_without_parseable_message,
            language=LanguageOption.GERMAN,
        )

        assert 'class="ai-explainer"' in result
        assert "fallback explanation" in result
        assert "iTB-TC-20021-PC-30037" in result


class TestGetErrorMessage:
    """Tests for ``get_error_message``."""

    _PREFIX = (
        "<pre>Start Time:   2025-08-27 07:44:13.781 "
        "End Time:     2025-08-27 07:44:19.889 </pre>"
        "<table style='font-family: monospace; border: none; table-layout: auto;'>"
    )
    _SUFFIX = "</table>"

    def _row(self, uid, status, error=""):
        msg = f"<pre>{error}</pre>" if error else ""
        return (
            f"<tr><td>{uid}</td><td></td>"
            f"<td style='background-color: #ce3e01; color: #fff;'><b>{status}</b></td>"
            f"<td>{msg}</td></tr>"
        )

    def test_no_table_returns_empty_dict(self):
        comment = "<pre>Start Time: 07:44:13.781 End Time: 07:44:19.889 </pre>"
        assert get_error_message(comment) == {}

    def test_empty_comment_returns_empty_dict(self):
        assert get_error_message("") == {}

    def test_single_fail_row(self):
        comment = (
            self._PREFIX
            + self._row("iTB-TC-20021-PC-30037", "FAIL", "Example Domain != AKShgdl")
            + self._SUFFIX
        )
        expected = {
            "iTB-TC-20021-PC-30037": {"status": "FAIL", "error": "Example Domain != AKShgdl"}
        }
        assert get_error_message(comment) == expected

    def test_multiple_fail_rows(self):
        comment = (
            self._PREFIX
            + self._row("UID-1", "FAIL", "Error 1")
            + self._row("UID-2", "FAIL", "Error 2")
            + self._SUFFIX
        )
        expected = {
            "UID-1": {"status": "FAIL", "error": "Error 1"},
            "UID-2": {"status": "FAIL", "error": "Error 2"},
        }
        assert get_error_message(comment) == expected

    def test_pass_rows_are_ignored(self):
        comment = (
            self._PREFIX + self._row("UID-1", "PASS") + self._row("UID-2", "PASS") + self._SUFFIX
        )
        assert get_error_message(comment) == {}

    def test_mixed_pass_and_fail_rows(self):
        comment = (
            self._PREFIX
            + self._row("UID-PASS", "PASS")
            + self._row("UID-FAIL", "FAIL", "Bad assertion")
            + self._SUFFIX
        )
        expected = {"UID-FAIL": {"status": "FAIL", "error": "Bad assertion"}}
        assert get_error_message(comment) == expected


class TestBuildUpdateTestCaseSet:
    """Tests for ``build_update_test_case_set``."""

    def test_sets_updated_exec_comments(self):
        comment = "updated comment"
        details = _make_tcs_details()
        result = build_update_test_case_set(updated_comment=comment, test_case_set_details=details)
        assert result.exec.comments == comment


class TestBuildProtocolJson:
    """Tests for ``build_protocol_json``."""

    def test_no_test_cases_produces_empty_list(self):
        comment = "updated comment"
        details = _make_tcs_details()
        expected = TestCaseSetProtocol(
            testCaseSetKey="key",
            durationMillis=0,
            executionKey="execKey",
            comments=Comments(html=comment),
            testCases=[],
        )
        assert build_protocol_json(comment, details) == expected

    def test_with_test_cases_maps_execution_keys_and_results(self):
        tc1 = TestCaseSummary(
            uniqueID="iTB-TC-001-PC-001",
            index=1,
            spec=TestCaseSpecificationSummary(key="sp1", comments="", requirements=[]),
            exec=TestCaseExecutionSummary(
                key="ek1",
                status=ActivityStatus.Assigned,
                execStatus=ExecStatus.Blocked,
                verdict=VerdictStatus.Fail,
                defects=[],
                comments="",
            ),
        )
        tc2 = TestCaseSummary(
            uniqueID="iTB-TC-001-PC-002",
            index=2,
            spec=TestCaseSpecificationSummary(key="sp2", comments="", requirements=[]),
            exec=TestCaseExecutionSummary(
                key="ek2",
                status=ActivityStatus.Canceled,
                execStatus=ExecStatus.NotBlocked,
                verdict=VerdictStatus.Fail,
                defects=[],
                comments="",
            ),
        )
        details = _make_tcs_details(test_cases=[tc1, tc2])
        result = build_protocol_json("comment", details)
        assert len(result.testCases) == 2
        assert result.testCases[0] == TestCase(
            testCaseExecutionKey="ek1",
            durationMillis=0,
            uniqueID="iTB-TC-001-PC-001",
            result=Result(
                status=ActivityStatus.Assigned,
                execStatus=ExecStatus.Blocked,
                verdict=VerdictStatus.Fail,
            ),
        )


class TestImportData:
    """Tests for ``import_data``."""

    @patch("testbench_ai_service.agents.defect_explainer.utils.ImportJSONExecutionResults")
    @patch("testbench_ai_service.agents.defect_explainer.utils.ImportJsonParameters")
    @patch("testbench_ai_service.agents.defect_explainer.utils.ConnectionLog")
    async def test_calls_trigger_with_active_connection(
        self, mock_connection_log, mock_import_params, mock_import_results
    ):
        mock_conn = MagicMock()
        mock_task_data = MagicMock(project_key="PROJ123", cycle_key="CYCLE456")
        mock_path = Path("fake.json")

        mock_connection_instance = MagicMock()
        mock_connection_log.return_value = mock_connection_instance
        mock_params_instance = MagicMock()
        mock_import_params.return_value = mock_params_instance
        mock_importer_instance = MagicMock()
        mock_import_results.return_value = mock_importer_instance
        mock_importer_instance.trigger.return_value = True

        await import_data(mock_conn, mock_task_data, mock_path)

        mock_connection_log.assert_called_once()
        mock_connection_instance.add_connection.assert_called_once_with(mock_conn)
        mock_import_params.assert_called_once_with(
            inputPath=mock_path, projectKey="PROJ123", cycleKey="CYCLE456"
        )
        mock_import_results.assert_called_once_with(parameters=mock_params_instance)
        mock_importer_instance.trigger.assert_called_once_with(
            mock_connection_instance.active_connection
        )

    @patch("testbench_ai_service.agents.defect_explainer.utils.ImportJSONExecutionResults")
    @patch("testbench_ai_service.agents.defect_explainer.utils.ImportJsonParameters")
    @patch("testbench_ai_service.agents.defect_explainer.utils.ConnectionLog")
    async def test_trigger_is_called_exactly_once(
        self, mock_connection_log, mock_import_params, mock_import_results
    ):
        mock_importer_instance = MagicMock()
        mock_import_results.return_value = mock_importer_instance
        mock_importer_instance.trigger.return_value = True
        await import_data(MagicMock(), MagicMock(project_key="X", cycle_key="Y"), Path("x.zip"))
        mock_importer_instance.trigger.assert_called_once()


class TestCreateImportZip:
    """Tests for ``create_import_zip``."""

    @patch(
        "testbench_ai_service.agents.defect_explainer.utils.build_update_test_case_set",
        return_value=_DummyTCS(),
    )
    @patch("testbench_ai_service.agents.defect_explainer.utils.build_protocol_json")
    @patch(
        "testbench_ai_service.agents.defect_explainer.utils.custom_serializer",
        side_effect=str,
    )
    def test_creates_protocol_and_tcs_files(
        self, mock_serializer, mock_build_protocol, mock_build_tcs
    ):
        mock_protocol = MagicMock()
        mock_protocol.model_dump.return_value = {"protocol": "data"}
        mock_build_protocol.return_value = mock_protocol

        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "output.zip"
            create_import_zip("<new comment>", MagicMock(), zip_path)

            assert zip_path.exists()
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
                assert "protocol.json" in names
                assert "TCS123.json" in names
                protocol_content = json.loads(zf.read("protocol.json").decode())
                assert protocol_content[0]["protocol"] == "data"
                tcs_content = json.loads(zf.read("TCS123.json").decode())
                assert tcs_content == {"uniqueID": "TCS123"}

    @patch(
        "testbench_ai_service.agents.defect_explainer.utils.build_update_test_case_set",
        return_value=_DummyTCS("TCSX"),
    )
    @patch("testbench_ai_service.agents.defect_explainer.utils.build_protocol_json")
    def test_overwrites_existing_zip(self, mock_build_protocol, mock_build_tcs):
        """Calling twice should overwrite the first archive without raising."""
        mock_protocol = MagicMock()
        mock_protocol.model_dump.return_value = {"p": "v"}
        mock_build_protocol.return_value = mock_protocol

        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "out.zip"
            create_import_zip("c1", MagicMock(), zip_path)
            create_import_zip("c2", MagicMock(), zip_path)

            with zipfile.ZipFile(zip_path, "r") as zf:
                assert "protocol.json" in zf.namelist()
                assert "TCSX.json" in zf.namelist()


class TestCustomSerializer:
    """Tests for ``custom_serializer``."""

    class _Status(Enum):
        PASS = "PASS"
        FAIL = "FAIL"

    def test_returns_enum_value(self):
        assert custom_serializer(self._Status.PASS) == "PASS"
        assert custom_serializer(self._Status.FAIL) == "FAIL"

    def test_raises_type_error_for_string(self):
        with pytest.raises(TypeError) as exc_info:
            custom_serializer("not an enum")
        assert "str" in str(exc_info.value)

    def test_raises_type_error_for_number(self):
        with pytest.raises(TypeError) as exc_info:
            custom_serializer(42)
        assert "int" in str(exc_info.value)


class TestTestCaseExecutionAsStr:
    """Tests for ``test_case_execution_as_str``."""

    def test_empty_test_sequence_returns_set_name_only(self):
        tcs = _make_tcs_ns("EmptySet", [])
        assert _tce_as_str(tcs, "tc1") == "EmptySet"

    def test_single_keyword_without_params(self):
        kw = _make_keyword_call("Login Step", numbering="1", verdict="Pass")
        tcs = _make_tcs_ns("LoginSet", [kw])
        lines = _tce_as_str(tcs, "tc1").splitlines()
        assert lines[0] == "LoginSet"
        assert "Login Step" in lines[1]
        assert "►[Pass]" in lines[1]
        assert "=" not in lines[1]

    def test_keyword_params_are_rendered(self):
        params = [_make_param("Username", "admin"), _make_param("*Password", "secret")]
        kw = _make_keyword_call("Login Step", verdict="Fail", params=params)
        tcs = _make_tcs_ns("LoginSet", [kw])
        result = _tce_as_str(tcs, "tc1")
        assert "Username=admin" in result
        assert "Password=secret" in result  # leading '*' is stripped

    def test_compound_step_shows_children_on_fail(self):
        parent = _make_keyword_call(
            "Compound Step", numbering="1", verdict="Fail", keyword_type=KeywordType.Compound
        )
        child = _make_keyword_call("Child Step", numbering="1.1", verdict="Fail", parent_id="1")
        tcs = _make_tcs_ns("TestSet", [parent, child])
        result = _tce_as_str(tcs, "tc1")
        assert "Compound Step" in result
        assert "Child Step" in result

    def test_nested_children_hidden_when_parent_passes(self):
        parent = _make_keyword_call(
            "Passing Compound", numbering="1", verdict="Pass", keyword_type=KeywordType.Compound
        )
        child = _make_keyword_call("Child Step", numbering="1.1", verdict="Pass", parent_id="1")
        tcs = _make_tcs_ns("TestSet", [parent, child])
        result = _tce_as_str(tcs, "tc1")
        assert "Passing Compound" in result
        assert "Child Step" not in result

    def test_raises_value_error_for_unknown_test_case(self):
        tcs = _make_tcs_ns("TestSet", [])
        with pytest.raises(ValueError, match="unknown_key"):
            _tce_as_str(tcs, "unknown_key")

    def test_failed_compound_step_uses_down_triangle_prefix(self):
        step = _make_keyword_call(
            "Compound", numbering="1", verdict="Fail", keyword_type=KeywordType.Compound
        )
        tcs = _make_tcs_ns("TestSet", [step])
        lines = _tce_as_str(tcs, "tc1").splitlines()
        assert "▼[Fail]" in lines[1]

    def test_child_indent_is_deeper_than_parent(self):
        parent = _make_keyword_call(
            "Compound", numbering="1", verdict="Fail", keyword_type=KeywordType.Compound
        )
        child = _make_keyword_call("Child", numbering="1.1", verdict="Fail", parent_id="1")
        tcs = _make_tcs_ns("TestSet", [parent, child])
        lines = _tce_as_str(tcs, "tc1").splitlines()
        parent_indent = len(lines[1]) - len(lines[1].lstrip())
        child_indent = len(lines[2]) - len(lines[2].lstrip())
        assert child_indent > parent_indent

    def test_passed_siblings_on_failed_level_are_shown(self):
        parent = _make_keyword_call(
            "Compound", numbering="1", verdict="Fail", keyword_type=KeywordType.Compound
        )
        pass_sibling = _make_keyword_call(
            "PassChild", numbering="1.1", verdict="Pass", parent_id="1"
        )
        fail_sibling = _make_keyword_call(
            "FailChild", numbering="1.2", verdict="Fail", parent_id="1"
        )
        tcs = _make_tcs_ns("TestSet", [parent, pass_sibling, fail_sibling])

        result = _tce_as_str(tcs, "tc1")
        assert "PassChild" in result
        assert "FailChild" in result

    def test_children_hidden_after_passing_top_level_following_a_failed_one(self):
        fail_parent = _make_keyword_call(
            "FailStep", numbering="1", verdict="Fail", keyword_type=KeywordType.Compound
        )
        fail_child = _make_keyword_call("FailChild", numbering="1.1", verdict="Fail", parent_id="1")
        pass_parent = _make_keyword_call(
            "PassStep", numbering="2", verdict="Pass", keyword_type=KeywordType.Compound
        )
        pass_child = _make_keyword_call("PassChild", numbering="2.1", verdict="Fail", parent_id="2")
        tcs = _make_tcs_ns("TestSet", [fail_parent, fail_child, pass_parent, pass_child])
        result = _tce_as_str(tcs, "tc1")
        assert "FailChild" in result
        assert "PassChild" not in result

    def test_failed_step_comment_is_rendered_without_html_tags(self):
        fail_step = _make_keyword_call("FailAtomic", numbering="1", verdict="Fail")
        fail_step.exec.comments = "<div>Error&nbsp;line<br/>Details <b>here</b></div>"
        tcs = _make_tcs_ns("TestSet", [fail_step])

        result = _tce_as_str(tcs, "tc1")

        assert "Error line" in result
        assert "Details here" in result
        assert "<div>" not in result
        assert "<b>" not in result
