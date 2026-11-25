"""What the service needs to know about an agent class."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, get_type_hints

from pydantic import BaseModel

from testbench_ai_service.models.config import AgentConfig
from testbench_ai_service.webui.agent_context import agent_data_sample


@dataclass(frozen=True)
class AgentInfo:
    data_fields: list[str]
    step_fields: dict[str, list[str]]
    args_schema: dict[str, Any] | None
    context_sample: dict[str, Any]
    agent_class: type


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


def agent_info(agent: AgentConfig) -> AgentInfo:
    """Describe the agent class of *agent*, importing it.

    Raises:
        ValueError: The class cannot be imported.
    """
    agent_class = import_agent_class(agent.class_path)
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
