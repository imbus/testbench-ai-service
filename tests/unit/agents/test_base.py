from abc import ABC
from unittest.mock import MagicMock

import pytest

from testbench_ai_service.agents.base import Agent


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
