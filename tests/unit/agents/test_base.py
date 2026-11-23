from abc import ABC
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from testbench_ai_service.agents.base import Agent
from testbench_ai_service.models.config import PromptConfig


class _ConcreteAgent(Agent):
    async def precheck(self, context, conn):
        return MagicMock(passed=True, warnings=[])

    async def run(self, context, conn, llm_client):
        pass


class TestAgentABC:
    def test_is_abstract(self):
        assert issubclass(Agent, ABC)

    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            Agent()  # type: ignore[abstract]

    def test_partial_subclass_raises_type_error(self):
        class _Partial(Agent):
            async def precheck(self, context, conn):
                pass

        with pytest.raises(TypeError):
            _Partial()

    def test_concrete_subclass_can_be_instantiated(self):
        uc = _ConcreteAgent()
        assert isinstance(uc, Agent)


class _Answer(BaseModel):
    value: str


async def test_a_structured_response_is_built_from_the_given_step(tmp_path):
    prompt = tmp_path / "prompt.yaml"
    prompt.write_text(
        'name: "x"\ndefault_model: "m"\ndefault_variant: "A"\nvariants:\n'
        '  - name: "A"\n    messages: []\n    steps:\n      one:\n'
        '        - role: "user"\n          text: "step {{ agent.x }}"\n',
        encoding="utf-8",
    )
    llm_client = SimpleNamespace(query_llm=AsyncMock(return_value='{"value": "ok"}'))

    result = await _ConcreteAgent().get_structured_ai_response(
        llm_client,
        SimpleNamespace(model="m", model_extra={}),
        PromptConfig(file=prompt),
        _Answer,
        {"x": "1"},
        step="one",
    )

    assert result.value == "ok"
    assert llm_client.query_llm.call_args.kwargs["messages"][0].content == "step 1"
