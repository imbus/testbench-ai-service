import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from testbench_ai_service.config import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    PROMPTS_DIR,
    AppConfig,
    LLMConfig,
    ProjectConfig,
    ProjectPromptConfig,
    ProjectUseCaseConfig,
    PromptConfig,
    UseCaseConfig,
)
from testbench_ai_service.llm.base import LLMProvider
from testbench_ai_service.models.language import LanguageOption


def _make_app_config(**kwargs):
    """Build an AppConfig with all validators that require I/O patched out."""
    with (
        patch("testbench_ai_service.config.validate_tb_server_url"),
        patch("testbench_ai_service.config.AppConfig.validate_prompt_paths", return_value=None),
        patch(
            "testbench_ai_service.config.AppConfig.validate_prompts_dir_exists",
            return_value=PROMPTS_DIR,
        ),
    ):
        return AppConfig(**kwargs)


class TestLLMConfig(unittest.TestCase):
    def test_defaults_to_openai_provider(self):
        cfg = LLMConfig()
        self.assertEqual(cfg.provider, LLMProvider.OPENAI)

    def test_model_can_be_set(self):
        cfg = LLMConfig(model="gpt-4o")
        self.assertEqual(cfg.model, "gpt-4o")

    def test_extra_fields_allowed(self):
        """LLMConfig has extra='allow' so arbitrary kwargs should not raise."""
        cfg = LLMConfig(temperature=0.7)
        self.assertEqual(cfg.temperature, 0.7)

    def test_custom_provider_requires_class_path(self):
        with self.assertRaises(ValidationError):
            LLMConfig(provider=LLMProvider.CUSTOM, class_path=None)

    def test_custom_provider_with_valid_class_path_succeeds(self):
        cfg = LLMConfig(
            provider=LLMProvider.CUSTOM,
            class_path="testbench_ai_service.llm.openai.OpenAIClient",
        )
        self.assertEqual(cfg.provider, LLMProvider.CUSTOM)


class TestPromptConfig(unittest.TestCase):
    def test_requires_file_field(self):
        with self.assertRaises(ValidationError):
            PromptConfig(name="MyPrompt")

    def test_minimal_valid_prompt_config(self):
        cfg = PromptConfig(file="prompts/test.yaml", name="MyPrompt")
        self.assertEqual(cfg.name, "MyPrompt")
        self.assertEqual(cfg.file, Path("prompts/test.yaml"))

    def test_optional_fields_default_to_none(self):
        cfg = PromptConfig(file="prompts/test.yaml", name="Test")
        self.assertIsNone(cfg.variant)
        self.assertIsNone(cfg.placeholder_data)

    def test_extra_fields_allowed(self):
        cfg = PromptConfig(file="prompts/test.yaml", name="Test", glossary="/path/glossary.txt")
        self.assertEqual(cfg.glossary, "/path/glossary.txt")


class TestProjectPromptConfig(unittest.TestCase):
    def test_all_fields_optional(self):
        cfg = ProjectPromptConfig()
        self.assertIsNone(cfg.file)
        self.assertIsNone(cfg.name)
        self.assertIsNone(cfg.variant)
        self.assertIsNone(cfg.placeholder_data)


class TestUseCaseConfig(unittest.TestCase):
    def test_required_fields(self):
        with self.assertRaises(ValidationError):
            UseCaseConfig()  # All required fields missing

    def test_valid_use_case_config(self):
        cfg = UseCaseConfig(
            enabled=True,
            endpoint_path="/test",
            class_path="testbench_ai_service.usecases.base.UseCase",
            prompt=PromptConfig(file="prompts/test.yaml", name="Test"),
        )
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.endpoint_path, "/test")


class TestProjectUseCaseConfig(unittest.TestCase):
    def test_all_fields_optional(self):
        cfg = ProjectUseCaseConfig()
        self.assertIsNone(cfg.enabled)
        self.assertIsNone(cfg.prompt)

    def test_can_override_enabled(self):
        cfg = ProjectUseCaseConfig(enabled=False)
        self.assertFalse(cfg.enabled)


class TestProjectConfig(unittest.TestCase):
    def test_defaults_are_none(self):
        cfg = ProjectConfig()
        self.assertIsNone(cfg.language)
        self.assertIsNone(cfg.llm_config)
        self.assertIsNone(cfg.usecases)

    def test_can_set_language(self):
        cfg = ProjectConfig(language=LanguageOption.ENGLISH)
        self.assertEqual(cfg.language, LanguageOption.ENGLISH)


class TestAppConfigDefaults(unittest.TestCase):
    def test_default_host_and_port(self):
        config = _make_app_config()
        self.assertEqual(config.host, DEFAULT_HOST)
        self.assertEqual(config.port, DEFAULT_PORT)

    def test_default_language_is_german(self):
        config = _make_app_config()
        self.assertEqual(config.language, LanguageOption.GERMAN)

    def test_debug_defaults_to_false(self):
        config = _make_app_config()
        self.assertFalse(config.debug)

    def test_ssl_fields_default_to_none(self):
        config = _make_app_config()
        self.assertIsNone(config.ssl_cert)
        self.assertIsNone(config.ssl_key)
        self.assertIsNone(config.ssl_ca_cert)

    def test_trusted_proxies_defaults_to_none(self):
        config = _make_app_config()
        self.assertIsNone(config.trusted_proxies)

    def test_default_usecases_loaded(self):
        config = _make_app_config()
        self.assertIn("test_case_set_reviews", config.usecases)
        self.assertIn("test_case_set_descriptions", config.usecases)
        self.assertIn("defect_explanations", config.usecases)

    def test_projects_defaults_to_empty_dict(self):
        config = _make_app_config()
        self.assertEqual(config.projects, {})


class TestAppConfigTrustedProxiesValidator(unittest.TestCase):
    def test_string_split_by_comma(self):
        config = _make_app_config(trusted_proxies="10.0.0.1,10.0.0.2")
        self.assertEqual(config.trusted_proxies, ["10.0.0.1", "10.0.0.2"])

    def test_list_accepted_as_is(self):
        config = _make_app_config(trusted_proxies=["192.168.1.1"])
        self.assertEqual(config.trusted_proxies, ["192.168.1.1"])

    def test_empty_string_becomes_none(self):
        config = _make_app_config(trusted_proxies="")
        self.assertIsNone(config.trusted_proxies)


class TestAppConfigSSLValidator(unittest.TestCase):
    def test_nonexistent_ssl_cert_raises(self):
        with (
            patch("testbench_ai_service.config.validate_tb_server_url"),
            patch("testbench_ai_service.config.AppConfig.validate_prompt_paths", return_value=None),
            patch(
                "testbench_ai_service.config.AppConfig.validate_prompts_dir_exists",
                return_value=PROMPTS_DIR,
            ),
            self.assertRaises(ValidationError),
        ):
            AppConfig(ssl_cert="/non/existent/cert.pem")


class TestAppConfigTbServerUrlValidator(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
