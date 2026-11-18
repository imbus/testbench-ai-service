from __future__ import annotations

import csv
import hashlib
import io
import zipfile

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
    with pytest.raises(WheelError, match="unsafe path"):
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
    with pytest.raises(WheelError, match="not a valid wheel"):
        read_wheel(path)


def test_read_wheel_rejects_bad_filename(tmp_path):
    path = tmp_path / "nonsense.whl"
    path.write_bytes(b"x")
    with pytest.raises(WheelError, match="file name"):
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
    with pytest.raises(WheelError, match="already exists"):
        extract_wheel(whl, target)


DIST_INFO = "acme_tb_agents-1.0.0.dist-info"


def _metadata(name: str, version: str) -> bytes:
    return f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n".encode()


@pytest.mark.parametrize("name", ["../evil", "a/b", "-x"])
def test_read_wheel_rejects_malicious_metadata_name(tmp_path, name):
    whl = build_wheel(
        tmp_path,
        files={"acme/__init__.py": ""},
        extra_entries={f"{DIST_INFO}/METADATA": _metadata(name, "1.0.0")},
    )
    with pytest.raises(WheelError, match="invalid name"):
        read_wheel(whl)


@pytest.mark.parametrize("version", ["1/../..", "not a version"])
def test_read_wheel_rejects_malicious_metadata_version(tmp_path, version):
    whl = build_wheel(
        tmp_path,
        files={"acme/__init__.py": ""},
        extra_entries={f"{DIST_INFO}/METADATA": _metadata("acme-tb-agents", version)},
    )
    with pytest.raises(WheelError, match="invalid version"):
        read_wheel(whl)


@pytest.mark.parametrize(("name", "version"), [("other", "1.0.0"), ("acme-tb-agents", "2.0")])
def test_read_wheel_rejects_filename_metadata_mismatch(tmp_path, name, version):
    whl = build_wheel(
        tmp_path,
        files={"acme/__init__.py": ""},
        extra_entries={f"{DIST_INFO}/METADATA": _metadata(name, version)},
    )
    with pytest.raises(WheelError, match="does not match its file name"):
        read_wheel(whl)


def test_read_wheel_accepts_equivalent_name_and_version_spelling(tmp_path):
    whl = build_wheel(
        tmp_path,
        files={"acme/__init__.py": ""},
        extra_entries={f"{DIST_INFO}/METADATA": _metadata("Acme.TB_Agents", "1.0.0")},
    )
    assert read_wheel(whl).name == "acme-tb-agents"


def test_read_wheel_rejects_unsafe_directory_entry(tmp_path):
    whl = build_wheel(tmp_path, files={"acme/__init__.py": ""}, extra_entries={"../x/": b""})
    with pytest.raises(WheelError, match="unsafe path"):
        read_wheel(whl)


def test_read_wheel_rejects_colon_in_path_segment(tmp_path):
    whl = build_wheel(
        tmp_path, files={"acme/__init__.py": ""}, extra_entries={"acme/a.py:stream": b"x"}
    )
    with pytest.raises(WheelError, match="unsafe path"):
        read_wheel(whl)


def test_read_wheel_rejects_empty_record_hash(tmp_path):
    whl = build_wheel(tmp_path, files={"acme/__init__.py": "x"})
    with zipfile.ZipFile(whl) as zf:
        items = {i.filename: zf.read(i) for i in zf.infolist()}
    record_name = f"{DIST_INFO}/RECORD"
    rows = list(csv.reader(io.StringIO(items[record_name].decode())))
    rows[0][1] = ""
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows(rows)
    items[record_name] = out.getvalue().encode()
    with zipfile.ZipFile(whl, "w") as zf:
        for name, data in items.items():
            zf.writestr(name, data)
    with pytest.raises(WheelError, match="no hash"):
        read_wheel(whl)
