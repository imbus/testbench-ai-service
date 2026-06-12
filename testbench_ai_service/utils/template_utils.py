from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from testbench_ai_service.models.language import LanguageOption


def resolve_template_path(
    file: str | Path,
    templates_dir: Path | None = None,
    language: LanguageOption | None = None,
    agent_key: str | None = None,
) -> Path:
    """
    Resolve a template file path against templates_dir, language, and agent_key.

    - If templates_dir is not set or file is absolute: return file as-is.
    - If templates_dir is set and file is relative: search `{templates_dir}/{language}/{agent_key}/{file}`,
      then `{templates_dir}/{language}/{file}`, then `{templates_dir}/{file}`; return the first that exists.

    Args:
        file: The template file path (absolute or relative).
        templates_dir: Base directory for resolving relative paths (optional).
        language: Language subdirectory to search first, e.g. "de" or "en" (optional).
        agent_key: Agent subdirectory to search first, e.g. "test_case_set_reviewer" (optional).

    Returns:
        The resolved Path.

    Raises:
        FileNotFoundError: If the file is relative and cannot be found under templates_dir.
    """
    file_path = Path(file)
    language = language.value if language else None

    if file_path.is_absolute() or templates_dir is None:
        return file_path

    templates_dir = Path(templates_dir)

    search_paths: list[Path] = []
    if language and agent_key:
        search_paths.append(templates_dir / language / agent_key / file_path)
    if language:
        search_paths.append(templates_dir / language / file_path)
    search_paths.append(templates_dir / file_path)

    for path in search_paths:
        if path.is_file():
            return path.resolve()

    searched = "\n  - ".join(str(p) for p in search_paths)
    raise FileNotFoundError(f"Template file '{file_path}' not found.\nSearched:\n  - {searched}")


def render_template(path: Path, values: dict[str, Any]) -> str:
    """Render a Jinja template from the given path with the provided values."""
    env = Environment(loader=FileSystemLoader(path.parent))
    template = env.get_template(path.name)
    return template.render(values)
