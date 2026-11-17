"""The package inspection, run end to end in its subprocess."""

from __future__ import annotations

from testbench_ai_service.agent_packages.runner import run_inspection
from tests.helpers.wheels import VALID_AGENT_FILES, extracted

AGENT = "acme/rater/agent.py"


def _with(**changes: str | None) -> dict[str, str | bytes]:
    """VALID_AGENT_FILES with files replaced (str) or removed (None)."""
    files = dict(VALID_AGENT_FILES)
    for path, content in changes.items():
        if content is None:
            files.pop(path, None)
        else:
            files[path] = content
    return files


def test_inspect_valid_package(tmp_path):
    report = run_inspection(extracted(tmp_path, VALID_AGENT_FILES))
    assert report.ok, report
    agent = report.agents["acme_rater"]
    assert agent.ok
    assert agent.entry_point == "acme.rater.agent:RaterAgent"
    assert agent.class_path == "acme.rater.agent.RaterAgent"
    assert agent.data_fields == ["title"]
    assert agent.context_sample == {"title": "<str>"}
    assert agent.args_schema is not None
    assert agent.uses_llm is True
    assert agent.default_endpoint_path is None
    assert agent.errors == []
    assert agent.warnings == []


def test_inspect_reports_class_settings(tmp_path):
    source = str(VALID_AGENT_FILES[AGENT]).replace(
        "    AGENT_DATA_CLASS = RaterData\n",
        "    AGENT_DATA_CLASS = RaterData\n"
        "    USES_LLM = False\n"
        "    DEFAULT_ENDPOINT_PATH = '/rate'\n"
        "    STEP_DATA_CLASSES = {}\n",
    )
    report = run_inspection(extracted(tmp_path, _with(**{AGENT: source})))
    agent = report.agents["acme_rater"]
    assert agent.ok, agent
    assert agent.uses_llm is False
    assert agent.default_endpoint_path == "/rate"


def test_inspect_reports_import_error(tmp_path):
    files = _with(**{AGENT: "raise RuntimeError('boom on import')\n"})
    report = run_inspection(extracted(tmp_path, files))
    assert not report.ok
    agent = report.agents["acme_rater"]
    assert agent.ok is False
    assert any("boom on import" in e for e in agent.errors)


def test_inspect_reports_wrong_prompt_variable(tmp_path):
    files = _with(**{"acme/rater/prompts/en/user.jinja": "Rate {{ agent.unknown }}."})
    report = run_inspection(extracted(tmp_path, files))
    agent = report.agents["acme_rater"]
    assert not report.ok
    assert not agent.ok
    assert any("agent.unknown" in e and "prompts/en" in e for e in agent.errors)


def test_inspect_reports_missing_de_prompt(tmp_path):
    files = _with(**{"acme/rater/prompts/de/prompt.yaml": None})
    report = run_inspection(extracted(tmp_path, files))
    agent = report.agents["acme_rater"]
    assert not agent.ok
    assert any("prompts/de/prompt.yaml" in e for e in agent.errors)


def test_inspect_reports_invalid_prompt_schema(tmp_path):
    files = _with(**{"acme/rater/prompts/en/prompt.yaml": "name: 1\n"})
    report = run_inspection(extracted(tmp_path, files))
    agent = report.agents["acme_rater"]
    assert not agent.ok
    assert any("prompts/en/prompt.yaml" in e for e in agent.errors)


def test_inspect_reports_missing_template(tmp_path):
    files = _with(**{"acme/rater/templates/de/failed.jinja": None})
    report = run_inspection(extracted(tmp_path, files))
    agent = report.agents["acme_rater"]
    assert not agent.ok
    assert any("templates/de" in e and "failed" in e for e in agent.errors)


def test_inspect_accepts_any_template_extension(tmp_path):
    files = _with(**{"acme/rater/templates/de/failed.jinja": None})
    files["acme/rater/templates/de/failed.html"] = "<p>failed</p>"
    report = run_inspection(extracted(tmp_path, files))
    assert report.agents["acme_rater"].ok


def test_inspect_reports_module_conflict(tmp_path):
    report = run_inspection(extracted(tmp_path, {"requests/__init__.py": "", **VALID_AGENT_FILES}))
    assert not report.ok
    assert any("module 'requests' already exists" in e for e in report.errors)
    assert report.agents == {}


def test_inspect_reports_unmet_requires_dist(tmp_path):
    site = extracted(tmp_path, VALID_AGENT_FILES, requires_dist=["nonexistent-pkg>=1"])
    report = run_inspection(site)
    assert not report.ok
    assert any("nonexistent-pkg" in e for e in report.errors)


def test_inspect_reports_wrong_service_version(tmp_path):
    site = extracted(tmp_path, VALID_AGENT_FILES, requires_dist=["testbench-ai-service>=999"])
    report = run_inspection(site)
    assert not report.ok
    assert any("testbench-ai-service" in e for e in report.errors)


def test_inspect_accepts_met_requirements(tmp_path):
    site = extracted(
        tmp_path,
        VALID_AGENT_FILES,
        requires_dist=[
            "testbench-ai-service>=0",
            "pydantic",
            'nonexistent-pkg>=1; python_version < "3"',
            'other-missing; extra == "dev"',
        ],
    )
    report = run_inspection(site)
    assert report.ok, report


def test_inspect_reports_missing_entry_point(tmp_path):
    report = run_inspection(extracted(tmp_path, VALID_AGENT_FILES, entry_points={}))
    assert not report.ok
    assert any("no entry point in group 'testbench_ai_service.agents'" in e for e in report.errors)


def test_inspect_rejects_non_agent_class(tmp_path):
    files = _with(**{AGENT: "class RaterAgent:\n    pass\n"})
    report = run_inspection(extracted(tmp_path, files))
    agent = report.agents["acme_rater"]
    assert not report.ok
    assert not agent.ok
    assert any("not a subclass of Agent" in e for e in agent.errors)


def test_inspect_warns_about_required_args(tmp_path):
    source = (
        str(VALID_AGENT_FILES[AGENT])
        .replace(
            "from testbench_ai_service.models.agent import AgentData\n",
            "from testbench_ai_service.models.agent import AgentArgs, AgentData\n\n\n"
            "class RaterArgs(AgentArgs):\n    limit: int\n",
        )
        .replace(
            "    AGENT_DATA_CLASS = RaterData\n",
            "    AGENT_DATA_CLASS = RaterData\n    ARGS_CLASS = RaterArgs\n",
        )
    )
    report = run_inspection(extracted(tmp_path, _with(**{AGENT: source})))
    agent = report.agents["acme_rater"]
    assert agent.ok, agent
    assert "args has required fields" in agent.warnings
    assert agent.args_schema is not None
    assert "limit" in agent.args_schema["properties"]


def test_inspect_survives_print_on_import(tmp_path):
    source = "print('junk on stdout')\n" + str(VALID_AGENT_FILES[AGENT])
    report = run_inspection(extracted(tmp_path, _with(**{AGENT: source})))
    assert report.ok, report
