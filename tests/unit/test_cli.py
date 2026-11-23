from __future__ import annotations

import argparse
from collections.abc import Callable
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import MagicMock, patch

import pytest

from testbench_ai_service import __version__, log
from testbench_ai_service.cli import (
    init_action,
    main,
    print_cli_banner,
    register_init_command,
    register_start_command,
    serve,
    start_action,
)
from testbench_ai_service.restart import RESTART_GRACE_SECONDS, RestartController


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


class TestInspectAgentPackageCommand:
    def test_runs_the_inspector(self):
        with (
            patch("sys.argv", ["testbench-ai-service", "inspect-agent-package", "site"]),
            patch("testbench_ai_service.agent_packages.inspector.main", return_value=0) as run,
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        run.assert_called_once_with(["site"])
        assert exc_info.value.code == 0

    def test_is_hidden_from_help(self, capsys):
        with patch("sys.argv", ["testbench-ai-service", "--help"]), pytest.raises(SystemExit):
            main()
        assert "inspect-agent-package" not in capsys.readouterr().out


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
    @pytest.fixture(autouse=True)
    def restore_reloader_flag(self, monkeypatch):
        """start_action sets the module-wide ``log.is_reloader_process``; with
        ``--dev`` it stays True and every later test gets NullHandlers instead
        of log files. monkeypatch puts the original value back afterwards."""
        monkeypatch.setattr(log, "is_reloader_process", log.is_reloader_process)

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
            patch("testbench_ai_service.cli.serve") as mock_serve,
            patch("testbench_ai_service.cli.setup_logging"),
            patch("testbench_ai_service.cli.get_log_config_dict", return_value={}),
            patch("testbench_ai_service.cli.print_cli_banner"),
        ):
            start_action(self._make_args())

        mock_serve.assert_called_once()

    def test_applies_host_port_overrides(self):
        mock_config = self._mock_config()
        with (
            patch("testbench_ai_service.cli.load_config_from_file", return_value=mock_config),
            patch("testbench_ai_service.cli.serve"),
            patch("testbench_ai_service.cli.setup_logging"),
            patch("testbench_ai_service.cli.get_log_config_dict", return_value={}),
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

    def test_serves_in_the_restart_loop(self):
        mock_config = self._mock_config()
        with (
            patch("testbench_ai_service.cli.load_config_from_file", return_value=mock_config),
            patch("testbench_ai_service.cli.serve") as mock_serve,
            patch("testbench_ai_service.cli.uvicorn.run") as mock_run,
            patch("testbench_ai_service.cli.setup_logging"),
            patch("testbench_ai_service.cli.get_log_config_dict", return_value={}),
            patch("testbench_ai_service.cli.print_cli_banner"),
        ):
            start_action(self._make_args(port=9000))

        mock_run.assert_not_called()
        config, _reload_config, _options, controller = mock_serve.call_args.args
        assert config is mock_config
        # The command-line options win over the file on every restart, too.
        reloaded = self._mock_config()
        controller.apply_overrides(reloaded)
        assert reloaded.port == 9000


class FakeServer:
    """Stands in for ``uvicorn.Server``; each ``run`` plays the next scripted step."""

    script: ClassVar[list[Callable[[FakeServer], None]]] = []
    instances: ClassVar[list[FakeServer]] = []

    def __init__(self, config):
        self.config = config
        self.started = False
        self.should_exit = False
        FakeServer.instances.append(self)

    def run(self):
        step = FakeServer.script.pop(0)
        step(self)


def _restart(server):
    server.started = True
    server.config.app.state.restart_controller.request()


def _stop(server):
    server.started = True


def _fail_to_bind(server):
    raise SystemExit(3)


class TestServe:
    @pytest.fixture(autouse=True)
    def fake_uvicorn(self):
        FakeServer.instances = []
        self.apps = []

        def make_app(config):
            app = MagicMock()
            app.state = SimpleNamespace(config=config, webui_sessions=object())
            self.apps.append(app)
            return app

        def make_config(app, **options):
            return SimpleNamespace(app=app, options=options, timeout_graceful_shutdown=None)

        with (
            patch("testbench_ai_service.cli.uvicorn.Server", FakeServer),
            patch("testbench_ai_service.cli.uvicorn.Config", side_effect=make_config),
            patch("testbench_ai_service.cli.create_app", side_effect=make_app),
        ):
            yield

    @staticmethod
    def _options(config):
        return {"port": config.port}

    def _ports(self):
        return [server.config.options["port"] for server in FakeServer.instances]

    def test_serves_once_without_a_restart(self):
        FakeServer.script = [_stop]
        reload = MagicMock()

        serve(SimpleNamespace(port=1), reload, self._options, RestartController())

        assert self._ports() == [1]
        reload.assert_not_called()

    def test_a_restart_reloads_the_config_and_serves_again(self):
        FakeServer.script = [_restart, _stop]
        new = SimpleNamespace(port=2)

        serve(SimpleNamespace(port=1), lambda: new, self._options, RestartController())

        assert self._ports() == [1, 2]
        assert FakeServer.instances[0].config.timeout_graceful_shutdown == RESTART_GRACE_SECONDS
        assert self.apps[1].state.config is new

    def test_a_restart_keeps_the_console_sessions(self):
        FakeServer.script = [_restart, _stop]

        serve(
            SimpleNamespace(port=1),
            lambda: SimpleNamespace(port=1),
            self._options,
            RestartController(),
        )

        assert self.apps[1].state.webui_sessions is self.apps[0].state.webui_sessions

    def test_falls_back_to_the_previous_config_when_the_new_one_cannot_start(self):
        FakeServer.script = [_restart, _fail_to_bind, _stop]
        old = SimpleNamespace(port=1)

        serve(old, lambda: SimpleNamespace(port=2), self._options, RestartController())

        assert self._ports() == [1, 2, 1]
        assert self.apps[2].state.config is old

    def test_keeps_the_running_config_when_the_file_cannot_be_loaded(self):
        FakeServer.script = [_restart, _stop]
        old = SimpleNamespace(port=1)

        def broken():
            raise SystemExit(1)

        serve(old, broken, self._options, RestartController())

        assert self.apps[1].state.config is old

    def test_a_first_start_failure_still_exits(self):
        FakeServer.script = [_fail_to_bind]

        with pytest.raises(SystemExit):
            serve(SimpleNamespace(port=1), MagicMock(), self._options, RestartController())
