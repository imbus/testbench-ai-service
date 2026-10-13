"""Data shared by the traceability agents: the requirement, its linked tests, and what
the model answers about them.

Each class whose name starts with ``Test`` sets ``__test__ = False``, or pytest would
try to collect it wherever a test module imports it.
"""

from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel

from testbench_ai_service.models.agent import AgentData
from testbench_ai_service.utils.rm_service import Requirement

T = TypeVar("T", bound=BaseModel)


class AskStep(Protocol):
    """Asks the model one step of the agent's prompt and validates the JSON answer."""

    async def __call__(self, step: str, schema: type[T], agent_data: AgentData) -> T: ...


class TestCall(BaseModel):
    """One call of a test sequence: a keyword (interaction) with its arguments."""

    __test__ = False

    phase: Literal["Setup", "TestStep", "Teardown"]
    keyword: str
    #: A check call verifies a result; a flow call only drives the system.
    check: bool
    arguments: dict[str, str]


class TestCase(BaseModel):
    """A linked test case: its call sequence and its own parameter values."""

    __test__ = False

    #: The test case's unique ID, which the model refers to it by.
    key: str
    parameters: dict[str, str]
    calls: list[TestCall]


class LinkedSet(BaseModel):
    """A test case set linked to the requirement, with only its linked test cases."""

    key: str
    spec_key: str
    unique_id: str
    title: str
    path: str
    description: str
    spec_status: str
    linked_as_whole: bool
    test_cases: list[TestCase]


class RequirementContext(BaseModel):
    requirement: Requirement
    linked_sets: list[LinkedSet]
    #: No requirement description was available, so the aspects rest on the title alone.
    reduced_mode: bool

    @property
    def requirement_ref(self) -> str:
        """How users know the requirement: its external ID, else its TestBench key."""
        return self.requirement.external_ref or self.requirement.key


AspectKind = Literal["happy_path", "negative", "boundary", "non_functional"]
EvidenceStrength = Literal["full", "partial"]


class Aspect(BaseModel):
    """One testable statement of the requirement."""

    id: str
    statement: str
    kind: AspectKind
    #: Where in the requirement text the statement comes from, verbatim.
    source_quote: str


class AspectList(BaseModel):
    aspects: list[Aspect]


class AspectEvidence(BaseModel):
    """A test case's evidence for one aspect, as the model reads it."""

    aspect_id: str
    test_case_key: str
    #: full: the test performs the action and checks the result the aspect describes.
    #: partial: the aspect occurs (e.g. as preparation) but its result is not checked.
    strength: EvidenceStrength
    evidence: str


class SetInterpretation(BaseModel):
    evidence: list[AspectEvidence]
