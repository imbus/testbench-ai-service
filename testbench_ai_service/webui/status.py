"""Read-only operational probes for the console's Status screen."""

import asyncio
import os
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone

import requests

from testbench_ai_service import __version__
from testbench_ai_service.agent_packages import loaded
from testbench_ai_service.agent_packages.manifest import ManifestError, load_manifest
from testbench_ai_service.config import AppConfig
from testbench_ai_service.llm.base import LLMProvider
from testbench_ai_service.log import logger
from testbench_ai_service.usage import UsageStore
from testbench_ai_service.webui.models import (
    AgentSummary,
    ApiKeyStatus,
    ModelUsageEntry,
    ServiceStatus,
    StatusResponse,
    TestBenchStatus,
    UsageSummary,
)

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
        unloaded_packages=_unloaded_packages(config),
        failed_agents=loaded.agent_failures(),
    )


def _unloaded_packages(config: AppConfig) -> dict[str, str]:
    """Package name -> why the package's agents are not in use."""
    unloaded = loaded.failures()
    pending = {
        agent.package
        for agent in config.agents.values()
        if agent.package is not None
        and agent.package not in unloaded
        and not loaded.is_loaded(agent.package)
    }
    if not pending:
        return unloaded
    try:
        known: set[str] | None = set(load_manifest(config.agent_packages.dir).packages)
    except ManifestError as e:
        logger.warning("Cannot read the agent package manifest for the status: %s", e)
        known = None
    for package in sorted(pending):
        if known is not None and package not in known:
            unloaded[package] = "The package is missing: it was never uploaded or was deleted."
        else:
            unloaded[package] = "Not loaded yet. Restart the service to load it."
    return unloaded


def llm_client_error(config: AppConfig) -> str | None:
    """Why the LLM client an uploaded package provides is not in use, if it is not."""
    llm = config.llm_config
    if llm.provider != LLMProvider.CUSTOM or llm.package is None:
        return None
    failure = loaded.failures().get(llm.package)
    if failure is not None:
        return failure
    if not loaded.is_loaded(llm.package):
        return "Not loaded yet. Restart the service to load it."
    return loaded.llm_client_failure()


async def read_token_usage(store: UsageStore) -> UsageSummary:
    """The per-model totals, or an explicit "unavailable" if the file cannot be read.

    Read off the event loop, like the writes: the file may be locked by a
    writer for up to the store's timeout.
    """
    try:
        totals = await asyncio.to_thread(store.totals)
    except (sqlite3.Error, OSError) as e:
        logger.warning("Could not read token usage from '%s': %r", store.path, e)
        return UsageSummary(available=False)
    return UsageSummary(models=[ModelUsageEntry(**asdict(entry)) for entry in totals])


def build_status(
    config: AppConfig,
    started_at: datetime,
    in_flight_tasks: int = 0,
    restart_required: list[str] | None = None,
    token_usage: UsageSummary | None = None,
    *,
    can_restart: bool = False,
) -> StatusResponse:
    uptime = (datetime.now(timezone.utc) - started_at).total_seconds()
    return StatusResponse(
        service=ServiceStatus(
            version=__version__,
            host=config.host,
            port=config.port,
            debug=config.debug,
            uptime_seconds=max(uptime, 0.0),
            language=config.language.value,
            started_at=started_at,
            can_restart=can_restart,
        ),
        testbench=probe_testbench(config),
        api_keys=api_key_statuses(config),
        agents=agent_summary(config),
        in_flight_tasks=in_flight_tasks,
        restart_required=restart_required or [],
        token_usage=token_usage or UsageSummary(),
        llm_client_error=llm_client_error(config),
    )
