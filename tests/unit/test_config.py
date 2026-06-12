from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from testbench_ai_service.config import DEFAULT_HOST, DEFAULT_PORT, PROMPTS_DIR, AppConfig
from testbench_ai_service.llm.base import LLMProvider
from testbench_ai_service.models.config import (
    AgentConfig,
    LLMConfig,
    ProjectAgentConfig,
    ProjectConfig,
    ProjectPromptConfig,
    PromptConfig,
)
from testbench_ai_service.models.language import LanguageOption


def _make_app_config(**kwargs):
    with (
        patch("testbench_ai_service.config.validate_tb_server_url"),
        patch("testbench_ai_service.config.AppConfig.validate_prompt_paths", return_value=None),
        patch(
            "testbench_ai_service.config.AppConfig.validate_prompts_dir_exists",
            return_value=PROMPTS_DIR,
        ),
    ):
        return AppConfig(**kwargs)


class TestLLMConfig:
    def test_defaults_to_openai_provider(self):
        cfg = LLMConfig()
        assert cfg.provider == LLMProvider.OPENAI

    def test_model_can_be_set(self):
        cfg = LLMConfig(model="gpt-4o")
        assert cfg.model == "gpt-4o"

    def test_extra_fields_allowed(self):
        cfg = LLMConfig(temperature=0.7)
        assert cfg.temperature == 0.7

    def test_custom_provider_requires_class_path(self):
        with pytest.raises(ValidationError):
            LLMConfig(provider=LLMProvider.CUSTOM, class_path=None)

    def test_custom_provider_with_valid_class_path_succeeds(self):
        cfg = LLMConfig(
            provider=LLMProvider.CUSTOM,
            class_path="testbench_ai_service.llm.openai.OpenAIClient",
        )
        assert cfg.provider == LLMProvider.CUSTOM

    def test_azure_openai_provider_requires_endpoint(self):
        with pytest.raises(ValidationError):
            LLMConfig(provider=LLMProvider.AZURE_OPENAI, api_version="2024-10-21")

    def test_azure_openai_provider_requires_api_version(self):
        with pytest.raises(ValidationError):
            LLMConfig(
                provider=LLMProvider.AZURE_OPENAI,
                azure_endpoint="https://example.openai.azure.com",
            )

    def test_azure_openai_provider_with_required_fields_succeeds(self):
        cfg = LLMConfig(
            provider=LLMProvider.AZURE_OPENAI,
            azure_endpoint="https://example.openai.azure.com",
            api_version="2024-10-21",
        )
        assert cfg.provider == LLMProvider.AZURE_OPENAI


class TestPromptConfig:
    def test_requires_file_field(self):
        with pytest.raises(ValidationError):
            PromptConfig()

    def test_minimal_valid_prompt_config(self):
        cfg = PromptConfig(file="prompts/test.yaml")
        assert cfg.file == Path("prompts/test.yaml")

    def test_optional_fields_default_to_none(self):
        cfg = PromptConfig(file="prompts/test.yaml")
        assert cfg.variant is None
        assert cfg.vars is None

    def test_extra_fields_allowed(self):
        cfg = PromptConfig(file="prompts/test.yaml", glossary="/path/glossary.txt")
        assert cfg.glossary == "/path/glossary.txt"


class TestProjectPromptConfig:
    def test_all_fields_optional(self):
        cfg = ProjectPromptConfig()
        assert cfg.file is None
        assert cfg.variant is None
        assert cfg.vars is None


class TestAgentConfig:
    def test_required_fields(self):
        with pytest.raises(ValidationError):
            AgentConfig()

    def test_valid_use_case_config(self):
        cfg = AgentConfig(
            enabled=True,
            endpoint_path="/test",
            class_path="testbench_ai_service.agents.base.Agent",
            prompt=PromptConfig(file="prompts/test.yaml"),
        )
        assert cfg.enabled
        assert cfg.endpoint_path == "/test"


class TestProjectAgentConfig:
    def test_all_fields_optional(self):
        cfg = ProjectAgentConfig()
        assert cfg.enabled is None
        assert cfg.prompt is None

    def test_can_override_enabled(self):
        cfg = ProjectAgentConfig(enabled=False)
        assert not cfg.enabled


class TestProjectConfig:
    def test_defaults_are_none(self):
        cfg = ProjectConfig()
        assert cfg.language is None
        assert cfg.llm_config is None
        assert cfg.agents is None

    def test_can_set_language(self):
        cfg = ProjectConfig(language=LanguageOption.ENGLISH)
        assert cfg.language == LanguageOption.ENGLISH


class TestAppConfigDefaults:
    @pytest.fixture(autouse=True)
    def config(self):
        self._config = _make_app_config()

    def test_default_host_and_port(self):
        assert self._config.host == DEFAULT_HOST
        assert self._config.port == DEFAULT_PORT

    def test_default_language_is_german(self):
        assert self._config.language == LanguageOption.GERMAN

    def test_debug_defaults_to_false(self):
        assert not self._config.debug

    def test_ssl_fields_default_to_none(self):
        assert self._config.ssl_cert is None
        assert self._config.ssl_key is None
        assert self._config.ssl_ca_cert is None

    def test_tb_ssl_verify_defaults_to_true(self):
        assert self._config.tb_ssl_verify

    def test_tb_ssl_ca_bundle_defaults_to_none(self):
        assert self._config.tb_ssl_ca_bundle is None

    def test_trusted_proxies_defaults_to_none(self):
        assert self._config.trusted_proxies is None

    def test_default_agents_loaded(self):
        assert "test_case_set_reviewer" in self._config.agents
        assert "test_case_set_describer" in self._config.agents
        assert "defect_explainer" in self._config.agents

    def test_projects_defaults_to_empty_dict(self):
        assert self._config.projects == {}


class TestAppConfigTrustedProxiesValidator:
    def test_string_split_by_comma(self):
        config = _make_app_config(trusted_proxies="10.0.0.1,10.0.0.2")
        assert config.trusted_proxies == ["10.0.0.1", "10.0.0.2"]

    def test_list_accepted_as_is(self):
        config = _make_app_config(trusted_proxies=["192.168.1.1"])
        assert config.trusted_proxies == ["192.168.1.1"]

    def test_empty_string_becomes_none(self):
        config = _make_app_config(trusted_proxies="")
        assert config.trusted_proxies is None


class TestAppConfigSSLValidator:
    def test_nonexistent_ssl_cert_raises(self):
        with (
            patch("testbench_ai_service.config.validate_tb_server_url"),
            patch("testbench_ai_service.config.AppConfig.validate_prompt_paths", return_value=None),
            patch(
                "testbench_ai_service.config.AppConfig.validate_prompts_dir_exists",
                return_value=PROMPTS_DIR,
            ),
            pytest.raises(ValidationError),
        ):
            AppConfig(ssl_cert="/non/existent/cert.pem")

    def test_nonexistent_tb_ssl_ca_bundle_raises(self):
        with (
            patch("testbench_ai_service.config.validate_tb_server_url"),
            patch("testbench_ai_service.config.AppConfig.validate_prompt_paths", return_value=None),
            patch(
                "testbench_ai_service.config.AppConfig.validate_prompts_dir_exists",
                return_value=PROMPTS_DIR,
            ),
            pytest.raises(ValidationError),
        ):
            AppConfig(tb_ssl_ca_bundle="/non/existent/ca-bundle.pem")

    def test_tb_ssl_verify_false_accepted(self):
        config = _make_app_config(tb_ssl_verify=False)
        assert config.tb_ssl_verify is False


class TestAppConfigTbServerUrlValidator:
    def test_valid_url_calls_validator(self):
        with (
            patch("testbench_ai_service.config.validate_tb_server_url") as mock_validate,
            patch("testbench_ai_service.config.AppConfig.validate_prompt_paths", return_value=None),
            patch(
                "testbench_ai_service.config.AppConfig.validate_prompts_dir_exists",
                return_value=PROMPTS_DIR,
            ),
        ):
            AppConfig(tb_server_url="https://mytb.example.com/api/")
        mock_validate.assert_called_once_with("https://mytb.example.com/api/")
