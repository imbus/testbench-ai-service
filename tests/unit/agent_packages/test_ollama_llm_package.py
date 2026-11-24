"""The Ollama client package: the inspection accepts it and the client speaks Ollama's chat API."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest

from testbench_ai_service.agent_packages.runner import run_inspection
from testbench_ai_service.llm.base import TokenUsage
from testbench_ai_service.models.prompt import Message
from tests.helpers.wheels import extracted

EXAMPLE = Path(__file__).resolve().parents[3] / "examples" / "ollama_llm_package"
MODULE = "ollama_llm"
ENTRY_POINTS = {"ollama": f"{MODULE}.client:OllamaLLMClient"}
MESSAGES = [Message(role="system", content="Be brief."), Message(role="user", content="Hi")]


def _package_files() -> dict[str, str | bytes]:
    files: dict[str, str | bytes] = {}
    for path in sorted((EXAMPLE / MODULE).rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            files[path.relative_to(EXAMPLE).as_posix()] = path.read_bytes()
    return files


def test_the_package_is_accepted(tmp_path):
    site = extracted(
        tmp_path,
        _package_files(),
        name="ollama-llm",
        entry_points={},
        llm_entry_points=ENTRY_POINTS,
    )
    report = run_inspection(site)
    assert report.ok is True, report
    assert report.llm_clients["ollama"].ok


def test_the_package_declares_the_entry_point_the_test_uses():
    pyproject = (EXAMPLE / "pyproject.toml").read_text(encoding="utf-8")
    assert '[project.entry-points."testbench_ai_service.llm_clients"]' in pyproject
    assert 'ollama = "ollama_llm.client:OllamaLLMClient"' in pyproject


@pytest.fixture
def client_module(monkeypatch):
    """The client module, loaded from the example folder under a private name."""
    for name in (
        "OLLAMA_HOST",
        "OLLAMA_API_KEY",
        "OLLAMA_NUM_CTX",
        "OLLAMA_KEEP_ALIVE",
        "OLLAMA_THINK",
    ):
        monkeypatch.delenv(name, raising=False)
    spec = importlib.util.spec_from_file_location(
        "_ollama_llm_client_under_test", EXAMPLE / MODULE / "client.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def _client(module, handler, **kwargs):
    return module.OllamaLLMClient(None, transport=httpx.MockTransport(handler), **kwargs)


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        (None, "http://localhost:11434"),
        ("", "http://localhost:11434"),
        ("gpu-box", "http://gpu-box:11434"),
        ("127.0.0.1:8080", "http://127.0.0.1:8080"),
        ("http://gpu-box:11434/", "http://gpu-box:11434"),
        ("https://ollama.example.com", "https://ollama.example.com"),
    ],
)
def test_base_url_reads_ollama_host_as_ollama_does(client_module, host, expected):
    assert client_module.base_url(host) == expected


async def test_sends_a_non_streaming_chat_request_and_returns_text_and_usage(
    client_module, monkeypatch
):
    monkeypatch.setenv("OLLAMA_HOST", "gpu-box")
    monkeypatch.setenv("OLLAMA_API_KEY", "secret")
    monkeypatch.setenv("OLLAMA_NUM_CTX", "16384")
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "10m")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": "Hello"},
                "prompt_eval_count": 12,
                "eval_count": 3,
            },
        )

    client = _client(client_module, handler, timeout=30, max_retries=2)
    result = await client.query_llm_with_usage("llama3.1:8b", MESSAGES)
    await client.close()

    assert result.text == "Hello"
    assert result.usage == TokenUsage(input_tokens=12, output_tokens=3)
    (request,) = seen
    assert str(request.url) == "http://gpu-box:11434/api/chat"
    assert request.headers["authorization"] == "Bearer secret"
    assert json.loads(request.content) == {
        "model": "llama3.1:8b",
        "messages": [
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": "Hi"},
        ],
        "stream": False,
        "options": {"num_ctx": 16384},
        "keep_alive": "10m",
    }


async def test_leaves_optional_settings_out_and_reports_no_usage_when_ollama_gives_none(
    client_module,
):
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": "Hello"}})

    client = _client(client_module, handler)
    assert await client.query_llm("llama3.1:8b", MESSAGES) == "Hello"
    result = await client.query_llm_with_usage("llama3.1:8b", MESSAGES)
    await client.close()

    assert result.usage is None
    assert set(bodies[0]) == {"model", "messages", "stream"}
    assert "authorization" not in {key.lower() for key in client.http.headers}


async def test_names_ollamas_reason_when_the_model_is_unknown(client_module):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model 'nope' not found"})

    client = _client(client_module, handler)
    with pytest.raises(client_module.OllamaError, match=r"404.*model 'nope' not found"):
        await client.query_llm("nope", MESSAGES)
    await client.close()


async def test_says_where_it_looked_when_ollama_is_not_running(client_module):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = _client(client_module, handler)
    with pytest.raises(
        client_module.OllamaError, match=r"Cannot reach Ollama at http://localhost:11434"
    ):
        await client.query_llm("llama3.1:8b", MESSAGES)
    await client.close()


async def test_refuses_an_answer_without_content(client_module):
    client = _client(client_module, lambda request: httpx.Response(200, json={"done": True}))
    with pytest.raises(client_module.OllamaError, match="no message content"):
        await client.query_llm("llama3.1:8b", MESSAGES)
    await client.close()


def test_refuses_a_context_size_that_is_not_a_number(client_module, monkeypatch):
    monkeypatch.setenv("OLLAMA_NUM_CTX", "big")
    with pytest.raises(client_module.OllamaError, match="OLLAMA_NUM_CTX"):
        client_module.OllamaLLMClient(None)


@pytest.mark.parametrize(
    ("setting", "expected"),
    [("false", False), ("TRUE", True), ("low", "low"), (" High ", "high")],
)
async def test_sends_the_think_setting(client_module, monkeypatch, setting, expected):
    monkeypatch.setenv("OLLAMA_THINK", setting)
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": "Hello"}})

    client = _client(client_module, handler)
    await client.query_llm("qwen3:8b", MESSAGES)
    await client.close()

    assert bodies[0]["think"] == expected


def test_refuses_an_unknown_think_setting(client_module, monkeypatch):
    monkeypatch.setenv("OLLAMA_THINK", "maybe")
    with pytest.raises(client_module.OllamaError, match="OLLAMA_THINK"):
        client_module.OllamaLLMClient(None)


async def test_names_the_cause_when_thinking_used_up_the_context(client_module):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": "", "thinking": "Let me see..."},
                "done_reason": "length",
            },
        )

    client = _client(client_module, handler)
    with pytest.raises(
        client_module.OllamaError, match=r"thinking.*OLLAMA_NUM_CTX.*OLLAMA_THINK=false"
    ):
        await client.query_llm("qwen3:8b", MESSAGES)
    await client.close()


async def test_passes_an_empty_answer_on_when_the_model_stopped_by_itself(client_module):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": ""}, "done_reason": "stop"})

    client = _client(client_module, handler)
    assert await client.query_llm("llama3.1:8b", MESSAGES) == ""
    await client.close()
