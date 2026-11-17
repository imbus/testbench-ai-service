"""Build small wheel files for tests."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import stat
import zipfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from testbench_ai_service.agent_packages.wheel import extract_wheel


def _record_hash(data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return f"sha256={digest}"


def build_wheel(
    tmp_path: Path,
    *,
    name: str = "acme-tb-agents",
    version: str = "1.0.0",
    files: dict[str, str | bytes],
    entry_points: dict[str, str] | None = None,
    requires_dist: Sequence[str] = (),
    tag: str = "py3-none-any",
    corrupt_record: bool = False,
    extra_entries: dict[str, bytes] | None = None,
    symlink: str | None = None,
) -> Path:
    """Write a valid wheel with a correct RECORD (unless ``corrupt_record``)."""
    dist = name.replace("-", "_").replace(".", "_")
    dist_info = f"{dist}-{version}.dist-info"
    metadata = ["Metadata-Version: 2.1", f"Name: {name}", f"Version: {version}"]
    metadata += [f"Requires-Dist: {req}" for req in requires_dist]
    entries: dict[str, bytes] = {}
    for rel, content in files.items():
        entries[rel] = content.encode() if isinstance(content, str) else content
    entries[f"{dist_info}/METADATA"] = ("\n".join(metadata) + "\n").encode()
    entries[f"{dist_info}/WHEEL"] = (
        f"Wheel-Version: 1.0\nGenerator: tests\nRoot-Is-Purelib: true\nTag: {tag}\n"
    ).encode()
    if entry_points:
        lines = ["[testbench_ai_service.agents]"]
        lines += [f"{key} = {value}" for key, value in entry_points.items()]
        entries[f"{dist_info}/entry_points.txt"] = ("\n".join(lines) + "\n").encode()
    entries.update(extra_entries or {})

    record = io.StringIO()
    writer = csv.writer(record, lineterminator="\n")
    for index, (arcname, data) in enumerate(entries.items()):
        digest = _record_hash(data)
        if corrupt_record and index == 0:
            digest = _record_hash(data + b"tampered")
        writer.writerow([arcname, digest, len(data)])
    if symlink:
        writer.writerow([symlink, _record_hash(b"target"), 6])
    writer.writerow([f"{dist_info}/RECORD", "", ""])

    path = tmp_path / f"{dist}-{version}-{tag}.whl"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, data in entries.items():
            zf.writestr(arcname, data)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, b"target")
        zf.writestr(f"{dist_info}/RECORD", record.getvalue())
    return path


VALID_ENTRY_POINTS = {"acme_rater": "acme.rater.agent:RaterAgent"}

_AGENT_PY = """\
from testbench_ai_service.agents.base import Agent
from testbench_ai_service.models.agent import AgentData


class RaterData(AgentData):
    title: str


class RaterAgent(Agent):
    AGENT_DATA_CLASS = RaterData

    async def precheck(self, context, conn):
        raise NotImplementedError

    async def run(self, context, conn, llm_client, item_ids):
        raise NotImplementedError
"""

_PROMPT_YAML = """\
name: "Rater"
summary: "Rate test case sets"
description: "Rates test case sets."
default_model: "gpt-5.5"
default_variant: "Default"
variants:
  - name: "Default"
    description: "Default rating."
    model: "gpt-5.5"
    messages:
      - role: "system"
        file: "system.jinja"
      - role: "user"
        file: "user.jinja"
"""


def _language_files(lang: str) -> dict[str, str | bytes]:
    return {
        f"acme/rater/prompts/{lang}/prompt.yaml": _PROMPT_YAML,
        f"acme/rater/prompts/{lang}/system.jinja": "You rate test case sets.",
        f"acme/rater/prompts/{lang}/user.jinja": "Rate {{ agent.title }}.",
        f"acme/rater/templates/{lang}/started.jinja": "<p>started</p>",
        f"acme/rater/templates/{lang}/failed.jinja": "<p>failed</p>",
        f"acme/rater/templates/{lang}/template.jinja": "<p>{{ result }}</p>",
    }


#: A package with one valid agent ``acme_rater`` (entry points: ``VALID_ENTRY_POINTS``).
VALID_AGENT_FILES: dict[str, str | bytes] = {
    "acme/__init__.py": "",
    "acme/rater/__init__.py": "",
    "acme/rater/agent.py": _AGENT_PY,
    **_language_files("en"),
    **_language_files("de"),
}


def extracted(tmp_path: Path, files: dict[str, str | bytes], **kwargs: Any) -> Path:
    """Build a wheel from *files* and unpack it into a fresh site directory.

    Entry points default to ``VALID_ENTRY_POINTS``; other keyword arguments go to
    :func:`build_wheel`.
    """
    kwargs.setdefault("entry_points", VALID_ENTRY_POINTS)
    wheel = build_wheel(tmp_path, files=files, **kwargs)
    site = tmp_path / "site"
    extract_wheel(wheel, site)
    return site
