"""Containment helpers for the console.

Every filesystem path the console derives from request data goes through
:func:`resolve_within`.  Without it the prompt endpoints would be an arbitrary
file read, and the write endpoints an arbitrary file write.
"""

from ipaddress import ip_address
from pathlib import Path

from fastapi import Depends, HTTPException, Request, status

from testbench_ai_service.config import AppConfig
from testbench_ai_service.dependencies import get_app_config
from testbench_ai_service.log import logger


def resolve_within(base: Path, candidate: str | Path) -> Path:
    """Resolve *candidate* against *base* and require the result to stay inside it.

    Symlinks are resolved before the check, so a link inside *base* that points
    outside it is refused as well.

    Raises:
        HTTPException 400: *candidate* is empty, or escapes *base*.
    """
    if not str(candidate).strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Empty path is not allowed"
        )

    base_resolved = Path(base).resolve()
    candidate_path = Path(candidate)
    target = (
        candidate_path.resolve()
        if candidate_path.is_absolute()
        else (base_resolved / candidate_path).resolve()
    )

    # relative_to on the resolved paths is what rejects both `..` traversal and a
    # sibling directory that merely shares a name prefix.
    try:
        target.relative_to(base_resolved)
    except ValueError:
        logger.warning("Rejected path outside %s: %r", base_resolved, str(candidate))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path is outside the permitted directory",
        ) from None

    return target


def is_loopback(host: str | None) -> bool:
    """Return True if *host* refers to this machine."""
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def require_loopback(
    request: Request, config: AppConfig = Depends(get_app_config)
) -> None:
    """Refuse non-loopback clients when ``admin_ui.require_loopback`` is set."""
    if not config.admin_ui.require_loopback:
        return
    client_host = request.client.host if request.client else None
    if not is_loopback(client_host):
        logger.warning("Refused console request from non-loopback client %s", client_host)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The console is restricted to local access",
        )
