import unittest
from abc import ABC
from unittest.mock import MagicMock

from testbench_ai_service.agents.base import Agent


class _ConcreteAgent(Agent):
    """Minimal concrete implementation for testing."""

    async def precheck(self, context, conn):
        return MagicMock(passed=True, warnings=[])

    async def run(self, context, conn, llm_client):
        pass


class TestAgentABC(unittest.TestCase):
    """Tests for the ``Agent`` abstract base class."""

    def test_is_abstract(self):
        self.assertTrue(issubclass(Agent, ABC))

    def test_cannot_instantiate_directly(self):
        with self.assertRaises(TypeError):
            Agent()  # type: ignore[abstract]

    def test_partial_subclass_raises_type_error(self):
        class _Partial(Agent):
            async def precheck(self, context, conn):
                pass

            # Missing run()

        with self.assertRaises(TypeError):
            _Partial()

    def test_concrete_subclass_can_be_instantiated(self):
        uc = _ConcreteAgent()
        self.assertIsInstance(uc, Agent)


if __name__ == "__main__":
    unittest.main()
