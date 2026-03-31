import unittest

from testbench_ai_service.llm.base import LLMProvider
from testbench_ai_service.utils.import_utils import load_class_from_path


class TestLoadClassFromPath(unittest.TestCase):
    """Tests for ``load_class_from_path``."""

    def test_loads_known_class(self):
        """Loading a class that exists in a valid module returns the class object."""
        cls = load_class_from_path("testbench_ai_service.llm.base.LLMProvider")
        self.assertIs(cls, LLMProvider)

    def test_unknown_class_name_raises_import_error(self):
        with self.assertRaises(ImportError):
            load_class_from_path("testbench_ai_service.llm.base.DoesNotExist")

    def test_unknown_module_raises_module_not_found(self):
        with self.assertRaises(ModuleNotFoundError):
            load_class_from_path("testbench_ai_service.nonexistent_module.SomeClass")


if __name__ == "__main__":
    unittest.main()
