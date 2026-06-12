import json
import shutil
import sys
from pathlib import Path

import tomli_w

from testbench_ai_service.validators import resolve_prompt_file_path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from pydantic import BaseModel, ValidationError

from testbench_ai_service.config import PROMPTS_DIR, TEMPLATES_DIR, AppConfig
from testbench_ai_service.log import logger
from testbench_ai_service.models.config import (
    AgentConfig,
    LLMConfig,
    ProjectPromptConfig,
    PromptConfig,
)
from testbench_ai_service.models.language import LanguageOption

CONFIG_PREFIX = "testbench-ai-service"


def _ignore_non_prompt_files(prompts_dir: str, contents: list[str]) -> set[str]:
    return {
        item
        for item in contents
        if not Path(prompts_dir, item).is_dir()
        and not any(
            item.endswith(ext)
            for ext in (".yaml", ".jinja", "jinja2", ".j2", ".md", ".txt", ".json")
        )
    }


def copy_default_prompts(target_dir: Path, force: bool = False) -> None:
    """
    Copy the built-in prompt YAML files from the package to a local directory.

    Args:
        target_dir: Destination directory for the copied prompts.
        force: Remove and recreate the directory if it already exists.
    """
    if target_dir.exists():
        if not force:
            print(
                f"Prompts directory already exists at '{target_dir.resolve()}'. "
                "Use --force to overwrite."
            )
            sys.exit(1)
        shutil.rmtree(target_dir)

    shutil.copytree(PROMPTS_DIR, target_dir, ignore=_ignore_non_prompt_files)
    print(f"Default prompts copied to '{target_dir.resolve()}'.")


def copy_default_templates(target_dir: Path, force: bool = False) -> None:
    """
    Copy the built-in jinja templates from the package to a local directory.

    Args:
        target_dir: Destination directory for the copied templates.
        force: Remove and recreate the directory if it already exists.
    """
    if target_dir.exists():
        if not force:
            print(
                f"Prompts directory already exists at '{target_dir.resolve()}'. "
                "Use --force to overwrite."
            )
            sys.exit(1)
        shutil.rmtree(target_dir)

    shutil.copytree(TEMPLATES_DIR, target_dir, ignore=_ignore_non_prompt_files)
    print(f"Default prompts copied to '{target_dir.resolve()}'.")


def create_default_config_file(
    output_path: str,
    force: bool = False,
    prompts_dir: str | None = None,
    templates_dir: str | None = None,
):
    """
    Write the default config to a TOML configuration file.

    When *prompts_dir* is given the built-in prompt files are copied there and
    all agent prompt paths in the generated config are made relative so that
    the config is portable and the prompts are easy to customise.

    Args:
        output_path: Path where the configuration file will be saved.
        force: Overwrite existing file if True.
        prompts_dir: If provided, copy default prompts to this directory and
            configure the service to load prompts from there.
        templates_dir: If provided, copy default templates to this directory and
            configure the service to load templates from there.
    """
    default_config_json = AppConfig().model_dump_json(exclude_none=True)
    default_config = json.loads(default_config_json)

    if prompts_dir is not None:
        target = Path(prompts_dir).resolve()
        copy_default_prompts(target, force=force)
        default_config["prompts_dir"] = str(target)

    if templates_dir is not None:
        target = Path(templates_dir).resolve()
        copy_default_templates(target, force=force)
        default_config["templates_dir"] = str(target)

    create_config_file(config=default_config, output_path=output_path, force=force)


def create_config_file(
    config: AppConfig | dict,
    output_path: str,
    config_prefix: str = CONFIG_PREFIX,
    force: bool = False,
):
    """
    Write the given config object to a TOML configuration file.

    Args:
        config: AppConfig instance or dict representing configuration.
        output_path: Path where the configuration file will be saved.
        config_prefix: String prefix to nest config under (default: 'testbench-ai-service').
        force: Overwrite existing file if True.
    """
    path = Path(output_path)
    if path.exists() and not force:
        print(
            f"Configuration file already exists at '{path.resolve()}'. "
            "Use --force to overwrite existing file."
        )
        sys.exit(1)

    config_data = config.model_dump() if isinstance(config, AppConfig) else config
    to_serialize = {config_prefix: config_data}
    toml_str = tomli_w.dumps(to_serialize)
    path.write_text(toml_str, encoding="utf-8")

    print(f"Configuration file created at '{path.resolve()}'.")


def print_config_errors(
    e: ValidationError,
    config_path: Path | None = None,
    config_prefix: str | None = CONFIG_PREFIX,
):
    """
    Print user-friendly config validation errors from a pydantic ValidationError.

    This function processes all validation errors in a pydantic ValidationError instance,
    formatting each error message to show only the field name and its context
    (TOML section or file).

    Args:
        e: Pydantic ValidationError with error details
        config_path: Optional path to the configuration file, used for error messages
        config_prefix: Optional TOML section name (e.g., "testbench-ai-service")
    """
    for error in e.errors():
        locs = [str(loc) for loc in error["loc"]]
        if locs:
            field_name = locs[-1]
            section_parts = [config_prefix, *locs[:-1]] if config_prefix else locs[:-1]
            section = ".".join(section_parts) if section_parts else config_prefix
            error_type = error.get("type", "")
            if error_type == "missing":
                msg = f"Missing required field '{field_name}' in TOML section [{section}]"
            else:
                msg = f"Invalid field '{field_name}' in TOML section [{section}]"
        else:
            section = config_prefix
            msg = f"Invalid configuration in TOML section [{section}]"

        if config_path is not None:
            msg += f" in file '{config_path.resolve()}'"

        print(f"Configuration Error: {msg}")
        detail = error.get("msg")
        if detail:
            print(f"  Detail: {detail}")
        print()


def merge_dicts(default: dict, override: dict) -> dict:
    """
    Return a new dictionary by merging `override` into `default`,
    with `override` values taking precedence on key conflicts.
    """
    merged = default.copy()
    merged.update(override or {})
    return merged


def merge_model_dicts(
    default: dict[str, BaseModel], override: dict[str, dict]
) -> dict[str, BaseModel]:
    """
    Merge a dictionary of Pydantic models with a dictionary of partial updates.

    For each key, combine the existing model from `default` with the values
    in `override`, updating only the specified fields. New keys are added as
    new model instances.

    Args:
        default: The dictionary of default Pydantic models.
        override: A dictionary where each value is a partial dict for update.

    Returns:
        A merged dictionary of Pydantic models.
    """
    merged = default.copy()
    for key, value in override.items():
        if key in merged:
            merged[key] = merged[key].model_copy(update=value)
        else:
            model_cls = type(next(iter(default.values()))) if default else BaseModel
            try:
                merged[key] = model_cls(**value)
            except ValidationError as e:
                errors = []
                for error in e.errors():
                    error["loc"] = (key, *error["loc"])
                    errors.append(error)
                raise ValidationError.from_exception_data(title=e.title, line_errors=errors) from e  # type: ignore[arg-type]
    return merged


def load_config_from_file(config_path: str, config_prefix: str = CONFIG_PREFIX) -> AppConfig:
    """
    This function reads a TOML configuration file, extracts the section specified by `config_prefix`,
    and validates it against the `AppConfig` model. If the file does not exist, a FileNotFoundError
    is raised. If validation fails, user-friendly error messages are printed and the program exits.

    Args:
        config_path (str): Path to the TOML configuration file.
        config_prefix (str): The top-level section in the TOML file containing the app config (default: 'testbench-ai-service').

    Returns:
        AppConfig: An instance of the validated application configuration.
    """
    config_file_path = Path(config_path)
    if not config_file_path.exists():
        # try reading configuration from pyproject.toml if it exists
        try:
            project_toml = Path(__file__).parent.parent / "pyproject.toml"
            with project_toml.open("rb") as config_file:
                config_dict = tomllib.load(config_file)

            config_dict = {config_prefix: config_dict["tool"][config_prefix]}

        except (FileNotFoundError, tomllib.TOMLDecodeError, KeyError):
            print(
                f"Configuration Error: Configuration file not found at: '{config_file_path.resolve()}'.\n\n"
                "If you don't have one yet, create it with:\n"
                "    testbench-ai-service init\n\n"
                "This will place a default config.toml in the current directory for you to edit."
            )
            sys.exit(1)
            return None  # type: ignore[unreachable]
    else:
        try:
            with config_file_path.open("rb") as config_file:
                config_dict = tomllib.load(config_file)
        except tomllib.TOMLDecodeError as e:
            print(
                f"Configuration Error: The configuration file contains invalid TOML syntax.\nDetails: {e}"
            )
            sys.exit(1)
            return None  # type: ignore[unreachable]

        if config_prefix not in config_dict:
            print(
                f"Configuration Error: TOML section [{config_prefix}] not found in the configuration file."
            )
            sys.exit(1)
            return None  # type: ignore[unreachable]

    try:
        return AppConfig(**config_dict[config_prefix])
    except ValidationError as e:
        print_config_errors(e, config_file_path, config_prefix)
        sys.exit(1)


def merge_prompt_configs(
    default: PromptConfig, override: PromptConfig | ProjectPromptConfig
) -> PromptConfig:
    """
    Return a new PromptConfig by merging `override` into `default`.

    All fields from `override` overwrite those in `default`.
    """
    update_data = override.model_dump(exclude_unset=True)
    return default.model_copy(update=update_data)


def get_prompt_config(
    agent_key: str,
    config: AppConfig,
    project_name: str | None = None,
    request_config: PromptConfig | None = None,
    language: LanguageOption | None = None,
) -> PromptConfig:
    """
    Get the prompt configuration for the given agent.

    Resolving config overrides in the following order:
    1. Request config (highest priority)
    2. Project-specific config
    3. Global config (lowest priority)

    Args:
        agent_key: Registry key of the agent (e.g., "test_case_set_reviewer")
        config: AppConfig containing global and project configurations
        project_name: Optional project name
        request_config: Optional prompt config from request

    Returns:
        PromptConfig: Prompt configuration with overrides applied
    """
    # Start with global config
    global_agent_config = get_agent_config(agent_key, config)
    global_prompt_config = global_agent_config.prompt

    prompt_config = global_prompt_config.model_copy(deep=True)

    # Override with project-specific config if available
    if project_name is not None:
        project_config = config.projects.get(project_name)
        project_agent_config = None
        if project_config and project_config.agents:
            project_agent_config = project_config.agents.get(agent_key)

        if project_agent_config and project_agent_config.prompt:
            project_prompt_config = project_agent_config.prompt
            prompt_config = merge_prompt_configs(prompt_config, project_prompt_config)

    # Override with request config if provided
    if request_config is not None:
        prompt_config = merge_prompt_configs(prompt_config, request_config)

    # Resolve the prompt file path using prompts_dir and language from config
    language = language or get_language_from_config(config, project_name)
    prompt_config.file = resolve_prompt_file_path(prompt_config.file, config.prompts_dir, language)
    logger.debug(f"Resolved prompt file path: {prompt_config.file}")

    return prompt_config


def get_llm_config(
    config: AppConfig, project_name: str | None = None, request_config: LLMConfig | None = None
) -> LLMConfig:
    """
    Get the LLM configuration based on the given app configuration, optional project name
    and optional request_config.

    Resolving config overrides in the following order:
    1. Request config (highest priority)
    2. Project-specific config
    3. Global config (lowest priority)

    Args:
        config: AppConfig containing global and project configurations
        project_name: Optional project name
        request_config: Optional LLM config from request

    Returns:
        LLMConfig: LLM configuration with overrides applied
    """
    # Start with global config
    llm_config = config.llm_config.model_copy(deep=True)

    # Override with project-specific config if available
    if project_name is not None:
        project_config = config.projects.get(project_name)
        if project_config is not None and project_config.llm_config is not None:
            llm_config = llm_config.model_copy(
                update=project_config.llm_config.model_dump(exclude_unset=True)
            )

    # Override with request config if provided
    if request_config:
        llm_config = llm_config.model_copy(update=request_config.model_dump(exclude_unset=True))

    return llm_config


def get_language_from_config(config: AppConfig, project_name: str | None = None) -> LanguageOption:
    """
    Get the language setting from app configuration.

    Args:
        config: AppConfig containing global and project configurations.
        project_name: Optional project name. If provided, checks for a project-specific language override.

    Returns:
        LanguageOption: Project-specific language override if exists, else app-level default language.
    """
    if project_name is not None:
        project_config = config.projects.get(project_name)
        if project_config is not None and project_config.language is not None:
            return project_config.language

    return config.language


def get_agent_config(
    agent_key: str, config: AppConfig, project_name: str | None = None
) -> AgentConfig:
    """
    Get the agent configuration based on the given app configuration and optional project name.

    Args:
        agent_key: Registry key of the agent.
        config: AppConfig containing global and project configurations.
        project_name: Optional project name. If provided, checks for a project-specific override.

    Returns:
        AgentConfig: Project-specific override if exists, else app-level agent config
    """
    # Start with global config
    agent_config = config.agents[agent_key].model_copy(deep=True)

    # Override with project-specific config if available
    if project_name is not None:
        project_config = config.projects.get(project_name)
        if project_config is not None and project_config.agents is not None:
            project_agent_config = project_config.agents.get(agent_key, None)
            if project_agent_config is not None:
                agent_config = agent_config.model_copy(
                    update=project_agent_config.model_dump(exclude_unset=True)
                )

    return agent_config


def agent_enabled(agent_key: str, config: AppConfig, project_name: str | None = None) -> bool:
    """
    Checks if a specific agent is enabled based on the given global or project-specific configuration.
    """
    agent_config = get_agent_config(agent_key, config, project_name)
    return agent_config.enabled
