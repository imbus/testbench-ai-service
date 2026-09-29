from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from testbench_ai_service.agents.test_planner.model import (
    CutoffMode,
    EmbeddingArgs,
    EmbeddingProvider,
    ExistingMode,
    PlannerRunParams,
    PlannerTestCase,
    TestPlannerArgs,
)
from testbench_ai_service.models.testbench import ActivityStatus


def _case(status: ActivityStatus) -> PlannerTestCase:
    return PlannerTestCase(
        unique_id="TC-1", key="1", set_key="S1", set_name="Set", path="/A", text="t", status=status
    )


class TestArgs:
    def test_defaults(self):
        args = TestPlannerArgs()

        assert args.mandatory_tag is None
        assert args.cluster_threshold == 0.05
        assert args.embedding == EmbeddingArgs()
        assert args.embedding.provider == EmbeddingProvider.OPENAI
        assert args.embedding.model == "text-embedding-3-small"
        assert args.embedding.cache_dir == Path("data/embedding_cache")
        assert args.embedding.batch_size == 256

    def test_unknown_key_is_rejected(self):
        with pytest.raises(ValidationError):
            TestPlannerArgs.model_validate({"mandatory_tags": "x"})

    def test_threshold_must_be_below_one(self):
        with pytest.raises(ValidationError):
            TestPlannerArgs(cluster_threshold=1.0)

    def test_local_provider_needs_fastembed(self):
        with patch("importlib.util.find_spec", return_value=None):
            with pytest.raises(ValidationError, match="local-embeddings"):
                EmbeddingArgs(provider=EmbeddingProvider.LOCAL)

    def test_local_provider_accepted_when_fastembed_is_importable(self):
        with patch("importlib.util.find_spec", return_value=object()):
            assert EmbeddingArgs(provider="local").provider == EmbeddingProvider.LOCAL


class TestRunParams:
    def test_auto_needs_no_value(self):
        params = PlannerRunParams(mode="auto")

        assert params.mode == CutoffMode.AUTO
        assert params.existing == ExistingMode.KEEP

    def test_strings_are_coerced(self):
        params = PlannerRunParams(mode="count", count="40", existing="replan")

        assert params.count == 40
        assert params.existing == ExistingMode.REPLAN

    @pytest.mark.parametrize("mode", ["count", "budget", "coverage"])
    def test_mode_value_is_required(self, mode):
        with pytest.raises(ValidationError, match="must be set"):
            PlannerRunParams(mode=mode)

    def test_coverage_is_capped_at_100(self):
        with pytest.raises(ValidationError):
            PlannerRunParams(mode="coverage", coverage_percent=101)


class TestPlannerTestCase:
    @pytest.mark.parametrize(
        ("status", "executed", "planned"),
        [
            (ActivityStatus.NotPlanned, False, False),
            (ActivityStatus.Planned, False, True),
            (ActivityStatus.Assigned, False, True),
            (ActivityStatus.Running, True, False),
            (ActivityStatus.Performed, True, False),
            (ActivityStatus.Skipped, False, False),
        ],
    )
    def test_status_flags(self, status, executed, planned):
        case = _case(status)

        assert case.executed is executed
        assert case.planned is planned
