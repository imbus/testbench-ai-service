from testbench2robotframework.json_reader import TestCaseDetails, TestCaseSet
from testbench2robotframework.model import (
    KeywordCall,
    KeywordCallExecution,
    KeywordCallSpecification,
    KeywordCallType,
    KeywordType,
    KeywordVerdict,
    SequencePhase,
    TestCaseDetailsOrigin,
    TestCaseExecutionDetails,
    TestCaseSpecificationDetails,
)

from testbench_ai_service.models.testbench import (
    ActivityStatus,
    AutStatus,
    ExecStatus,
    Priority,
    SpecStatus,
    TestCaseExecutionSummary,
    TestCaseSetDetails,
    TestCaseSetExecutionSummary,
    TestCaseSetNode,
    TestCaseSetSpecificationSummary,
    TestCaseSpecificationSummary,
    TestCaseSummary,
    TestStructureAutomation,
    TestStructureElementType,
    TestStructureItemBaseInformation,
    TestStructureItemExecution,
    TestStructureItemSpecification,
    TestStructureTree,
    UserReference,
    VerdictStatus,
)


def build_unlocked_structure_tree(tab: str) -> TestStructureTree:
    """Return a TestStructureTree whose *tab* (``spec`` or ``exec``) has no locker."""
    spec = TestStructureItemSpecification(key="17", locker=None, status=SpecStatus.InProgress)
    exec_ = TestStructureItemExecution(
        key="32",
        locker=None,
        status=ActivityStatus.Performed,
        execStatus=ExecStatus.NotBlocked,
        verdict=VerdictStatus.Pass,
    )
    node = TestCaseSetNode(
        base=TestStructureItemBaseInformation(
            key="9",
            numbering="1.1",
            parentKey="1",
            name="Calculate final price",
            uniqueID="iTB-TC-66",
            matchesFilter=True,
        ),
        spec=spec if tab == "spec" else None,
        aut=TestStructureAutomation(key="16", locker=None, status=AutStatus.NotPlanned),
        exec=exec_ if tab == "exec" else None,
        elementType=TestStructureElementType.TestCaseSetNode,
    )
    return TestStructureTree(root=node, nodes=[])


def build_locked_structure_tree(tab: str, locker_key: str = "99") -> TestStructureTree:
    """Return a TestStructureTree whose *tab* is locked by a *different* user (key ``99``)."""
    locker = UserReference(key=locker_key, name="Someone Else")
    spec = TestStructureItemSpecification(key="17", locker=locker, status=SpecStatus.InReview)
    exec_ = TestStructureItemExecution(
        key="32",
        locker=locker,
        status=ActivityStatus.Running,
        execStatus=ExecStatus.NotBlocked,
        verdict=VerdictStatus.Undefined,
    )
    node = TestCaseSetNode(
        base=TestStructureItemBaseInformation(
            key="9",
            numbering="1.1",
            parentKey="1",
            name="Calculate final price",
            uniqueID="iTB-TC-66",
            matchesFilter=True,
        ),
        spec=spec if tab == "spec" else None,
        aut=TestStructureAutomation(key="16", locker=None, status=AutStatus.NotPlanned),
        exec=exec_ if tab == "exec" else None,
        elementType=TestStructureElementType.TestCaseSetNode,
    )
    return TestStructureTree(root=node, nodes=[])


def build_tcs_catalog(
    uid: str = "iTB-TC-66",
    spec_key: str = "17",
    exec_key: str = "32",
) -> dict[str, TestCaseSet]:
    """Return a minimal test-case-set catalog with one unlocked entry."""
    details = TestCaseSetDetails(
        key="9",
        numbering="1.1",
        uniqueID=uid,
        name="Calculate final price",
        spec=TestCaseSetSpecificationSummary(
            key=spec_key,
            description="<html><body>Check price calculation</body></html>",
            reviewComment="<html><body></body></html>",
            responsible=None,
            status=SpecStatus.InProgress,
            priority=Priority.Undefined,
            preConditions=[],
            postConditions=[],
            dueDate=None,
            reviewer=None,
            udfs=[],
            keywords=[],
            references=[],
            requirements=[],
        ),
        exec=TestCaseSetExecutionSummary(
            key=exec_key,
            comments="<html><body></body></html>",
            udfs=[],
            keywords=[],
        ),
        testCases=[
            TestCaseSummary(
                uniqueID=f"{uid}-PC-1",
                index=1,
                spec=TestCaseSpecificationSummary(
                    key="19",
                    comments="<html><body></body></html>",
                    requirements=[],
                ),
                exec=TestCaseExecutionSummary(
                    key="37",
                    status=ActivityStatus.Performed,
                    execStatus=ExecStatus.NotBlocked,
                    verdict=VerdictStatus.Pass,
                    defects=[],
                    comments="<html><body/></html>",
                    tester=UserReference(key="0", name="tester"),
                ),
            )
        ],
    )
    test_case = _make_test_case_details(uid)
    return {uid: TestCaseSet(details=details, test_cases={f"{uid}-PC-1": test_case})}


def _make_test_case_details(uid: str) -> TestCaseDetails:
    return TestCaseDetails(
        uniqueID=f"{uid}-PC-1",
        spec=TestCaseSpecificationDetails(
            key="19",
            comments="<html><body></body></html>",
            udfs=[],
            tags=[],
            requirements=[],
            version=None,
        ),
        testSequence=[
            KeywordCall(
                sequenceID="1",
                numbering="1",
                spec=KeywordCallSpecification(
                    key="58",
                    name="Open application",
                    sequencePhase=SequencePhase.TestStep,
                    callType=KeywordCallType.Flow,
                    comments="",
                    callParameters=[],
                    keywordType=KeywordType.Textual,
                    description="<html><body>Open application</body></html>",
                    keywordKey=None,
                    callingKeywordKey=None,
                ),
                parentID=None,
                exec=KeywordCallExecution(
                    verdict=KeywordVerdict.Undefined,
                    duration=0,
                    currentUser=UserReference(key="-1", name=""),
                    comments="",
                    references=[],
                    defects=[],
                    time=None,
                    tester=UserReference(key="0", name="tester"),
                ),
            ),
        ],
        parameters=[],
        keywords=[],
        exec=TestCaseExecutionDetails(
            key="37",
            status=ActivityStatus.Performed,
            execStatus=ExecStatus.NotBlocked,
            verdict=VerdictStatus.Pass,
            plannedDuration=0,
            actualDuration=0,
            currentUser=UserReference(key="-1", name=""),
            comments="<html><body/></html>",
            defects=[],
            udfs=[],
            tags=[],
            references=[],
            version=None,
            tester=UserReference(key="0", name="tester"),
        ),
        origin=TestCaseDetailsOrigin.Generated,
    )
