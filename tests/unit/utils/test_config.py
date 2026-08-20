import tempfile
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from pydantic import BaseModel, ValidationError

from testbench_ai_service.config import AppConfig
from testbench_ai_service.llm.base import AzureAuthMethod, LLMProvider
from testbench_ai_service.models.config import LLMConfig, ProjectConfig
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


class TestLoadConfigFromFile:
    """load_config_from_file reads a TOML file and creates an AppConfig."""

    def test_valid_file_produces_app_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_toml(tmpdir, CONFIG_PREFIX, {"some_setting": "value"})
            result = load_config_from_file(path)

        assert isinstance(result, AppConfig)

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


class TestGetLLMConfig:
    """get_llm_config merges global LLM config with optional project/request overrides."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.llm_config = MagicMock()
        self.llm_config.model_copy.return_value = self.llm_config
        self.llm_config.model_dump.return_value = {"key": "global_value"}

        self.config = MagicMock()
        self.config.llm_config = self.llm_config
        self.config.projects = {}

    def test_global_config_only(self):
        result = get_llm_config(self.config)
        self.llm_config.model_copy.assert_called_with(deep=True)
        assert result == self.llm_config

    def test_project_override_is_applied(self):
        project_llm_config = MagicMock()
        project_llm_config.model_dump.return_value = {"key": "project_value"}
        self.config.projects["proj1"] = MagicMock(llm_config=project_llm_config)

        result = get_llm_config(self.config, project_name="proj1")

        self.llm_config.model_copy.assert_has_calls(
            [call(deep=True), call(update={"key": "project_value"})]
        )
        assert result == self.llm_config

    def test_request_override_only(self):
        request_config = MagicMock()
        request_config.model_dump.return_value = {"key": "request_value"}

        result = get_llm_config(self.config, request_config=request_config)

        self.llm_config.model_copy.assert_has_calls(
            [call(deep=True), call(update={"key": "request_value"})]
        )
        assert result == self.llm_config

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
        assert result == self.llm_config


class TestGetLLMConfigEntraIdConsistency:
    """
    'model_copy(update=...)' skips validation, so 'entra_id' could otherwise escape
    its azure_openai-only guarantee through a project or request override.
    """

    def _app_config(self, llm_config: LLMConfig) -> MagicMock:
        """
        A stand-in for AppConfig: 'get_llm_config' only reads 'llm_config' and
        'projects', and a real AppConfig would drag in prompt template validation.
        """
        config = MagicMock()
        config.llm_config = llm_config
        config.projects = {}
        return config

    def _entra_global_config(self) -> MagicMock:
        return self._app_config(
            LLMConfig(
                provider=LLMProvider.AZURE_OPENAI,
                auth_method=AzureAuthMethod.ENTRA_ID,
                model="gpt-4o",
                azure_endpoint="https://example.openai.azure.com",
                api_version="2024-10-21",
            )
        )

    def test_project_override_to_a_non_azure_provider_raises(self):
        config = self._entra_global_config()
        config.projects = {
            "proj1": ProjectConfig(llm_config=LLMConfig(provider=LLMProvider.OPENAI))
        }

        with pytest.raises(ValueError, match="entra_id") as exc_info:
            get_llm_config(config, project_name="proj1")

        message = str(exc_info.value)
        assert "'azure_openai'" in message
        assert "uses provider 'openai'" in message

    def test_request_override_to_a_non_azure_provider_raises(self):
        config = self._entra_global_config()

        with pytest.raises(ValueError, match="entra_id"):
            get_llm_config(config, request_config=LLMConfig(provider=LLMProvider.ANTHROPIC))

    def test_azure_entra_config_still_merges(self):
        config = self._entra_global_config()
        config.projects = {"proj1": ProjectConfig(llm_config=LLMConfig(model="gpt-4o-mini"))}

        result = get_llm_config(config, project_name="proj1")

        assert result.provider == LLMProvider.AZURE_OPENAI
        assert result.auth_method == AzureAuthMethod.ENTRA_ID
        assert result.model == "gpt-4o-mini"

    def test_api_key_config_is_unaffected(self):
        config = self._app_config(LLMConfig(provider=LLMProvider.OPENAI, model="gpt-4o"))
        config.projects = {"proj1": ProjectConfig(llm_config=LLMConfig(model="gpt-4o-mini"))}

        result = get_llm_config(config, project_name="proj1")

        assert result.provider == LLMProvider.OPENAI
        assert result.auth_method == AzureAuthMethod.API_KEY


class TestGetPromptConfig:
    """get_prompt_config returns a deep-copied and optionally merged PromptConfig."""

    @pytest.fixture(autouse=True)
    def setup(self):
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
        assert result == self.prompt_config

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
        assert result is merged

    @patch("testbench_ai_service.utils.config.get_agent_config")
    @patch("testbench_ai_service.utils.config.merge_prompt_configs")
    def test_request_override_is_merged(self, mock_merge, mock_get_uc):
        mock_get_uc.return_value = self.agent_config
        request_prompt_config = MagicMock()
        merged = MagicMock()
        mock_merge.return_value = merged

        result = get_prompt_config("uc1", self.config, request_config=request_prompt_config)

        mock_merge.assert_called_once_with(self.prompt_config, request_prompt_config)
        assert result is merged

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
        assert result is after_request

    @patch("testbench_ai_service.utils.config.get_agent_config")
    @patch("testbench_ai_service.utils.config.merge_prompt_configs")
    def test_project_without_prompt_skips_merge(self, mock_merge, mock_get_uc):
        mock_get_uc.return_value = self.agent_config
        self.config.projects["proj1"] = MagicMock(agents={"uc1": MagicMock(prompt=None)})

        result = get_prompt_config("uc1", self.config, project_name="proj1")

        mock_merge.assert_not_called()
        assert result == self.prompt_config


class TestGetLanguageFromConfig:
    """get_language_from_config resolves the language at global or project level."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.config = MagicMock()
        self.config.language = "en"
        self.config.projects = {}

    def test_global_language_returned_without_project(self):
        assert get_language_from_config(self.config) == "en"

    def test_project_language_overrides_global(self):
        self.config.projects["proj1"] = MagicMock(language="de")
        assert get_language_from_config(self.config, "proj1") == "de"

    def test_project_without_language_falls_back_to_global(self):
        self.config.projects["proj1"] = MagicMock(language=None)
        assert get_language_from_config(self.config, "proj1") == "en"

    def test_unknown_project_falls_back_to_global(self):
        assert get_language_from_config(self.config, "unknown") == "en"


class TestGetAgentConfig:
    """get_agent_config merges global and per-project agent configurations."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.agent_config = MagicMock()
        self.agent_config.model_copy.return_value = self.agent_config
        self.agent_config.model_dump.return_value = {"key": "value"}

        self.config = MagicMock()
        self.config.agents = {"uc1": self.agent_config}
        self.config.projects = {}

    def test_global_only_returns_deep_copy(self):
        result = get_agent_config("uc1", self.config)
        self.agent_config.model_copy.assert_called_with(deep=True)
        assert result == self.agent_config

    def test_project_without_override_returns_global(self):
        self.config.projects["proj1"] = MagicMock(agents=None)
        result = get_agent_config("uc1", self.config, "proj1")
        assert result == self.agent_config

    def test_project_partial_override_is_applied(self):
        project_override = MagicMock()
        project_override.model_dump.return_value = {"override_key": "override_value"}
        self.config.projects["proj1"] = MagicMock(agents={"uc1": project_override})

        result = get_agent_config("uc1", self.config, "proj1")

        self.agent_config.model_copy.assert_has_calls(
            [call(deep=True), call(update={"override_key": "override_value"})]
        )
        assert result == self.agent_config

    def test_unknown_project_returns_global(self):
        result = get_agent_config("uc1", self.config, "unknown_project")
        assert result == self.agent_config


class TestMergeDicts:
    """merge_dicts creates a new dict with override values taking precedence."""

    def test_override_value_wins_on_key_conflict(self):
        result = merge_dicts(default={"a": 1, "b": 2}, override={"b": 3, "c": 4})
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_empty_override_returns_copy_of_default(self):
        result = merge_dicts(default={"a": 1, "b": 2}, override={})
        assert result == {"a": 1, "b": 2}

    def test_disjoint_dicts_are_combined(self):
        result = merge_dicts(default={"a": 1}, override={"b": 2})
        assert result == {"a": 1, "b": 2}


class TestMergeModelDicts:
    """merge_model_dicts updates existing models and creates new ones from dicts."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.default = {
            "user1": _UserModel(name="Alice", age=30),
            "user2": _UserModel(name="Bob", age=25),
        }

    def test_updates_existing_key_preserving_other_fields(self):
        merged = merge_model_dicts(self.default, {"user1": {"age": 31}})
        assert merged["user1"].age == 31
        assert merged["user1"].name == "Alice"
        assert merged["user2"].age == 25

    def test_new_key_with_complete_dict_creates_model(self):
        merged = merge_model_dicts(self.default, {"user3": {"name": "Charlie", "age": 22}})
        assert "user3" in merged
        assert merged["user3"].name == "Charlie"
        assert merged["user3"].age == 22

    def test_combined_update_and_new_key(self):
        override = {"user1": {"age": 32}, "user3": {"name": "Charlie", "age": 22}}
        merged = merge_model_dicts(self.default, override)
        assert merged["user1"].age == 32
        assert merged["user3"].name == "Charlie"
        assert merged["user2"].age == 25

    def test_new_key_with_incomplete_dict_raises_validation_error(self):
        """Missing required field on a new entry raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            merge_model_dicts(self.default, {"user3": {"name": "Charlie"}})
        error_str = str(exc_info.value)
        assert "user3" in error_str
        assert "age" in error_str

    def test_new_key_with_model_object_raises_type_error(self):
        """Passing a full model instance (not a dict) for a new key raises TypeError."""
        with pytest.raises(TypeError):
            merge_model_dicts(
                default={"a": _SimpleModel(id=1, name="x")},
                override={"b": _SimpleModel(id=2, name="y")},
            )


class TestMergePromptConfigs:
    """merge_prompt_configs replaces all fields with the override model's values."""

    def test_override_values_win_for_all_fields(self):
        default = _SimpleModel(id=1, name="default")
        override = _SimpleModel(id=2, name="override")
        result = merge_prompt_configs(default=default, override=override)
        assert result.name == "override"
        assert result.id == 2
