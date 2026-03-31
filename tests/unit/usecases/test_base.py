import unittest
from abc import ABC
from unittest.mock import MagicMock

from testbench_ai_service.usecases.base import UseCase


class _ConcreteUseCase(UseCase):
    """Minimal concrete implementation for testing."""

    async def precheck(self, context, conn):
        return MagicMock(passed=True, items=[], warnings=[])

    async def run(self, context, conn, llm_client, items):
        pass


class TestUseCaseABC(unittest.TestCase):
    """Tests for the ``UseCase`` abstract base class."""

    def test_is_abstract(self):
        self.assertTrue(issubclass(UseCase, ABC))

    def test_cannot_instantiate_directly(self):
        with self.assertRaises(TypeError):
            UseCase()  # type: ignore[abstract]

    def test_partial_subclass_raises_type_error(self):
        class _Partial(UseCase):
            async def precheck(self, context, conn):
                pass

            # Missing run()

        with self.assertRaises(TypeError):
            _Partial()

    def test_concrete_subclass_can_be_instantiated(self):
        uc = _ConcreteUseCase()
        self.assertIsInstance(uc, UseCase)


if __name__ == "__main__":
    unittest.main()
