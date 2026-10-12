import os
import tempfile
from pathlib import Path

import pytest
from fastapi import HTTPException

from testbench_ai_service.webui.atomic import write_atomic


def test_writing_a_new_file_creates_it_and_reports_no_backup(tmp_path: Path):
    target = tmp_path / "config.toml"

    backup = write_atomic(target, "port = 8010\n")

    assert backup is None
    assert target.read_text(encoding="utf-8") == "port = 8010\n"


def test_overwriting_keeps_the_previous_contents_as_bak(tmp_path: Path):
    target = tmp_path / "config.toml"
    target.write_text("port = 1\n", encoding="utf-8")

    backup = write_atomic(target, "port = 2\n")

    assert backup == tmp_path / "config.toml.bak"
    assert backup.read_text(encoding="utf-8") == "port = 1\n"
    assert target.read_text(encoding="utf-8") == "port = 2\n"


def test_a_second_write_replaces_the_bak_rather_than_stacking_them(tmp_path: Path):
    target = tmp_path / "config.toml"
    target.write_text("port = 1\n", encoding="utf-8")

    write_atomic(target, "port = 2\n")
    write_atomic(target, "port = 3\n")

    assert (tmp_path / "config.toml.bak").read_text(encoding="utf-8") == "port = 2\n"
    assert not (tmp_path / "config.toml.bak.bak").exists()
    assert target.read_text(encoding="utf-8") == "port = 3\n"


def test_no_temp_files_are_left_behind(tmp_path: Path):
    target = tmp_path / "config.toml"
    target.write_text("port = 1\n", encoding="utf-8")

    write_atomic(target, "port = 2\n")

    assert sorted(entry.name for entry in tmp_path.iterdir()) == [
        "config.toml",
        "config.toml.bak",
    ]


def test_the_temp_file_lands_in_the_target_directory(tmp_path: Path, monkeypatch):
    """os.replace is only atomic within one filesystem, so the temp file must
    be a sibling of the target -- never in the system temp dir."""
    target = tmp_path / "config.toml"
    seen: list[str] = []
    real_mkstemp = tempfile.mkstemp

    def spy(*args, **kwargs):
        seen.append(str(kwargs.get("dir")))
        return real_mkstemp(*args, **kwargs)

    monkeypatch.setattr("testbench_ai_service.webui.atomic.tempfile.mkstemp", spy)
    write_atomic(target, "port = 8010\n")

    assert seen == [str(tmp_path)]


def test_utf8_content_round_trips(tmp_path: Path):
    target = tmp_path / "config.toml"

    write_atomic(target, 'note = "Pruefstand — groesser"\n')

    assert target.read_text(encoding="utf-8") == 'note = "Pruefstand — groesser"\n'


def test_the_file_is_written_with_lf_only(tmp_path: Path):
    """A CRLF-translating write would change every line of the diff on Windows."""
    target = tmp_path / "config.toml"

    write_atomic(target, "a = 1\nb = 2\n")

    assert target.read_bytes() == b"a = 1\nb = 2\n"


def test_a_missing_parent_directory_is_a_400(tmp_path: Path):
    target = tmp_path / "nope" / "config.toml"

    with pytest.raises(HTTPException) as exc:
        write_atomic(target, "port = 8010\n")

    assert exc.value.status_code == 400


def test_a_failed_replace_leaves_the_original_intact_and_no_temp_file_but_keeps_the_backup(
    tmp_path: Path, monkeypatch
):
    """When os.replace fails, the target is untouched. The .bak is redundant with
    the unchanged original, but it exists because the only state-mutating call
    is last (os.replace), so raised => target unchanged is an invariant."""
    target = tmp_path / "config.toml"
    target.write_text("port = 1\n", encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", boom)

    with pytest.raises(HTTPException):
        write_atomic(target, "port = 2\n")

    assert target.read_text(encoding="utf-8") == "port = 1\n"
    # No .tmp files left behind by cleanup
    assert not any(entry.name.endswith(".tmp") for entry in tmp_path.iterdir())
    # .bak exists (redundant with unchanged original, but expected under this ordering)
    assert (tmp_path / "config.toml.bak").read_text(encoding="utf-8") == "port = 1\n"


def test_a_failed_backup_write_leaves_the_original_intact_and_raises_400(
    tmp_path: Path, monkeypatch
):
    """This test is the regression guard for keeping os.replace as the last
    state-mutating call. If .bak write moved after replace, a failed .bak write
    would leave the new content on disk with no backup and a false failure
    reported. Here, the .bak write fails and we must see the original content
    unchanged, no .tmp file, and a 400 raised."""
    target = tmp_path / "config.toml"
    target.write_text("port = 1\n", encoding="utf-8")

    real_write_bytes = Path.write_bytes

    def selective_write_bytes(self: Path, data: bytes) -> None:
        if str(self).endswith(".bak"):
            raise OSError("write_bytes failed for .bak")
        return real_write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", selective_write_bytes)

    with pytest.raises(HTTPException) as exc:
        write_atomic(target, "port = 2\n")

    assert exc.value.status_code == 400
    assert target.read_text(encoding="utf-8") == "port = 1\n"
    assert not any(entry.name.endswith(".tmp") for entry in tmp_path.iterdir())
