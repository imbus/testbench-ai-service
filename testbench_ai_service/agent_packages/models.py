"""Data models of uploaded agent packages: inspection reports and the manifest."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentReport(BaseModel):
    """Inspection result for one agent entry point of a package."""

    entry_point: str
    class_path: str
    ok: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    data_fields: list[str] = Field(default_factory=list)
    step_fields: dict[str, list[str]] = Field(default_factory=dict)
    args_schema: dict[str, Any] | None = None
    context_sample: dict[str, Any] = Field(default_factory=dict)
    uses_llm: bool = True
    default_endpoint_path: str | None = None


class InspectionReport(BaseModel):
    """Inspection result for a whole package version."""

    ok: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    agents: dict[str, AgentReport] = Field(default_factory=dict)


class PackageVersion(BaseModel):
    """One uploaded wheel."""

    name: str
    version: str
    filename: str
    sha256: str
    size: int
    uploaded_at: datetime
    uploaded_by: str | None = None
    active: bool = False
    report: InspectionReport


class Manifest(BaseModel):
    """All uploaded packages: name -> version -> entry."""

    packages: dict[str, dict[str, PackageVersion]] = Field(default_factory=dict)

    def active(self, name: str) -> PackageVersion | None:
        """Return the active version of *name*, if any."""
        for entry in self.packages.get(name, {}).values():
            if entry.active:
                return entry
        return None

    def set_active(self, name: str, version: str | None) -> None:
        """Make *version* the only active version of *name*; ``None`` deactivates all.

        Raises:
            KeyError: *version* is not known for *name*.
        """
        versions = self.packages.get(name, {})
        if version is not None and version not in versions:
            raise KeyError(f"{name} {version}")
        for key, entry in versions.items():
            entry.active = key == version
