import argparse
import ssl

import uvicorn

from testbench_ai_service.__init__ import __title__, __version__
from testbench_ai_service.config import DEFAULT_HOST, DEFAULT_PORT
from testbench_ai_service.log import get_log_config_dict, logger, setup_logging
from testbench_ai_service.main import create_app
from testbench_ai_service.utils.config import (
    create_default_config_file,
    load_config_from_file,
)


def print_cli_banner():
    print(rf"""
  ______          __  ____                  __       ___    ____   _____                 _         
 /_  __/__  _____/ /_/ __ )___  ____  _____/ /_     /   |  /  _/  / ___/___  ______   __(_)_______ 
  / / / _ \/ ___/ __/ __  / _ \/ __ \/ ___/ __ \   / /| |  / /    \__ \/ _ \/ ___/ | / / / ___/ _ \
 / / /  __(__  ) /_/ /_/ /  __/ / / / /__/ / / /  / ___ |_/ /    ___/ /  __/ /   | |/ / / /__/  __/  version:
/_/  \___/____/\__/_____/\___/_/ /_/\___/_/ /_/  /_/  |_/___/   /____/\___/_/    |___/_/\___/\___/   {__version__}

""")  # noqa: W291


def main():
    parser = argparse.ArgumentParser(
        description="TestBench AI Service CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-v", "--version", action="version", version="%(prog)s " + __version__)
    subparsers = parser.add_subparsers(title="commands", dest="command")

    register_init_command(subparsers)
    register_start_command(subparsers)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


def register_init_command(subparsers):
    init_parser = subparsers.add_parser(
        "init",
        help="Generate a default configuration file.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    init_parser.add_argument(
        "--path",
        type=str,
        metavar="PATH",
        default="config.toml",
        help="Path to the configuration file to generate.",
    )
    init_parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Overwrite the configuration file if it exists.",
    )
    init_parser.add_argument(
        "--prompts-dir",
        type=str,
        metavar="PATH",
        default="prompts",
        help="Copy default prompt files to PATH and set prompts_dir in the config. "
        "Defaults to 'prompts' in the current directory. Pass an empty string to skip.",
    )
    init_parser.set_defaults(func=init_action)


def register_start_command(subparsers):
    start_parser = subparsers.add_parser(
        "start",
        help="Start the TestBench AI Service.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    start_parser.add_argument(
        "--config",
        type=str,
        metavar="PATH",
        default="config.toml",
        help="Path to the app configuration file.",
    )
    start_parser.add_argument(
        "--host", type=str, help=f"Host to run the service on. (default: {DEFAULT_HOST})"
    )
    start_parser.add_argument(
        "--port", type=int, help=f"Port to run the service on. (default: {DEFAULT_PORT})"
    )
    start_parser.add_argument(
        "--dev", action="store_true", help="Run the service in development mode with auto-reload."
    )
    start_parser.add_argument(
        "--tb-server-url",
        type=str,
        metavar="URL",
        help="Base URL of the TestBench REST API Server (e.g., https://localhost:9443/api/).",
    )
    start_parser.set_defaults(func=start_action)


def init_action(args):
    create_default_config_file(args.path, force=args.force, prompts_dir=args.prompts_dir)


def start_action(args):
    config = load_config_from_file(args.config)

    # Apply CLI overrides
    if "tb_server_url" in args and args.tb_server_url is not None:
        config.tb_server_url = args.tb_server_url
    if "host" in args and args.host is not None:
        config.host = args.host
    if "port" in args and args.port is not None:
        config.port = args.port
    config.debug = getattr(args, "dev", False) or config.debug

    print_cli_banner()

    setup_logging(config.logging)
    logger.info("Starting %s v%s", __title__, __version__)

    # Server configuration
    server_config = {
        "host": config.host,
        "port": config.port,
        "log_config": get_log_config_dict(config.logging),
        "ssl_certfile": config.ssl_cert,
        "ssl_keyfile": config.ssl_key,
    }
    if config.ssl_ca_cert:
        server_config["ssl_ca_certs"] = config.ssl_ca_cert
        server_config["ssl_cert_reqs"] = ssl.CERT_REQUIRED
    if config.trusted_proxies:
        server_config["proxy_headers"] = True
        server_config["forwarded_allow_ips"] = config.trusted_proxies

    if config.debug:
        # Run in development mode with auto-reload
        uvicorn.run(
            "testbench_ai_service.main:create_app",
            reload=True,
            factory=True,
            **server_config,
        )
    else:
        # Run in production mode
        app = create_app(config)
        uvicorn.run(app, **server_config)


if __name__ == "__main__":
    main()
