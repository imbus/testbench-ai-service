import pytest

from testbench_ai_service.agents.test_planner.cutoff import (
    CutoffNote,
    RankedEntry,
    apply_cutoff,
    compute_hints,
    knee_index,
)
from testbench_ai_service.agents.test_planner.model import PlannerRunParams


def _entry(index, score, minutes=10.0, reqs=(), reason="farthest"):
    return RankedEntry(index, reason, score, minutes, frozenset(reqs))


# picks with a clear knee after the second one, then a duplicate
PICKS = [
    _entry(0, 1.0, reqs=("R1",)),
    _entry(1, 0.2, reqs=("R2",)),
    _entry(2, 0.15),
    _entry(3, 0.1, reqs=("R3",)),
    _entry(4, 0.05),
    _entry(5, 0.0),
]
REQS = frozenset({"R1", "R2", "R3"})


class TestKnee:
    def test_knee_after_the_steep_drop(self):
        assert knee_index([1.0, 0.2, 0.15, 0.1, 0.05]) == 1

    @pytest.mark.parametrize("scores", [[1.0], [1.0, 0.5], [0.5, 0.5, 0.5]])
    def test_short_or_flat_curve_takes_everything(self, scores):
        assert knee_index(scores) == len(scores) - 1

    def test_straight_line_has_no_knee(self):
        assert knee_index([1.0, 0.75, 0.5, 0.25, 0.0]) == 4


class TestModes:
    def test_count(self):
        outcome = apply_cutoff(PICKS, 0, PlannerRunParams(mode="count", count=3), REQS)

        assert outcome.length == 3
        assert outcome.notes == []

    def test_count_never_takes_duplicates(self):
        outcome = apply_cutoff(PICKS, 0, PlannerRunParams(mode="count", count=99), REQS)

        assert outcome.length == 5

    def test_count_keeps_all_seeds_with_a_note(self):
        seeds = [_entry(9, 1.0, reason="mandatory"), _entry(8, 0.9, reason="mandatory")]

        outcome = apply_cutoff(seeds + PICKS, 2, PlannerRunParams(mode="count", count=1), REQS)

        assert outcome.length == 2
        assert outcome.notes == [CutoffNote.SEEDS_EXCEED_COUNT]

    def test_budget_stops_before_overflow(self):
        outcome = apply_cutoff(PICKS, 0, PlannerRunParams(mode="budget", budget_minutes=25), REQS)

        assert outcome.length == 2

    def test_budget_counts_zero_minute_tests_as_free(self):
        picks = [_entry(0, 1.0, minutes=0), _entry(1, 0.5, minutes=0), _entry(2, 0.4, minutes=30)]

        outcome = apply_cutoff(picks, 0, PlannerRunParams(mode="budget", budget_minutes=10), REQS)

        assert outcome.length == 2

    def test_budget_seeds_over_budget_note(self):
        seeds = [_entry(9, 1.0, minutes=60, reason="mandatory")]

        outcome = apply_cutoff(
            seeds + PICKS, 1, PlannerRunParams(mode="budget", budget_minutes=30), REQS
        )

        assert outcome.length == 1
        assert outcome.notes == [CutoffNote.SEEDS_EXCEED_BUDGET]

    def test_coverage_stops_when_target_reached(self):
        params = PlannerRunParams(mode="coverage", coverage_percent=60)

        assert apply_cutoff(PICKS, 0, params, REQS).length == 2

    def test_full_coverage(self):
        params = PlannerRunParams(mode="coverage", coverage_percent=100)

        assert apply_cutoff(PICKS, 0, params, REQS).length == 4

    def test_coverage_without_requirements_falls_back_to_auto(self):
        params = PlannerRunParams(mode="coverage", coverage_percent=100)

        outcome = apply_cutoff(PICKS, 0, params, frozenset())

        assert outcome.length == 2
        assert outcome.notes == [CutoffNote.NO_REQUIREMENTS_FALLBACK]

    def test_auto_uses_the_knee(self):
        assert apply_cutoff(PICKS, 0, PlannerRunParams(mode="auto"), REQS).length == 2

    @pytest.mark.parametrize(
        ("percent", "length"), [(100, 2), (150, 3), (200, 4), (50, 1), (300, 5), (10, 1)]
    )
    def test_auto_scales_the_knee(self, percent, length):
        params = PlannerRunParams(mode="auto", knee_percent=percent)

        assert apply_cutoff(PICKS, 0, params, REQS).length == length

    def test_auto_scales_only_the_picks(self):
        seeds = [_entry(9, 1.0, reason="mandatory")]
        params = PlannerRunParams(mode="auto", knee_percent=200)

        # seed, then the knee after two picks; doubled to four picks
        assert apply_cutoff(seeds + PICKS, 1, params, REQS).length == 5

    def test_hints_show_the_unscaled_knee(self):
        assert compute_hints(PICKS, 0, REQS).knee == 2

    def test_auto_with_only_seeds(self):
        seeds = [_entry(9, 1.0, reason="mandatory")]

        assert apply_cutoff(seeds, 1, PlannerRunParams(mode="auto"), REQS).length == 1


class TestHints:
    def test_all_hints(self):
        hints = compute_hints(PICKS, 0, REQS)

        assert hints.knee == 2
        assert hints.full_requirement_coverage == 4
        assert hints.distance_zero_from == 6

    def test_hints_count_seeds_in_the_rank(self):
        seeds = [_entry(9, 1.0, reason="mandatory")]

        hints = compute_hints(seeds + PICKS, 1, REQS)

        assert hints.knee == 3
        assert hints.distance_zero_from == 7

    def test_missing_hints_are_none(self):
        picks = [_entry(0, 1.0), _entry(1, 0.5)]

        hints = compute_hints(picks, 0, frozenset({"R9"}))

        assert hints.full_requirement_coverage is None
        assert hints.distance_zero_from is None


# first pick with the placeholder 1.0, then small real distances with a drop
LOW_DISTANCE_PICKS = [
    _entry(i, s) for i, s in enumerate([1.0, 0.30, 0.29, 0.28, 0.27, 0.10, 0.09, 0.08, 0.07, 0.06])
]


class TestUnscoredFirstPick:
    """The first pick of a run without seeds has the placeholder score 1.0.

    Real distances of one domain are small, so that point must not take part in
    the knee, or the normalisation squeezes the real curve and the knee lands
    right after the first pick.
    """

    def test_placeholder_distorts_the_knee(self):
        assert apply_cutoff(LOW_DISTANCE_PICKS, 0, PlannerRunParams(mode="auto"), REQS).length == 2

    def test_knee_without_the_placeholder(self):
        outcome = apply_cutoff(
            LOW_DISTANCE_PICKS, 0, PlannerRunParams(mode="auto"), REQS, skip_first=True
        )

        assert outcome.length == 6

    def test_hint_without_the_placeholder(self):
        assert compute_hints(LOW_DISTANCE_PICKS, 0, REQS, skip_first=True).knee == 6

    def test_single_pick_without_predecessor(self):
        picks = [_entry(0, 1.0)]

        assert (
            apply_cutoff(picks, 0, PlannerRunParams(mode="auto"), REQS, skip_first=True).length == 1
        )
