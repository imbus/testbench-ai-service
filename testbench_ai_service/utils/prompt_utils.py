from pathlib import Path

import yaml
from jinja2 import (
    Environment,
    nodes,
)

from testbench_ai_service.log import logger
from testbench_ai_service.models.prompt import (
    Message,
    PromptDefinition,
    PromptVariant,
)


def load_prompt_file(prompt_path: str) -> dict:
    """Loads a prompt YAML file from the given path."""
    prompt_file = Path(prompt_path)
    if not prompt_file.is_file():
        logger.error(f"Prompt file not found: {prompt_path}")
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

    with prompt_file.open("r", encoding="utf-8") as f:
        try:
            prompt_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML file {prompt_path}: {e}")
            raise

    if not isinstance(prompt_data, dict):
        raise ValueError(f"Expected mapping at root of {prompt_path}, got {type(prompt_data)}")

    return prompt_data


def get_prompt_definition(prompt_path) -> PromptDefinition:
    """Retrieves the prompt definition from the prompt file."""
    prompt_data = load_prompt_file(prompt_path)
    return PromptDefinition.model_validate(prompt_data)


def get_prompt_variant(
    prompt_definition: PromptDefinition, variant_name: str | None
) -> PromptVariant:
    """Retrieves a specific prompt variant by name from the prompt definition."""
    target_variant = variant_name or prompt_definition.default_variant
    if not target_variant:
        logger.error(
            f"No variant specified and no default_variant found for prompt '{prompt_definition.name}'."
        )
        raise ValueError(
            f"No variant specified and no default_variant found for prompt '{prompt_definition.name}'."
        )

    for variant in prompt_definition.variants:
        if variant.name == target_variant:
            return variant

    logger.error(f"Variant '{target_variant}' not found in prompt '{prompt_definition.name}'.")
    raise ValueError(f"Variant '{target_variant}' not found in prompt '{prompt_definition.name}'.")


def pretty_messages(messages: list[Message]) -> str:
    pretty = []
    for msg in messages:
        pretty.append(f"\nRole: {msg.role}\nContent:\n{msg.content}\n")
    separator = "-" * 100
    return separator.join(pretty)


def _build_ast_path(node: nodes.Node) -> str | None:
    """Recursively builds dot-separated variable paths from Jinja AST nodes."""
    if isinstance(node, nodes.Name):
        if getattr(node, "ctx", None) == "load" and getattr(node, "name", None) == "agent":
            return node.name
    elif isinstance(node, nodes.Getattr):
        base_path = _build_ast_path(node.node)
        if base_path:
            return f"{base_path}.{node.attr}"
    return None


def template_variables(prompt_file: Path, prompt_variant: str) -> set[str]:
    prompt_definition = get_prompt_definition(prompt_file)
    prompt_variant = get_prompt_variant(prompt_definition, prompt_variant)
    base_path = Path(prompt_file).parent

    extracted_paths: set[str] = set()

    env = Environment()

    for msg_template in prompt_variant.messages:
        try:
            content = msg_template.get_content(base_path)
            ast = env.parse(content)

            for node in ast.find_all(nodes.Getattr):
                path = _build_ast_path(node)
                if path:
                    extracted_paths.add(path)

        except Exception as e:
            logger.warning("Failed to parse template variables: %s", e)

    return extracted_paths


def validate_template(
    template_variables: set[str] | None,
    agent_variables: dict[str, type] | None,
) -> bool:
    if not template_variables:
        return True

    allowed_variables = set()

    if agent_variables:
        allowed_variables.update(f"agent.{var}" for var in agent_variables)
    return template_variables.issubset(allowed_variables)
