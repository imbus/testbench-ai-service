from pathlib import Path

import yaml
from jinja2 import (
    Environment,
    TemplateSyntaxError,
    UndefinedError,
    meta,
)

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


def get_rendered_blocks(blocks: list[Block], placeholder_data: dict[str, str]) -> list[Block]:
    """Renders the given blocks with placeholder data using the Jinja2 template engine.

    Args:
        blocks: List of Block objects to render
        placeholder_data: Dictionary of placeholder key-value pairs

    Returns:
        List of Block objects with rendered text
    """

    rendered_blocks = []
    template_placeholders = set()

    env = Environment(trim_blocks=True, lstrip_blocks=True)

    for block in blocks:
        try:
            # Parse template to find variables
            ast = env.parse(block.text)
            block_vars = meta.find_undeclared_variables(ast)
            template_placeholders.update(block_vars)

            # Render template
            template = env.from_string(block.text)
            new_text = template.render(**placeholder_data)

        except UndefinedError as e:
            new_text = block.text
            logger.error(f"Missing placeholder in block: {e}")
        except TemplateSyntaxError as e:
            new_text = block.text
            logger.error(f"Invalid Jinja2 syntax in block: {e}")
        except Exception as e:
            new_text = block.text
            logger.warning(f"Unexpected error rendering block: {e}")

        rendered_blocks.append(block.model_copy(update={"text": new_text}))

    # Check for unused placeholders
    extra = set(placeholder_data.keys()) - template_placeholders
    if extra:
        logger.debug(f"Provided placeholder(s) not found in template: {extra}")

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
        text = block.text.strip()
        if block.role == current_role:
            buffer.append(text)
        else:
            flush()
            current_role = block.role
            buffer = [text]

    flush()
    return combined_messages


def build_prompt(prompt_config: PromptConfig) -> Prompt:
    """
    Builds and returns a Prompt object by loading, rendering, and preparing prompt data.

    This function handles the entire prompt preparation workflow:
    1. Loads the prompt definition from the specified file
    2. Retrieves the appropriate variant
    3. Renders blocks with placeholder data
    4. Builds messages from rendered blocks

    Args:
        prompt_config: Configuration containing file path, name, variant, and placeholder data for the prompt.

    Returns:
        Prompt: A fully initialized Prompt object ready for use with an LLM.

    Raises:
        FileNotFoundError: If the prompt file doesn't exist.
        ValueError: If prompt name or variant is not found.
    """
    prompt_definition = get_prompt_definition(prompt_config.file, prompt_config.name)
    prompt_variant = get_prompt_variant(prompt_definition, prompt_config.variant)

    placeholder_data = prompt_config.placeholder_data or {}
    rendered_blocks = get_rendered_blocks(prompt_variant.blocks, placeholder_data)
    messages = build_messages(rendered_blocks)

    return Prompt(model_name=get_prompt_model(prompt_config), messages=messages)

def get_prompt_model(prompt_config: PromptConfig) -> str:
    prompt_definition = get_prompt_definition(prompt_config.file, prompt_config.name)
    prompt_variant = get_prompt_variant(prompt_definition, prompt_config.variant)

    prompt_model = None
    prompt_data = load_prompt_file(prompt_config.file)
    for prompt_block in prompt_data:
        if prompt_block.get("name", "") == prompt_config.name:
            prompt_model = prompt_block.get("default_model", None)

    if prompt_variant.model:
        prompt_model = prompt_variant.model
    
    return prompt_model



def pretty_messages(messages: list[Message]) -> str:
    pretty = []
    for msg in messages:
        # Add a tab before each line in content
        indented_content = "\n".join(f"\t{line}" for line in msg.content.splitlines())
        pretty.append(f"Role: {msg.role}\nContent:\n{indented_content}\n")
    return "\n---\n".join(pretty)


def get_placeholders_from_blocks(blocks: list[Block]) -> list[str]:
    """
    Extract all placeholder variable names from the given blocks.

    Returns a sorted list of unique placeholder names.
    """
    placeholders: set[str] = set()
    env = Environment()
    for block in blocks:
        try:
            ast = env.parse(block.text)
            placeholders.update(meta.find_undeclared_variables(ast))
        except TemplateSyntaxError:
            pass
    return sorted(placeholders)
