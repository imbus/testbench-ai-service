"""Tests for querying the LLM for JSON validated against a Pydantic model."""

import json

import pytest
from pydantic import BaseModel, ValidationError

from testbench_ai_service.models.prompt import Message
from testbench_ai_service.utils.structured_output import (
    StructuredOutputError,
    parse_structured_output,
    query_structured,
)


class _Answer(BaseModel):
    value: int


class _FakeLLM:
    """Returns the queued replies in turn and records the messages of each query."""

    def __init__(self, *replies: str):
        self.replies = list(replies)
        self.queries: list[list[Message]] = []

    async def query_llm(self, model: str, messages: list[Message], **_kwargs) -> str:
        self.queries.append(messages)
        return self.replies.pop(0)


PROMPT = [Message(role="system", content="Answer as JSON."), Message(content="Go.")]


class TestParseStructuredOutput:
    def test_parses_plain_json(self):
        assert parse_structured_output('{"value": 1}', _Answer) == _Answer(value=1)

    def test_parses_json_in_a_code_fence(self):
        assert parse_structured_output('```json\n{"value": 2}\n```', _Answer).value == 2

    def test_rejects_json_of_another_shape(self):
        with pytest.raises(ValidationError):
            parse_structured_output('{"other": 1}', _Answer)


class TestQueryStructured:
    async def test_returns_a_valid_reply_without_a_retry(self):
        llm = _FakeLLM('{"value": 1}')

        assert await query_structured(llm, "m", PROMPT, _Answer) == _Answer(value=1)
        assert len(llm.queries) == 1

    async def test_sends_an_invalid_reply_back_with_the_error_once(self):
        llm = _FakeLLM("not json", '{"value": 3}')

        assert (await query_structured(llm, "m", PROMPT, _Answer)).value == 3

        repair = llm.queries[1]
        assert repair[: len(PROMPT)] == PROMPT
        assert repair[-2] == Message(role="assistant", content="not json")
        assert repair[-1].role == "user"
        assert "Invalid JSON" in repair[-1].content

    async def test_the_repair_request_spells_out_the_schema(self):
        llm = _FakeLLM("not json", '{"value": 3}')

        await query_structured(llm, "m", PROMPT, _Answer)

        assert json.dumps(_Answer.model_json_schema()) in llm.queries[1][-1].content

    async def test_gives_up_after_the_repair_retry_fails(self):
        llm = _FakeLLM("not json", '{"value": "x"}')

        with pytest.raises(StructuredOutputError) as error:
            await query_structured(llm, "m", PROMPT, _Answer)

        assert error.value.raw_response == '{"value": "x"}'
        assert len(llm.queries) == 2
