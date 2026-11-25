import pytest

from testbench_ai_service.webui.models import PromptMessageDoc
from testbench_ai_service.webui.prompt_render import (
    context_skeleton,
    lint_template,
    render_messages,
)


def msg(text, role="user"):
    return PromptMessageDoc(role=role, source="inline", file=None, content=text, readable=True)


class TestLint:
    def test_a_valid_template_is_ok(self):
        result = lint_template("Hallo {{ agent.name }}")
        assert result.ok is True
        assert result.errors == []

    def test_a_syntax_error_reports_its_line(self):
        result = lint_template("line one\n{% if %}\nline three")
        assert result.ok is False
        assert result.errors[0].line == 2

    def test_the_message_does_not_leak_a_filesystem_path(self):
        result = lint_template("{% for %}")
        assert "/" not in result.errors[0].message.replace("Encountered unknown tag", "")

    def test_parse_does_not_execute(self):
        """env.parse builds an AST; it must not evaluate the expression."""
        assert lint_template("{{ ''.__class__.__mro__ }}").ok is True


class TestRenderIsSandboxed:
    @pytest.mark.parametrize(
        "attack",
        [
            "{{ ''.__class__ }}",
            "{{ ''.__class__.__mro__[1].__subclasses__() }}",
            "{{ self.__init__.__globals__ }}",
            "{{ cycler.__init__.__globals__.os.popen('echo pwned').read() }}",
        ],
    )
    def test_dunder_traversal_is_refused(self, attack):
        """Design §3.2: a default Environment here would be RCE."""
        rendered = render_messages([msg(attack)], {}, {})
        assert rendered[0].error is not None, f"sandbox did not stop {attack!r}"
        assert "pwned" not in rendered[0].content


class TestRender:
    def test_renders_both_namespaces(self):
        rendered = render_messages(
            [msg("{{ agent.title }} / {{ vars.tone }}")],
            {"tone": "kurz"},
            {"title": "Bericht"},
        )
        assert rendered[0].content == "Bericht / kurz"
        assert rendered[0].error is None

    def test_whitespace_flags_match_the_runtime(self):
        """build_prompt_utils.py:34 uses trim_blocks and lstrip_blocks.

        The template must differ in INTERIOR whitespace between flagged and
        unflagged rendering -- render_messages ends in .strip(), so a template
        that differs only at the edges cannot detect the flags going missing.
        """
        rendered = render_messages([msg("A\n{% if true %}\nB\n{% endif %}\nC")], {}, {})
        assert rendered[0].content == "A\nB\nC"

    def test_a_failing_message_does_not_abort_the_batch(self):
        rendered = render_messages([msg("{% if %}"), msg("fine")], {}, {})
        assert rendered[0].error is not None
        assert rendered[1].content == "fine"
        assert rendered[1].error is None

    def test_an_undefined_variable_is_reported_not_silently_blank(self):
        rendered = render_messages([msg("{{ agent.absent }}")], {}, {})
        assert rendered[0].error is not None

    def test_the_role_is_carried_through(self):
        rendered = render_messages([msg("x", role="system")], {}, {})
        assert rendered[0].role == "system"


class TestContextSkeleton:
    def test_builds_nested_keys_from_agent_paths(self):
        assert context_skeleton(["{{ agent.report.title }} {{ agent.count }}"]) == {
            "report": {"title": ""},
            "count": "",
        }

    def test_ignores_the_vars_namespace(self):
        assert context_skeleton(["{{ vars.tone }}"]) == {}

    def test_an_unparseable_template_contributes_nothing(self):
        assert context_skeleton(["{% if %}"]) == {}


class TestLintBeyondSyntax:
    def test_an_unclosed_block_is_reported_where_it_opens(self):
        content = "line one\n{% if agent.x %}\n" + "body\n" * 40 + "last line"

        result = lint_template(content)

        assert result.ok is False
        assert result.errors[0].line == 2
        assert "{% endif %}" in result.errors[0].message

    def test_the_innermost_unclosed_block_is_the_one_named(self):
        result = lint_template("{% for x in agent.items %}\n{% if x %}\n{{ x }}\n{% endfor %}")

        assert result.ok is False
        assert "{% if %}" in result.errors[0].message
        assert result.errors[0].line == 2

    def test_a_closed_block_and_an_inline_set_are_fine(self):
        content = "{% set n = 1 %}\n{% if n %}a{% else %}b{% endif %}\n{% set t %}x{% endset %}"

        assert lint_template(content).ok is True

    def test_an_unknown_filter_is_reported_at_its_line(self):
        result = lint_template("ok\n{{ agent.name|nosuchfilter }}")

        assert result.ok is False
        assert (result.errors[0].line, result.errors[0].message) == (
            2,
            "No filter named 'nosuchfilter'.",
        )

    def test_an_unknown_test_is_reported(self):
        result = lint_template("{% if agent.name is nosuchtest %}x{% endif %}")

        assert result.ok is False
        assert result.errors[0].message == "No test named 'nosuchtest'."

    def test_a_known_filter_and_test_pass(self):
        assert lint_template("{{ agent.name|upper }}{% if agent.n is defined %}x{% endif %}").ok

    def test_loading_another_file_is_reported(self):
        result = lint_template("a\n{% include 'other.jinja' %}")

        assert result.ok is False
        assert result.errors[0].line == 2
        assert "cannot load other files" in result.errors[0].message
