"""Splitting a requirement into aspects, and keeping only those the text backs."""

import pytest

from testbench_ai_service.utils.rm_service import Requirement
from testbench_ai_service.utils.traceability.aspects import (
    NoAspectsError,
    decompose,
    render_requirement,
    requirement_text,
    validate_aspects,
)
from testbench_ai_service.utils.traceability.models import Aspect, AspectList

DESCRIPTION = (
    "<html><head><style>.rate-limit { color: red }</style></head><body>"
    "<p>A user can log in with e-mail and password.</p>"
    "<p>After 3 failed attempts the account is locked.</p></body></html>"
)


def _requirement(description: str | None = DESCRIPTION) -> Requirement:
    return Requirement(
        key="473",
        version="1",
        title="Login",
        description=description,
        status="approved",
        priority="high",
        owner=None,
        documents=[],
        external_ref="REQ-42",
    )


def _aspect(statement: str, quote: str, kind: str = "happy_path", aspect_id: str = "x") -> Aspect:
    return Aspect(id=aspect_id, statement=statement, kind=kind, source_quote=quote)


SOURCE = requirement_text(_requirement())


class TestValidateAspects:
    def test_aspects_quoting_the_text_are_kept_and_numbered(self):
        answer = AspectList(
            aspects=[
                _aspect("Login succeeds", "log in with e-mail and password"),
                _aspect("Lock after 3 failures", "after 3 failed attempts", "boundary"),
            ]
        )

        kept = validate_aspects(answer, SOURCE, max_aspects=12)

        assert [(a.id, a.statement) for a in kept] == [
            ("A1", "Login succeeds"),
            ("A2", "Lock after 3 failures"),
        ]

    def test_a_quote_not_in_the_text_is_dropped_and_ids_close_the_gap(self):
        answer = AspectList(
            aspects=[
                _aspect("Rate limiting", "requests are rate limited"),
                _aspect("Login succeeds", "log in with e-mail and password"),
            ]
        )

        kept = validate_aspects(answer, SOURCE, max_aspects=12)

        assert [(a.id, a.statement) for a in kept] == [("A1", "Login succeeds")]

    def test_quote_from_the_head_is_not_requirement_text(self):
        answer = AspectList(aspects=[_aspect("Rate limit is red", "rate-limit { color: red }")])

        assert validate_aspects(answer, SOURCE, max_aspects=12) == []

    def test_quotes_match_regardless_of_case_and_whitespace(self):
        answer = AspectList(aspects=[_aspect("Lock", "AFTER 3   failed\nattempts")])

        assert len(validate_aspects(answer, SOURCE, max_aspects=12)) == 1

    def test_a_quote_across_list_items_is_found_as_the_model_read_it(self):
        requirement = _requirement("<ul><li>Lock after 3 attempts</li><li>Unlock by mail</li></ul>")
        rendered = render_requirement(requirement)
        answer = AspectList(aspects=[_aspect("Lock", "- Lock after 3 attempts\n- Unlock by mail")])

        assert "Description:\n- Lock after 3 attempts\n- Unlock by mail" in rendered
        assert len(validate_aspects(answer, requirement_text(requirement), max_aspects=12)) == 1

    def test_duplicate_statements_are_dropped(self):
        answer = AspectList(
            aspects=[
                _aspect("Login succeeds", "log in with e-mail"),
                _aspect("  login   SUCCEEDS ", "with e-mail and password"),
            ]
        )

        assert len(validate_aspects(answer, SOURCE, max_aspects=12)) == 1

    def test_the_list_is_cut_to_max_aspects(self):
        answer = AspectList(
            aspects=[_aspect(f"Statement {n}", "the account is locked") for n in range(5)]
        )

        kept = validate_aspects(answer, SOURCE, max_aspects=3)

        assert [a.id for a in kept] == ["A1", "A2", "A3"]


class TestRendering:
    def test_the_requirement_renders_ref_title_attributes_and_visible_description(self):
        rendered = render_requirement(_requirement())

        assert rendered.splitlines()[0] == "REQ-42: Login"
        assert "status: approved | priority: high" in rendered
        assert "After 3 failed attempts the account is locked." in rendered
        assert "color: red" not in rendered

    def test_a_requirement_without_description_says_so(self):
        assert "(none, only the title is known)" in render_requirement(_requirement(None))


async def test_decompose_asks_the_aspects_step_and_validates_the_answer():
    calls = []

    async def ask(step, schema, agent_data):
        calls.append((step, schema, agent_data))
        return AspectList(aspects=[_aspect("Login succeeds", "log in with e-mail and password")])

    aspects = await decompose(ask, _requirement(), max_aspects=12)

    assert [a.id for a in aspects] == ["A1"]
    ((step, schema, agent_data),) = calls
    assert step == "aspects"
    assert schema is AspectList
    assert agent_data["max_aspects"] == "12"
    assert agent_data["requirement"].startswith("REQ-42: Login")


async def test_decompose_raises_when_no_aspect_is_backed_by_the_text():
    async def ask(step, schema, agent_data):
        return AspectList(aspects=[_aspect("Invented", "nowhere in the text")])

    with pytest.raises(NoAspectsError):
        await decompose(ask, _requirement(), max_aspects=12)
