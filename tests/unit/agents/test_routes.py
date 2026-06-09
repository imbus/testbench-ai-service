import json as _json
import tempfile
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from testbench2robotframework.json_reader import TestBenchJsonReader

from testbench_ai_service.auth import AuthInfo, AuthType, validate_auth_token
from testbench_ai_service.config import AppConfig
from testbench_ai_service.dependencies import get_app_config, get_llm_factory, get_tb_connection
from testbench_ai_service.main import create_app
from testbench_ai_service.models.agent import (
    ExecutionContext,
    PrecheckResult,
    TriggerAgentRequest,
)
from testbench_ai_service.models.config import ProjectAgentConfig, ProjectConfig
from testbench_ai_service.models.testbench import ProjectMember, ProjectRole
from tests.unit.helpers.data import get_test_data_path


def _make_auth_info():
    return AuthInfo(
        auth_type=AuthType.SESSION_TOKEN, token="test-token", user_key="1", conn=MagicMock()
    )


def _make_app_config():
    with patch("testbench_ai_service.config.validate_tb_server_url"):
        return AppConfig(tb_server_url="https://localhost:9443/api/")


class TestTriggerTestCaseSetReviews:
    mock_tb_connection: MagicMock
    """HTTP-level tests for POST /test-case-set-reviews."""

    @pytest.fixture(autouse=True, scope="class")
    def class_setup(self, request):
        app_config = _make_app_config()
        with patch("testbench_ai_service.main.LLMFactory") as mock_factory_cls:
            mock_factory = MagicMock()
            mock_factory.init_clients = MagicMock()
            mock_factory.close_clients = AsyncMock()
            mock_factory_cls.return_value = mock_factory
            app = create_app(app_config)
        client = TestClient(app)
        client.__enter__()

        mock_tb_connection = MagicMock()
        mock_tb_connection.server_url = app_config.tb_server_url
        mock_llm_factory = MagicMock()

        app.dependency_overrides[validate_auth_token] = _make_auth_info
        app.dependency_overrides[get_tb_connection] = lambda: mock_tb_connection
        app.dependency_overrides[get_llm_factory] = lambda: mock_llm_factory

        request.cls.app_config = app_config
        request.cls.app = app
        request.cls.client = client
        request.cls.mock_tb_connection = mock_tb_connection
        request.cls.mock_llm_factory = mock_llm_factory

        yield

        app.dependency_overrides.clear()
        client.__exit__(None, None, None)

    @pytest.fixture(autouse=True)
    def method_setup(self):
        self.mock_tb_connection.session.get.side_effect = self._tb_session_get_side_effect
        self.mock_tb_connection.session.post.side_effect = self._tb_session_post_side_effect
        self.mock_tb_connection.get_project_key_new_play.side_effect = (
            self._tb_get_project_key_side_effect
        )
        self.mock_tb_connection.get_tov_key_new_play.side_effect = self._tb_get_tov_key_side_effect
        self.mock_tb_connection.get_cycle_key_new_play.side_effect = (
            self._tb_get_cycle_key_side_effect
        )

        self.user_key = "1"
        self.project_key = "1"
        self.tov_key = "2"
        self.cycle_key = "3"
        self.project_name = "Car Configurator"

        self.mock_tb_connection.get_project.return_value = {"name": self.project_name}

        reviewer_patcher = patch(
            "testbench_ai_service.agents.test_case_set_reviewer.agent.TestCaseSetReviewer"
        )
        self.mock_reviewer_class = reviewer_patcher.start()
        self.mock_reviewer = AsyncMock()
        self.mock_reviewer.precheck.return_value = PrecheckResult(passed=True)
        self.mock_reviewer_class.__name__ = "TestCaseSetReviewer"
        self.mock_reviewer_class.return_value = self.mock_reviewer

        self.valid_request = TriggerAgentRequest(
            project_key=self.project_key,
            tov_key=self.tov_key,
            cycle_key=self.cycle_key,
            root_uid="iTB-TT-4091",
            language="de",
        )

        self.global_roles: list = []
        self.project_roles: list = [ProjectRole.TestDesigner]

        with tempfile.TemporaryDirectory() as report_dir:
            report_zip = zipfile.ZipFile(get_test_data_path("cycle_report.zip"))
            report_zip.extractall(report_dir)
            reader = TestBenchJsonReader(report_dir)
            tcs_catalog = reader.get_test_case_set_catalog()
            self.test_case_sets = list(tcs_catalog.values())

        yield

        reviewer_patcher.stop()

    # ── Happy path ────────────────────────────────────────────────────────────

    def test_valid_request_returns_202_accepted(self):
        payload = self.valid_request.model_dump()
        with patch("fastapi.BackgroundTasks.add_task") as mock_add_task:
            response = self.client.post("/test-case-set-reviews", json=payload)

        assert response.status_code == 202
        assert response.json() == {"status": "accepted", "warnings": []}
        mock_add_task.assert_called_once()
        call_kwargs = mock_add_task.call_args.kwargs
        assert call_kwargs["agent"] is self.mock_reviewer
        assert call_kwargs["conn"] is self.mock_tb_connection
        assert call_kwargs["llm_factory"] is self.mock_llm_factory
        assert isinstance(call_kwargs["context"], ExecutionContext)

    # ── Payload validation ────────────────────────────────────────────────────

    def test_empty_payload_returns_422(self):
        assert self.client.post("/test-case-set-reviews", json={}).status_code == 422

    def test_missing_required_field_returns_422(self):
        payload = {"tov_key": "V1.0", "root_uid": "UID"}
        assert self.client.post("/test-case-set-reviews", json=payload).status_code == 422

    def test_wrong_field_type_returns_422(self):
        payload = {"project_key": True, "tov_key": "V1.0", "root_uid": "UID"}
        assert self.client.post("/test-case-set-reviews", json=payload).status_code == 422

    # ── Authentication ────────────────────────────────────────────────────────

    def test_missing_auth_token_returns_401(self):
        self.app.dependency_overrides.pop(validate_auth_token, None)
        try:
            response = self.client.post(
                "/test-case-set-reviews", json={"project_key": "P", "tov_key": "T", "root_uid": "R"}
            )
            assert response.status_code == 401
        finally:
            self.app.dependency_overrides[validate_auth_token] = _make_auth_info

    def test_invalid_auth_token_returns_401(self):
        self.app.dependency_overrides.pop(validate_auth_token, None)
        try:
            with patch("testbench_ai_service.auth._validate_token") as mock_validate:
                mock_validate.side_effect = HTTPException(
                    status_code=401, detail="Invalid authorization token"
                )
                response = self.client.post(
                    "/test-case-set-reviews",
                    json={"project_key": "P", "tov_key": "T", "root_uid": "R"},
                    headers={"Authorization": "INVALID"},
                )
            assert response.status_code == 401
        finally:
            self.app.dependency_overrides[validate_auth_token] = _make_auth_info

    # ── Feature flags ─────────────────────────────────────────────────────────

    def test_globally_disabled_feature_returns_404(self):
        config = self.app_config.model_copy(deep=True)
        config.agents["test_case_set_reviewer"].enabled = False
        self.app.dependency_overrides[get_app_config] = lambda: config
        try:
            response = self.client.post(
                "/test-case-set-reviews", json=self.valid_request.model_dump()
            )
            assert response.status_code == 404
        finally:
            self.app.dependency_overrides.pop(get_app_config, None)

    def test_per_project_disabled_feature_returns_404(self):
        config = self.app_config.model_copy(deep=True)
        config.projects[self.project_name] = ProjectConfig(
            agents={"test_case_set_reviewer": ProjectAgentConfig(enabled=False)}
        )
        self.app.dependency_overrides[get_app_config] = lambda: config
        try:
            response = self.client.post(
                "/test-case-set-reviews", json=self.valid_request.model_dump()
            )
            assert response.status_code == 404
        finally:
            self.app.dependency_overrides.pop(get_app_config, None)

    # ── Authorisation ─────────────────────────────────────────────────────────

    def test_insufficient_role_fails_precheck_and_returns_409(self):
        self.project_roles = []
        self.mock_reviewer.precheck = AsyncMock(
            return_value=PrecheckResult(passed=False, warnings=["Insufficient role"])
        )
        response = self.client.post("/test-case-set-reviews", json=self.valid_request.model_dump())
        assert response.status_code == 409  # precheck failed → 409 Conflict

    def test_read_only_role_fails_precheck_and_returns_409(self):
        self.project_roles = [ProjectRole.ReadOnlyDesigner]
        self.mock_reviewer.precheck = AsyncMock(
            return_value=PrecheckResult(passed=False, warnings=["Insufficient role"])
        )
        response = self.client.post("/test-case-set-reviews", json=self.valid_request.model_dump())
        assert response.status_code == 409  # precheck failed → 409 Conflict

    def test_precheck_lock_lookup_http_403_returns_403(self):
        self.mock_reviewer.precheck = AsyncMock(
            side_effect=HTTPException(status_code=403, detail="Forbidden")
        )
        response = self.client.post("/test-case-set-reviews", json=self.valid_request.model_dump())
        assert response.status_code == 403
        assert response.json() == {"detail": "Forbidden"}

    # ── Side-effect helpers ───────────────────────────────────────────────────

    def _tb_session_get_side_effect(self, url: str):
        base = self.mock_tb_connection.server_url
        if url == f"{base}2/login/session":
            r = MagicMock()
            r.json.return_value = {"userKey": self.user_key}
            return r
        if url == f"{base}2/users/self/globalRoles":
            r = MagicMock()
            r.json.return_value = self.global_roles
            return r
        if url == f"{base}2/users/self/projectRoles":
            r = MagicMock()
            r.json.return_value = [
                ProjectMember(
                    userKey=self.user_key,
                    userLogin="",
                    userName="",
                    projectKey=self.project_key,
                    projectName=self.project_name,
                    roles=self.project_roles,
                ).model_dump()
            ]
            return r
        return None

    def _tb_get_project_key_side_effect(self, project_name: str):
        return self.project_key if project_name == self.valid_request.project_name else None

    def _tb_get_tov_key_side_effect(self, project_key: str, tov_name: str):
        if project_key == self.project_key and tov_name == self.valid_request.tov_name:
            return self.tov_key
        return None

    def _tb_get_cycle_key_side_effect(self, project_key: str, tov_key: str, cycle_name: str):
        if (
            project_key == self.project_key
            and tov_key == self.tov_key
            and cycle_name == self.valid_request.cycle_name
        ):
            return self.cycle_key
        return None

    def _tb_session_post_side_effect(self, url: str, json: dict):
        base = self.mock_tb_connection.server_url
        structure_url = f"{base}2/projects/{self.project_key}/cycles/{self.cycle_key}/structure"
        if url == structure_url and json["treeRootUID"] == self.valid_request.root_uid:
            with (
                zipfile.ZipFile(get_test_data_path("cycle_report.zip"), "r") as zf,
                zf.open("cycle_structure.json") as f,
            ):
                structure = _json.load(f)
            r = MagicMock()
            r.json.return_value = structure
            return r
        return None
