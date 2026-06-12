import argparse
from unittest.mock import MagicMock, patch

import pytest

from testbench_ai_service import __version__
from testbench_ai_service.cli import (
    init_action,
    main,
    print_cli_banner,
    register_init_command,
    register_start_command,
    start_action,
)


class TestPrintCliBanner:
    def test_prints_without_error(self):
        with patch("builtins.print") as mock_print:
            print_cli_banner()
        mock_print.assert_called_once()

    def test_banner_contains_version(self):
        with patch("builtins.print") as mock_print:
            print_cli_banner()

        output = mock_print.call_args[0][0]
        assert __version__ in output


class TestMainParserSetup:
    """main() builds an ArgumentParser with 'init' and 'start' sub-commands."""

    def test_no_args_prints_help(self):
        with (
            patch("sys.argv", ["testbench-ai-service"]),
            patch("argparse.ArgumentParser.print_help") as mock_help,
        ):
            main()
        mock_help.assert_called_once()

    def test_version_flag(self):
        with (
            patch("sys.argv", ["testbench-ai-service", "--version"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 0


class TestRegisterInitCommand:
    def _make_subparsers(self):
        parser = argparse.ArgumentParser()
        return parser, parser.add_subparsers(dest="command")

    def test_init_command_registered(self):
        _, subparsers = self._make_subparsers()
        register_init_command(subparsers)
        args = subparsers.choices["init"].parse_args([])
        assert args.path == "config.toml"
        assert not args.force
        assert args.prompts_dir == "prompts"

    def test_init_command_accepts_path_flag(self):
        _, subparsers = self._make_subparsers()
        register_init_command(subparsers)
        args = subparsers.choices["init"].parse_args(["--path", "custom.toml"])
        assert args.path == "custom.toml"

    def test_init_command_accepts_force_flag(self):
        _, subparsers = self._make_subparsers()
        register_init_command(subparsers)
        args = subparsers.choices["init"].parse_args(["--force"])
        assert args.force


class TestRegisterStartCommand:
    def _make_subparsers(self):
        parser = argparse.ArgumentParser()
        return parser, parser.add_subparsers(dest="command")

    def test_start_command_registered(self):
        _, subparsers = self._make_subparsers()
        register_start_command(subparsers)
        assert "start" in subparsers.choices

    def test_start_command_accepts_config_flag(self):
        _, subparsers = self._make_subparsers()
        register_start_command(subparsers)
        args = subparsers.choices["start"].parse_args(["--config", "prod.toml"])
        assert args.config == "prod.toml"


class TestInitAction:
    def test_delegates_to_create_default_config_file(self):
        mock_args = MagicMock()
        mock_args.path = "my.toml"
        mock_args.force = True
        mock_args.prompts_dir = "prompts"

        with patch("testbench_ai_service.cli.create_default_config_file") as mock_create:
            init_action(mock_args)

        mock_create.assert_called_once_with("my.toml", force=True, prompts_dir="prompts")


class TestStartAction:
    def _make_args(self, **overrides):
        defaults = {
            "config": "config.toml",
            "host": None,
            "port": None,
            "dev": False,
            "tb_server_url": None,
        }
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    def _mock_config(self):
        mock_config = MagicMock()
        mock_config.ssl_ca_cert = None
        mock_config.trusted_proxies = None
        mock_config.debug = False
        return mock_config

    def test_loads_config_and_runs_uvicorn(self):
        mock_config = self._mock_config()
        with (
            patch("testbench_ai_service.cli.load_config_from_file", return_value=mock_config),
            patch("testbench_ai_service.cli.uvicorn.run") as mock_run,
            patch("testbench_ai_service.cli.setup_logging"),
            patch("testbench_ai_service.cli.get_log_config_dict", return_value={}),
            patch("testbench_ai_service.cli.create_app", return_value=MagicMock()),
            patch("testbench_ai_service.cli.print_cli_banner"),
        ):
            start_action(self._make_args())

        mock_run.assert_called_once()

    def test_applies_host_port_overrides(self):
        mock_config = self._mock_config()
        with (
            patch("testbench_ai_service.cli.load_config_from_file", return_value=mock_config),
            patch("testbench_ai_service.cli.uvicorn.run"),
            patch("testbench_ai_service.cli.setup_logging"),
            patch("testbench_ai_service.cli.get_log_config_dict", return_value={}),
            patch("testbench_ai_service.cli.create_app", return_value=MagicMock()),
            patch("testbench_ai_service.cli.print_cli_banner"),
        ):
            start_action(self._make_args(host="0.0.0.0", port=9000))

        assert mock_config.host == "0.0.0.0"
        assert mock_config.port == 9000

    def test_dev_mode_sets_debug(self):
        mock_config = self._mock_config()
        with (
            patch("testbench_ai_service.cli.load_config_from_file", return_value=mock_config),
            patch("testbench_ai_service.cli.uvicorn.run"),
            patch("testbench_ai_service.cli.setup_logging"),
            patch("testbench_ai_service.cli.get_log_config_dict", return_value={}),
            patch("testbench_ai_service.cli.create_app", return_value=MagicMock()),
            patch("testbench_ai_service.cli.print_cli_banner"),
        ):
            start_action(self._make_args(dev=True))

        assert mock_config.debug
