"""Inspect an unpacked agent package. Runs in a separate process, never in the service.

Importing a package runs its code, so the service starts this module as a subprocess
(see ``runner.py``) and reads the :class:`InspectionReport` it prints as JSON on stdout.
Everything else (prints of the package, log output) goes to stderr.
"""

from __future__ import annotations

import configparser
import contextlib
import importlib.util
import sys
from email.parser import Parser
from importlib.metadata import EntryPoint, PackageNotFoundError, version
from pathlib import Path
from typing import Any, get_type_hints

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion
from pydantic import BaseModel, ValidationError

from testbench_ai_service import __version__
from testbench_ai_service.agent_packages.models import AgentReport, InspectionReport
from testbench_ai_service.agent_packages.wheel import ENTRY_POINT_GROUP
from testbench_ai_service.agents.base import Agent
from testbench_ai_service.utils.prompt_utils import (
    step_agent_variable_errors,
    template_variables,
    validate_agent_variable,
)
from testbench_ai_service.validators import validate_prompt_file
from testbench_ai_service.webui.agent_context import agent_data_sample

LANGUAGES = ("en", "de")
TEMPLATE_NAMES = ("started", "failed", "template")
SERVICE_DISTRIBUTION = "testbench-ai-service"


def _dist_info(site_dir: Path) -> Path | None:
    found = sorted(site_dir.glob("*.dist-info"))
    return found[0] if len(found) == 1 else None


def _top_level_modules(site_dir: Path, dist_info: Path | None) -> list[str]:
    """Names the package adds to the top level of ``sys.path``.

    ``top_level.txt`` is only a claim of the package, so the unpacked entries are always
    added to it.
    """
    names: set[str] = set()
    if dist_info is not None and (dist_info / "top_level.txt").is_file():
        text = (dist_info / "top_level.txt").read_text(encoding="utf-8")
        names.update(line.strip() for line in text.splitlines() if line.strip())
    for entry in site_dir.iterdir():
        if entry.name.endswith((".dist-info", ".data")) or entry.name == "__pycache__":
            continue
        names.add(entry.name if entry.is_dir() else entry.name.split(".", 1)[0])
    return sorted(names)


def _module_conflicts(modules: list[str]) -> list[str]:
    errors = []
    for module in modules:
        try:
            exists = module in sys.modules or importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):
            exists = True
        if exists:
            errors.append(f"module '{module}' already exists in the service")
    return errors


def _requires_dist(dist_info: Path | None) -> list[str]:
    if dist_info is None or not (dist_info / "METADATA").is_file():
        return []
    metadata = Parser().parsestr((dist_info / "METADATA").read_text(encoding="utf-8"))
    return metadata.get_all("Requires-Dist") or []


def _requirement_errors(requirements: list[str], warnings: list[str]) -> list[str]:
    """Errors for requirements the service does not meet.

    In the binary, PyInstaller may not ship a bundled library's metadata, so a missing
    distribution is only a warning there (added to *warnings*).
    """
    errors = []
    frozen = bool(getattr(sys, "frozen", False))
    for line in requirements:
        try:
            requirement = Requirement(line)
        except InvalidRequirement as e:
            errors.append(f"invalid requirement '{line}': {e}")
            continue
        if requirement.marker is not None and not requirement.marker.evaluate({"extra": ""}):
            continue
        if canonicalize_name(requirement.name) == SERVICE_DISTRIBUTION:
            installed: str | None = __version__
        else:
            try:
                installed = version(requirement.name)
            except PackageNotFoundError:
                installed = None
        if installed is None and frozen:
            warnings.append(f"cannot verify '{line}' in the binary")
            continue
        if installed is None:
            errors.append(f"requires '{line}', which is not installed")
            continue
        try:
            matches = requirement.specifier.contains(installed, prereleases=True)
        except InvalidVersion:
            matches = False
        if not matches:
            errors.append(f"requires '{line}', but version {installed} is installed")
    return errors


def _entry_points(dist_info: Path | None) -> dict[str, str]:
    if dist_info is None or not (dist_info / "entry_points.txt").is_file():
        return {}
    parser = configparser.ConfigParser(delimiters=("=",), interpolation=None)
    parser.optionxform = str  # type: ignore[assignment,method-assign]
    parser.read_string((dist_info / "entry_points.txt").read_text(encoding="utf-8"))
    if not parser.has_section(ENTRY_POINT_GROUP):
        return {}
    return {key: value.strip() for key, value in parser.items(ENTRY_POINT_GROUP)}


def _field_names(data_class: Any) -> list[str]:
    return list(get_type_hints(data_class))


def _check_prompts(folder: Path, report: AgentReport, agent_class: type[Agent]) -> None:
    for language in LANGUAGES:
        relative = f"prompts/{language}/prompt.yaml"
        prompt_file = folder / "prompts" / language / "prompt.yaml"
        if not prompt_file.is_file():
            report.errors.append(f"{relative} is missing")
            continue
        try:
            validate_prompt_file(prompt_file)
        except ValueError as e:
            report.errors.append(f"{relative} is invalid: {e}")
            continue
        used = template_variables(prompt_file)
        if not validate_agent_variable(used, report.data_fields):
            undeclared = sorted(used - {f"agent.{name}" for name in report.data_fields})
            report.errors.append(f"{relative} uses undeclared agent variables: {undeclared}")
        for error in step_agent_variable_errors(prompt_file, agent_class.STEP_DATA_CLASSES):
            report.errors.append(f"{relative}: {error}")


def _check_templates(folder: Path, report: AgentReport) -> None:
    for language in LANGUAGES:
        directory = folder / "templates" / language
        for name in TEMPLATE_NAMES:
            if not directory.is_dir() or not any(
                path.is_file() and path.name.split(".", 1)[0] == name
                for path in directory.iterdir()
            ):
                report.errors.append(f"templates/{language}/{name}.* is missing")


def _check_args(agent_class: type[Agent], report: AgentReport) -> None:
    args_class = getattr(agent_class, "ARGS_CLASS", None)
    if not (isinstance(args_class, type) and issubclass(args_class, BaseModel)):
        return
    report.args_schema = args_class.model_json_schema()
    try:
        args_class.model_validate({})
    except ValidationError:
        report.warnings.append("args has required fields")


def _inspect_agent(name: str, value: str) -> AgentReport:
    entry_point = EntryPoint(name=name, value=value, group=ENTRY_POINT_GROUP)
    match = EntryPoint.pattern.match(value)
    if match is None or not match.group("attr"):
        return AgentReport(
            entry_point=value,
            class_path="",
            ok=False,
            errors=[f"entry point '{name} = {value}' is not of the form 'module:Class'"],
        )
    report = AgentReport(
        entry_point=value,
        class_path=f"{match.group('module')}.{match.group('attr')}",
        ok=False,
    )
    try:
        agent_class = entry_point.load()
    except (Exception, SystemExit) as e:
        report.errors.append(f"cannot import '{value}': {type(e).__name__}: {e}")
        return report
    if not (isinstance(agent_class, type) and issubclass(agent_class, Agent)):
        report.errors.append(f"'{report.class_path}' is not a subclass of Agent")
        return report
    try:
        data_class = getattr(agent_class, "AGENT_DATA_CLASS", None)
        if data_class is None:
            report.errors.append("AGENT_DATA_CLASS is not set")
        else:
            report.data_fields = _field_names(data_class)
            report.context_sample = agent_data_sample(data_class)
        report.step_fields = {
            step: _field_names(step_class)
            for step, step_class in agent_class.STEP_DATA_CLASSES.items()
        }
        report.uses_llm = bool(agent_class.USES_LLM)
        endpoint_path = getattr(agent_class, "DEFAULT_ENDPOINT_PATH", None)
        report.default_endpoint_path = endpoint_path if isinstance(endpoint_path, str) else None
        _check_args(agent_class, report)
        module_file = getattr(sys.modules[agent_class.__module__], "__file__", None)
        if module_file is None:
            report.errors.append(f"module '{agent_class.__module__}' has no file")
        else:
            folder = Path(module_file).parent
            _check_prompts(folder, report, agent_class)
            _check_templates(folder, report)
    except Exception as e:
        report.errors.append(f"{type(e).__name__}: {e}")
    report.ok = not report.errors
    return report


def inspect_site(site_dir: Path) -> InspectionReport:
    """Check the package unpacked in *site_dir*. Imports its code: run it in a subprocess."""
    site_dir = Path(site_dir).resolve()
    errors: list[str] = []
    dist_info = _dist_info(site_dir)
    if dist_info is None:
        errors.append("the package needs exactly one *.dist-info directory")

    # Before site_dir is on sys.path, so find_spec only sees what the service has.
    conflicts = _module_conflicts(_top_level_modules(site_dir, dist_info))
    errors += conflicts
    warnings: list[str] = []
    errors += _requirement_errors(_requires_dist(dist_info), warnings)
    try:
        entry_points = _entry_points(dist_info)
    except configparser.Error as e:
        errors.append(f"entry_points.txt is malformed: {e}")
        entry_points = {}
    if not entry_points:
        errors.append(f"no entry point in group '{ENTRY_POINT_GROUP}'")

    agents: dict[str, AgentReport] = {}
    # A conflicting module would shadow the service's own code, so nothing is imported then.
    if not conflicts and entry_points:
        sys.path.insert(0, str(site_dir))
        agents = {name: _inspect_agent(name, value) for name, value in entry_points.items()}
    ok = not errors and bool(agents) and all(agent.ok for agent in agents.values())
    return InspectionReport(ok=ok, errors=errors, warnings=warnings, agents=agents)


def main(argv: list[str]) -> int:
    """Inspect ``argv[0]`` and print the report as JSON; exit 0 even if the package fails."""
    if len(argv) != 1:
        sys.stderr.write("usage: inspector <site_dir>\n")
        return 2
    stdout = sys.stdout
    with contextlib.redirect_stdout(sys.stderr):
        report = inspect_site(Path(argv[0]))
    output = report.model_dump_json()
    buffer = getattr(stdout, "buffer", None)
    if buffer is not None:
        buffer.write(output.encode("utf-8"))
        buffer.flush()
    else:
        stdout.write(output)
        stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
