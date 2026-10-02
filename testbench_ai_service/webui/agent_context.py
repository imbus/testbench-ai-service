"""A typed sample of the ``agent.*`` namespace, for the prompt editor.

The template-derived skeleton (``prompt_render.context_skeleton``) only knows
the paths a template already uses, each as ``""``. What an agent actually
*provides* is declared on its ``AGENT_DATA_CLASS`` TypedDict, so this module
walks those type hints into a sample object whose leaves name their type
(``"<str>"``, ``"<int | None>"``, ...). The editor shows it as the list of
insertable fields and prefills the render context with it.

It is a hint, not a contract: anything the walk cannot describe degrades to
the type's name rather than failing the prompt document.
"""

import dataclasses
import importlib
import types
from collections.abc import Iterable, Mapping
from pathlib import PurePath
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints, is_typeddict

from pydantic import BaseModel

from testbench_ai_service.log import logger
from testbench_ai_service.models.config import AgentConfig

#: Nested objects deeper than this are summarised as ``"<TypeName>"``. Deep
#: enough for ``test_case_set_obj.details.spec.description``, shallow enough
#: that a recursive model cannot flood the pane.
MAX_DEPTH = 5

#: The key placeholder for a ``dict[str, T]`` sample.
DICT_KEY = "<key>"


def _type_name(tp: Any) -> str:
    if tp is type(None):
        return "None"
    if get_origin(tp) is Literal:
        return " | ".join(repr(arg) for arg in get_args(tp))
    return getattr(tp, "__name__", None) or str(tp).replace("typing.", "")


def _fields(tp: Any) -> dict[str, Any] | None:
    """The field types of a structured type, or None for anything else."""
    try:
        if is_typeddict(tp):
            return get_type_hints(tp)
        if isinstance(tp, type) and issubclass(tp, BaseModel):
            return {name: field.annotation for name, field in tp.model_fields.items()}
        if dataclasses.is_dataclass(tp) and isinstance(tp, type):
            hints = get_type_hints(tp)
            return {field.name: hints.get(field.name, Any) for field in dataclasses.fields(tp)}
    except Exception as e:  # A forward reference that does not resolve, say.
        logger.debug("Cannot read the fields of %r: %s", tp, e)
        return {}
    return None


def _is_union(tp: Any) -> bool:
    return get_origin(tp) is Union or (
        hasattr(types, "UnionType") and isinstance(tp, types.UnionType)
    )


def _describe_union(tp: Any, depth: int, seen: frozenset[Any]) -> Any:
    args = get_args(tp)
    present = [arg for arg in args if arg is not type(None)]
    if len(present) != 1:
        return "<" + " | ".join(_type_name(arg) for arg in args) + ">"
    inner = describe(present[0], depth, seen)
    if isinstance(inner, str) and len(present) < len(args):
        return f"{inner[:-1]} | None>"
    return inner


def _describe_collection(tp: Any, depth: int, seen: frozenset[Any]) -> Any:
    """A mapping's or a sequence's sample, or None for anything else."""
    origin = get_origin(tp)
    if not isinstance(origin, type) or origin is str:
        return None
    args = [arg for arg in get_args(tp) if arg is not Ellipsis]
    if issubclass(origin, Mapping):
        return {DICT_KEY: describe(args[-1], depth + 1, seen)} if args else {}
    if issubclass(origin, Iterable):
        return [describe(args[0], depth + 1, seen)] if args else ["<Any>"]
    return None


def describe(tp: Any, depth: int = 0, seen: frozenset[Any] = frozenset()) -> Any:
    """A sample value for *tp*: a dict for objects, a one-item list for
    sequences, ``{"<key>": ...}`` for mappings, ``"<type>"`` for leaves."""
    if _is_union(tp):
        return _describe_union(tp, depth, seen)

    collection = _describe_collection(tp, depth, seen)
    if collection is not None:
        return collection

    fields = _fields(tp)
    if fields is None or depth >= MAX_DEPTH or tp in seen:
        return "<Any>" if tp is Any else f"<{_type_name(tp)}>"
    return {
        name: describe(field_type, depth + 1, seen | {tp}) for name, field_type in fields.items()
    }


def agent_data_sample(agent_data_class: type) -> dict[str, Any]:
    """The typed sample for one ``AGENT_DATA_CLASS``."""
    sample = describe(agent_data_class)
    return sample if isinstance(sample, dict) else {}


def _prompt_dir(agent: AgentConfig) -> str | None:
    # Config files are written on Windows as often as not, so a backslash in
    # ``prompt.file`` is a separator here no matter which OS reads it.
    parts = PurePath(str(agent.prompt.file).replace("\\", "/")).parts
    return parts[0] if len(parts) > 1 else None


def _agent_data_class(class_path: str) -> type | None:
    try:
        module_path, class_name = class_path.rsplit(".", 1)
        agent_class = getattr(importlib.import_module(module_path), class_name)
    except Exception as e:
        logger.warning("Cannot import agent class '%s' for its context: %s", class_path, e)
        return None
    return getattr(agent_class, "AGENT_DATA_CLASS", None)


def _deep_union(into: dict[str, Any], other: Mapping[str, Any]) -> None:
    for key, value in other.items():
        if isinstance(into.get(key), dict) and isinstance(value, dict):
            _deep_union(into[key], value)
        else:
            into.setdefault(key, value)


def agent_context_sample(agents: Mapping[str, AgentConfig], prompt_dir: str) -> dict[str, Any]:
    """The typed ``agent.*`` sample for the prompt in *prompt_dir*.

    Every configured agent whose prompt lives in that directory contributes,
    so a prompt shared by two agents lists what either provides.
    """
    sample: dict[str, Any] = {}
    for agent in agents.values():
        if _prompt_dir(agent) != prompt_dir:
            continue
        data_class = _agent_data_class(agent.class_path)
        if data_class is not None:
            _deep_union(sample, agent_data_sample(data_class))
    return sample
