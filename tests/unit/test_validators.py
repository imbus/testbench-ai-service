import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import requests
import yaml
from pydantic import BaseModel, ValidationError

from testbench_ai_service.validators import (
    raise_field_validation_error,
    validate_custom_class_path,
    validate_file,
    validate_tb_server_url,
    validate_value_in_yaml,
    validate_yaml_to_schema,
)


class _DummyModel(BaseModel):
    name: str
    age: int


class TestRaiseFieldValidationError(unittest.TestCase):
    """raise_field_validation_error wraps a ValueError in a pydantic ValidationError."""

    def test_produces_a_validation_error_for_the_named_field(self):
        model = _DummyModel(name="Alice", age=30)
        cause = ValueError("invalid value")

        with self.assertRaises(ValidationError) as ctx:
            raise_field_validation_error(model, "age", cause, error_type="value_error")

        errors = ctx.exception.errors()
        self.assertEqual(len(errors), 1)
        err = errors[0]
        self.assertEqual(err["type"], "value_error")
        self.assertEqual(err["loc"], ("age",))
        self.assertEqual(err["input"], 30)
        self.assertIs(err["ctx"]["error"], cause)
        self.assertIs(ctx.exception.__cause__, cause)

    def test_defaults_to_value_error_type(self):
        model = _DummyModel(name="Bob", age=25)
        cause = ValueError("oops")

        with self.assertRaises(ValidationError) as ctx:
            raise_field_validation_error(model, "name", cause)

        err = ctx.exception.errors()[0]
        self.assertEqual(err["type"], "value_error")
        self.assertEqual(err["loc"], ("name",))
        self.assertIs(err["ctx"]["error"], cause)


class TestValidateCustomClassPath(unittest.TestCase):
    """validate_custom_class_path ensures the path is importable and the class exists."""

    def test_empty_string_raises(self):
        with self.assertRaises(ValueError) as ctx:
            validate_custom_class_path("")
        self.assertIn("'class_path' must be set", str(ctx.exception))

    def test_path_without_dot_raises(self):
        with self.assertRaises(ValueError) as ctx:
            validate_custom_class_path("InvalidClassPath")
        self.assertIn("'class_path' must be a valid import path", str(ctx.exception))

    @patch("testbench_ai_service.validators.importlib.import_module")
    def test_missing_module_raises(self, mock_import):
        mock_import.side_effect = ImportError("No module named foo")
        with self.assertRaises(ValueError) as ctx:
            validate_custom_class_path("foo.bar.Baz")
        self.assertIn("cannot import 'Baz' from 'foo.bar'", str(ctx.exception))

    @patch("testbench_ai_service.validators.importlib.import_module")
    def test_class_not_in_module_raises(self, mock_import):
        mock_module = MagicMock()
        del mock_module.MissingClass
        mock_import.return_value = mock_module
        with self.assertRaises(ValueError) as ctx:
            validate_custom_class_path("some.module.MissingClass")
        self.assertIn("cannot import 'MissingClass' from 'some.module'", str(ctx.exception))

    @patch("testbench_ai_service.validators.importlib.import_module")
    def test_valid_path_returns_the_path_string(self, mock_import):
        class _Fake:
            pass

        mock_module = MagicMock()
        mock_module.ExistingClass = _Fake
        mock_import.return_value = mock_module

        result = validate_custom_class_path("some.module.ExistingClass")
        self.assertEqual(result, "some.module.ExistingClass")


class TestValidateFile(unittest.TestCase):
    """validate_file rejects non-existent, non-file, and empty paths."""

    def test_non_existent_path_raises(self):
        with self.assertRaises(ValueError) as ctx:
            validate_file(Path("/non/existent/file.txt"))
        self.assertIn("File not found", str(ctx.exception))

    def test_directory_path_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError) as ctx:
                validate_file(Path(tmpdir))
            self.assertIn("Path is not a file", str(ctx.exception))

    def test_empty_file_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "empty.txt"
            file_path.write_text("")
            with self.assertRaises(ValueError) as ctx:
                validate_file(file_path)
            self.assertIn("File is empty", str(ctx.exception))

    def test_valid_file_returns_path_object(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "valid.txt"
            file_path.write_text("Hello, world!")
            result = validate_file(file_path)
            self.assertIsInstance(result, Path)
            self.assertTrue(result.samefile(file_path))

    def test_string_path_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "string_path.txt"
            file_path.write_text("Some data")
            result = validate_file(str(file_path))
            self.assertIsInstance(result, Path)
            self.assertTrue(result.samefile(file_path))


class TestValidateYamlToSchema(unittest.TestCase):
    """validate_yaml_to_schema parses YAML and validates it against the prompt schema."""

    def _write_yaml(self, tmpdir: str, name: str, data) -> Path:
        path = Path(tmpdir) / name
        path.write_text(yaml.safe_dump(data))
        return path

    def test_valid_yaml_returns_path(self):
        valid_data = [
            {
                "name": "Test Item",
                "description": "desc",
                "default_variant": "default",
                "variants": [
                    {
                        "name": "Variant 1",
                        "model": "ModelA",
                        "blocks": [{"role": "user", "text": "Hi"}],
                    }
                ],
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_yaml(tmpdir, "valid.yaml", valid_data)
            result = validate_yaml_to_schema(path)
            self.assertTrue(result.samefile(path))

    def test_malformed_yaml_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad.yaml"
            path.write_text("name: Alice\nage: [30")
            with self.assertRaises(ValueError) as ctx:
                validate_yaml_to_schema(path)
            self.assertIn("YAML parsing error", str(ctx.exception))

    def test_yaml_failing_schema_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_yaml(tmpdir, "invalid.yaml", {"name": "Alice"})
            with self.assertRaises(ValueError) as ctx:
                validate_yaml_to_schema(path)
            self.assertIn("Schema validation error", str(ctx.exception))


class TestValidateValueInYaml(unittest.TestCase):
    """validate_value_in_yaml checks that a list-of-dicts YAML contains a key=value entry."""

    def _write_yaml(self, tmpdir: str, data) -> Path:
        path = Path(tmpdir) / "test.yaml"
        path.write_text(yaml.safe_dump(data))
        return path

    def test_existing_key_value_pair_passes(self):
        data = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_yaml(tmpdir, data)
            validate_value_in_yaml(path, "name", "Alice")
            validate_value_in_yaml(path, "age", 25)

    def test_non_list_yaml_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_yaml(tmpdir, {"name": "Alice"})
            with self.assertRaises(ValueError) as ctx:
                validate_value_in_yaml(path, "name", "Alice")
            self.assertIn("Expected a list of mappings", str(ctx.exception))

    def test_missing_value_raises(self):
        data = [{"name": "Alice"}, {"name": "Bob"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_yaml(tmpdir, data)
            with self.assertRaises(ValueError) as ctx:
                validate_value_in_yaml(path, "name", "Charlie")
            self.assertIn("No entry with 'name: Charlie' found", str(ctx.exception))


class TestValidateTbServerUrl(unittest.TestCase):
    """validate_tb_server_url reachability checks via HTTP GET."""

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

        with self.assertRaises(ValueError) as ctx:
            validate_tb_server_url("https://testserver.example.com")
        self.assertIn("Unable to connect to the server", str(ctx.exception))

    @patch("testbench_ai_service.validators.requests.get")
    def test_connection_error_raises(self, mock_get):
        mock_get.side_effect = requests.ConnectionError("Failed to connect")

        with self.assertRaises(ValueError) as ctx:
            validate_tb_server_url("https://testserver.example.com")
        self.assertIn("Unable to connect to the server", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
