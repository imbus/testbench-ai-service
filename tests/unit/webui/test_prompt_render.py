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
        """build_prompt_utils.py:34 uses trim_blocks and lstrip_blocks."""
        rendered = render_messages([msg("{% if true %}\nX\n{% endif %}\n")], {}, {})
        assert rendered[0].content == "X"

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
