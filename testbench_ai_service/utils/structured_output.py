"""Querying an LLM for JSON that is validated against a Pydantic model.

The model is told the schema by the prompt; this module only parses and validates
what comes back. A reply that does not parse is sent back once together with the
validation error (a repair retry); if the repaired reply fails too, the caller gets
a :class:`StructuredOutputError` and decides how to abort.
"""

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from testbench_ai_service.llm.base import LLMClient
from testbench_ai_service.log import logger
from testbench_ai_service.models.prompt import Message

T = TypeVar("T", bound=BaseModel)

#: A reply wrapped in a Markdown code fence, e.g. ```` ```json ... ``` ````.
CODE_FENCE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*\n(?P<body>.*?)\n?\s*```\s*$", re.DOTALL)

#: Sent back to the model after a reply that failed validation. The schema is
#: spelled out because the prompt may not name it, e.g. a custom or outdated one;
#: without it the model can only guess, and tends to answer with an empty object.
REPAIR_INSTRUCTION = (
    "Your previous answer could not be parsed:\n{error}\n\n"
    "Answer again with the same content as one JSON object matching this JSON Schema:\n"
    "{schema}\n\n"
    "No Markdown, no code fences, no text before or after the JSON."
)


class StructuredOutputError(ValueError):
    """The LLM's reply did not validate against the schema, even after the repair retry."""

    def __init__(self, message: str, raw_response: str):
        super().__init__(message)
        self.raw_response = raw_response


def strip_code_fence(text: str) -> str:
    """Return the body of a reply wrapped in a single Markdown code fence, else the reply."""
    match = CODE_FENCE.match(text)
    return match.group("body") if match else text.strip()


def parse_structured_output(raw: str, schema: type[T]) -> T:
    """Parse and validate an LLM reply as JSON of the given schema.

    Args:
        raw: The reply as returned by the LLM.
        schema: The Pydantic model the reply must validate against.

    Returns:
        The validated model.

    Raises:
        ValidationError: The reply is not valid JSON or does not match ``schema``.
    """
    return schema.model_validate_json(strip_code_fence(raw))


async def query_structured(
    llm_client: LLMClient,
    model: str,
    messages: list[Message],
    schema: type[T],
    **kwargs,
) -> T:
    """Query the LLM and validate its reply, repairing an invalid reply once.

    Args:
        llm_client: Initialised LLM client.
        model: The model to query.
        messages: The prompt; it must tell the model the expected JSON schema.
        schema: The Pydantic model the reply must validate against.
        **kwargs: Provider-specific arguments passed to every query.

    Returns:
        The validated model.

    Raises:
        StructuredOutputError: The reply failed validation twice.
    """
    raw = await llm_client.query_llm(model=model, messages=messages, **kwargs)
    try:
        return parse_structured_output(raw, schema)
    except ValidationError as error:
        logger.warning(
            "LLM reply did not match %s; asking once for a repair: %s", schema.__name__, error
        )
        repair_messages = [
            *messages,
            Message(role="assistant", content=raw),
            Message(
                role="user",
                content=REPAIR_INSTRUCTION.format(
                    error=error, schema=json.dumps(schema.model_json_schema())
                ),
            ),
        ]

    repaired = await llm_client.query_llm(model=model, messages=repair_messages, **kwargs)
    try:
        return parse_structured_output(repaired, schema)
    except ValidationError as error:
        raise StructuredOutputError(
            f"LLM reply did not match {schema.__name__} after a repair retry: {error}",
            raw_response=repaired,
        ) from error
