import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

MESSAGE = {"role": "user", "source": "inline", "file": None, "content": "Hallo {{ vars.name }}"}


def csrf(client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["tbai_admin_csrf"]}


def body(**overrides) -> dict:
    payload = {
        "messages": [MESSAGE],
        "vars": {"name": "Welt"},
        "agent_context": {},
        "model": "claude-opus-5",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def fake_client(app):
    """Install a fake LLM client and return it."""
    client = MagicMock()
    client.query_llm = AsyncMock(return_value="the answer")
    app.state.llm_factory.get_client = MagicMock(return_value=client)
    app.state.llm_factory.has_project_credential = MagicMock(return_value=False)
    return client


class TestGates:
    def test_a_non_admin_is_refused(self, client, login):
        login(roles=[])
        response = client.post("/admin/api/prompts/test", json=body(), headers=csrf(client))
        assert response.status_code == 403

    def test_missing_csrf_is_refused(self, client, login):
        login(roles=["Administrator"])
        assert client.post("/admin/api/prompts/test", json=body()).status_code == 403


class TestHappyPath:
    def test_returns_the_text_and_a_latency(self, client, login, fake_client):
        login(roles=["Administrator"])
        response = client.post("/admin/api/prompts/test", json=body(), headers=csrf(client))
        assert response.status_code == 200
        payload = response.json()
        assert payload["text"] == "the answer"
        assert payload["latency_ms"] >= 0

    def test_sends_the_rendered_draft_not_the_raw_template(self, client, login, fake_client):
        login(roles=["Administrator"])
        client.post("/admin/api/prompts/test", json=body(), headers=csrf(client))
        sent = fake_client.query_llm.await_args.kwargs["messages"]
        assert sent[0].content == "Hallo Welt"

    def test_lets_the_factory_resolve_the_provider(self, client, login, app, fake_client):
        login(roles=["Administrator"])
        client.post("/admin/api/prompts/test", json=body(), headers=csrf(client))
        kwargs = app.state.llm_factory.get_client.call_args.kwargs
        assert kwargs["prompt_model"] == "claude-opus-5"

    def test_reports_global_credential_scope_by_default(self, client, login, fake_client):
        login(roles=["Administrator"])
        response = client.post("/admin/api/prompts/test", json=body(), headers=csrf(client))
        assert response.json()["resolved"]["credential_scope"] == "global"

    def test_reports_project_scope_when_a_project_key_exists(self, client, login, app, fake_client):
        app.state.llm_factory.has_project_credential = MagicMock(return_value=True)
        login(roles=["Administrator"])
        response = client.post(
            "/admin/api/prompts/test",
            json=body(project="Car Configurator"),
            headers=csrf(client),
        )
        assert response.json()["resolved"]["credential_scope"] == "project"


class TestMoneySafety:
    def test_a_render_failure_creates_no_client(self, client, login, app, fake_client):
        # The money-safety property, asserted against the factory rather than
        # the status code: a broken template must cost nothing (design 5.5).
        login(roles=["Administrator"])
        broken = dict(MESSAGE, content="{% if %}")
        response = client.post(
            "/admin/api/prompts/test", json=body(messages=[broken]), headers=csrf(client)
        )
        assert response.status_code == 400
        app.state.llm_factory.get_client.assert_not_called()

    def test_an_undefined_variable_is_a_render_failure(self, client, login, app, fake_client):
        login(roles=["Administrator"])
        response = client.post("/admin/api/prompts/test", json=body(vars={}), headers=csrf(client))
        assert response.status_code == 400
        app.state.llm_factory.get_client.assert_not_called()


class TestProductionResolution:
    def test_a_partial_project_override_merges_rather_than_replaces(self, make_app, tb_connection):
        """The regression test D3 exists to prevent.

        get_llm_config merges the project block onto the global one with
        exclude_unset=True, so a project overriding only `model` keeps the
        global timeout and max_retries. A console that read
        config.projects[...].llm_config directly would REPLACE, and the test
        run would resolve differently from the agent it is meant to predict --
        silently, and only for projects with partial overrides. This fails
        loudly if the route ever stops calling get_llm_config.

        Builds its own app because the shared `client` fixture has no projects
        table to override.
        """
        app = make_app(
            llm_config={"provider": "anthropic", "timeout": 42.0, "max_retries": 7},
            projects={"Car Configurator": {"llm_config": {"model": "claude-sonnet-5"}}},
        )
        fake = MagicMock()
        fake.query_llm = AsyncMock(return_value="ok")
        app.state.llm_factory.get_client = MagicMock(return_value=fake)
        app.state.llm_factory.has_project_credential = MagicMock(return_value=False)

        with TestClient(app, raise_server_exceptions=False) as scoped:
            with patch("testbench_ai_service.webui.auth.TBConnection", return_value=tb_connection):
                scoped.post("/admin/api/session", json={"username": "a", "password": "p"})
            scoped.post(
                "/admin/api/prompts/test",
                json=body(project="Car Configurator"),
                headers={"X-CSRF-Token": scoped.cookies["tbai_admin_csrf"]},
            )

        resolved = app.state.llm_factory.get_client.call_args.kwargs["config"]
        assert resolved.model == "claude-sonnet-5"  # the project's own override
        assert resolved.timeout == 42.0  # inherited, not dropped
        assert resolved.max_retries == 7  # inherited, not dropped

    def test_the_factory_resolves_the_provider_from_the_model_name(
        self, client, login, app, fake_client
    ):
        # Provider resolution stays in _resolve_provider (design D3): the
        # console never branches on a model prefix itself.
        login(roles=["Administrator"])
        response = client.post("/admin/api/prompts/test", json=body(), headers=csrf(client))
        assert response.json()["resolved"]["provider"] == "anthropic"

    def test_a_gpt_model_resolves_to_openai(self, client, login, app, fake_client):
        login(roles=["Administrator"])
        response = client.post(
            "/admin/api/prompts/test", json=body(model="gpt-4o"), headers=csrf(client)
        )
        assert response.json()["resolved"]["provider"] == "openai"

    def test_the_run_is_counted_while_in_flight(self, client, login, app, fake_client):
        """Design D6: the reload path's in-flight count must include a test run.

        Captured from inside query_llm, because the count is back to zero by
        the time the response is returned -- which is exactly the property
        TaskRegistry.track's finally guarantees.
        """
        seen = []

        async def counting_query(model, messages, **kwargs):
            seen.append(app.state.task_registry.labels())
            return "ok"

        fake_client.query_llm = AsyncMock(side_effect=counting_query)
        login(roles=["Administrator"])

        client.post("/admin/api/prompts/test", json=body(), headers=csrf(client))

        assert seen == [["prompt-test"]]
        assert app.state.task_registry.count == 0


class TestSingleFlightOverTheWire:
    async def test_a_second_concurrent_run_for_one_session_is_refused(self, app, tb_connection):
        """Two genuinely overlapping requests: the second is refused with 409.

        Uses httpx.ASGITransport rather than TestClient. TestClient drives the
        app on a single shared event loop, so a request held open by a
        synchronous wait starves that loop and the "concurrent" request never
        starts -- it would pass or fail for reasons unrelated to SingleFlight.
        asyncio.Event + create_task produces real overlap.
        """
        gate = asyncio.Event()

        async def slow_query(model, messages, **kwargs):
            await gate.wait()  # holds the first request open, yields the loop
            return "answer"

        fake = MagicMock()
        fake.query_llm = AsyncMock(side_effect=slow_query)
        app.state.llm_factory.get_client = MagicMock(return_value=fake)
        app.state.llm_factory.has_project_credential = MagicMock(return_value=False)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            with patch("testbench_ai_service.webui.auth.TBConnection", return_value=tb_connection):
                signed_in = await client.post(
                    "/admin/api/session", json={"username": "a", "password": "p"}
                )
            assert signed_in.status_code == 200
            headers = {"X-CSRF-Token": client.cookies["tbai_admin_csrf"]}

            first = asyncio.create_task(
                client.post("/admin/api/prompts/test", json=body(), headers=headers)
            )
            await asyncio.sleep(0.2)  # let the first request reach query_llm
            second = await client.post("/admin/api/prompts/test", json=body(), headers=headers)
            gate.set()
            first_response = await first

        assert first_response.status_code == 200
        assert second.status_code == 409


class TestFailures:
    def test_a_provider_error_is_a_502(self, client, login, app, fake_client):
        fake_client.query_llm = AsyncMock(side_effect=RuntimeError("404 model not found"))
        login(roles=["Administrator"])
        response = client.post("/admin/api/prompts/test", json=body(), headers=csrf(client))
        assert response.status_code == 502
        assert "model not found" in response.text

    def test_a_provider_error_never_echoes_the_credential(
        self, client, login, app, fake_client, monkeypatch
    ):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret-value")
        fake_client.query_llm = AsyncMock(side_effect=RuntimeError("401 bad key sk-secret-value"))
        login(roles=["Administrator"])
        response = client.post("/admin/api/prompts/test", json=body(), headers=csrf(client))
        assert response.status_code == 502
        assert "sk-secret-value" not in response.text
        assert "***" in response.text

    def test_a_missing_credential_is_a_400_naming_the_variable(
        self, client, login, app, fake_client
    ):
        app.state.llm_factory.get_client = MagicMock(
            side_effect=ValueError(
                "API key for provider 'anthropic' not found in environment variables."
            )
        )
        login(roles=["Administrator"])
        response = client.post("/admin/api/prompts/test", json=body(), headers=csrf(client))
        assert response.status_code == 400
        assert "anthropic" in response.text

    def test_the_400_from_get_client_is_scrubbed_too(
        self, client, login, app, fake_client, monkeypatch
    ):
        """The 400 is a provider-sourced string like the 502, and D9 covers both.

        It used to be built from `str(e)` computed BEFORE `secrets`, so it was
        the one message on this route that reached the operator unmasked.
        """
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret-value")
        app.state.llm_factory.get_client = MagicMock(
            side_effect=ValueError("credential 'sk-secret-value' was rejected")
        )
        login(roles=["Administrator"])
        response = client.post("/admin/api/prompts/test", json=body(), headers=csrf(client))
        assert response.status_code == 400
        assert "sk-secret-value" not in response.text
        assert "***" in response.text


class TestEntraIdSuppression:
    """Design 6/9: the Entra ID path has no credential string to scrub.

    `resolve_entra_credentials` yields a credential OBJECT, so
    `_credential_values` finds nothing for AZURE_OPENAI + ENTRA_ID and
    `scrub_all` would hand the provider's message back verbatim -- the exact
    disclosure D9 exists to prevent. That path returns the exception type and a
    pointer to the log instead.
    """

    def _azure_app(self, make_app, auth_method: str):
        return make_app(
            llm_config={
                "provider": "azure_openai",
                "auth_method": auth_method,
                "azure_endpoint": "https://example.openai.azure.com/",
                "api_version": "2024-02-01",
            }
        )

    def _run(self, app, tb_connection, message: str):
        fake = MagicMock()
        fake.query_llm = AsyncMock(side_effect=RuntimeError(message))
        app.state.llm_factory.get_client = MagicMock(return_value=fake)
        app.state.llm_factory.has_project_credential = MagicMock(return_value=False)

        with TestClient(app, raise_server_exceptions=False) as scoped:
            with patch("testbench_ai_service.webui.auth.TBConnection", return_value=tb_connection):
                scoped.post("/admin/api/session", json={"username": "a", "password": "p"})
            return scoped.post(
                "/admin/api/prompts/test",
                json=body(model="gpt-4o"),
                headers={"X-CSRF-Token": scoped.cookies["tbai_admin_csrf"]},
            )

    def test_the_provider_message_is_suppressed(self, make_app, tb_connection):
        app = self._azure_app(make_app, "entra_id")
        response = self._run(app, tb_connection, "401 token https://x/?sig=leaked-token")

        assert response.status_code == 502
        # The type is still reported -- the operator needs to know WHAT failed.
        assert "RuntimeError" in response.text
        # The message is not, in any part.
        assert "leaked-token" not in response.text
        assert "sig=" not in response.text
        assert "401" not in response.text
        assert "log" in response.text.lower()

    def test_the_api_key_path_still_reports_the_message(self, make_app, tb_connection):
        # The suppression is narrow: only the path with no string to scrub.
        app = self._azure_app(make_app, "api_key")
        response = self._run(app, tb_connection, "404 deployment not found")

        assert response.status_code == 502
        assert "deployment not found" in response.text
