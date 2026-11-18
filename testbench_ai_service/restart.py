"""Restarting the service from the console, inside the running process.

``testbench-ai-service start`` serves in a loop (``cli.serve``): when the
console asks for a restart, uvicorn shuts down gracefully, the configuration is
read from disk again and a new app and server are built from it -- new host,
port and TLS files, agent routes and agent package versions included. The
process itself keeps running, so this works the same in a terminal, from the
executable and as a Windows service; no supervisor is needed.

Only ``serve`` attaches a :class:`RestartController` to the app. An app built
any other way (``--dev`` with auto-reload, tests, ``create_app`` in an ASGI
server of one's own) has none, and the console offers no restart.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from fastapi import Request

from testbench_ai_service.log import logger

if TYPE_CHECKING:
    import uvicorn

    from testbench_ai_service.config import AppConfig

#: How long open requests may take to finish before a restart cancels them.
#: Without a bound, one long agent request would hold the restart forever.
RESTART_GRACE_SECONDS = 15


def _keep(_config: AppConfig) -> None:
    return None


class RestartController:
    """Lets a request ask the serving loop for an in-process restart.

    ``apply_overrides`` applies the command-line options (``--host``,
    ``--port``, ...) that take precedence over the file, so the console can
    say where the restarted service will listen.
    """

    def __init__(self, apply_overrides: Callable[[AppConfig], None] = _keep) -> None:
        self.apply_overrides = apply_overrides
        self.requested = False
        self._server: uvicorn.Server | None = None

    def attach(self, server: uvicorn.Server) -> None:
        """Serve *server* next; any earlier request is used up."""
        self._server = server
        self.requested = False

    def request(self) -> None:
        """Shut the current server down gracefully and have the loop start a new one."""
        if self._server is None:
            raise RuntimeError("No server is attached")
        logger.info("Restart requested")
        self.requested = True
        self._server.config.timeout_graceful_shutdown = RESTART_GRACE_SECONDS
        self._server.should_exit = True


def get_restart_controller(request: Request) -> RestartController | None:
    """The controller of the serving loop, or ``None`` if the app was not started by it."""
    return getattr(request.app.state, "restart_controller", None)
