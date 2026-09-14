"""Containment helpers for the console.

Every filesystem path the console derives from request data goes through
:func:`resolve_within`.  Without it the prompt endpoints would be an arbitrary
file read, and the write endpoints an arbitrary file write.

Two things a caller building on top of :func:`resolve_within` must know:

- It accepts non-existent paths, directories, and NTFS alternate-data-stream
  names as long as they stay inside *base* — it is a containment check, not an
  existence or file-type check. Any extension allowlist a later endpoint
  applies must be applied to the **returned** path's ``.suffix``, never to the
  raw candidate string, or names like ``p.yaml:evil`` or ``p.yaml.`` slip past
  a string-based check.
- ``Path("")`` is identical to ``Path(".")`` in pathlib and therefore resolves
  to *base* itself rather than raising. The empty-candidate guard below covers
  the string spelling only; a caller that first converts user input to a
  ``Path`` before calling this function must check for emptiness itself.
"""

import re
from ipaddress import ip_address
from pathlib import Path

from fastapi import Depends, HTTPException, Request, status

from testbench_ai_service.config import AppConfig
from testbench_ai_service.dependencies import get_app_config
from testbench_ai_service.log import logger

#: A segment made up entirely of dots -- ".", "..", "...", and so on. Windows
#: also accepts three-or-more-dot spellings where POSIX would not, so this is
#: checked regardless of platform rather than trusted to `.parts` collapsing.
_ALL_DOTS = re.compile(r"^\.+$")


def require_single_segment(name: str) -> Path:
    """*name* as a single, non-empty path segment that is not all dots.

    Shared by every caller that lets an operator name a bare file or directory
    segment (a new template's name, a fork's target directory): each used to
    run its own version of this check, and the two drifted -- one accepted a
    disguised ``".."`` the other had already learned to reject (see the
    module-level history of ``resolve_template_target`` and
    ``fork._require_segment``). One validator, used by both, is how that stops
    happening again.

    Checked on the NORMALISED parts, not the raw string: pathlib collapses a
    leading ``"./"`` (so ``"./.."`` also has exactly one part, ``".."``), and a
    raw-string check against ``{".", ".."}`` would let ``"./.."``, ``".//.."``,
    ``"././.."`` and ``"..//"`` all through as a bogus single segment that
    resolves to the parent directory itself.

    Raises:
        HTTPException 400: *name* is empty, is not a single path segment, or
            (in any disguised spelling) resolves to a segment made up entirely
            of dots.
    """
    if not name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Empty path is not allowed"
        )
    candidate = Path(name)
    if candidate.is_absolute() or len(candidate.parts) != 1 or _ALL_DOTS.match(candidate.parts[0]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{name!r} is not a plain path segment.",
        )
    return candidate


def resolve_within(base: Path, candidate: str | Path) -> Path:
    """Resolve *candidate* against *base* and require the result to stay inside it.

    Symlinks are resolved before the check, so a link inside *base* that points
    outside it is refused as well.

    Raises:
        HTTPException 400: *candidate* is empty, contains a NUL byte, or escapes
            *base*.
    """
    candidate_str = str(candidate)
    if not candidate_str.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Empty path is not allowed"
        )
    if "\x00" in candidate_str:
        # Path()/.resolve() pass a NUL through untouched; the eventual open()
        # raises ValueError rather than HTTPException, which would surface as
        # an unhandled 500 instead of the 400 this chokepoint promises.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Path contains a NUL byte"
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
        addr = ip_address(host)
    except ValueError:
        return False
    # IPv4Address.is_loopback and (unmapped) IPv6Address.is_loopback are stable
    # across Python versions. But whether IPv6Address.is_loopback itself
    # follows IPv4-mapped addresses (e.g. "::ffff:127.0.0.1") depends on the
    # interpreter: that delegation to `ipv4_mapped` postdates this project's
    # Python floor. Handle the mapped case ourselves so a dual-stack bind
    # ("::") does not 403 every legitimate local client on Python 3.10-3.12.
    mapped = getattr(addr, "ipv4_mapped", None)
    if mapped is not None:
        return bool(mapped.is_loopback)
    return addr.is_loopback


def require_loopback(request: Request, config: AppConfig = Depends(get_app_config)) -> None:
    """Refuse non-loopback clients when ``admin_ui.require_loopback`` is set."""
    if not config.admin_ui.require_loopback:
        return
    client_host = request.client.host if request.client else None
    if not is_loopback(client_host):
        logger.warning("Refused console request from non-loopback client %r", client_host)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The console is restricted to local access",
        )
