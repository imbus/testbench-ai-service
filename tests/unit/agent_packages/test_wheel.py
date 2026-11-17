from __future__ import annotations

import hashlib

import pytest

from testbench_ai_service.agent_packages import wheel
from testbench_ai_service.agent_packages.wheel import WheelError, extract_wheel, read_wheel
from tests.helpers.wheels import build_wheel


def test_read_wheel_returns_metadata(tmp_path):
    whl = build_wheel(
        tmp_path,
        files={"acme/__init__.py": ""},
        entry_points={"acme_rater": "acme.rater.agent:RaterAgent"},
        requires_dist=["testbench-ai-service>=4.0"],
    )
    info = read_wheel(whl)
    assert (info.name, info.version) == ("acme-tb-agents", "1.0.0")
    assert info.filename == whl.name
    assert info.entry_points == {"acme_rater": "acme.rater.agent:RaterAgent"}
    assert info.requires_dist == ["testbench-ai-service>=4.0"]
    assert info.top_level_modules == ["acme"]
    assert info.sha256 == hashlib.sha256(whl.read_bytes()).hexdigest()
    assert info.size == whl.stat().st_size


@pytest.mark.parametrize("entry", ["../evil.py", "/abs.py", "C:/abs.py", "a/../../b.py"])
def test_read_wheel_rejects_unsafe_paths(tmp_path, entry):
    whl = build_wheel(tmp_path, files={"acme/__init__.py": ""}, extra_entries={entry: b"x"})
    with pytest.raises(WheelError):
        read_wheel(whl)


def test_read_wheel_rejects_symlink(tmp_path):
    whl = build_wheel(tmp_path, files={"acme/__init__.py": ""}, symlink="acme/link")
    with pytest.raises(WheelError, match="symlink"):
        read_wheel(whl)


def test_read_wheel_rejects_bad_record_hash(tmp_path):
    whl = build_wheel(tmp_path, files={"acme/__init__.py": ""}, corrupt_record=True)
    with pytest.raises(WheelError, match="RECORD"):
        read_wheel(whl)


def test_read_wheel_rejects_too_many_files(tmp_path, monkeypatch):
    monkeypatch.setattr(wheel, "MAX_FILES", 3)
    whl = build_wheel(tmp_path, files={"acme/__init__.py": "", "acme/a.py": ""})
    with pytest.raises(WheelError, match="files"):
        read_wheel(whl)


def test_read_wheel_rejects_unpacked_size(tmp_path, monkeypatch):
    monkeypatch.setattr(wheel, "MAX_UNPACKED_BYTES", 10)
    whl = build_wheel(tmp_path, files={"acme/__init__.py": "x" * 100})
    with pytest.raises(WheelError, match="unpacked"):
        read_wheel(whl)


def test_read_wheel_rejects_foreign_tag(tmp_path):
    whl = build_wheel(tmp_path, files={"acme/__init__.py": ""}, tag="cp27-cp27m-manylinux1_x86_64")
    with pytest.raises(WheelError, match="not compatible"):
        read_wheel(whl)


def test_read_wheel_rejects_non_zip(tmp_path):
    path = tmp_path / "acme-1.0.0-py3-none-any.whl"
    path.write_bytes(b"not a zip")
    with pytest.raises(WheelError):
        read_wheel(path)


def test_read_wheel_rejects_bad_filename(tmp_path):
    path = tmp_path / "nonsense.whl"
    path.write_bytes(b"x")
    with pytest.raises(WheelError):
        read_wheel(path)


def test_top_level_modules_derived_from_paths(tmp_path):
    whl = build_wheel(tmp_path, files={"acme/__init__.py": "", "other.py": ""})
    assert read_wheel(whl).top_level_modules == ["acme", "other"]


def test_extract_wheel_is_atomic(tmp_path):
    whl = build_wheel(tmp_path, files={"acme/__init__.py": "x = 1\n"})
    target = tmp_path / "out" / "pkg"
    target.parent.mkdir()
    extract_wheel(whl, target)
    assert (target / "acme" / "__init__.py").read_text() == "x = 1\n"
    assert not target.with_name("pkg.tmp").exists()
    with pytest.raises(WheelError):
        extract_wheel(whl, target)
