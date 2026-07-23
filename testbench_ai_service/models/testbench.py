from enum import Enum

from pydantic import BaseModel, Field


class PermissionWithCode(int, Enum):
    AccessSecuredData = 1
    ReadUserDetails = 2
    ReadUserMemberships = 3
    SynchronizeUsers = 4
    ReadUserSessions = 5
    DeleteUserSession = 6
    ModifyUserData = 7
    DeleteUserAccount = 8
    RestrictProjectUDFs = 9
    ReadProjectDetails = 10
    ReadProjectMembers = 11
    ReadProjectHierarchy = 12
    ModifyProjectDetails = 13
    ModifyUserRolesInProject = 14
    ReadProjectExportOverRMI = 15
    ReadTovReportOverRMI = 16
    ReadCycleReportOverRMI = 17
    ReadTovReport = 18
    ReadCycleReport = 19
    DownloadReportFile = 20
    ReadProjectUDFs = 21
    ModifyProjectUDFs = 22
    ReadProjectDefectsAndTheirAssignments = 23
    ReadTestThemeStatusDistribution = 24
    ReadTovRequirements = 25
    ReadCycleRequirements = 26
    ReadTestThemeTree = 27
    ReadTestThemeDetails = 28
    ReadTestCaseSetDetails = 29
    ReadTestCaseDetails = 30
    ReadReportingJobDetails = 31
    ReadExecutionImportingJobDetails = 32
    ReadDefectsMetricDistribution = 33
    ReadTestLabels = 34
    ModifyTestLabels = 35
    ImportExecutionResults = 36
    ReadTestElements = 37
    ModifyTestElements = 38
    ModifySpecifications = 39
    ModifyGlobalTestLabels = 40
    PrivatizeGlobalTestLabels = 41
    ReadCompleteProjectsList = 42
    ReadOwnProjectsList = 43
    ReadInvisibleProjectContent = 44
    UnlockForeignTestElements = 45
    UnlockForeignSpecs = 46
    ModifySpecManagementInfo = 47
    ModifySpecPriorityAndDueDate = 48
    ReadCompleteUsersList = 49
    ReadActiveUsersList = 50
    ReadOwnUserDetails = 51


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


class GlobalHumanRole(str, Enum):
    Administrator = "Administrator"
    ProjectAdministrator = "ProjectAdministrator"
    ProjectUser = "ProjectUser"


class ProjectRole(str, Enum):
    TestManager = "TestManager"
    TestDesigner = "TestDesigner"
    TestProgrammer = "TestProgrammer"
    Tester = "Tester"
    ReadOnlyDesigner = "ReadOnlyDesigner"
    ReadOnlyImplementer = "ReadOnlyImplementer"
    ReadOnlyTester = "ReadOnlyTester"


class ExecutionMode(str, Enum):
    execute = "execute"
    continue_ = "continue"
    view = "view"
    simulate = "simulate"


class ProjectStatus(str, Enum):
    Planned = "Planned"
    InProgress = "InProgress"
    Finished = "Finished"
    Closed = "Closed"


class TOVExchangeFormat(str, Enum):
    xml = "xml"
    json = "json"
    inherit = "inherit"


class OptionalUser(BaseModel):
    optional: str | None = None


class OptionalLocalDate(BaseModel):
    optional: str | None = Field(None, examples=["2025-03-13"])


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
    dueDate: OptionalLocalDate | None = None
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


class RequirementReference(BaseModel):
    key: str
    edited: bool


class Tag(BaseModel):
    key: str
    name: str
    isVariantsMarker: bool


class TestThemeSpecification(BaseModel):
    key: str
    description: str
    reviewComment: str
    status: SpecStatus
    priority: Priority
    dueDate: str | None = None
    reviewer: UserReference | None = None
    responsible: UserReference | None = None
    udfs: list[UserDefinedField]
    tags: list[Tag]
    requirements: list[RequirementReference]
    references: list[str]


class TestCaseSetExecutionSummary(BaseModel):
    key: str
    comments: str
    udfs: list[UserDefinedField]
    tags: list[Tag]


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


class SequencePhase(str, Enum):
    Setup = "Setup"
    TestStep = "TestStep"
    Teardown = "Teardown"


class KeywordCallType(str, Enum):
    Flow = "Flow"
    Check = "Check"


class KeywordType(str, Enum):
    Atomic = "Atomic"
    Compound = "Compound"
    Textual = "Textual"


class KindOfDataType(str, Enum):
    Regular = "Regular"
    Reference = "Reference"
    Global = "Global"
    AcceptingGlobal = "AcceptingGlobal"


class DataTypeSummary(BaseModel):
    key: str
    kind: KindOfDataType
    name: str
    path: str
    uniqueID: str
    version: str | None = None


class ParameterDefinitionType(str, Enum):
    DetailedInstance = "DetailedInstance"
    InstanceTable = "InstanceTable"
    AtomicInstance = "AtomicInstance"


class ParameterValue(BaseModel):
    name: str
    key: str
    dtSequenceKeys: list[str]


class InstanceArrayValue(BaseModel):
    name: str
    isDefaultValue: bool


class ParameterEvaluationType(str, Enum):
    CallByValue = "CallByValue"
    CallByReference = "CallByReference"
    CallByReferenceMandatory = "CallByReferenceMandatory"


class RepresentativeType(str, Enum):
    Text = "Text"
    Placeholder = "Placeholder"
    Attachment = "Attachment"
    Hyperlink = "Hyperlink"
    Reference = "Reference"


class RepresentativeValue(BaseModel):
    name: str
    valueType: RepresentativeType
    isDefaultValue: bool


class ParameterSummary(BaseModel):
    dataType: DataTypeSummary | None = None
    definitionType: ParameterDefinitionType
    key: str
    name: str
    evaluationType: ParameterEvaluationType
    value: str | None = None
    valueType: RepresentativeType | None = None
    representativeValue: RepresentativeValue | None = None
    parameterValue: ParameterValue | None = None
    instanceArrayValue: InstanceArrayValue | None = None
    parentAlias: str | None = None
    rootAlias: str | None = None
    usesCount: int | None = None


class KeywordCallSpecification(BaseModel):
    key: str
    keywordType: KeywordType | None = None
    name: str
    sequencePhase: SequencePhase
    callType: KeywordCallType
    description: str | None = None
    comments: str
    keywordKey: str | None = None
    callParameters: list[ParameterSummary]
    callingKeywordKey: str | None = None


class KeywordVerdict(str, Enum):
    Pass = "Pass"
    Fail = "Fail"
    Skipped = "Skipped"
    ToVerify = "ToVerify"
    Warn = "Warn"
    Undefined = "Undefined"
    Blocked = "Blocked"


class KeywordCallExecution(BaseModel):
    verdict: KeywordVerdict
    time: str | None = None
    duration: int
    currentUser: UserReference
    tester: UserReference | None = None
    comments: str
    references: list[str]
    defects: list[str]


class KeywordCall(BaseModel):
    sequenceID: str
    parentID: str | None = None
    numbering: str
    spec: KeywordCallSpecification
    exec: KeywordCallExecution | None = None


class ArgumentValueType(str, Enum):
    EquivalenceClass = "EquivalenceClass"
    Representative = "Representative"
    InstancesArray = "InstancesArray"
    CBRRepresentative = "CBRRepresentative"


class DefaultValue(BaseModel):
    name: str
    valueType: ArgumentValueType


class ParameterDetails(BaseModel):
    key: str
    name: str
    definitionType: ParameterDefinitionType
    evaluationType: ParameterEvaluationType
    dataTypeKey: str | None = None
    defaultValue: DefaultValue | None = None
    signatureID: str | None = None


class TestElementStatus(str, Enum):
    InProgress = "InProgress"
    Released = "Released"


class ContentType(str, Enum):
    txt = "txt"
    xml = "xml"


class AdvancedContent(BaseModel):
    contentType: ContentType | None = None
    contentExtID: str | None = None
    content: str | None = None


class KeywordDetails(BaseModel):
    key: str
    name: str
    uniqueID: str
    status: TestElementStatus
    defaultCallType: KeywordCallType
    locker: UserReference | None = None
    description: str
    version: str | None = None
    parentUniqueID: str | None = None
    libraryKey: str | None = None
    advancedContent: AdvancedContent | None = None
    path: str
    parameters: list[ParameterDetails]
    preConditions: list[ConditionSummary]
    postConditions: list[ConditionSummary]
    references: list[str]


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
    tags: list[Tag]
    references: list[str]
    requirements: list[RequirementReference]


class TestCaseSetDetails(BaseModel):
    key: str
    numbering: str
    path: str
    uniqueID: str
    name: str
    spec: TestCaseSetSpecificationSummary
    exec: TestCaseSetExecutionSummary | None = None
    testCases: list[TestCaseSummary]
    testSequence: list[KeywordCall]
    parameters: list[ParameterDetails]
    keywords: list[KeywordDetails]


class TestStructureElementType(str, Enum):
    RootNode = "RootNode"
    TestThemeNode = "TestThemeNode"
    TestCaseSetNode = "TestCaseSetNode"
    TestCaseNode = "TestCaseNode"


class TestStructureItemBaseInformation(BaseModel):
    key: str
    numbering: str
    path: str
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


class TestFilterType(str, Enum):
    TestTheme = "TestTheme"
    TestCaseSet = "TestCaseSet"
    TestCase = "TestCase"


class AttachedFilter(BaseModel):
    key: str
    name: str
    filterType: TestFilterType
    content: str


class TestStructureTreeNode(BaseModel):
    elementType: TestStructureElementType


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


class FilterInfo(BaseModel):
    name: str
    filterType: TestFilterType
    testThemeUID: str | None = None


class FilteringOptions(BaseModel):
    appliedFilters: list[FilterInfo] | None = None
    excludedTestThemes: list[str] | None = None
    labelFilter: str | None = None


class ReportExportOptions(BaseModel):
    pass


class TovStructureOptions(ReportExportOptions):
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


class CycleReportOptions(ReportExportOptions):
    treeRootUID: str | None = None
    executionMode: ExecutionMode | None = None
    suppressFilteredData: bool | None = Field(None, examples=[False])
    suppressNotExecutable: bool | None = Field(None, examples=[False])
    suppressEmptyTestThemes: bool | None = Field(None, examples=[False])
    filters: list[FilterInfo] | None = None


class ProjectMember(BaseModel):
    userKey: str
    userLogin: str
    userName: str
    projectKey: str
    projectName: str
    roles: list[ProjectRole]


class TOVDetails(BaseModel):
    key: str
    creationTime: str
    name: str
    status: ProjectStatus
    visibility: bool
    cyclesCount: int
    description: str
    lockerKey: str | None
    startDate: str | None
    endDate: str | None
    exchangeFormat: TOVExchangeFormat
