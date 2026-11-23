"""Reading the linked test cases against the aspects."""

from testbench_ai_service.utils.traceability.interpretation import (
    batches,
    interpret_set,
    render_test_case,
    validate_evidence,
)
from testbench_ai_service.utils.traceability.models import (
    Aspect,
    AspectEvidence,
    LinkedSet,
    SetInterpretation,
    TestCall,
    TestCase,
)

ASPECTS = [
    Aspect(id="A1", statement="Login succeeds", kind="happy_path", source_quote="log in"),
    Aspect(id="A2", statement="Lock after 3 failures", kind="boundary", source_quote="locked"),
]


def _evidence(aspect_id, key, strength="full"):
    return AspectEvidence(aspect_id=aspect_id, test_case_key=key, strength=strength, evidence="e")


def _set(count: int) -> LinkedSet:
    return LinkedSet(
        key="1",
        spec_key="s1",
        unique_id="U-1",
        title="Login",
        path="/Auth/Login",
        description="Checks the login",
        spec_status="Released",
        linked_as_whole=True,
        test_cases=[TestCase(key=f"TC-{n}", parameters={}, calls=[]) for n in range(count)],
    )


class TestValidateEvidence:
    def test_unknown_aspects_and_test_cases_are_dropped(self):
        kept = validate_evidence(
            [_evidence("A9", "TC-0"), _evidence("A1", "TC-99"), _evidence("A1", "TC-0")],
            ["A1", "A2"],
            {"TC-0"},
        )

        assert [(e.aspect_id, e.test_case_key) for e in kept] == [("A1", "TC-0")]

    def test_a_pair_keeps_its_stronger_evidence(self):
        kept = validate_evidence(
            [_evidence("A1", "TC-0", "partial"), _evidence("A1", "TC-0", "full")],
            ["A1"],
            {"TC-0"},
        )

        assert [e.strength for e in kept] == ["full"]

    def test_ids_are_matched_after_trimming(self):
        kept = validate_evidence([_evidence(" a2 ", " TC-0 ")], ["A1", "A2"], {"TC-0"})

        assert [(e.aspect_id, e.test_case_key) for e in kept] == [("A2", "TC-0")]

    def test_evidence_is_sorted_by_aspect_order_then_test_case(self):
        kept = validate_evidence(
            [_evidence("A2", "TC-0"), _evidence("A1", "TC-1"), _evidence("A1", "TC-0")],
            ["A1", "A2"],
            {"TC-0", "TC-1"},
        )

        assert [(e.aspect_id, e.test_case_key) for e in kept] == [
            ("A1", "TC-0"),
            ("A1", "TC-1"),
            ("A2", "TC-0"),
        ]


def test_batches_cut_a_list_into_portions():
    assert batches([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_a_test_case_renders_parameters_phases_and_checks():
    test_case = TestCase(
        key="TC-1",
        parameters={"user": "bob"},
        calls=[
            TestCall(phase="Setup", keyword="Open login page", check=False, arguments={}),
            TestCall(
                phase="TestStep", keyword="Check message", check=True, arguments={"text": "Locked"}
            ),
        ],
    )

    assert render_test_case(test_case) == (
        "Test case TC-1\n"
        "  parameters: user=bob\n"
        "  Setup: Open login page()\n"
        "  TestStep: Check message(text=Locked) [check]"
    )


async def test_a_large_set_is_interpreted_in_batches_and_merged():
    seen_batches = []

    async def ask(step, schema, agent_data):
        assert step == "interpretation"
        assert schema is SetInterpretation
        keys = [
            line.split()[-1]
            for line in agent_data["test_cases"].splitlines()
            if line.startswith("Test case")
        ]
        seen_batches.append(keys)
        return SetInterpretation(
            evidence=[_evidence("A1", keys[0], "partial"), _evidence("A1", "TC-0")]
        )

    evidence = await interpret_set(ask, "REQ-42: Login", ASPECTS, _set(5), batch_size=2)

    assert seen_batches == [["TC-0", "TC-1"], ["TC-2", "TC-3"], ["TC-4"]]
    assert [(e.aspect_id, e.test_case_key, e.strength) for e in evidence] == [
        ("A1", "TC-0", "full"),
        ("A1", "TC-2", "partial"),
        ("A1", "TC-4", "partial"),
    ]


async def test_a_set_without_test_cases_asks_nothing():
    async def ask(step, schema, agent_data):
        raise AssertionError("must not be called")

    assert await interpret_set(ask, "REQ-42: Login", ASPECTS, _set(0), batch_size=2) == []
