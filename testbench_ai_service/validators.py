import functools
import importlib
import json
from pathlib import Path
from typing import Any

import jsonschema
import requests
import yaml
from pydantic import ValidationError
from pydantic_core import InitErrorDetails


def resolve_prompt_file_path(
    file: Path,
    prompts_dir: Path | None = None,
    language: str | None = None,
) -> Path:
    """
    Resolve a prompt file path against prompts_dir and language.

    - If prompts_dir is not set or file is absolute: return file as-is.
    - If prompts_dir is set and file is relative: search prompts_dir/{language}/{file},
      then prompts_dir/{file}; return the first that exists.

    Args:
        file: The prompt file path (absolute or relative).
        prompts_dir: Base directory for resolving relative paths (optional).
        language: Language subdirectory to search first, e.g. "de" or "en" (optional).

    Returns:
        The resolved Path.

    Raises:
        ValueError: If the file is relative and cannot be found under prompts_dir.
    """
    language = language.strip() if language else None

    if not file.is_absolute() and prompts_dir is not None:
        lang_path = (prompts_dir / language / file).resolve() if language else None
        base_path = (prompts_dir / file).resolve()
        if lang_path and lang_path.is_file():
            return lang_path
        if base_path.is_file():
            return base_path
        searched = f"  - {lang_path}\n  - {base_path}" if lang_path else f"  - {base_path}"
        raise ValueError(f"Relative prompt file '{file}' not found.\n  Searched:\n{searched}")

    return file


def raise_field_validation_error(
    model_instance, field: str | tuple, error: ValueError, error_type: str = "value_error"
):
    """
    Raise a pydantic ValidationError for a specific field from a caught ValueError.

    Args:
        model_instance: Pydantic model instance (self in validators)
        field: Field name (str) or full loc tuple (e.g. ("usecases", "foo", "prompt", "file"))
        error: ValueError instance
        error_type: Optional error type string (default: "value_error")
    """
    loc = field if isinstance(field, tuple) else (field,)
    input_value = getattr(model_instance, loc[-1], None)
    raise ValidationError.from_exception_data(
        title=model_instance.__class__.__name__,
        line_errors=[
            InitErrorDetails(
                type=error_type,
                loc=loc,
                input=input_value,
                ctx={"error": error},
            )
        ],
    ) from error


def validate_custom_class_path(class_path: str) -> str:
    """
    Check that custom class_path is valid and importable.

    Returns:
        The class_path if valid.

    Raises:
        ValueError: If class_path is missing or cannot be imported.
    """
    if not class_path:
        raise ValueError("'class_path' must be set.")

    try:
        module_path, class_name = class_path.rsplit(".", 1)
    except ValueError as e:
        raise ValueError(
            "'class_path' must be a valid import path, e.g. 'package.module.ClassName'."
        ) from e

    try:
        module = importlib.import_module(module_path)
        getattr(module, class_name)
    except (ImportError, AttributeError) as e:
        raise ValueError(f"cannot import '{class_name}' from '{module_path}': {e}") from e

    return class_path


def validate_file(path: str | Path) -> Path:
    """
    Validate that the given path points to a non-empty, existing file.

    Ensures that:
    1. The input is converted to a Path object if necessary.
    2. The path exists on the filesystem.
    3. The path refers to a regular file (not a directory).
    4. The file contains non-whitespace content.

    Args:
        path: The file path to validate, as a string or Path object.

    Returns:
        The validated, resolved file path as a Path object.

    Raises:
        ValueError: If the file does not exist, is not a file, or is empty.
    """
    if not isinstance(path, Path):
        path = Path(path)
    path = path.resolve()
    if not path.exists():
        raise ValueError(f"File not found: '{path}'")
    if not path.is_file():
        raise ValueError(f"Path is not a file: '{path}'")
    if not path.read_text(encoding="utf-8").strip():
        raise ValueError(f"File is empty: '{path}'")
    return path


@functools.lru_cache(maxsize=1)
def _load_prompt_schema() -> dict:
    """Load and cache the prompt JSON schema from disk."""
    schema_path = Path(__file__).parent / "prompts" / "prompt.schema.json"
    with schema_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def validate_yaml_to_schema(path: Path) -> Path:
    """
    Validate a YAML file against the predefined prompt JSON schema.

    Loads the schema, parses the YAML file, and validates
    the content against the schema.

    Args:
        path: Path to the YAML file to validate.

    Returns:
        The validated YAML file path.

    Raises:
        ValueError: If the YAML file cannot be parsed or does not conform
            to the schema.
    """
    schema = _load_prompt_schema()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        jsonschema.validate(instance=data, schema=schema)
    except yaml.YAMLError as e:
        raise ValueError(f"YAML parsing error in '{path}': {e}") from e
    except jsonschema.ValidationError as e:
        raise ValueError(f"Schema validation error in '{path}': {e.message}") from e
    return path


def validate_value_in_yaml(path: Path, key: str, value: Any):
    """
    Validate that a given key-value pair exists in a YAML file.

    Expects the YAML file to contain a list of mappings and checks
    whether any mapping contains the specified key-value pair.

    Args:
        path: Path to the YAML file to inspect.
        key: The key to look for in each mapping.
        value: The expected value for the given key.

    Raises:
        ValueError: If the YAML content is not a list, or the key-value
            pair is not found in any mapping.
    """
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, list):
        raise ValueError(f"Expected a list of mappings in '{path}', got {type(data).__name__}.")

    for item in data:
        if isinstance(item, dict) and item.get(key) == value:
            return

    raise ValueError(f"No entry with '{key}: {value}' found in '{path}'.")


def validate_tb_server_url(tb_server_url: str):
    """Checks whether the Testbench server is accessible."""
    try:
        response = requests.get(
            f"{tb_server_url.rstrip('/')}/2/serverVersions",
            timeout=5,  # Timeout verhindert ewiges Warten
            verify=False,
        )
        response.raise_for_status()  # Löst HTTPError bei Statuscode 4xx/5xx aus
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Unable to connect to the server {tb_server_url}.") from e


def validate_prompt_file(
    file: Path,
    name: str | None = None,
    prompts_dir: Path | None = None,
    language: str | None = None,
) -> Path:
    """
    Resolve and validate a prompt file path.

    - If prompts_dir is not set: file is used as-is (absolute or relative to CWD).
    - If prompts_dir is set and file is absolute: validate as-is.
    - If prompts_dir is set and file is relative: search prompts_dir/{language}/{file},
      then prompts_dir/{file}; use the first that exists.

    Args:
        file: The prompt file path (absolute or relative).
        name: Expected prompt name to verify inside the YAML file (optional).
        prompts_dir: Base directory for resolving relative paths (optional).
        language: Language subdirectory to search first, e.g. "de" or "en" (optional).

    Returns:
        The resolved, validated absolute Path.

    Raises:
        ValueError: If the file cannot be found or fails validation.
    """
    file = resolve_prompt_file_path(file, prompts_dir=prompts_dir, language=language)
    validate_file(file)
    validate_yaml_to_schema(file)
    if name:
        validate_value_in_yaml(file, "name", name)
    return file
