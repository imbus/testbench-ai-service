"""Configuration, parameter, data and result models of the test planner agent."""

import importlib.util
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from testbench_ai_service.models.agent import AgentArgs
from testbench_ai_service.models.testbench import ActivityStatus

#: Test cases in these states keep their results and are never selected.
EXECUTED_STATUSES = frozenset({ActivityStatus.Performed, ActivityStatus.Running})
#: Test cases in these states count as already planned for ``existing = keep``.
PLANNED_STATUSES = frozenset({ActivityStatus.Planned, ActivityStatus.Assigned})


class EmbeddingProvider(str, Enum):
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    LOCAL = "local"


class EmbeddingArgs(AgentArgs):
    """The ``args.embedding`` config table of the test planner."""

    provider: EmbeddingProvider = EmbeddingProvider.OPENAI
    #: Embedding model; for ``azure_openai`` the name of the deployment.
    model: str = "text-embedding-3-small"
    cache_dir: Path = Path("data/embedding_cache")
    batch_size: int = Field(256, gt=0)

    @model_validator(mode="after")
    def check_local_backend(self) -> "EmbeddingArgs":
        if (
            self.provider == EmbeddingProvider.LOCAL
            and importlib.util.find_spec("fastembed") is None
        ):
            raise ValueError(
                "provider 'local' needs the optional package 'fastembed': "
                "pip install testbench-ai-service[local-embeddings]"
            )
        return self


class TestPlannerArgs(AgentArgs):
    """The ``args`` config table of the test planner."""

    __test__ = False  # not a pytest test class

    #: Test cases carrying this tag are always selected.
    mandatory_tag: str | None = None
    #: Distance below which two test cases count as redundant.
    cluster_threshold: float = Field(0.05, ge=0, lt=1)
    embedding: EmbeddingArgs = Field(default_factory=EmbeddingArgs)


class CutoffMode(str, Enum):
    AUTO = "auto"
    COUNT = "count"
    BUDGET = "budget"
    COVERAGE = "coverage"


class ExistingMode(str, Enum):
    KEEP = "keep"
    REPLAN = "replan"


_MODE_VALUE_FIELD = {
    CutoffMode.COUNT: "count",
    CutoffMode.BUDGET: "budget_minutes",
    CutoffMode.COVERAGE: "coverage_percent",
}


class PlannerRunParams(BaseModel):
    """Per-run parameters, taken from the prompt variant and its vars."""

    mode: CutoffMode
    existing: ExistingMode = ExistingMode.KEEP
    count: int | None = Field(None, gt=0)
    budget_minutes: float | None = Field(None, gt=0)
    coverage_percent: float | None = Field(None, gt=0, le=100)

    @model_validator(mode="after")
    def check_mode_value(self) -> "PlannerRunParams":
        field = _MODE_VALUE_FIELD.get(self.mode)
        if field is not None and getattr(self, field) is None:
            raise ValueError(f"'{field}' must be set for mode '{self.mode.value}'")
        return self


class PlannerTestCase(BaseModel):
    """One test case of the cycle, reduced to what the planner needs."""

    unique_id: str
    key: str
    set_key: str
    set_name: str
    path: str
    text: str
    planned_minutes: float = 0.0
    tags: frozenset[str] = frozenset()
    requirement_keys: frozenset[str] = frozenset()
    status: ActivityStatus = ActivityStatus.NotPlanned

    @property
    def executed(self) -> bool:
        return self.status in EXECUTED_STATUSES

    @property
    def planned(self) -> bool:
        return self.status in PLANNED_STATUSES


SelectionReason = Literal["mandatory", "existing", "farthest"]


class SelectionEntry(BaseModel):
    rank: int
    unique_id: str
    key: str
    path: str
    min_distance: float
    reason: SelectionReason


class CutoffHints(BaseModel):
    knee: int | None = None
    full_requirement_coverage: int | None = None
    distance_zero_from: int | None = None


class RedundancyCluster(BaseModel):
    tests: list[str]
    sets: list[str]


class PlannerResult(BaseModel):
    selected: int
    total: int
    planned_minutes: float
    mode: CutoffMode
    cutoff_hints: CutoffHints
    selection: list[SelectionEntry]
    redundancy_clusters: list[RedundancyCluster]
    warnings: list[str] = Field(default_factory=list)
