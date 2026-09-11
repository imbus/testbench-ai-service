from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from testbench_ai_service.webui.multi_write import write_all


def test_writes_every_file(tmp_path):
    a, b = tmp_path / "a.yaml", tmp_path / "b.jinja"
    result = write_all({a: "alpha", b: "beta"})
    assert a.read_text(encoding="utf-8") == "alpha"
    assert b.read_text(encoding="utf-8") == "beta"
    assert set(result.written) == {a, b}


def test_backs_up_the_previous_contents(tmp_path):
    a = tmp_path / "a.yaml"
    a.write_text("old", encoding="utf-8")
    result = write_all({a: "new"})
    assert a.read_text(encoding="utf-8") == "new"
    assert Path(f"{a}.bak").read_text(encoding="utf-8") == "old"
    assert result.backups[a] == Path(f"{a}.bak")


def test_a_new_file_has_no_backup(tmp_path):
    a = tmp_path / "a.yaml"
    result = write_all({a: "new"})
    assert a not in result.backups
    assert not Path(f"{a}.bak").exists()


def test_a_missing_directory_writes_nothing(tmp_path):
    good = tmp_path / "good.yaml"
    bad = tmp_path / "absent" / "bad.yaml"
    with pytest.raises(HTTPException) as e:
        write_all({good: "x", bad: "y"})
    assert e.value.status_code == 400
    assert not good.exists(), "staging must fail before any target is replaced"


def test_a_failure_part_way_through_replace_rolls_back(tmp_path):
    a, b = tmp_path / "a.yaml", tmp_path / "b.yaml"
    a.write_text("old-a", encoding="utf-8")
    b.write_text("old-b", encoding="utf-8")

    real_replace = __import__("os").replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("simulated failure on the second replace")
        return real_replace(src, dst)

    with (
        patch("testbench_ai_service.webui.multi_write.os.replace", side_effect=flaky),
        pytest.raises(HTTPException),
    ):
        write_all({a: "new-a", b: "new-b"})

    assert a.read_text(encoding="utf-8") == "old-a", "the first replace must be undone"
    assert b.read_text(encoding="utf-8") == "old-b"


def test_a_rolled_back_file_that_never_existed_before_is_removed(tmp_path):
    # Alphabetically first, so it is replaced (and committed) before the
    # second replace -- for "existing" -- is made to fail.
    brand_new = tmp_path / "brandnew.yaml"
    existing = tmp_path / "existing.yaml"
    existing.write_text("old-existing", encoding="utf-8")

    real_replace = __import__("os").replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("simulated failure on the second replace")
        return real_replace(src, dst)

    with (
        patch("testbench_ai_service.webui.multi_write.os.replace", side_effect=flaky),
        pytest.raises(HTTPException),
    ):
        write_all({brand_new: "new-content", existing: "new-existing"})

    assert existing.read_text(encoding="utf-8") == "old-existing"
    assert not brand_new.exists(), "a rolled-back file with no backup must be removed"


def test_temp_file_for_the_failed_replace_is_cleaned_up(tmp_path):
    a, b = tmp_path / "a.yaml", tmp_path / "b.yaml"
    a.write_text("old-a", encoding="utf-8")
    b.write_text("old-b", encoding="utf-8")

    real_replace = __import__("os").replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("simulated failure on the second replace")
        return real_replace(src, dst)

    with (
        patch("testbench_ai_service.webui.multi_write.os.replace", side_effect=flaky),
        pytest.raises(HTTPException),
    ):
        write_all({a: "new-a", b: "new-b"})

    assert list(tmp_path.glob("*.tmp")) == []
    assert list(tmp_path.glob(".*.tmp")) == []


def test_writes_utf8_without_newline_translation(tmp_path):
    a = tmp_path / "a.yaml"
    write_all({a: "erste\nzweite\nÜberschrift"})
    assert a.read_bytes() == "erste\nzweite\nÜberschrift".encode()


def test_an_empty_set_is_a_no_op(tmp_path):
    result = write_all({})
    assert result.written == []
