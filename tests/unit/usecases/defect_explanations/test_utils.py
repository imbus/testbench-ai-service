"""
- add_explanations_to_comment   (adds/overrides AI explanation in HTML comment)
- get_error_message             (parses FAIL entries from an HTML execution table)
- build_update_test_case_set    (constructs the update payload from TCS details)
- build_protocol_json           (builds the protocol import model)
- import_data                   (triggers a JSON execution-result import)
- create_import_zip             (creates a ZIP archive ready for import)
- custom_serializer             (JSON serializer helper for Enum values)
- get_test_case_set_as_string   (formats a test case set as a readable string)
"""

import json
import tempfile
import unittest
import zipfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from testbench2robotframework.model import KeywordType

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
from testbench_ai_service.usecases.defect_explanations.model import (
    Comments,
    Result,
    TestCase,
    TestCaseSetProtocol,
)
from testbench_ai_service.usecases.defect_explanations.utils import (
    add_explanations_to_comment,
    build_protocol_json,
    build_update_test_case_set,
    create_import_zip,
    custom_serializer,
    get_error_message,
    get_test_case_set_as_string,
    import_data,
)


@dataclass
class _DummyTCS:
    """Minimal stand-in for ``TestCaseSetDetails`` that supports ``asdict()``."""

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


class TestAddExplanationsToComment(unittest.TestCase):
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

    @patch("testbench_ai_service.usecases.defect_explanations.utils.get_translation")
    def test_appends_explanation_heading_and_text(self, mock_get_translation):
        mock_get_translation.return_value = "KI-Erklärung"
        result = add_explanations_to_comment(
            comment=self._FAIL_COMMENT,
            errors=self._ERRORS,
            language=LanguageOption.GERMAN,
        )
        self.assertIn("KI-Erklärung", result)
        self.assertIn("something went wrong", result)

    @patch("testbench_ai_service.usecases.defect_explanations.utils.get_translation")
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
        self.assertIn("something went wrong", result)
        self.assertNotIn("nothing went wrong", result)

    @patch("testbench_ai_service.usecases.defect_explanations.utils.get_translation")
    def test_empty_comment_returns_empty_string(self, mock_get_translation):
        """An empty comment (no HTML table) should be returned unchanged."""
        mock_get_translation.return_value = "KI-Erklärung"
        result = add_explanations_to_comment(
            comment="", errors=self._ERRORS, language=LanguageOption.GERMAN
        )
        self.assertEqual(result, "")


class TestGetErrorMessage(unittest.TestCase):
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
        self.assertDictEqual(get_error_message(comment), {})

    def test_empty_comment_returns_empty_dict(self):
        self.assertDictEqual(get_error_message(""), {})

    def test_single_fail_row(self):
        comment = (
            self._PREFIX
            + self._row("iTB-TC-20021-PC-30037", "FAIL", "Example Domain != AKShgdl")
            + self._SUFFIX
        )
        expected = {
            "iTB-TC-20021-PC-30037": {"status": "FAIL", "error": "Example Domain != AKShgdl"}
        }
        self.assertDictEqual(get_error_message(comment), expected)

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
        self.assertDictEqual(get_error_message(comment), expected)

    def test_pass_rows_are_ignored(self):
        comment = (
            self._PREFIX + self._row("UID-1", "PASS") + self._row("UID-2", "PASS") + self._SUFFIX
        )
        self.assertDictEqual(get_error_message(comment), {})

    def test_mixed_pass_and_fail_rows(self):
        comment = (
            self._PREFIX
            + self._row("UID-PASS", "PASS")
            + self._row("UID-FAIL", "FAIL", "Bad assertion")
            + self._SUFFIX
        )
        expected = {"UID-FAIL": {"status": "FAIL", "error": "Bad assertion"}}
        self.assertDictEqual(get_error_message(comment), expected)


class TestBuildUpdateTestCaseSet(unittest.TestCase):
    """Tests for ``build_update_test_case_set``."""

    def test_sets_updated_exec_comments(self):
        comment = "updated comment"
        details = _make_tcs_details()
        result = build_update_test_case_set(updated_comment=comment, test_case_set_details=details)
        self.assertEqual(result.exec.comments, comment)


class TestBuildProtocolJson(unittest.TestCase):
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
        self.assertEqual(build_protocol_json(comment, details), expected)

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
        self.assertEqual(len(result.testCases), 2)
        self.assertEqual(
            result.testCases[0],
            TestCase(
                testCaseExecutionKey="ek1",
                durationMillis=0,
                uniqueID="iTB-TC-001-PC-001",
                result=Result(
                    status=ActivityStatus.Assigned,
                    execStatus=ExecStatus.Blocked,
                    verdict=VerdictStatus.Fail,
                ),
            ),
        )


class TestImportData(unittest.TestCase):
    """Tests for ``import_data``."""

    @patch("testbench_ai_service.usecases.defect_explanations.utils.ImportJSONExecutionResults")
    @patch("testbench_ai_service.usecases.defect_explanations.utils.ImportJsonParameters")
    @patch("testbench_ai_service.usecases.defect_explanations.utils.ConnectionLog")
    def test_calls_trigger_with_active_connection(
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

        import_data(mock_conn, mock_task_data, mock_path)

        mock_connection_log.assert_called_once()
        mock_connection_instance.add_connection.assert_called_once_with(mock_conn)
        mock_import_params.assert_called_once_with(
            inputPath=mock_path, projectKey="PROJ123", cycleKey="CYCLE456"
        )
        mock_import_results.assert_called_once_with(parameters=mock_params_instance)
        mock_importer_instance.trigger.assert_called_once_with(
            mock_connection_instance.active_connection
        )

    @patch("testbench_ai_service.usecases.defect_explanations.utils.ImportJSONExecutionResults")
    @patch("testbench_ai_service.usecases.defect_explanations.utils.ImportJsonParameters")
    @patch("testbench_ai_service.usecases.defect_explanations.utils.ConnectionLog")
    def test_trigger_is_called_exactly_once(
        self, mock_connection_log, mock_import_params, mock_import_results
    ):
        mock_importer_instance = MagicMock()
        mock_import_results.return_value = mock_importer_instance
        import_data(MagicMock(), MagicMock(project_key="X", cycle_key="Y"), Path("x.zip"))
        mock_importer_instance.trigger.assert_called_once()


class TestCreateImportZip(unittest.TestCase):
    """Tests for ``create_import_zip``."""

    @patch(
        "testbench_ai_service.usecases.defect_explanations.utils.build_update_test_case_set",
        return_value=_DummyTCS(),
    )
    @patch("testbench_ai_service.usecases.defect_explanations.utils.build_protocol_json")
    @patch(
        "testbench_ai_service.usecases.defect_explanations.utils.custom_serializer",
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

            self.assertTrue(zip_path.exists())
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
                self.assertIn("protocol.json", names)
                self.assertIn("TCS123.json", names)
                protocol_content = json.loads(zf.read("protocol.json").decode())
                self.assertEqual(protocol_content[0]["protocol"], "data")
                tcs_content = json.loads(zf.read("TCS123.json").decode())
                self.assertEqual(tcs_content, {"uniqueID": "TCS123"})

    @patch(
        "testbench_ai_service.usecases.defect_explanations.utils.build_update_test_case_set",
        return_value=_DummyTCS("TCSX"),
    )
    @patch("testbench_ai_service.usecases.defect_explanations.utils.build_protocol_json")
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
                self.assertIn("protocol.json", zf.namelist())
                self.assertIn("TCSX.json", zf.namelist())


class TestCustomSerializer(unittest.TestCase):
    """Tests for ``custom_serializer``."""

    class _Status(Enum):
        PASS = "PASS"
        FAIL = "FAIL"

    def test_returns_enum_value(self):
        self.assertEqual(custom_serializer(self._Status.PASS), "PASS")
        self.assertEqual(custom_serializer(self._Status.FAIL), "FAIL")

    def test_raises_type_error_for_string(self):
        with self.assertRaises(TypeError) as ctx:
            custom_serializer("not an enum")
        self.assertIn("str", str(ctx.exception))

    def test_raises_type_error_for_number(self):
        with self.assertRaises(TypeError) as ctx:
            custom_serializer(42)
        self.assertIn("int", str(ctx.exception))


class TestGetTestCaseSetAsString(unittest.TestCase):
    """Tests for ``get_test_case_set_as_string``."""

    def test_empty_test_sequence_returns_set_name_only(self):
        tcs = _make_tcs_ns("EmptySet", [])
        self.assertEqual(get_test_case_set_as_string(tcs, "tc1"), "EmptySet")

    def test_single_keyword_without_params(self):
        kw = _make_keyword_call("Login Step", numbering="1", verdict="Pass")
        tcs = _make_tcs_ns("LoginSet", [kw])
        lines = get_test_case_set_as_string(tcs, "tc1").splitlines()
        self.assertEqual(lines[0], "LoginSet")
        self.assertIn("Login Step", lines[1])
        self.assertIn("►[Pass]", lines[1])
        self.assertNotIn("=", lines[1])

    def test_keyword_params_are_rendered(self):
        params = [_make_param("Username", "admin"), _make_param("*Password", "secret")]
        kw = _make_keyword_call("Login Step", verdict="Pass", params=params)
        tcs = _make_tcs_ns("LoginSet", [kw])
        result = get_test_case_set_as_string(tcs, "tc1")
        self.assertIn("Username=admin", result)
        self.assertIn("Password=secret", result)  # leading '*' is stripped

    def test_compound_step_shows_children_on_fail(self):
        parent = _make_keyword_call(
            "Compound Step", numbering="1", verdict="Fail", keyword_type=KeywordType.Compound
        )
        child = _make_keyword_call("Child Step", numbering="1.1", verdict="Fail", parent_id="1")
        tcs = _make_tcs_ns("TestSet", [parent, child])
        result = get_test_case_set_as_string(tcs, "tc1")
        self.assertIn("Compound Step", result)
        self.assertIn("Child Step", result)

    def test_nested_children_hidden_when_parent_passes(self):
        parent = _make_keyword_call(
            "Passing Compound", numbering="1", verdict="Pass", keyword_type=KeywordType.Compound
        )
        child = _make_keyword_call("Child Step", numbering="1.1", verdict="Pass", parent_id="1")
        tcs = _make_tcs_ns("TestSet", [parent, child])
        result = get_test_case_set_as_string(tcs, "tc1")
        self.assertIn("Passing Compound", result)
        self.assertNotIn("Child Step", result)


if __name__ == "__main__":
    unittest.main()
