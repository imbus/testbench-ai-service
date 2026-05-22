import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests
import yaml
from pydantic import BaseModel, ValidationError

from testbench_ai_service.validators import (
    raise_field_validation_error,
    validate_custom_class_path,
    validate_file,
    validate_tb_server_url,
    validate_yaml_to_schema,
)


class _DummyModel(BaseModel):
    name: str
    age: int


class TestRaiseFieldValidationError:
    def test_produces_a_validation_error_for_the_named_field(self):
        model = _DummyModel(name="Alice", age=30)
        cause = ValueError("invalid value")

        with pytest.raises(ValidationError) as exc_info:
            raise_field_validation_error(model, "age", cause, error_type="value_error")

        errors = exc_info.value.errors()
        assert len(errors) == 1
        err = errors[0]
        assert err["type"] == "value_error"
        assert err["loc"] == ("age",)
        assert err["input"] == 30
        assert err["ctx"]["error"] is cause
        assert exc_info.value.__cause__ is cause

    def test_defaults_to_value_error_type(self):
        model = _DummyModel(name="Bob", age=25)
        cause = ValueError("oops")

        with pytest.raises(ValidationError) as exc_info:
            raise_field_validation_error(model, "name", cause)

        err = exc_info.value.errors()[0]
        assert err["type"] == "value_error"
        assert err["loc"] == ("name",)
        assert err["ctx"]["error"] is cause


class TestValidateCustomClassPath:
    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="'class_path' must be set"):
            validate_custom_class_path("")

    def test_path_without_dot_raises(self):
        with pytest.raises(ValueError, match="'class_path' must be a valid import path"):
            validate_custom_class_path("InvalidClassPath")

    @patch("testbench_ai_service.validators.importlib.import_module")
    def test_missing_module_raises(self, mock_import):
        mock_import.side_effect = ImportError("No module named foo")
        with pytest.raises(ValueError, match=r"cannot import 'Baz' from 'foo\.bar'"):
            validate_custom_class_path("foo.bar.Baz")

    @patch("testbench_ai_service.validators.importlib.import_module")
    def test_class_not_in_module_raises(self, mock_import):
        mock_module = MagicMock()
        del mock_module.MissingClass
        mock_import.return_value = mock_module
        with pytest.raises(ValueError, match=r"cannot import 'MissingClass' from 'some\.module'"):
            validate_custom_class_path("some.module.MissingClass")

    @patch("testbench_ai_service.validators.importlib.import_module")
    def test_valid_path_returns_the_path_string(self, mock_import):
        class _Fake:
            pass

        mock_module = MagicMock()
        mock_module.ExistingClass = _Fake
        mock_import.return_value = mock_module

        result = validate_custom_class_path("some.module.ExistingClass")
        assert result == "some.module.ExistingClass"


class TestValidateFile:
    def test_non_existent_path_raises(self):
        with pytest.raises(ValueError, match="File not found"):
            validate_file(Path("/non/existent/file.txt"))

    def test_directory_path_raises(self):
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            pytest.raises(ValueError, match="Path is not a file"),
        ):
            validate_file(Path(tmpdir))

    def test_empty_file_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "empty.txt"
            file_path.write_text("")
            with pytest.raises(ValueError, match="File is empty"):
                validate_file(file_path)

    def test_valid_file_returns_path_object(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "valid.txt"
            file_path.write_text("Hello, world!")
            result = validate_file(file_path)
            assert isinstance(result, Path)
            assert result.samefile(file_path)

    def test_string_path_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "string_path.txt"
            file_path.write_text("Some data")
            result = validate_file(str(file_path))
            assert isinstance(result, Path)
            assert result.samefile(file_path)


class TestValidateYamlToSchema:
    def _write_yaml(self, tmpdir: str, name: str, data) -> Path:
        path = Path(tmpdir) / name
        path.write_text(yaml.safe_dump(data))
        return path

    def test_valid_yaml_returns_path(self):
        valid_data = {
            "name": "Test Item",
            "description": "desc",
            "default_model": "ModelA",
            "default_variant": "default",
            "variants": [
                {
                    "name": "Variant 1",
                    "model": "ModelA",
                    "messages": [{"role": "user", "text": "Hi"}],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_yaml(tmpdir, "valid.yaml", valid_data)
            result = validate_yaml_to_schema(path)
            assert result.samefile(path)

    def test_malformed_yaml_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad.yaml"
            path.write_text("name: Alice\nage: [30")
            with pytest.raises(ValueError, match="YAML parsing error"):
                validate_yaml_to_schema(path)

    def test_yaml_failing_schema_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_yaml(tmpdir, "invalid.yaml", {"name": "Alice"})
            with pytest.raises(ValueError, match="Schema validation error"):
                validate_yaml_to_schema(path)


class TestValidateTbServerUrl:
    @patch("testbench_ai_service.validators.requests.get")
    def test_accessible_server_passes(self, mock_get):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        validate_tb_server_url("https://testserver.example.com")

        mock_get.assert_called_once_with(
            "https://testserver.example.com/2/serverVersions",
            timeout=5,
            verify=False,
        )

    @patch("testbench_ai_service.validators.requests.get")
    def test_http_error_from_server_raises(self, mock_get):
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Client Error")
        mock_get.return_value = mock_response

        with pytest.raises(ValueError, match="Unable to connect to the server"):
            validate_tb_server_url("https://testserver.example.com")

    @patch("testbench_ai_service.validators.requests.get")
    def test_connection_error_raises(self, mock_get):
        mock_get.side_effect = requests.ConnectionError("Failed to connect")

        with pytest.raises(ValueError, match="Unable to connect to the server"):
            validate_tb_server_url("https://testserver.example.com")
