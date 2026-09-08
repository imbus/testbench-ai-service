"""Read-only operational probes for the console's Status screen."""

import os
from datetime import datetime, timezone

import requests

from testbench_ai_service import __version__
from testbench_ai_service.config import AppConfig
from testbench_ai_service.log import logger
from testbench_ai_service.webui.models import (
    AgentSummary,
    ApiKeyStatus,
    ServiceStatus,
    StatusResponse,
    TestBenchStatus,
)

#: Provider credentials the service understands. Presence is reported, never values.
API_KEY_NAMES = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "AZURE_TENANT_ID",
    "AZURE_CLIENT_ID",
    "AZURE_CLIENT_SECRET",
)

_PROBE_TIMEOUT = 3.0


def known_api_key_names(config: AppConfig) -> list[str]:
    """The credential names worth reporting, most relevant provider first."""
    del config  # reserved for provider-specific narrowing in a later phase
    return list(API_KEY_NAMES)


def api_key_statuses(config: AppConfig) -> list[ApiKeyStatus]:
    return [
        ApiKeyStatus(name=name, present=bool(os.environ.get(name)))
        for name in known_api_key_names(config)
    ]


def probe_testbench(config: AppConfig) -> TestBenchStatus:
    """Check that the configured TestBench server answers, without authenticating.

    Requests the configured base URL itself rather than any guessed API path:
    any HTTP response -- including a 401 or 404 -- proves the server is up, so
    there is nothing to gain from targeting a specific endpoint.
    """
    verify: bool | str = config.tb_ssl_ca_bundle or config.tb_ssl_verify
    try:
        response = requests.get(
            config.tb_server_url,
            verify=verify,
            timeout=_PROBE_TIMEOUT,
        )
    except requests.exceptions.RequestException as e:
        logger.debug("TestBench probe failed: %s", e)
        return TestBenchStatus(url=config.tb_server_url, reachable=False, detail=type(e).__name__)
    # Any HTTP answer means the server is up; 401/404 are expected without credentials.
    return TestBenchStatus(
        url=config.tb_server_url,
        reachable=True,
        detail=f"HTTP {response.status_code}",
    )


def agent_summary(config: AppConfig) -> AgentSummary:
    overrides = sum(
        len(project.agents or {}) + (1 if project.language else 0)
        for project in config.projects.values()
    )
    return AgentSummary(
        total=len(config.agents),
        enabled=sum(1 for agent in config.agents.values() if agent.enabled),
        project_overrides=overrides,
        projects=len(config.projects),
    )


def build_status(config: AppConfig, started_at: datetime) -> StatusResponse:
    uptime = (datetime.now(timezone.utc) - started_at).total_seconds()
    return StatusResponse(
        service=ServiceStatus(
            version=__version__,
            host=config.host,
            port=config.port,
            debug=config.debug,
            uptime_seconds=max(uptime, 0.0),
            language=config.language.value,
        ),
        testbench=probe_testbench(config),
        api_keys=api_key_statuses(config),
        agents=agent_summary(config),
        log_file=config.logging.file.file_name,
    )
