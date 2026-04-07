import json as _json
import tempfile
import unittest
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

import requests
from fastapi.testclient import TestClient
from testbench2robotframework.json_reader import TestBenchJsonReader

from testbench_ai_service.auth import validate_session_token
from testbench_ai_service.config import AppConfig, ProjectConfig, ProjectUseCaseConfig
from testbench_ai_service.dependencies import get_app_config, get_llm_factory, get_tb_connection
from testbench_ai_service.main import create_app
from testbench_ai_service.models.testbench import ProjectMember, ProjectRole
from testbench_ai_service.models.usecase import (
    ExecutionContext,
    PrecheckResult,
    TriggerUseCaseRequest,
)
from tests.unit.helpers.data import get_test_data_path


class TestTriggerTestCaseSetReviews(unittest.TestCase):
    """HTTP-level tests for POST /test-case-set-reviews.

    Uses FastAPI TestClient with dependency overrides to exercise the router
    without a live TestBench or LLM connection.
    """

    @classmethod
    def setUpClass(cls):
        cls.app_config = AppConfig(tb_server_url="https://localhost:9443/api/")
        cls.app = create_app(cls.app_config)
        cls.client = TestClient(cls.app)
        cls.client.__enter__()

        cls.mock_validate_token = MagicMock()
        cls.mock_tb_connection = MagicMock()
        cls.mock_tb_connection.server_url = cls.app_config.tb_server_url
        cls.mock_llm_factory = MagicMock()

        cls.app.dependency_overrides[validate_session_token] = lambda: cls.mock_validate_token
        cls.app.dependency_overrides[get_tb_connection] = lambda: cls.mock_tb_connection
        cls.app.dependency_overrides[get_llm_factory] = lambda: cls.mock_llm_factory

    @classmethod
    def tearDownClass(cls):
        cls.app.dependency_overrides.clear()
        cls.client.__exit__(None, None, None)

    def setUp(self):
        # Configure TB connection side effects
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

        # Patch the reviewer so no real AI calls are made
        self.reviewer_patcher = patch(
            "testbench_ai_service.usecases.test_case_set_reviews.service.TestCaseSetReviewer"
        )
        self.mock_reviewer_class = self.reviewer_patcher.start()
        self.mock_reviewer = AsyncMock()
        self.mock_reviewer.precheck.return_value = PrecheckResult(passed=True)
        self.mock_reviewer_class.__name__ = "TestCaseSetReviewer"
        self.mock_reviewer_class.return_value = self.mock_reviewer

        # Default valid request payload
        self.valid_request = TriggerUseCaseRequest(
            project_key=self.project_key,
            tov_key=self.tov_key,
            cycle_key=self.cycle_key,
            root_uid="iTB-TT-4091",
            language="de",
        )

        self.global_roles: list = []
        self.project_roles: list = [ProjectRole.TestDesigner]

        # Preload test case sets
        with tempfile.TemporaryDirectory() as report_dir:
            report_zip = zipfile.ZipFile(get_test_data_path("cycle_report.zip"))
            report_zip.extractall(report_dir)
            reader = TestBenchJsonReader(report_dir)
            tcs_catalog = reader.get_test_case_set_catalog()
            self.test_case_sets = list(tcs_catalog.values())

    def tearDown(self):
        self.reviewer_patcher.stop()

    # ── Happy path ────────────────────────────────────────────────────────────

    def test_valid_request_returns_202_accepted(self):
        payload = self.valid_request.model_dump()
        with patch("fastapi.BackgroundTasks.add_task") as mock_add_task:
            response = self.client.post("/test-case-set-reviews", json=payload)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"status": "accepted", "warnings": []})
        mock_add_task.assert_called_once()
        call_kwargs = mock_add_task.call_args.kwargs
        self.assertIs(call_kwargs["usecase_service"], self.mock_reviewer)
        self.assertIs(call_kwargs["conn"], self.mock_tb_connection)
        self.assertIs(call_kwargs["llm_factory"], self.mock_llm_factory)
        self.assertIsInstance(call_kwargs["context"], ExecutionContext)

    # ── Payload validation ────────────────────────────────────────────────────

    def test_empty_payload_returns_422(self):
        self.assertEqual(self.client.post("/test-case-set-reviews", json={}).status_code, 422)

    def test_missing_required_field_returns_422(self):
        payload = {"tov_key": "V1.0", "root_uid": "UID"}
        self.assertEqual(self.client.post("/test-case-set-reviews", json=payload).status_code, 422)

    def test_wrong_field_type_returns_422(self):
        payload = {"project_key": True, "tov_key": "V1.0", "root_uid": "UID"}
        self.assertEqual(self.client.post("/test-case-set-reviews", json=payload).status_code, 422)

    # ── Authentication ────────────────────────────────────────────────────────

    def test_missing_auth_token_returns_401(self):
        self.app.dependency_overrides.pop(validate_session_token, None)
        try:
            response = self.client.post(
                "/test-case-set-reviews", json={"project_key": "P", "tov_key": "T", "root_uid": "R"}
            )
            self.assertEqual(response.status_code, 401)
        finally:
            self.app.dependency_overrides[validate_session_token] = lambda: self.mock_validate_token

    def test_invalid_auth_token_returns_401(self):
        self.app.dependency_overrides.pop(validate_session_token, None)
        try:
            with patch("testbench_ai_service.auth.TBConnection") as MockConn:
                mock_conn = MockConn.return_value
                mock_response = MagicMock()
                mock_response.status_code = 401
                mock_conn.check_is_working.side_effect = requests.exceptions.HTTPError(
                    "Invalid token", response=mock_response
                )
                response = self.client.post(
                    "/test-case-set-reviews",
                    json={"project_key": "P", "tov_key": "T", "root_uid": "R"},
                    headers={"Authorization": "INVALID"},
                )
            self.assertEqual(response.status_code, 401)
        finally:
            self.app.dependency_overrides[validate_session_token] = lambda: self.mock_validate_token

    # ── Feature flags ─────────────────────────────────────────────────────────

    def test_globally_disabled_feature_returns_404(self):
        config = self.app_config.model_copy(deep=True)
        config.usecases["test_case_set_reviews"].enabled = False
        self.app.dependency_overrides[get_app_config] = lambda: config
        try:
            response = self.client.post(
                "/test-case-set-reviews", json=self.valid_request.model_dump()
            )
            self.assertEqual(response.status_code, 404)
        finally:
            self.app.dependency_overrides.pop(get_app_config)

    def test_per_project_disabled_feature_returns_404(self):
        config = self.app_config.model_copy(deep=True)
        config.projects[self.project_name] = ProjectConfig(
            usecases={"test_case_set_reviews": ProjectUseCaseConfig(enabled=False)}
        )
        self.app.dependency_overrides[get_app_config] = lambda: config
        try:
            response = self.client.post(
                "/test-case-set-reviews", json=self.valid_request.model_dump()
            )
            self.assertEqual(response.status_code, 404)
        finally:
            self.app.dependency_overrides.pop(get_app_config, None)

    # ── Authorisation ─────────────────────────────────────────────────────────

    def test_user_without_required_role_returns_403(self):
        self.project_roles = []
        response = self.client.post("/test-case-set-reviews", json=self.valid_request.model_dump())
        self.assertEqual(response.status_code, 403)

    def test_user_with_read_only_role_returns_403(self):
        self.project_roles = [ProjectRole.ReadOnlyDesigner]
        response = self.client.post("/test-case-set-reviews", json=self.valid_request.model_dump())
        self.assertEqual(response.status_code, 403)

    # ── Side-effect helpers ───────────────────────────────────────────────────

    def _tb_session_get_side_effect(self, url: str):
        base = self.mock_tb_connection.server_url  # type: ignore[attr-defined]
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
        base = self.mock_tb_connection.server_url  # type: ignore[attr-defined]
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


if __name__ == "__main__":
    unittest.main()
