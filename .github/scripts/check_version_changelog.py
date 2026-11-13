# ruff: noqa: INP001  (standalone CI script, not part of a package)
"""Check version bump and CHANGELOG.md of a pull request against its base branch.

Rules:
1. CHANGELOG.md must be changed in the PR, unless SKIP_CHANGELOG=true
   (label "skip-changelog" or Dependabot PR).
2. If __version__ changed, it must be higher than the base version and
   CHANGELOG.md must contain a heading "## [<version>]".

Environment:
    BASE_REF        Git ref of the base branch, e.g. "origin/main".
    SKIP_CHANGELOG  "true" to skip rule 1.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from packaging.version import InvalidVersion, Version

INIT_FILE = "testbench_ai_service/__init__.py"
CHANGELOG = "CHANGELOG.md"
VERSION_RE = re.compile(r'^__version__\s*=\s*[\'"]([^\'"]+)[\'"]', re.MULTILINE)


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout


def parse_version(source: str, origin: str) -> Version:
    match = VERSION_RE.search(source)
    if not match:
        sys.exit(f"::error::Could not find __version__ in {origin}")
    try:
        return Version(match.group(1))
    except InvalidVersion:
        sys.exit(f"::error::Invalid __version__ '{match.group(1)}' in {origin}")


def changelog_has_heading(changelog: str, version: Version) -> bool:
    pattern = rf"^##\s*\[{re.escape(str(version))}\]"
    return re.search(pattern, changelog, re.MULTILINE) is not None


def main() -> int:
    base_ref = os.environ.get("BASE_REF", "origin/main")
    skip_changelog = os.environ.get("SKIP_CHANGELOG", "false").lower() == "true"

    changed = set(git("diff", "--name-only", f"{base_ref}...HEAD").split())
    errors: list[str] = []

    if CHANGELOG in changed:
        print(f"OK: {CHANGELOG} was changed.")
    elif skip_changelog:
        print(f"SKIP: {CHANGELOG} not changed, but the check is skipped for this PR.")
    else:
        errors.append(
            f"{CHANGELOG} was not changed. Add an entry, or set the label "
            "'skip-changelog' if the PR needs none (e.g. CI or docs only)."
        )

    base_version = parse_version(git("show", f"{base_ref}:{INIT_FILE}"), f"{base_ref}:{INIT_FILE}")
    head_version = parse_version(Path(INIT_FILE).read_text(encoding="utf-8"), INIT_FILE)

    if head_version == base_version:
        print(f"OK: version unchanged ({head_version}).")
    elif head_version < base_version:
        errors.append(f"__version__ went down: {base_version} -> {head_version}.")
    else:
        print(f"OK: version bumped {base_version} -> {head_version}.")
        changelog = Path(CHANGELOG).read_text(encoding="utf-8")
        if not changelog_has_heading(changelog, head_version):
            errors.append(
                f"__version__ is {head_version}, but {CHANGELOG} has no heading "
                f"'## [{head_version}]'."
            )

    for error in errors:
        print(f"::error::{error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
