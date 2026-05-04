import unittest

from testbench_ai_service.agents.defect_explainer.model import (
    Comments,
    Result,
    TestCase,
    TestCaseSetProtocol,
)
from testbench_ai_service.models.testbench import ActivityStatus, ExecStatus, VerdictStatus


class TestResult(unittest.TestCase):
    """Tests for ``Result``."""

    def test_stores_required_fields(self):
        result = Result(
            status=ActivityStatus.Assigned,
            execStatus=ExecStatus.Blocked,
            verdict=VerdictStatus.Fail,
        )
        self.assertEqual(result.status, ActivityStatus.Assigned)
        self.assertEqual(result.execStatus, ExecStatus.Blocked)
        self.assertEqual(result.verdict, VerdictStatus.Fail)

    def test_timestamp_has_default(self):
        result = Result(
            status=ActivityStatus.Performed,
            execStatus=ExecStatus.NotBlocked,
            verdict=VerdictStatus.Pass,
        )
        self.assertIsNotNone(result.timestamp)
        self.assertIsInstance(result.timestamp, str)


class TestTestCase(unittest.TestCase):
    """Tests for ``TestCase``."""

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
        self.assertEqual(tc.testCaseExecutionKey, "ek1")
        self.assertEqual(tc.uniqueID, "iTB-TC-001")


class TestComments(unittest.TestCase):
    """Tests for ``Comments``."""

    def test_html_can_be_none(self):
        comments = Comments(html=None)
        self.assertIsNone(comments.html)

    def test_html_stores_string(self):
        comments = Comments(html="<p>Note</p>")
        self.assertEqual(comments.html, "<p>Note</p>")


class TestTestCaseSetProtocol(unittest.TestCase):
    """Tests for ``TestCaseSetProtocol``."""

    def test_valid_protocol_with_no_test_cases(self):
        protocol = TestCaseSetProtocol(
            testCaseSetKey="tcs1",
            durationMillis=0,
            executionKey="ek",
            comments=Comments(html=None),
            testCases=[],
        )
        self.assertEqual(protocol.testCaseSetKey, "tcs1")
        self.assertEqual(protocol.testCases, [])


if __name__ == "__main__":
    unittest.main()
