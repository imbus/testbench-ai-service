"""Tests for selecting and loading the one baseline the agent works from."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from testbench_ai_service.agents.requirement.utils import load_current_baseline

BASE = "https://tb/api/"
TOV = "42"
FIXTURE = Path(__file__).parents[2] / "data" / "requirement_baseline.json"


def _conn(baselines: list[dict], *, tree: dict | None = None, udfs: list | None = None):
    """Build a connection that routes legacy GETs by URL and records them."""
    tree = tree if tree is not None else json.loads(FIXTURE.read_text(encoding="utf-8"))
    routes = {
        f"{BASE}tovs/{TOV}/baselines": {"baselines": baselines},
        f"{BASE}tovs/{TOV}/baselines/3/requirements": {"jobID": "j1", "completed": True},
        f"{BASE}requirementsLoaderJob/j1": {
            "id": "j1",
            "completion": {"result": {"Right": tree}},
        },
        f"{BASE}tovs/{TOV}/baselines/3/udfs": udfs if udfs is not None else [],
    }
    conn = MagicMock()
    conn.server_legacy_url = BASE
    conn.calls = []

    def get(url):
        conn.calls.append(url)
        response = MagicMock()
        response.json.return_value = routes[url]
        return response

    conn.legacy_session.get.side_effect = get
    return conn


def _entry(serial: str, baseline_type: str | None = None) -> dict:
    entry = {"key": {"key": {"serial": serial}}}
    if baseline_type is not None:
        entry["type"] = baseline_type
    return entry


class TestLoadCurrentBaseline:
    async def test_loads_the_baseline_marked_current(self):
        conn = _conn([_entry("2", "OLD"), _entry("3", "CURRENT")])

        loaded = await load_current_baseline(conn, TOV, poll_interval=0)

        assert loaded.key.serial == "3"
        assert loaded.reqProjectName == "VSR-Dreamcar"

    async def test_never_loads_the_requirements_of_another_baseline(self):
        conn = _conn([_entry("2", "OLD"), _entry("3", "CURRENT")])

        await load_current_baseline(conn, TOV, poll_interval=0)

        assert not any("baselines/2/" in url for url in conn.calls)

    async def test_attaches_udfs_to_the_loaded_tree(self):
        udfs = [
            {
                "key": {"serial": "473"},
                "value": [{"name": "Extra", "type": "ShortTextfield", "value": "attached"}],
            }
        ]
        conn = _conn([_entry("3", "CURRENT")], udfs=udfs)

        loaded = await load_current_baseline(conn, TOV, poll_interval=0)

        configure_car = loaded.children[0].children[0]
        assert configure_car.requirementKey.serial == "473"
        assert [udf.name for udf in configure_car.udfs] == ["Extra"]

    async def test_raises_when_no_baseline_is_marked_current(self):
        conn = _conn([_entry("2", "OLD"), _entry("3", "OLD")])

        with pytest.raises(RuntimeError, match="CURRENT"):
            await load_current_baseline(conn, TOV, poll_interval=0)

    async def test_raises_rather_than_guessing_when_no_entry_declares_a_type(self):
        conn = _conn([_entry("3")])

        with pytest.raises(RuntimeError, match="CURRENT"):
            await load_current_baseline(conn, TOV, poll_interval=0)
