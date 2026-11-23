"""A project's prompt override resolves against the project's own language.

``utils.config.get_prompt_config`` resolves a project's ``prompt.file`` with
``get_language_from_config(config, project_name)`` -- the project's override when
it has one. The boot validator passed the GLOBAL language instead, so a project
overriding both ``language`` and ``prompt.file`` could not start the service it
would have run correctly.
"""

from unittest.mock import patch

import pytest

from testbench_ai_service.config import AppConfig

TB_URL = "https://localhost:9443/api/"

PROMPT_YAML = """\
name: "Reviewer"
default_variant: "A"
default_model: "gpt-5.5"
variants:
  - name: "A"
    messages:
      - role: "user"
        text: "hallo"
"""


@pytest.fixture
def prompts_dir(tmp_path):
    """An English fork, with no German copy of it anywhere."""
    fork = tmp_path / "en" / "reviewer__proj"
    fork.mkdir(parents=True)
    (fork / "prompt.yaml").write_text(PROMPT_YAML, encoding="utf-8")
    return tmp_path


def build(prompts_dir, **kwargs):
    with patch("testbench_ai_service.config.validate_tb_server_url"):
        return AppConfig(tb_server_url=TB_URL, prompts_dir=prompts_dir, **kwargs)


def test_a_project_override_resolves_under_the_projects_own_language(prompts_dir):
    config = build(
        prompts_dir,
        language="de",
        projects={
            "Proj": {
                "language": "en",
                "agents": {
                    "test_case_set_reviewer": {"prompt": {"file": "reviewer__proj/prompt.yaml"}}
                },
            }
        },
    )
    override = config.projects["Proj"].agents["test_case_set_reviewer"].prompt
    assert override is not None
    assert override.file is not None


def test_a_project_without_a_language_override_still_uses_the_global_one(prompts_dir):
    # The same file, reached through the global language rather than an override.
    config = build(
        prompts_dir,
        language="en",
        projects={
            "Proj": {
                "agents": {
                    "test_case_set_reviewer": {"prompt": {"file": "reviewer__proj/prompt.yaml"}}
                }
            }
        },
    )
    assert config.projects["Proj"].agents["test_case_set_reviewer"].prompt is not None


def test_a_genuinely_missing_project_prompt_is_still_refused(prompts_dir):
    with pytest.raises(ValueError, match="not found"):
        build(
            prompts_dir,
            language="de",
            projects={
                "Proj": {
                    "language": "en",
                    "agents": {"test_case_set_reviewer": {"prompt": {"file": "nope/prompt.yaml"}}},
                }
            },
        )
