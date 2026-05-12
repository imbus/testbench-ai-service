"""
- load_config_from_file: TOML loading, missing/invalid files, missing section
- get_llm_config: global, project, request overrides in correct priority order
- get_prompt_config: same layered override logic for prompt configs
- get_language_from_config: global and per-project language resolution
- get_agent_config: global and per-project agent config merging
- merge_dicts: shallow dict merge with override precedence
- merge_model_dicts: pydantic model dict merging, new-key creation, validation
- merge_prompt_configs: prompt config model merging
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from pydantic import BaseModel, ValidationError

from testbench_ai_service.config import AppConfig
from testbench_ai_service.utils.config import (
    CONFIG_PREFIX,
    get_agent_config,
    get_language_from_config,
    get_llm_config,
    get_prompt_config,
    load_config_from_file,
    merge_dicts,
    merge_model_dicts,
    merge_prompt_configs,
)


class _SimpleModel(BaseModel):
    id: int
    name: str


class _UserModel(BaseModel):
    name: str
    age: int


def _write_toml(tmpdir: str, section: str, content: dict) -> Path:
    """Write a minimal TOML file with the given section header."""
    path = Path(tmpdir) / "config.toml"
    toml_str = f"[{section}]\n"
    toml_str += "\n".join(
        f"{k} = '{v}'" if isinstance(v, str) else f"{k} = {v}" for k, v in content.items()
    )
    path.write_text(toml_str)
    return path


class TestLoadConfigFromFile(unittest.TestCase):
    """load_config_from_file reads a TOML file and creates an AppConfig."""

    @patch("testbench_ai_service.utils.config.create_app_config")
    def test_valid_file_produces_app_config(self, mock_create):
        mock_create.return_value = MagicMock(spec=AppConfig)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_toml(tmpdir, CONFIG_PREFIX, {"some_setting": "value"})
            result = load_config_from_file(path)

        mock_create.assert_called_once_with({"some_setting": "value"})
        self.assertIsInstance(result, MagicMock)

    @patch("testbench_ai_service.utils.config.sys.exit")
    def test_missing_file_exits_with_code_1(self, mock_exit):
        with tempfile.TemporaryDirectory() as tmpdir:
            missing = Path(tmpdir) / "nonexistent.toml"
            with patch("pathlib.Path.open", side_effect=FileNotFoundError):
                load_config_from_file(missing)
        mock_exit.assert_called_once_with(1)

    @patch("testbench_ai_service.utils.config.sys.exit")
    def test_invalid_toml_syntax_exits_with_code_1(self, mock_exit):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.toml"
            path.write_text("[testbench-ai-service\ninvalid = ]")
            load_config_from_file(path)
        mock_exit.assert_called_once_with(1)

    @patch("testbench_ai_service.utils.config.sys.exit")
    def test_missing_config_section_exits_with_code_1(self, mock_exit):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.toml"
            path.write_text("[other_section]\nsome_setting = 'value'")
            load_config_from_file(path)
        mock_exit.assert_called_once_with(1)


class TestGetLLMConfig(unittest.TestCase):
    """get_llm_config merges global LLM config with optional project/request overrides."""

    def setUp(self):
        self.llm_config = MagicMock()
        self.llm_config.model_copy.return_value = self.llm_config
        self.llm_config.model_dump.return_value = {"key": "global_value"}

        self.config = MagicMock()
        self.config.llm_config = self.llm_config
        self.config.projects = {}

    def test_global_config_only(self):
        result = get_llm_config(self.config)
        self.llm_config.model_copy.assert_called_with(deep=True)
        self.assertEqual(result, self.llm_config)

    def test_project_override_is_applied(self):
        project_llm_config = MagicMock()
        project_llm_config.model_dump.return_value = {"key": "project_value"}
        self.config.projects["proj1"] = MagicMock(llm_config=project_llm_config)

        result = get_llm_config(self.config, project_name="proj1")

        self.llm_config.model_copy.assert_has_calls(
            [call(deep=True), call(update={"key": "project_value"})]
        )
        self.assertEqual(result, self.llm_config)

    def test_request_override_only(self):
        request_config = MagicMock()
        request_config.model_dump.return_value = {"key": "request_value"}

        result = get_llm_config(self.config, request_config=request_config)

        self.llm_config.model_copy.assert_has_calls(
            [call(deep=True), call(update={"key": "request_value"})]
        )
        self.assertEqual(result, self.llm_config)

    def test_request_override_takes_precedence_over_project(self):
        project_llm_config = MagicMock()
        project_llm_config.model_dump.return_value = {"key": "project_value"}
        self.config.projects["proj1"] = MagicMock(llm_config=project_llm_config)

        request_config = MagicMock()
        request_config.model_dump.return_value = {"key": "request_value"}

        get_llm_config(self.config, "proj1", request_config=request_config)

        self.llm_config.model_copy.assert_has_calls(
            [
                call(deep=True),
                call(update={"key": "project_value"}),
                call(update={"key": "request_value"}),
            ]
        )

    def test_unknown_project_falls_back_to_global(self):
        result = get_llm_config(self.config, "unknown_project")
        self.assertEqual(result, self.llm_config)


class TestGetPromptConfig(unittest.TestCase):
    """get_prompt_config returns a deep-copied and optionally merged PromptConfig."""

    def setUp(self):
        self.prompt_config = MagicMock()
        self.prompt_config.model_copy.return_value = self.prompt_config

        self.agent_config = MagicMock()
        self.agent_config.prompt = self.prompt_config

        self.config = MagicMock()
        self.config.projects = {}

    @patch("testbench_ai_service.utils.config.get_agent_config")
    @patch("testbench_ai_service.utils.config.merge_prompt_configs")
    def test_global_only_returns_deep_copy(self, mock_merge, mock_get_uc):
        mock_get_uc.return_value = self.agent_config

        result = get_prompt_config("uc1", self.config)

        self.prompt_config.model_copy.assert_called_with(deep=True)
        mock_merge.assert_not_called()
        self.assertEqual(result, self.prompt_config)

    @patch("testbench_ai_service.utils.config.get_agent_config")
    @patch("testbench_ai_service.utils.config.merge_prompt_configs")
    def test_project_override_is_merged(self, mock_merge, mock_get_uc):
        mock_get_uc.return_value = self.agent_config
        project_prompt_config = MagicMock()
        self.config.projects["proj1"] = MagicMock(
            agents={"uc1": MagicMock(prompt=project_prompt_config)}
        )
        merged = MagicMock()
        mock_merge.return_value = merged

        result = get_prompt_config("uc1", self.config, project_name="proj1")

        mock_merge.assert_called_once_with(self.prompt_config, project_prompt_config)
        self.assertIs(result, merged)

    @patch("testbench_ai_service.utils.config.get_agent_config")
    @patch("testbench_ai_service.utils.config.merge_prompt_configs")
    def test_request_override_is_merged(self, mock_merge, mock_get_uc):
        mock_get_uc.return_value = self.agent_config
        request_prompt_config = MagicMock()
        merged = MagicMock()
        mock_merge.return_value = merged

        result = get_prompt_config("uc1", self.config, request_config=request_prompt_config)

        mock_merge.assert_called_once_with(self.prompt_config, request_prompt_config)
        self.assertIs(result, merged)

    @patch("testbench_ai_service.utils.config.get_agent_config")
    @patch("testbench_ai_service.utils.config.merge_prompt_configs")
    def test_request_override_applied_after_project(self, mock_merge, mock_get_uc):
        mock_get_uc.return_value = self.agent_config
        project_prompt_config = MagicMock()
        request_prompt_config = MagicMock()
        self.config.projects["proj1"] = MagicMock(
            agents={"uc1": MagicMock(prompt=project_prompt_config)}
        )
        after_project = MagicMock()
        after_request = MagicMock()
        mock_merge.side_effect = [after_project, after_request]

        result = get_prompt_config("uc1", self.config, "proj1", request_prompt_config)

        mock_merge.assert_has_calls(
            [
                call(self.prompt_config, project_prompt_config),
                call(after_project, request_prompt_config),
            ]
        )
        self.assertIs(result, after_request)

    @patch("testbench_ai_service.utils.config.get_agent_config")
    @patch("testbench_ai_service.utils.config.merge_prompt_configs")
    def test_project_without_prompt_skips_merge(self, mock_merge, mock_get_uc):
        mock_get_uc.return_value = self.agent_config
        self.config.projects["proj1"] = MagicMock(agents={"uc1": MagicMock(prompt=None)})

        result = get_prompt_config("uc1", self.config, project_name="proj1")

        mock_merge.assert_not_called()
        self.assertEqual(result, self.prompt_config)


class TestGetLanguageFromConfig(unittest.TestCase):
    """get_language_from_config resolves the language at global or project level."""

    def setUp(self):
        self.config = MagicMock()
        self.config.language = "en"
        self.config.projects = {}

    def test_global_language_returned_without_project(self):
        self.assertEqual(get_language_from_config(self.config), "en")

    def test_project_language_overrides_global(self):
        self.config.projects["proj1"] = MagicMock(language="de")
        self.assertEqual(get_language_from_config(self.config, "proj1"), "de")

    def test_project_without_language_falls_back_to_global(self):
        self.config.projects["proj1"] = MagicMock(language=None)
        self.assertEqual(get_language_from_config(self.config, "proj1"), "en")

    def test_unknown_project_falls_back_to_global(self):
        self.assertEqual(get_language_from_config(self.config, "unknown"), "en")


class TestGetAgentConfig(unittest.TestCase):
    """get_agent_config merges global and per-project agent configurations."""

    def setUp(self):
        self.agent_config = MagicMock()
        self.agent_config.model_copy.return_value = self.agent_config
        self.agent_config.model_dump.return_value = {"key": "value"}

        self.config = MagicMock()
        self.config.agents = {"uc1": self.agent_config}
        self.config.projects = {}

    def test_global_only_returns_deep_copy(self):
        result = get_agent_config("uc1", self.config)
        self.agent_config.model_copy.assert_called_with(deep=True)
        self.assertEqual(result, self.agent_config)

    def test_project_without_override_returns_global(self):
        self.config.projects["proj1"] = MagicMock(agents=None)
        result = get_agent_config("uc1", self.config, "proj1")
        self.assertEqual(result, self.agent_config)

    def test_project_partial_override_is_applied(self):
        project_override = MagicMock()
        project_override.model_dump.return_value = {"override_key": "override_value"}
        self.config.projects["proj1"] = MagicMock(agents={"uc1": project_override})

        result = get_agent_config("uc1", self.config, "proj1")

        self.agent_config.model_copy.assert_has_calls(
            [call(deep=True), call(update={"override_key": "override_value"})]
        )
        self.assertEqual(result, self.agent_config)

    def test_unknown_project_returns_global(self):
        result = get_agent_config("uc1", self.config, "unknown_project")
        self.assertEqual(result, self.agent_config)


class TestMergeDicts(unittest.TestCase):
    """merge_dicts creates a new dict with override values taking precedence."""

    def test_override_value_wins_on_key_conflict(self):
        result = merge_dicts(default={"a": 1, "b": 2}, override={"b": 3, "c": 4})
        self.assertDictEqual(result, {"a": 1, "b": 3, "c": 4})

    def test_empty_override_returns_copy_of_default(self):
        result = merge_dicts(default={"a": 1, "b": 2}, override={})
        self.assertDictEqual(result, {"a": 1, "b": 2})

    def test_disjoint_dicts_are_combined(self):
        result = merge_dicts(default={"a": 1}, override={"b": 2})
        self.assertDictEqual(result, {"a": 1, "b": 2})


class TestMergeModelDicts(unittest.TestCase):
    """merge_model_dicts updates existing models and creates new ones from dicts."""

    def setUp(self):
        self.default = {
            "user1": _UserModel(name="Alice", age=30),
            "user2": _UserModel(name="Bob", age=25),
        }

    def test_updates_existing_key_preserving_other_fields(self):
        merged = merge_model_dicts(self.default, {"user1": {"age": 31}})
        self.assertEqual(merged["user1"].age, 31)
        self.assertEqual(merged["user1"].name, "Alice")
        self.assertEqual(merged["user2"].age, 25)

    def test_new_key_with_complete_dict_creates_model(self):
        merged = merge_model_dicts(self.default, {"user3": {"name": "Charlie", "age": 22}})
        self.assertIn("user3", merged)
        self.assertEqual(merged["user3"].name, "Charlie")
        self.assertEqual(merged["user3"].age, 22)

    def test_combined_update_and_new_key(self):
        override = {"user1": {"age": 32}, "user3": {"name": "Charlie", "age": 22}}
        merged = merge_model_dicts(self.default, override)
        self.assertEqual(merged["user1"].age, 32)
        self.assertEqual(merged["user3"].name, "Charlie")
        self.assertEqual(merged["user2"].age, 25)

    def test_new_key_with_incomplete_dict_raises_validation_error(self):
        """Missing required field on a new entry raises ValidationError."""
        with self.assertRaises(ValidationError) as ctx:
            merge_model_dicts(self.default, {"user3": {"name": "Charlie"}})
        error_str = str(ctx.exception)
        self.assertIn("user3", error_str)
        self.assertIn("age", error_str)

    def test_new_key_with_model_object_raises_type_error(self):
        """Passing a full model instance (not a dict) for a new key raises TypeError."""
        with self.assertRaises(TypeError):
            merge_model_dicts(
                default={"a": _SimpleModel(id=1, name="x")},
                override={"b": _SimpleModel(id=2, name="y")},
            )


class TestMergePromptConfigs(unittest.TestCase):
    """merge_prompt_configs replaces all fields with the override model's values."""

    def test_override_values_win_for_all_fields(self):
        default = _SimpleModel(id=1, name="default")
        override = _SimpleModel(id=2, name="override")
        result = merge_prompt_configs(default=default, override=override)
        self.assertEqual(result.name, "override")
        self.assertEqual(result.id, 2)


if __name__ == "__main__":
    unittest.main()
