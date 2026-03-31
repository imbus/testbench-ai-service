from enum import Enum

from pydantic import BaseModel, Field


class Priority(str, Enum):
    Undefined = "Undefined"
    Low = "Low"
    Middle = "Middle"
    High = "High"


class SpecStatus(str, Enum):
    NotPlanned = "NotPlanned"
    Planned = "Planned"
    InProgress = "InProgress"
    InReview = "InReview"
    Released = "Released"


class UDFType(str, Enum):
    String = "String"
    Enumeration = "Enumeration"
    Boolean = "Boolean"


class ActivityStatus(str, Enum):
    NotPlanned = "NotPlanned"
    Planned = "Planned"
    Assigned = "Assigned"
    Running = "Running"
    Skipped = "Skipped"
    Canceled = "Canceled"
    Performed = "Performed"


class ExecStatus(str, Enum):
    NotBlocked = "NotBlocked"
    Blocked = "Blocked"


class VerdictStatus(str, Enum):
    Undefined = "Undefined"
    ToVerify = "ToVerify"
    Fail = "Fail"
    Pass = "Pass"


class OptionalUser(BaseModel):
    optional: str | None = None


class OptionalLocalDateTime(BaseModel):
    optional: str | None = Field(None, examples=["2025-03-13T00:00:00"])


class ImageDetails(BaseModel):
    key: str = Field(..., examples=["-1"])
    suffix: str = Field(..., examples=["png"])
    imageData: str = Field(
        ...,
        examples=[
            "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAGXRFWHRTb2Z0d2FyZQBBZG9iZSBJbWFnZVJlYWR5ccllPAAAAn5JREFUeNqkk89rE0EUx9/sj2R/JVuj9pelqK2JUkstiIgHUShSIVD05N+g9eBVr15FKOjFu3gr/qB6L4r0IGop2NYf0Katdk2bbDq7ye7MrDOTNmnPDnx33ryZz5v3ZmdQkiTwP02Tn+E3AEgBUFQ+Qt2AUJEbF7j6dteVuOYgSfjC5DcwyjsGZL7YDLCvjVumduf8ub5CfuBIl2OnbZHgzk4DL/7wrnz6ujYRhPETvu7dgQz24Jxr3L9ZHB5llDn1III/G56ccF03mz+Ryw4cz/W8ervgblcC2AuiNNmkxzLUyYnxM6N+teb4/g54ngfTjwpSwvZ9DCEOnGtXB0fNtDIpmHYARosjZ3sKvl9zMA4gDEOIoqiVmrCFT8w1wtDJD+QKgmmVkFBysbfb6apW/BbEGIPC9WmglIGma0AJlX5VU3lJh7oEw4fPmmfASJ+qgEUpBcIXVnkJGGN4/rCf/xAEtx6UQNHSzWK54phYgmkfIiOIEILCBoFqrc53R6DoaQmbpglqygBF0dvZIQ0Jph2AklJ5KwxwpDpqygZVuuoSdhwHtJTFUzdaAeJ6FAhm3yGSudWV8qZhZSFlZKQ03ZKwbdvS3vMLVco1TzDtAJS8XF36tcxzw7qRBT2dkbsKWJQhbOETIjHgv6ulJcG0S0jYRhQGU/Ozs+7Q5bFhM9Nha4YDY3d/yunM0ZOyD6rbePHj+3lSD6b4td84eBMTNhN4a+jz6xf3ek+PnOocHDrsdubNJrgVbn5fKK9/+7IcR43HyMjOgDwp/nLEa1SPPeVlxJCEFUjquJdfjBt87hJX/274Fa4PgNRpZNjryOzgvA507XYzwP+0fwIMAOelHuF3cN5hAAAAAElFTkSuQmCC"
        ],
    )


class ImageInfo(BaseModel):
    key: str = Field(..., examples=["infoIcon.png"])
    value: ImageDetails


class RichTextInfo(BaseModel):
    html: str = Field(
        ...,
        examples=['<html><body><img src="infoIcon.png" />New <b>Description</b></body></html>'],
    )
    images: list[ImageInfo]


class SpecificationDetailsForUpdate(BaseModel):
    responsible: OptionalUser | None = None
    reviewer: OptionalUser | None = None
    locker: OptionalUser | None = None
    priority: Priority | None = None
    dueDate: OptionalLocalDateTime | None = None
    description: RichTextInfo | None = None
    reviewComment: RichTextInfo | None = None


class UserReference(BaseModel):
    key: str
    name: str


class ConditionSummary(BaseModel):
    key: str
    uniqueID: str
    name: str
    description: str
    version: str | None = None


class UserDefinedField(BaseModel):
    key: str
    name: str
    value: str
    udfType: UDFType


class Keyword(BaseModel):
    key: str
    name: str
    isVariantsMarker: bool


class RequirementReference(BaseModel):
    key: str
    edited: bool


class TestCaseSetSpecificationSummary(BaseModel):
    key: str
    description: str
    reviewComment: str
    responsible: UserReference | None = None
    status: SpecStatus
    priority: Priority
    preConditions: list[ConditionSummary]
    postConditions: list[ConditionSummary]
    dueDate: str | None = None
    reviewer: UserReference | None = None
    udfs: list[UserDefinedField]
    keywords: list[Keyword] = []
    references: list[str]
    requirements: list[RequirementReference]


class TestCaseSetExecutionSummary(BaseModel):
    key: str
    comments: str
    udfs: list[UserDefinedField]
    keywords: list[Keyword] = []


class TestCaseSpecificationSummary(BaseModel):
    key: str
    comments: str
    requirements: list[RequirementReference]


class TestCaseExecutionSummary(BaseModel):
    key: str
    status: ActivityStatus
    tester: UserReference | None = None
    execStatus: ExecStatus
    verdict: VerdictStatus
    defects: list[str]
    comments: str


class TestCaseSummary(BaseModel):
    uniqueID: str
    index: int
    spec: TestCaseSpecificationSummary
    exec: TestCaseExecutionSummary | None = None


class TestCaseSetDetails(BaseModel):
    key: str
    numbering: str
    uniqueID: str
    name: str
    spec: TestCaseSetSpecificationSummary
    exec: TestCaseSetExecutionSummary | None = None
    testCases: list[TestCaseSummary]


class TestStructureElementType(str, Enum):
    RootNode = "RootNode"
    TestThemeNode = "TestThemeNode"
    TestCaseSetNode = "TestCaseSetNode"
    TestCaseNode = "TestCaseNode"


class TestStructureItemBaseInformation(BaseModel):
    key: str
    numbering: str
    parentKey: str
    name: str
    uniqueID: str
    matchesFilter: bool


class TestStructureSpecification(BaseModel):
    pass


class TestStructureItemSpecification(TestStructureSpecification):
    key: str
    locker: UserReference | None = None
    status: SpecStatus


class TestCaseBaseInformation(BaseModel):
    numbering: str
    parentKey: str
    name: str
    uniqueID: str
    matchesFilter: bool


class AutStatus(str, Enum):
    NotPlanned = "NotPlanned"
    Planned = "Planned"
    InProgress = "InProgress"
    InReview = "InReview"
    Released = "Released"


class TestStructureAutomation(BaseModel):
    key: str
    locker: UserReference | None = None
    status: AutStatus


class TestStructureExecution(BaseModel):
    status: ActivityStatus
    execStatus: ExecStatus
    verdict: VerdictStatus


class TestStructureItemExecution(TestStructureExecution):
    key: str
    locker: UserReference | None = None


class TestStructureTreeNode(BaseModel):
    pass


class TestFilterType(str, Enum):
    TestTheme = "TestTheme"
    TestCaseSet = "TestCaseSet"
    TestCase = "TestCase"


class AttachedFilter(BaseModel):
    key: str
    name: str
    filterType: TestFilterType
    content: str


class RootNode(TestStructureTreeNode):
    base: TestStructureItemBaseInformation
    filters: list[AttachedFilter]
    elementType: TestStructureElementType = TestStructureElementType.RootNode


class TestThemeNode(TestStructureTreeNode):
    base: TestStructureItemBaseInformation
    spec: TestStructureItemSpecification | None = None
    aut: TestStructureAutomation | None = None
    exec: TestStructureItemExecution | None = None
    filters: list[AttachedFilter]
    elementType: TestStructureElementType = TestStructureElementType.TestThemeNode


class TestCaseSetNode(TestStructureTreeNode):
    base: TestStructureItemBaseInformation
    spec: TestStructureItemSpecification | None = None
    aut: TestStructureAutomation | None = None
    exec: TestStructureItemExecution | None = None
    elementType: TestStructureElementType = TestStructureElementType.TestCaseSetNode


class TestCaseSpecification(TestStructureSpecification):
    key: str


class TestCaseExecution(TestStructureExecution):
    key: str


class TestCaseNode(TestStructureTreeNode):
    base: TestCaseBaseInformation
    spec: TestCaseSpecification | None = None
    exec: TestCaseExecution | None = None
    elementType: TestStructureElementType = TestStructureElementType.TestCaseNode


class TestStructureTree(BaseModel):
    root: RootNode | TestThemeNode | TestCaseSetNode | TestCaseNode | None = None
    nodes: list[TestThemeNode | TestCaseSetNode | TestCaseNode]


class TestFilterType(str, Enum):
    TestTheme = "TestTheme"
    TestCaseSet = "TestCaseSet"
    TestCase = "TestCase"


class FilterInfo(BaseModel):
    name: str
    filterType: TestFilterType
    testThemeUID: str | None = None


class TovStructureOptions(BaseModel):
    treeRootUID: str | None = None
    suppressFilteredData: bool | None = Field(None, examples=[False])
    suppressEmptyTestThemes: bool | None = Field(None, examples=[False])
    filters: list[FilterInfo] | None = None


class CycleStructureOptions(BaseModel):
    treeRootUID: str | None = None
    basedOnExecution: bool | None = Field(None, examples=[True])
    suppressFilteredData: bool | None = Field(None, examples=[False])
    suppressNotExecutable: bool | None = Field(None, examples=[False])
    suppressEmptyTestThemes: bool | None = Field(None, examples=[False])
    filters: list[FilterInfo] | None = None


class GlobalHumanRole(str, Enum):
    Administrator = "Administrator"
    ProjectAdministrator = "Project Administrator"
    ProjectUser = "Project User"


class ProjectRole(str, Enum):
    TestManager = "TestManager"
    TestDesigner = "TestDesigner"
    TestProgrammer = "TestProgrammer"
    Tester = "Tester"
    ReadOnlyDesigner = "ReadOnlyDesigner"
    ReadOnlyImplementer = "ReadOnlyImplementer"
    ReadOnlyTester = "ReadOnlyTester"


class ProjectMember(BaseModel):
    userKey: str
    userLogin: str
    userName: str
    projectKey: str
    projectName: str
    roles: list[ProjectRole]
