"""Jinja lint and preview for the prompt editor.

**Why the sandbox is not optional.** ``POST /prompts/render`` evaluates template
text taken from the request body. Jinja2's default ``Environment`` permits
attribute traversal, so ``{{ ''.__class__.__mro__[1].__subclasses__() }}``
reaches Python internals and from there the process's own globals -- an
unsandboxed render endpoint is remote code execution against the service.
``SandboxedEnvironment`` refuses that traversal. Real templates use
``agent.*`` and ``vars.*`` and nothing else, so the preview still matches what
the agent sends. The route is admin-only on top of this (design D3).

Lint uses a plain environment because ``parse()`` builds an AST and evaluates
nothing.

Both environments carry ``trim_blocks``/``lstrip_blocks`` to match
``utils/build_prompt_utils.py:34``. Whitespace control changes what a template
*emits*, so different flags would make the preview disagree with the runtime.
"""

from collections.abc import Iterable
from typing import Any

from jinja2 import Environment, StrictUndefined, TemplateSyntaxError, nodes
from jinja2.exceptions import SecurityError, UndefinedError
from jinja2.sandbox import SandboxedEnvironment

from testbench_ai_service.log import logger
from testbench_ai_service.webui.models import (
    LintError,
    LintResponse,
    PromptMessageDoc,
    RenderedMessage,
)

AGENT_NAMESPACE = "agent"

_MIN_AGENT_PATH_LENGTH = 2


def _lint_env() -> Environment:
    return Environment(autoescape=False, trim_blocks=True, lstrip_blocks=True)


def _render_env() -> SandboxedEnvironment:
    return SandboxedEnvironment(
        autoescape=False,  # Prompts are plain text, never HTML.
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


#: Tags that open a block which must be closed by ``end<tag>``.
_BLOCK_TAGS = frozenset(
    {"if", "for", "macro", "call", "filter", "with", "block", "raw", "autoescape", "trans"}
)


def _unclosed_block(content: str) -> tuple[str, int] | None:
    """The innermost block *content* opens and never closes, with its line.

    Jinja reports an unclosed block where it noticed -- at the end of the
    template -- which for a long prompt is a screen away from the ``{% if %}``
    that needs its ``{% endif %}``. Walking the tags finds where it started.
    """
    open_blocks: list[tuple[str, int]] = []
    try:
        tokens = list(_lint_env().lex(content))
    except TemplateSyntaxError:
        return None
    for index, (line, kind, _value) in enumerate(tokens):
        if kind != "block_begin":
            continue
        name = next((value for _l, k, value in tokens[index + 1 :] if k != "whitespace"), "")
        if name in _BLOCK_TAGS:
            open_blocks.append((name, line))
        elif name == "set":
            # `{% set x %}...{% endset %}` is a block; `{% set x = 1 %}` is not.
            rest = [k for _l, k, _v in tokens[index + 1 :]]
            end = rest.index("block_end") if "block_end" in rest else len(rest)
            if "operator" not in rest[:end]:
                open_blocks.append((name, line))
        elif name.startswith("end") and open_blocks and open_blocks[-1][0] == name[3:]:
            open_blocks.pop()
    return open_blocks[-1] if open_blocks else None


def _unusable_nodes(template: nodes.Template) -> list[LintError]:
    """What parses but cannot render here: unknown filters and tests, other files.

    The render environment has no loader and only the built-in filters, so these
    fail at the first render -- for a prompt in use, in the middle of an agent run.
    """
    env = _render_env()
    errors: list[LintError] = []
    for node in template.find_all((nodes.Filter, nodes.Test)):
        known = env.filters if isinstance(node, nodes.Filter) else env.tests
        kind = "filter" if isinstance(node, nodes.Filter) else "test"
        if node.name not in known:
            errors.append(
                LintError(line=node.lineno, column=1, message=f"No {kind} named '{node.name}'.")
            )
    for node in template.find_all((nodes.Include, nodes.Import, nodes.FromImport, nodes.Extends)):
        tag = type(node).__name__.replace("FromImport", "from").lower()
        errors.append(
            LintError(
                line=node.lineno,
                column=1,
                message=f"'{{% {tag} %}}' is not available: a prompt cannot load other files.",
            )
        )
    return sorted(errors, key=lambda error: error.line)


def lint_template(content: str) -> LintResponse:
    """Check *content* as a prompt template: its syntax, and that it can render here."""
    try:
        template = _lint_env().parse(content)
    except TemplateSyntaxError as e:
        line, message = e.lineno or 1, e.message or "Syntax error"
        # Both of Jinja's ways of saying "a block was left open": it ran out of
        # template, or it met an end tag that belongs to an outer block.
        left_open = "end of template" in message or "needs to be closed" in message
        unclosed = _unclosed_block(content) if left_open else None
        if unclosed is not None:
            tag, line = unclosed
            message = f"'{{% {tag} %}}' is never closed: '{{% end{tag} %}}' is missing."
        return LintResponse(ok=False, errors=[LintError(line=line, column=1, message=message)])
    errors = _unusable_nodes(template)
    return LintResponse(ok=not errors, errors=errors)


def render_messages(
    messages: list[PromptMessageDoc],
    prompt_vars: dict[str, Any],
    agent_context: dict[str, Any],
) -> list[RenderedMessage]:
    """Render every message, reporting per-message failures in place.

    A failing message does not abort the batch, mirroring ``build_messages``,
    which logs and falls back rather than dropping the rest.
    """
    env = _render_env()
    rendered: list[RenderedMessage] = []

    for message in messages:
        try:
            text = (
                env.from_string(message.content)
                .render(agent=agent_context, vars=prompt_vars)
                .strip()
            )
            rendered.append(RenderedMessage(role=message.role, content=text, error=None))
        except SecurityError as e:
            logger.warning("Refused a sandboxed prompt render: %s", e)
            rendered.append(
                RenderedMessage(
                    role=message.role,
                    content="",
                    error=f"This template is not permitted in a preview: {e}",
                )
            )
        except (TemplateSyntaxError, UndefinedError) as e:
            rendered.append(RenderedMessage(role=message.role, content="", error=str(e)))
        except Exception as e:
            logger.warning("Prompt preview failed: %s", e)
            rendered.append(
                RenderedMessage(role=message.role, content="", error=f"{type(e).__name__}: {e}")
            )

    return rendered


def _dotted_path(node: nodes.Getattr) -> list[str] | None:
    """The attribute chain under a ``Getattr``, root first, or None."""
    parts: list[str] = []
    current: Any = node
    while isinstance(current, nodes.Getattr):
        parts.append(current.attr)
        current = current.node
    if not isinstance(current, nodes.Name):
        return None
    parts.append(current.name)
    parts.reverse()
    return parts


def context_skeleton(contents: Iterable[str]) -> dict[str, Any]:
    """A nested skeleton of every ``agent.*`` path *contents* reference.

    Uses the real Jinja AST rather than a regex, so it agrees with what the
    renderer will actually look up. An unparseable template contributes nothing
    -- lint is what reports that, and a broken template must not empty the pane.

    Not scope-aware: a template that rebinds ``agent`` locally (e.g.
    ``{% set agent = 5 %}{{ agent.x }}``) still contributes ``x`` to the
    skeleton, since the AST walk does not track ``set``/loop bindings. That is
    acceptable for a preview aid -- it is not a security boundary -- but it
    means the skeleton can list a path a real render never uses.
    """
    env = _lint_env()
    skeleton: dict[str, Any] = {}

    for content in contents:
        try:
            ast = env.parse(content)
        except TemplateSyntaxError:
            continue
        for node in ast.find_all(nodes.Getattr):
            parts = _dotted_path(node)
            if not parts or parts[0] != AGENT_NAMESPACE or len(parts) < _MIN_AGENT_PATH_LENGTH:
                continue
            cursor = skeleton
            for part in parts[1:-1]:
                nested = cursor.get(part)
                if not isinstance(nested, dict):
                    nested = {}
                    cursor[part] = nested
                cursor = nested
            cursor.setdefault(parts[-1], "")

    return skeleton
