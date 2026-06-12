from pathlib import Path
from typing import Any

from jinja2 import Environment, TemplateSyntaxError, UndefinedError

from testbench_ai_service.log import logger
from testbench_ai_service.models.agent import AgentData
from testbench_ai_service.models.config import PromptConfig
from testbench_ai_service.models.prompt import Message, MessageTemplate, Prompt
from testbench_ai_service.utils.prompt_utils import get_prompt_definition, get_prompt_variant


def build_messages(
    templates: list[MessageTemplate],
    agent_data: AgentData,
    prompt_vars: dict[str, Any],
    base_path: Path,
) -> list[Message]:
    """Renders message templates into a list of ``Message`` objects.

    Each template is rendered with Jinja2 using two namespaces:
    ``{{ agent.<key> }}`` for agent-generated data and ``{{ vars.<key> }}``
    for user-provided values. Each template produces exactly one ``Message``.

    Args:
        templates: Ordered list of ``MessageTemplate`` objects to render.
        agent_data: Agent-generated variable values (``agent.*`` namespace).
        prompt_vars: User-provided variable values (``vars.*`` namespace).
        base_path: Directory used to resolve relative ``file`` paths in templates.

    Returns:
        List of ``Message`` objects ready to be sent to an LLM.
    """
    env = Environment(trim_blocks=True, lstrip_blocks=True)
    messages: list[Message] = []

    for msg_template in templates:
        try:
            content = msg_template.get_content(base_path)
            text = env.from_string(content).render(agent=agent_data, vars=prompt_vars).strip()
        except UndefinedError as e:
            text = (msg_template.text or "").strip()
            logger.error(f"Missing variable in message template: {e}")
        except TemplateSyntaxError as e:
            text = (msg_template.text or "").strip()
            logger.error(f"Invalid Jinja2 syntax in message template: {e}")
        except FileNotFoundError as e:
            text = (msg_template.text or "").strip()
            logger.error(f"Template file not found: {e}")
        except Exception as e:
            text = (msg_template.text or "").strip()
            logger.warning(f"Unexpected error rendering message template: {e}")

        messages.append(Message(role=msg_template.role, content=text))

    return messages


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
    prompt_definition = get_prompt_definition(prompt_config.file)
    prompt_variant = get_prompt_variant(prompt_definition, prompt_config.variant)
    base_path = Path(prompt_config.file).parent

    messages = build_messages(
        templates=prompt_variant.messages,
        agent_data=agent_data or {},
        prompt_vars=prompt_config.vars or {},
        base_path=base_path,
    )

    return Prompt(model_name=get_prompt_model(prompt_config), messages=messages)


def get_prompt_model(prompt_config: PromptConfig) -> str:
    prompt_definition = get_prompt_definition(prompt_config.file)
    prompt_variant = get_prompt_variant(prompt_definition, prompt_config.variant)
    return prompt_variant.model or prompt_definition.default_model
