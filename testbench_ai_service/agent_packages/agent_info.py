"""What the service needs to know about an agent class, with or without importing it.

Built-in agents and agents of loaded packages are imported. An agent from a
package that is registered but not loaded (it needs a restart) is described by
the inspection report of the package's active version: its code must not run in
the service process yet.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, get_type_hints

from pydantic import BaseModel

from testbench_ai_service.agent_packages import loaded
from testbench_ai_service.agent_packages.manifest import ManifestError, load_manifest
from testbench_ai_service.models.config import AgentConfig
from testbench_ai_service.webui.agent_context import agent_data_sample


@dataclass(frozen=True)
class AgentInfo:
    data_fields: list[str]
    step_fields: dict[str, list[str]]
    args_schema: dict[str, Any] | None
    context_sample: dict[str, Any]
    agent_class: type | None  # None: described by the inspection report


class AgentUnavailable(Exception):  # noqa: N818 - name fixed by the plan's interface
    """A package agent without inspection report, or whose import failed."""


def import_agent_class(class_path: str) -> type:
    """Import *class_path* (``package.module.ClassName``).

    Raises:
        ValueError: *class_path* is malformed or cannot be imported.
    """
    try:
        module_path, class_name = class_path.rsplit(".", 1)
    except ValueError as e:
        raise ValueError(
            "'class_path' must be a valid import path, e.g. 'package.module.ClassName'."
        ) from e
    try:
        module = importlib.import_module(module_path)
        agent_class: type = getattr(module, class_name)
        return agent_class
    except (ImportError, AttributeError) as e:
        raise ValueError(f"cannot import '{class_name}' from '{module_path}': {e}") from e


def _args_schema(agent_class: type) -> dict[str, Any] | None:
    args_class = getattr(agent_class, "ARGS_CLASS", None)
    if not (isinstance(args_class, type) and issubclass(args_class, BaseModel)):
        return None
    try:
        return args_class.model_json_schema()
    except Exception:  # the class itself is used for validation; the schema is informative
        return None


def _from_class(agent_class: type) -> AgentInfo:
    data_class = getattr(agent_class, "AGENT_DATA_CLASS", None)
    return AgentInfo(
        data_fields=list(get_type_hints(data_class)) if data_class is not None else [],
        step_fields={
            step: list(get_type_hints(step_class))
            for step, step_class in getattr(agent_class, "STEP_DATA_CLASSES", {}).items()
        },
        args_schema=_args_schema(agent_class),
        context_sample=agent_data_sample(data_class) if data_class is not None else {},
        agent_class=agent_class,
    )


def _from_report(agent: AgentConfig, packages_dir: Path) -> AgentInfo:
    package = agent.package
    try:
        version = load_manifest(packages_dir).active(package or "")
    except ManifestError as e:
        raise AgentUnavailable(str(e)) from e
    if version is None:
        raise AgentUnavailable(f"agent package '{package}' has no active version")
    for report in version.report.agents.values():
        if report.class_path == agent.class_path:
            return AgentInfo(
                data_fields=list(report.data_fields),
                step_fields={step: list(fields) for step, fields in report.step_fields.items()},
                args_schema=report.args_schema,
                context_sample=dict(report.context_sample),
                agent_class=None,
            )
    raise AgentUnavailable(
        f"agent package '{package}' {version.version} has no agent '{agent.class_path}'"
    )


def _newer_version_active(package: str, packages_dir: Path) -> bool:
    """Whether another version of the loaded *package* was activated since startup.

    Its agents are then described by that version's report: the loaded code is
    the old version, and importing the new one needs a restart.
    """
    try:
        active = load_manifest(packages_dir).active(package)
    except ManifestError:
        return False
    return active is not None and active.version != loaded.loaded_version(package)


def agent_info(agent: AgentConfig, packages_dir: Path) -> AgentInfo:
    """Describe the agent class of *agent*.

    Without ``package`` the class is imported and import errors pass through as
    ``ValueError``. A loaded package is imported too, unless another version
    was activated since startup; a failing import marks the package failed. A
    package that is not loaded is never imported.

    Raises:
        ValueError: A built-in or ``class_path`` agent cannot be imported.
        AgentUnavailable: A package agent has no report or cannot be imported.
    """
    if agent.package is None:
        return _from_class(import_agent_class(agent.class_path))
    if not loaded.is_loaded(agent.package) or _newer_version_active(agent.package, packages_dir):
        return _from_report(agent, packages_dir)
    try:
        return _from_class(import_agent_class(agent.class_path))
    except Exception as e:
        reason = f"cannot import '{agent.class_path}': {e}"
        loaded.mark_failed(agent.package, reason)
        raise AgentUnavailable(reason) from e
