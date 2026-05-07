from pathlib import Path
from typing import Any

import yaml
from jinja2 import (
    Environment,
    TemplateSyntaxError,
    UndefinedError,
)

from testbench_ai_service.agents.base import AgentData
from testbench_ai_service.config import PromptConfig
from testbench_ai_service.log import logger
from testbench_ai_service.models.prompt import (
    Block,
    Message,
    Prompt,
    PromptDefinition,
    PromptVariant,
)


def load_prompt_file(prompt_path: str) -> list[dict]:
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

    if not isinstance(prompt_data, list):
        raise ValueError(f"Expected list at root of {prompt_path}, got {type(prompt_data)}")

    return prompt_data


def load_prompt_definitions(prompt_path: str) -> list[PromptDefinition]:
    """Loads prompt definitions from the given path."""
    prompt_data = load_prompt_file(prompt_path)
    return [PromptDefinition.model_validate(prompt) for prompt in prompt_data]


def get_prompt_definition(prompt_path, prompt_name) -> PromptDefinition:
    """Retrieves a specific prompt definition by name from the prompt file."""
    prompt_definitions = load_prompt_definitions(prompt_path)
    for prompt_def in prompt_definitions:
        if prompt_def.name == prompt_name:
            return prompt_def
    raise ValueError(f"Prompt '{prompt_name}' not found in prompt file.")


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


def get_rendered_blocks(
    blocks: list[Block],
    agent_data: AgentData,
    prompt_vars: dict[str, Any],
    base_path: Path,
) -> list[Block]:
    """Renders blocks using Jinja2 with two separate namespaces.

    Templates access agent-generated variables as ``{{ agent.<key> }}``
    and user-provided variables as ``{{ vars.<key> }}``.

    Args:
        blocks: List of Block objects to render.
        agent_data: Agent-generated variable values (``agent.*`` namespace).
        prompt_vars: User-provided variable values (``vars.*`` namespace).
        base_path: Directory used to resolve relative ``file`` paths in blocks.

    Returns:
        List of Block objects with rendered ``text`` content.
    """
    rendered_blocks = []
    env = Environment(trim_blocks=True, lstrip_blocks=True)

    for block in blocks:
        try:
            content = block.get_content(base_path)
            template = env.from_string(content)
            new_text = template.render(agent=agent_data, vars=prompt_vars)
        except UndefinedError as e:
            new_text = block.text or ""
            logger.error(f"Missing variable in block: {e}")
        except TemplateSyntaxError as e:
            new_text = block.text or ""
            logger.error(f"Invalid Jinja2 syntax in block: {e}")
        except FileNotFoundError as e:
            new_text = block.text or ""
            logger.error(f"Template file not found: {e}")
        except Exception as e:
            new_text = block.text or ""
            logger.warning(f"Unexpected error rendering block: {e}")

        rendered_blocks.append(block.model_copy(update={"text": new_text, "file": None}))

    return rendered_blocks


def build_messages(blocks: list[Block]) -> list[Message]:
    """Builds a list of Message objects from the given blocks."""
    combined_messages: list[Message] = []
    current_role = None
    buffer: list[str] = []

    def flush():
        if buffer:
            combined_messages.append(Message(role=current_role, content="\n\n".join(buffer)))

    for block in blocks:
        text = (block.text or "").strip()
        if block.role == current_role:
            buffer.append(text)
        else:
            flush()
            current_role = block.role
            buffer = [text]

    flush()
    return combined_messages


def build_prompt(prompt_config: PromptConfig, agent_data: AgentData | None = None) -> Prompt:
    """
    Builds and returns a Prompt object by loading, rendering, and preparing prompt data.

    Template variables are split into two Jinja2 namespaces:
    - ``{{ agent.<key> }}``: agent-generated values from ``agent_data``
    - ``{{ vars.<key> }}``: user-provided values from ``prompt_config.vars``

    Missing ``vars`` keys are filled from ``PromptVariableDefinition.default_value``
    declared in the variant before rendering.

    Args:
        prompt_config: Configuration containing file path, name, variant, and user vars.
        agent_data: Agent-generated variable values (``agent.*`` namespace).

    Returns:
        Prompt: A fully initialized Prompt object ready for use with an LLM.

    Raises:
        FileNotFoundError: If the prompt file or a referenced template file doesn't exist.
        ValueError: If prompt name or variant is not found.
    """
    prompt_definition = get_prompt_definition(prompt_config.file, prompt_config.name)
    prompt_variant = get_prompt_variant(prompt_definition, prompt_config.variant)
    base_path = Path(prompt_config.file).parent

    rendered_blocks = get_rendered_blocks(
        blocks=prompt_variant.blocks,
        agent_data=agent_data or {},
        prompt_vars=prompt_config.vars or {},
        base_path=base_path,
    )
    messages = build_messages(rendered_blocks)

    return Prompt(model_name=get_prompt_model(prompt_config), messages=messages)


def get_prompt_model(prompt_config: PromptConfig) -> str:
    prompt_definition = get_prompt_definition(prompt_config.file, prompt_config.name)
    prompt_variant = get_prompt_variant(prompt_definition, prompt_config.variant)
    return prompt_variant.model or prompt_definition.default_model


def pretty_messages(messages: list[Message]) -> str:
    pretty = []
    for msg in messages:
        indented_content = "\n".join(f"\t{line}" for line in msg.content.splitlines())
        pretty.append(f"Role: {msg.role}\nContent:\n{indented_content}\n")
    return "\n---\n".join(pretty)
