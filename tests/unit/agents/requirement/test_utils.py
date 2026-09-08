from unittest.mock import MagicMock

import pytest

from testbench_ai_service.agents.requirement.utils import load_requirements

BASE = "https://tb/api/"


def _conn(responses):
    """Build a connection whose legacy GET returns each queued payload in turn."""
    conn = MagicMock()
    conn.server_legacy_url = BASE
    calls: list[str] = []

    def get(url):
        calls.append(url)
        response = MagicMock()
        response.json.return_value = responses.pop(0)
        return response

    conn.legacy_session.get.side_effect = get
    conn.calls = calls
    return conn


class TestLoadRequirements:
    @pytest.mark.asyncio
    async def test_polls_until_completed_then_fetches_result(self):
        conn = _conn(
            [
                {"jobID": "job-1", "completed": False},
                {"jobID": "job-1", "completed": False},
                {"jobID": "job-1", "completed": True},
                {"requirements": [{"name": "REQ-1"}]},
            ]
        )

        result = await load_requirements(conn, "10004", "42", poll_interval=0)

        assert result == {"requirements": [{"name": "REQ-1"}]}
        assert conn.calls == [
            f"{BASE}tovs/10004/baselines/42/requirements",
            f"{BASE}tovs/10004/baselines/42/requirements",
            f"{BASE}tovs/10004/baselines/42/requirements",
            f"{BASE}requirementsLoaderJob/job-1",
        ]

    @pytest.mark.asyncio
    async def test_completed_on_first_poll_skips_sleeping(self):
        conn = _conn([{"jobID": "job-9", "completed": True}, {"requirements": []}])

        result = await load_requirements(conn, "1", "2", poll_interval=0)

        assert result == {"requirements": []}
        assert conn.calls[-1] == f"{BASE}requirementsLoaderJob/job-9"

    @pytest.mark.asyncio
    async def test_uses_job_id_from_the_completed_poll(self):
        """A server that starts a new job per poll must not be read with a stale id."""
        conn = _conn(
            [
                {"jobID": "stale", "completed": False},
                {"jobID": "fresh", "completed": True},
                {"requirements": []},
            ]
        )

        await load_requirements(conn, "1", "2", poll_interval=0)

        assert conn.calls[-1] == f"{BASE}requirementsLoaderJob/fresh"

    @pytest.mark.asyncio
    async def test_raises_when_job_never_completes(self):
        conn = _conn([{"jobID": "job-1", "completed": False}] * 50)

        with pytest.raises(RuntimeError, match="did not complete within"):
            await load_requirements(conn, "10004", "42", timeout=0, poll_interval=0)

    @pytest.mark.asyncio
    async def test_raises_when_no_job_id_returned(self):
        conn = _conn([{"completed": False}])

        with pytest.raises(RuntimeError, match="was not triggered"):
            await load_requirements(conn, "10004", "42", poll_interval=0)
