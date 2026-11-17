"""The lock that serialises console writes to the config file and the files next to it."""

import asyncio
from collections.abc import AsyncIterator

from fastapi import Request


def get_write_lock(request: Request) -> asyncio.Lock:
    """The app-wide lock created in ``init_webui``."""
    return request.app.state.config_write_lock  # type: ignore[no-any-return]


async def hold_write_lock(request: Request) -> AsyncIterator[None]:
    """Dependency: hold the lock for the whole request.

    Declare it after the auth dependencies so a rejected request never waits for it.
    """
    async with get_write_lock(request):
        yield
