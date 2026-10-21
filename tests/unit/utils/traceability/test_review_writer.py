"""Writing one marked block per requirement into a set's review comment."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from testbench_ai_service.utils.traceability import review_writer
from testbench_ai_service.utils.traceability.models import LinkedSet
from testbench_ai_service.utils.traceability.review_writer import (
    WriteOutcome,
    block_pattern,
    remove_block,
    remove_review_block,
    render_block,
    replace_block,
    write_review_block,
)

HEADINGS = ["AI Coverage", "KI-Abdeckung"]


def _block(ref="REQ-42", body="Proves for REQ-42: A1 (full).", heading="AI Coverage", time="t1"):
    return render_block(heading, ref, body, "AI-generated responses may be inaccurate.", time)


REVIEWER_BLOCK = (
    "<b>AI Review - 2026-10-01</b><br/>Looks fine."
    "<div style='padding-top: 5px;'><div style='border-top: 1px solid black;'>"
    "AI-generated responses may be inaccurate.</div></div>"
)


class TestReplaceBlock:
    def test_an_empty_comment_becomes_the_block(self):
        block = _block()

        assert (
            replace_block("<html><body></body></html>", block_pattern(HEADINGS, "REQ-42"), block)
            == block
        )

    def test_the_block_goes_above_an_existing_comment(self):
        block = _block()

        result = replace_block(
            "<p>Please check step 3</p>", block_pattern(HEADINGS, "REQ-42"), block
        )

        assert result == f"{block}<br/><p>Please check step 3</p>"

    def test_a_rerun_replaces_its_own_block_in_place(self):
        old = _block(body="old", time="t1")
        new = _block(body="new", time="t2")
        comment = f"<p>before</p>{old}<p>after</p>"

        result = replace_block(comment, block_pattern(HEADINGS, "REQ-42"), new)

        assert result == f"<p>before</p>{new}<p>after</p>"

    def test_prefix_of_another_requirement_is_not_replaced(self):
        other = _block(ref="REQ-42", body="other")
        own = _block(ref="REQ-4", body="own")

        result = replace_block(other, block_pattern(HEADINGS, "REQ-4"), own)

        assert result == f"{own}<br/>{other}"

    def test_a_block_written_in_the_other_language_is_replaced(self):
        german = _block(heading="KI-Abdeckung", body="alt")
        english = _block(body="new")

        assert replace_block(german, block_pattern(HEADINGS, "REQ-42"), english) == english

    def test_html_normalised_by_testbench_is_still_recognised(self):
        normalised = (
            '<b>AI Coverage REQ-42 - t1</b>\n<br>\n<div style="white-space: pre-wrap">old</div>\n'
            '<div style="padding-top: 5px"><div style="border-top: 1px solid black">x</div></div>'
        )
        new = _block(body="new")

        assert replace_block(normalised, block_pattern(HEADINGS, "REQ-42"), new) == new

    def test_the_reviewer_block_survives(self):
        own = _block(body="new")
        comment = f"{REVIEWER_BLOCK}<br/>{_block(body='old')}"

        result = replace_block(comment, block_pattern(HEADINGS, "REQ-42"), own)

        assert result == f"{REVIEWER_BLOCK}<br/>{own}"

    def test_the_body_is_escaped(self):
        assert "&lt;script&gt;" in _block(body="<script>")


def _linked_set():
    return LinkedSet(
        key="1",
        spec_key="spec-1",
        unique_id="U-1",
        title="Login",
        path="/Auth/Login",
        description="",
        spec_status="Released",
        linked_as_whole=True,
        test_cases=[],
    )


def _conn(patch_error=None):
    conn = MagicMock()
    conn.server_url = "https://tb/api/"
    response = MagicMock()
    response.raise_for_status.side_effect = patch_error
    conn.session.patch.return_value = response
    return conn


def _stub_testbench(monkeypatch, locker_key=None, comment="<p>old note</p>", root="default"):
    locker = SimpleNamespace(key=locker_key) if locker_key else None
    if root == "default":
        root = SimpleNamespace(spec=SimpleNamespace(locker=locker))
    monkeypatch.setattr(
        review_writer, "post_project_tov_structure", lambda *args: SimpleNamespace(root=root)
    )
    monkeypatch.setattr(
        review_writer,
        "get_test_case_set_details",
        lambda *args: SimpleNamespace(
            spec=SimpleNamespace(key="fresh-spec", reviewComment=comment)
        ),
    )


async def _write(conn):
    return await write_review_block(
        conn, "7", "42", "me", _linked_set(), block_pattern(HEADINGS, "REQ-42"), _block()
    )


async def test_an_unlocked_set_gets_the_block_prepended(monkeypatch):
    _stub_testbench(monkeypatch)
    conn = _conn()

    assert await _write(conn) == WriteOutcome.WRITTEN

    url = conn.session.patch.call_args.args[0]
    body = conn.session.patch.call_args.kwargs["json"]
    assert url == "https://tb/api/2/projects/7/specifications/fresh-spec"
    assert set(body) == {"reviewComment"}
    assert (
        body["reviewComment"]["html"] == f"<html><body>{_block()}<br/><p>old note</p></body></html>"
    )


async def test_a_set_locked_by_the_triggering_user_is_written_without_touching_the_lock(
    monkeypatch,
):
    _stub_testbench(monkeypatch, locker_key="me")
    conn = _conn()

    assert await _write(conn) == WriteOutcome.WRITTEN
    assert "locker" not in conn.session.patch.call_args.kwargs["json"]


async def test_a_set_locked_by_someone_else_is_skipped(monkeypatch):
    _stub_testbench(monkeypatch, locker_key="other")
    conn = _conn()

    assert await _write(conn) == WriteOutcome.LOCKED
    conn.session.patch.assert_not_called()


async def test_a_failed_patch_is_reported_not_raised(monkeypatch):
    _stub_testbench(monkeypatch)

    assert await _write(_conn(patch_error=RuntimeError("409"))) == WriteOutcome.FAILED


async def test_the_patch_goes_to_the_spec_key_of_the_fresh_read(monkeypatch):
    _stub_testbench(monkeypatch)
    conn = _conn()

    await _write(conn)

    assert conn.session.patch.call_args.args[0].endswith("/specifications/fresh-spec")


@pytest.mark.parametrize("root", [None, SimpleNamespace(spec=None)])
async def test_an_unknown_lock_state_is_not_written(monkeypatch, root):
    _stub_testbench(monkeypatch, root=root)
    conn = _conn()

    assert await _write(conn) == WriteOutcome.FAILED
    conn.session.patch.assert_not_called()


class TestRemoveBlock:
    def test_a_comment_without_the_block_is_left_alone(self):
        assert remove_block("<p>note</p>", block_pattern(HEADINGS, "REQ-42")) is None

    def test_the_block_and_its_separator_go(self):
        comment = f"{_block()}<br/><p>Please check step 3</p>"

        assert remove_block(comment, block_pattern(HEADINGS, "REQ-42")) == (
            "<p>Please check step 3</p>"
        )

    def test_only_the_block_of_this_requirement_goes(self):
        other = _block(ref="REQ-43")
        comment = f"{_block()}<br/>{other}"

        assert remove_block(comment, block_pattern(HEADINGS, "REQ-42")) == other

    def test_a_comment_of_only_the_block_becomes_empty(self):
        assert remove_block(_block(), block_pattern(HEADINGS, "REQ-42")) == ""


async def test_removing_patches_the_comment_without_the_block(monkeypatch):
    _stub_testbench(monkeypatch, comment=f"<html><body>{_block()}<br/><p>note</p></body></html>")
    conn = _conn()

    outcome = await remove_review_block(
        conn, "7", "42", "me", _linked_set(), block_pattern(HEADINGS, "REQ-42")
    )

    assert outcome == WriteOutcome.WRITTEN
    body = conn.session.patch.call_args.kwargs["json"]
    assert body["reviewComment"]["html"] == "<html><body><p>note</p></body></html>"


async def test_removing_from_a_comment_without_the_block_writes_nothing(monkeypatch):
    _stub_testbench(monkeypatch)
    conn = _conn()

    outcome = await remove_review_block(
        conn, "7", "42", "me", _linked_set(), block_pattern(HEADINGS, "REQ-42")
    )

    assert outcome == WriteOutcome.WRITTEN
    conn.session.patch.assert_not_called()


async def test_removing_skips_a_set_locked_by_someone_else(monkeypatch):
    _stub_testbench(monkeypatch, locker_key="other", comment=_block())
    conn = _conn()

    outcome = await remove_review_block(
        conn, "7", "42", "me", _linked_set(), block_pattern(HEADINGS, "REQ-42")
    )

    assert outcome == WriteOutcome.LOCKED
    conn.session.patch.assert_not_called()
