import pytest

from testbench_ai_service.llm.base import LLMProvider
from testbench_ai_service.utils.import_utils import load_class_from_path


class TestLoadClassFromPath:
    """Tests for ``load_class_from_path``."""

    def test_loads_known_class(self):
        """Loading a class that exists in a valid module returns the class object."""
        cls = load_class_from_path("testbench_ai_service.llm.base.LLMProvider")
        assert cls is LLMProvider

    def test_unknown_class_name_raises_import_error(self):
        with pytest.raises(ImportError):
            load_class_from_path("testbench_ai_service.llm.base.DoesNotExist")

    def test_unknown_module_raises_module_not_found(self):
        with pytest.raises(ModuleNotFoundError):
            load_class_from_path("testbench_ai_service.nonexistent_module.SomeClass")

    def test_path_without_dot_raises_value_error(self):
        """A path with no module separator cannot be split into module + class."""
        with pytest.raises(ValueError, match="not enough values to unpack"):
            load_class_from_path("NoDotInPath")
