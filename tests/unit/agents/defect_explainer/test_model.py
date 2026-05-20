from testbench_ai_service.agents.defect_explainer.model import (
    Comments,
    Result,
    TestCase,
    TestCaseSetProtocol,
)
from testbench_ai_service.models.testbench import ActivityStatus, ExecStatus, VerdictStatus


class TestResult:
    def test_stores_required_fields(self):
        result = Result(
            status=ActivityStatus.Assigned,
            execStatus=ExecStatus.Blocked,
            verdict=VerdictStatus.Fail,
        )
        assert result.status == ActivityStatus.Assigned
        assert result.execStatus == ExecStatus.Blocked
        assert result.verdict == VerdictStatus.Fail

    def test_timestamp_has_default(self):
        result = Result(
            status=ActivityStatus.Performed,
            execStatus=ExecStatus.NotBlocked,
            verdict=VerdictStatus.Pass,
        )
        assert result.timestamp is not None
        assert isinstance(result.timestamp, str)


class TestTestCase:
    def test_stores_all_fields(self):
        result = Result(
            status=ActivityStatus.Performed,
            execStatus=ExecStatus.NotBlocked,
            verdict=VerdictStatus.Pass,
        )
        tc = TestCase(
            testCaseExecutionKey="ek1",
            durationMillis=0,
            uniqueID="iTB-TC-001",
            result=result,
        )
        assert tc.testCaseExecutionKey == "ek1"
        assert tc.uniqueID == "iTB-TC-001"


class TestComments:
    def test_html_can_be_none(self):
        comments = Comments(html=None)
        assert comments.html is None

    def test_html_stores_string(self):
        comments = Comments(html="<p>Note</p>")
        assert comments.html == "<p>Note</p>"


class TestTestCaseSetProtocol:
    def test_valid_protocol_with_no_test_cases(self):
        protocol = TestCaseSetProtocol(
            testCaseSetKey="tcs1",
            durationMillis=0,
            executionKey="ek",
            comments=Comments(html=None),
            testCases=[],
        )
        assert protocol.testCaseSetKey == "tcs1"
        assert protocol.testCases == []
