"""Work out what a set of config edits would do, without doing any of it."""

from collections.abc import Collection
from pathlib import Path
from typing import Any

from testbench_ai_service.config import AppConfig
from testbench_ai_service.webui.config_io import read_config_file, redact_toml_text
from testbench_ai_service.webui.diff import file_diff
from testbench_ai_service.webui.document import (
    apply_edits,
    line_ending,
    load_document,
    render_document,
    render_edited,
    with_line_ending,
)
from testbench_ai_service.webui.edits import merge_edits, validate_edit_paths
from testbench_ai_service.webui.models import PreviewResponse
from testbench_ai_service.webui.reload import restart_required
from testbench_ai_service.webui.validate import prompt_var_issues, validate_config_dict


def plan_change(
    edits: dict[str, Any],
    config_path: Path,
    running: AppConfig,
    *,
    routed_agents: Collection[str] | None = None,
) -> tuple[PreviewResponse, str, bool]:
    """Work out what applying *edits* would do, without doing any of it.

    Returns the preview payload, the rendered TOML text, and whether there is
    anything to write, so ``apply`` can reuse exactly the text ``preview``
    showed rather than re-deriving it and risking a different result.

    The text to write keeps the line endings of the file on disk: a ``config.toml``
    saved with CRLF stays CRLF. The preview's diff and ``toml`` always use LF, which
    is what the browser displays.

    Everything is computed against *config_path* as it is on disk right now,
    which is what makes a second operator's diff show the first operator's
    changes instead of silently reverting them (spec 6.1).

    ``routed_agents`` are the agents that got an endpoint at startup; see
    :func:`~testbench_ai_service.webui.reload.restart_required`.

    """
    validate_edit_paths(edits)

    document = load_document(config_path)
    current_text = render_document(document)

    merged = merge_edits(read_config_file(config_path), edits)
    candidate, issues = validate_config_dict(merged)
    if candidate is not None:
        issues = prompt_var_issues(candidate, edits)
        if issues:
            candidate = None

    if candidate is None:
        return (
            PreviewResponse(
                valid=False,
                issues=issues,
                diffs=[],
                restart_required=[],
                in_flight_tasks=0,
                toml=redact_toml_text(current_text),
            ),
            current_text,
            False,
        )

    apply_edits(document, edits)
    proposed_text = render_edited(document, current_text)
    diff = file_diff(
        str(config_path.resolve()),
        redact_toml_text(current_text),
        redact_toml_text(proposed_text),
    )

    has_write = current_text != proposed_text

    return (
        PreviewResponse(
            valid=True,
            issues=[],
            diffs=[diff] if diff is not None else [],
            restart_required=restart_required(running, candidate, routed_agents),
            in_flight_tasks=0,
            toml=redact_toml_text(proposed_text),
        ),
        with_line_ending(proposed_text, line_ending(config_path)),
        has_write,
    )
