"""Hot reload, and what a hot reload cannot cover.

Most of the configuration can be swapped in a running process: every request
reads ``app.state.config`` through ``get_app_config``, the LLM clients can be
closed and rebuilt, translations and logging can be re-applied.

Two things cannot:

- ``host``, ``port``, the three TLS paths and ``trusted_proxies`` are handed to
  uvicorn and the middleware stack at boot and are never consulted again;
- ``admin_ui.enabled`` controls whether the console is mounted at all, decided
  once in ``create_app()`` when ``init_webui()`` is called;
- an agent's ``endpoint_path`` and ``class_path`` are consumed by
  ``init_routers()`` exactly once, at startup, so adding, removing, moving or
  re-classing an agent cannot change the live routing table.

Those changes are still written to disk. They just raise the console's
"restart needed" banner rather than pretending to take effect. There is no
self-restart button: re-execing only works under a supervisor and would kill a
bare terminal process outright (spec 7).

Note: ``admin_ui.require_loopback`` is deliberately NOT in the restart-required
set because it is read per request through ``get_app_config`` and is genuinely
hot-swappable.
"""

from fastapi import FastAPI

from testbench_ai_service.config import AppConfig
from testbench_ai_service.llm.factory import LLMFactory
from testbench_ai_service.log import logger, setup_logging
from testbench_ai_service.utils.i18n import load_translations

# Fixed at boot by uvicorn or by the middleware stack.
RESTART_FIELDS: tuple[str, ...] = (
    "host",
    "port",
    "ssl_cert",
    "ssl_key",
    "ssl_ca_cert",
    "trusted_proxies",
    # init_webui() mounts the console router and static files once, from
    # create_app(), so switching the console off cannot take effect live.
    # 'admin_ui.require_loopback' is deliberately NOT here: it is read per
    # request through get_app_config and is genuinely hot-swappable.
    "admin_ui.enabled",
)

# Consumed once by init_routers(); a change cannot reach the live router table.
RESTART_AGENT_FIELDS: tuple[str, ...] = ("endpoint_path", "class_path")


def _resolve_dotted_path(obj: object, path: str) -> object:
    """Resolve a dotted path like 'admin_ui.enabled' by walking attributes.

    Args:
        obj: The object to traverse (e.g., an AppConfig instance).
        path: A dotted attribute path (e.g., 'admin_ui.enabled').

    Returns:
        The value at the path, or raises AttributeError if any component missing.
    """
    current = obj
    for part in path.split("."):
        current = getattr(current, part)
    return current


def restart_required(old: AppConfig, new: AppConfig) -> list[str]:
    """Dotted paths of changes between *old* and *new* that a live swap cannot cover.

    An empty list means the whole change set can be applied in process.
    """
    changed: list[str] = []

    for field in RESTART_FIELDS:
        if _resolve_dotted_path(old, field) != _resolve_dotted_path(new, field):
            changed.append(field)

    old_keys = set(old.agents)
    new_keys = set(new.agents)
    # An added or removed agent is reported as the agent itself rather than as
    # its fields: there is no old (or new) value to name, and the operator's
    # takeaway is the same either way.
    changed.extend(f"agents.{key}" for key in old_keys ^ new_keys)

    for key in sorted(old_keys & new_keys):
        for field in RESTART_AGENT_FIELDS:
            if getattr(old.agents[key], field) != getattr(new.agents[key], field):
                changed.append(f"agents.{key}.{field}")

    return sorted(changed)


async def hot_reload(app: FastAPI, config: AppConfig) -> None:
    """Make *config* the running configuration, in process.

    Ordered deliberately:

    1. logging first, so everything after it is logged the way the operator
       just asked for;
    2. translations, which are a module-level dict and cheap to re-read;
    3. the config swap, which every subsequent request sees through
       ``get_app_config``;
    4. the LLM clients last, because rebuilding them is the only step that
       touches the network and the only one that can be slow.

    Re-applying ``setup_logging`` is safe to repeat: the dict config names every
    logger the service cares about (``testbench_ai_service``, the four
    ``uvicorn`` loggers, ``py.warnings``), so ``disable_existing_loggers`` has
    nothing new to disable, and ``dictConfig`` flushes and closes the handlers
    it replaces.

    Failures closing the *old* clients are logged and swallowed. By the time
    this runs the new config is already on disk, so aborting would leave the
    file and the process disagreeing with no way to reconcile them -- and a
    client that cannot be closed is a leaked connection, not a corrupt state.

    Changes this cannot cover do not belong here at all; see
    :func:`restart_required`.
    """
    setup_logging(config.logging)
    load_translations()

    previous_factory = app.state.llm_factory
    app.state.config = config

    try:
        await previous_factory.close_clients()
    except Exception as e:
        logger.warning("Could not close the previous LLM clients during reload: %r", e)

    factory = LLMFactory()
    factory.init_clients([config.llm_config])
    app.state.llm_factory = factory

    logger.info("Configuration reloaded in process")
