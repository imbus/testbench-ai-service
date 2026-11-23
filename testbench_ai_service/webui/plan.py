"""Work out what a set of config edits would do, without doing any of it."""

from pathlib import Path
from typing import Any

from testbench_ai_service.config import AppConfig
from testbench_ai_service.webui.config_io import read_config_file, redact_toml_text
from testbench_ai_service.webui.diff import file_diff
from testbench_ai_service.webui.document import apply_edits, load_document, render_document
from testbench_ai_service.webui.edits import merge_edits, validate_edit_paths
from testbench_ai_service.webui.models import PreviewResponse
from testbench_ai_service.webui.reload import restart_required
from testbench_ai_service.webui.validate import validate_config_dict


def plan_change(
    edits: dict[str, Any],
    config_path: Path,
    running: AppConfig,
    *,
    allow_server_only: bool = False,
) -> tuple[PreviewResponse, str, bool]:
    """Work out what applying *edits* would do, without doing any of it.

    Returns the preview payload, the rendered TOML text, and whether there is
    anything to write, so ``apply`` can reuse exactly the text ``preview``
    showed rather than re-deriving it and risking a different result.

    Everything is computed against *config_path* as it is on disk right now,
    which is what makes a second operator's diff show the first operator's
    changes instead of silently reverting them (spec 6.1).

    ``allow_server_only`` lets server-side callers (agent package registration) set
    ``agents.<key>.package``, which the console's own edits may never touch.
    """
    validate_edit_paths(edits, allow_server_only=allow_server_only)

    document = load_document(config_path)
    current_text = render_document(document)

    merged = merge_edits(read_config_file(config_path), edits)
    candidate, issues = validate_config_dict(merged)

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
    proposed_text = render_document(document)
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
            restart_required=restart_required(running, candidate),
            in_flight_tasks=0,
            toml=redact_toml_text(proposed_text),
        ),
        proposed_text,
        has_write,
    )
