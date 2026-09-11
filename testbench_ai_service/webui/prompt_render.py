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

#: The namespace the render context pane fills in. ``vars`` comes from the
#: variant's own declarations, so it is not part of the skeleton.
AGENT_NAMESPACE = "agent"

#: A ``Getattr`` chain rooted at ``agent`` needs at least this many segments
#: (the ``agent`` name itself plus one attribute) to name a real field.
_MIN_AGENT_PATH_LENGTH = 2


def _lint_env() -> Environment:
    # trim_blocks/lstrip_blocks match utils/build_prompt_utils.py:34 (and
    # _render_env, below) -- keep all three in sync if either changes, or the
    # lint pane will disagree with what the runtime actually emits. Prompts
    # are rendered as plain text, never HTML, so autoescape is off.
    return Environment(autoescape=False, trim_blocks=True, lstrip_blocks=True)


def _render_env() -> SandboxedEnvironment:
    # StrictUndefined so a typo in a variable name is reported rather than
    # rendering as an empty string the operator would never notice.
    return SandboxedEnvironment(
        autoescape=False,  # Prompts are plain text, never HTML.
        undefined=StrictUndefined,
        # trim_blocks/lstrip_blocks match utils/build_prompt_utils.py:34 (and
        # _lint_env, above) -- keep all three in sync if either changes, or
        # the preview will disagree with what the agent actually receives.
        trim_blocks=True,
        lstrip_blocks=True,
    )


def lint_template(content: str) -> LintResponse:
    """Parse *content* as Jinja and report a syntax error, if any."""
    try:
        _lint_env().parse(content)
    except TemplateSyntaxError as e:
        return LintResponse(
            ok=False,
            errors=[LintError(line=e.lineno or 1, column=1, message=e.message or "Syntax error")],
        )
    return LintResponse(ok=True, errors=[])


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
            # A template can raise anything at all through a filter or a call,
            # and a preview must never turn that into a 500.
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
