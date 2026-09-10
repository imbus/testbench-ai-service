import logging
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from testbench_ai_service.config import (
    DEFAULT_AGENTS,
    DEFAULT_HOST,
    DEFAULT_PORT,
    PROMPTS_DIR,
    AppConfig,
)
from testbench_ai_service.llm.base import AzureAuthMethod, LLMProvider
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

    def test_auth_method_defaults_to_api_key(self):
        cfg = LLMConfig()
        assert cfg.auth_method == AzureAuthMethod.API_KEY

    def test_azure_openai_provider_accepts_entra_id_auth(self):
        cfg = LLMConfig(
            provider=LLMProvider.AZURE_OPENAI,
            auth_method=AzureAuthMethod.ENTRA_ID,
            azure_endpoint="https://example.openai.azure.com",
            api_version="2024-10-21",
        )
        assert cfg.auth_method == AzureAuthMethod.ENTRA_ID

    @pytest.mark.parametrize(
        "provider",
        [LLMProvider.OPENAI, LLMProvider.ANTHROPIC],
    )
    def test_entra_id_auth_rejected_for_non_azure_provider(self, provider):
        with pytest.raises(ValidationError):
            LLMConfig(provider=provider, auth_method=AzureAuthMethod.ENTRA_ID)

    def test_auth_method_accepts_plain_string_from_toml(self):
        cfg = LLMConfig(
            provider=LLMProvider.AZURE_OPENAI,
            auth_method="entra_id",
            azure_endpoint="https://example.openai.azure.com",
            api_version="2024-10-21",
        )
        assert cfg.auth_method == AzureAuthMethod.ENTRA_ID


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


class TestPromptVarsAreTyped:
    """Spec 11.1: prompt variables carry typed values, not only strings.

    PromptVariableDefinition already declares 'number' and 'boolean' value
    types, so a config that supplies one was a hard boot failure before this.
    """

    @pytest.mark.parametrize(
        ("value", "expected_type"),
        [(10, int), (1.5, float), (True, bool), ("ten", str)],
    )
    def test_a_prompt_var_keeps_the_type_it_was_written_with(self, value, expected_type):
        cfg = PromptConfig(file="prompts/test.yaml", vars={"max_findings": value})

        assert cfg.vars is not None
        assert type(cfg.vars["max_findings"]) is expected_type
        assert cfg.vars["max_findings"] == value

    @pytest.mark.parametrize(
        ("value", "expected_type"),
        [(10, int), (1.5, float), (True, bool), ("ten", str)],
    )
    def test_a_project_prompt_var_keeps_the_type_it_was_written_with(self, value, expected_type):
        cfg = ProjectPromptConfig(vars={"max_findings": value})

        assert cfg.vars is not None
        assert type(cfg.vars["max_findings"]) is expected_type
        assert cfg.vars["max_findings"] == value

    def test_a_quoted_number_stays_a_string(self):
        """'10' and 10 are different values; the union must not collapse them."""
        cfg = PromptConfig(file="prompts/test.yaml", vars={"max_findings": "10"})

        assert cfg.vars == {"max_findings": "10"}
        assert type(cfg.vars["max_findings"]) is str


class TestAgentsMergeOntoDefaults:
    """A partial [agents.<key>] block overrides one setting, not the whole dict.

    Before this, ``agents`` was a plain default: declaring one agent replaced
    every built-in, and declaring one *partially* was rejected outright because
    every AgentConfig field is required. There was therefore no way to write
    "turn this agent off" into config.toml -- the naive spelling failed
    validation and the complete spelling silently deleted the other agents.
    """

    def test_a_partial_block_leaves_the_other_agents_in_place(self):
        cfg = _make_app_config(agents={"test_case_set_reviewer": {"enabled": False}})

        assert set(cfg.agents) == {
            "test_case_set_reviewer",
            "test_case_set_describer",
            "defect_explainer",
        }
        assert cfg.agents["test_case_set_reviewer"].enabled is False
        assert cfg.agents["test_case_set_describer"].enabled is True

    def test_a_partial_block_keeps_the_fields_it_did_not_mention(self):
        cfg = _make_app_config(agents={"test_case_set_reviewer": {"enabled": False}})

        agent = cfg.agents["test_case_set_reviewer"]
        assert agent.endpoint_path == "/test-case-set-reviews"
        assert agent.class_path.endswith("TestCaseSetReviewer")

    def test_a_nested_partial_merges_rather_than_replacing_the_prompt(self):
        """The console writes 'agents.<key>.prompt.variant' on its own."""
        cfg = _make_app_config(
            agents={"test_case_set_reviewer": {"prompt": {"variant": "Quick Review"}}}
        )

        prompt = cfg.agents["test_case_set_reviewer"].prompt
        assert isinstance(prompt, PromptConfig)
        assert prompt.variant == "Quick Review"
        # The file was not mentioned, so the built-in value must survive.
        assert prompt.file == Path("test_case_set_reviewer/prompt.yaml")

    def test_a_complete_block_for_a_builtin_also_keeps_the_others(self):
        """The one behaviour change: declaring one agent no longer deletes the rest."""
        cfg = _make_app_config(
            agents={
                "test_case_set_reviewer": {
                    "enabled": False,
                    "endpoint_path": "/custom",
                    "class_path": (
                        "testbench_ai_service.agents.test_case_set_reviewer.agent"
                        ".TestCaseSetReviewer"
                    ),
                    "prompt": {"file": "test_case_set_reviewer/prompt.yaml"},
                }
            }
        )

        assert len(cfg.agents) == 3
        assert cfg.agents["test_case_set_reviewer"].endpoint_path == "/custom"

    def test_an_unknown_agent_key_still_requires_every_field(self):
        with pytest.raises(ValidationError) as exc:
            _make_app_config(agents={"my_agent": {"enabled": True}})

        missing = {tuple(error["loc"]) for error in exc.value.errors()}
        assert ("agents", "my_agent", "endpoint_path") in missing
        assert ("agents", "my_agent", "class_path") in missing
        assert ("agents", "my_agent", "prompt") in missing

    def test_a_complete_unknown_agent_is_added_beside_the_builtins(self):
        cfg = _make_app_config(
            agents={
                "second_reviewer": {
                    "enabled": True,
                    "endpoint_path": "/second-reviews",
                    "class_path": (
                        "testbench_ai_service.agents.test_case_set_reviewer.agent"
                        ".TestCaseSetReviewer"
                    ),
                    "prompt": {"file": "test_case_set_reviewer/prompt.yaml"},
                }
            }
        )

        assert len(cfg.agents) == 4
        assert cfg.agents["second_reviewer"].endpoint_path == "/second-reviews"

    def test_a_bad_value_in_a_partial_block_is_field_addressed(self):
        with pytest.raises(ValidationError) as exc:
            _make_app_config(agents={"test_case_set_reviewer": {"enabled": "yes please"}})

        locations = {tuple(error["loc"]) for error in exc.value.errors()}
        assert ("agents", "test_case_set_reviewer", "enabled") in locations

    def test_merging_does_not_mutate_the_shared_defaults(self):
        """DEFAULT_AGENTS is a module-level dict; poisoning it would leak everywhere."""
        _make_app_config(agents={"test_case_set_reviewer": {"enabled": False}})

        assert DEFAULT_AGENTS["test_case_set_reviewer"].enabled is True
        assert _make_app_config().agents["test_case_set_reviewer"].enabled is True

    def test_omitting_agents_entirely_still_yields_the_builtins(self):
        cfg = _make_app_config()

        assert set(cfg.agents) == set(DEFAULT_AGENTS)

    def test_an_agent_declared_as_a_model_instance_still_works(self):
        """Python callers pass AgentConfig objects, not dicts."""
        cfg = _make_app_config(
            agents={
                "test_case_set_reviewer": AgentConfig(
                    enabled=False,
                    endpoint_path="/x",
                    class_path=(
                        "testbench_ai_service.agents.test_case_set_reviewer.agent"
                        ".TestCaseSetReviewer"
                    ),
                    prompt=PromptConfig(file="test_case_set_reviewer/prompt.yaml"),
                )
            }
        )

        assert cfg.agents["test_case_set_reviewer"].endpoint_path == "/x"


class TestBuiltinsWithNoPromptFile:
    """A built-in the operator never configured must not stop the service.

    Merging the ``agents`` table onto the built-ins means every built-in is now
    present in every config -- including one whose ``prompts_dir`` holds only
    the operator's own prompt files. Validating a built-in's prompt file into a
    hard error there would turn a config that booted before the merge into one
    that refuses to start, naming an agent the operator never wrote down.
    """

    REVIEWER = "testbench_ai_service.agents.test_case_set_reviewer.agent.TestCaseSetReviewer"

    @pytest.fixture
    def prompts_dir(self, tmp_path):
        """A prompts_dir holding one prompt file, and none of the built-ins'."""
        for language in ("de", "en"):
            (tmp_path / language).mkdir()
            shutil.copy(
                PROMPTS_DIR / language / "test_case_set_reviewer" / "prompt.yaml",
                tmp_path / language / "mine.yaml",
            )
        return tmp_path

    def _config(self, prompts_dir, **kwargs):
        with patch("testbench_ai_service.config.validate_tb_server_url"):
            return AppConfig(
                tb_server_url="https://localhost:9443/api/", prompts_dir=prompts_dir, **kwargs
            )

    def test_a_custom_agent_set_with_its_own_prompts_dir_still_boots(self, prompts_dir):
        cfg = self._config(
            prompts_dir,
            agents={
                "my_agent": {
                    "enabled": True,
                    "endpoint_path": "/mine",
                    "class_path": self.REVIEWER,
                    "prompt": {"file": "mine.yaml"},
                }
            },
        )

        assert set(cfg.agents) == {"my_agent"}

    def test_disabling_a_builtin_does_not_require_its_prompt_file(self, prompts_dir):
        """The documented way to switch an agent off has to work everywhere."""
        cfg = self._config(
            prompts_dir,
            agents={
                "test_case_set_reviewer": {"enabled": False},
                "test_case_set_describer": {"enabled": False},
                "defect_explainer": {"enabled": False},
                "my_agent": {
                    "enabled": True,
                    "endpoint_path": "/mine",
                    "class_path": self.REVIEWER,
                    "prompt": {"file": "mine.yaml"},
                },
            },
        )

        assert cfg.agents["test_case_set_reviewer"].enabled is False
        assert cfg.agents["my_agent"].enabled is True

    def test_a_configured_prompt_file_that_is_missing_is_still_an_error(self, prompts_dir):
        """Leniency covers what the operator did not write, not what they did."""
        with pytest.raises(ValidationError) as excinfo:
            self._config(
                prompts_dir,
                agents={"test_case_set_reviewer": {"prompt": {"file": "nope.yaml"}}},
            )

        assert excinfo.value.errors()[0]["loc"] == (
            "agents",
            "test_case_set_reviewer",
            "prompt",
            "file",
        )

    def test_the_builtins_survive_when_their_prompt_files_are_there(self):
        with patch("testbench_ai_service.config.validate_tb_server_url"):
            cfg = AppConfig(tb_server_url="https://localhost:9443/api/")

        assert set(cfg.agents) == set(DEFAULT_AGENTS)

    def test_a_dropped_builtin_is_logged(self, prompts_dir, caplog):
        with caplog.at_level(logging.WARNING):
            self._config(
                prompts_dir,
                agents={
                    "my_agent": {
                        "enabled": True,
                        "endpoint_path": "/mine",
                        "class_path": self.REVIEWER,
                        "prompt": {"file": "mine.yaml"},
                    }
                },
            )

        assert "test_case_set_reviewer" in caplog.text
