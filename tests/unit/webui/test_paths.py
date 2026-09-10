"""The edit-path tokenizer, driven by the vectors the TypeScript side also uses.

``tests/fixtures/path_vectors.json`` is consumed by this module and by
``frontend/src/api/paths.test.ts``. The two tokenizers must agree exactly: if
they drift, the browser prunes an edit the server still applies, silently.
Change the fixture, never one side's expectations.
"""

import json
from pathlib import Path

import pytest

from testbench_ai_service.webui.paths import join_path, split_path

VECTORS = json.loads(
    (Path(__file__).parents[3] / "tests" / "fixtures" / "path_vectors.json").read_text(
        encoding="utf-8"
    )
)


def _ids(paths: list[str]) -> list[str]:
    return [repr(path) for path in paths]


ROUNDTRIP = VECTORS["roundtrip"]
SPLIT_ONLY = VECTORS["split_only"]
INVALID = VECTORS["invalid"]


@pytest.mark.parametrize("case", ROUNDTRIP, ids=_ids([case["path"] for case in ROUNDTRIP]))
def test_split_matches_the_shared_vectors(case: dict):
    assert split_path(case["path"]) == case["segments"]


@pytest.mark.parametrize("case", ROUNDTRIP, ids=_ids([case["path"] for case in ROUNDTRIP]))
def test_join_is_the_inverse_of_split(case: dict):
    assert join_path(case["segments"]) == case["path"]


@pytest.mark.parametrize("case", SPLIT_ONLY, ids=_ids([case["path"] for case in SPLIT_ONLY]))
def test_a_non_canonical_path_still_splits(case: dict):
    assert split_path(case["path"]) == case["segments"]


@pytest.mark.parametrize("case", SPLIT_ONLY, ids=_ids([case["path"] for case in SPLIT_ONLY]))
def test_join_emits_the_canonical_spelling(case: dict):
    assert join_path(case["segments"]) == case["joins_to"]


@pytest.mark.parametrize("path", INVALID, ids=_ids(INVALID))
def test_a_malformed_path_is_rejected(path: str):
    with pytest.raises(ValueError, match=r"(?i)edit path"):
        split_path(path)


def test_the_fixture_is_not_empty():
    """A silently empty fixture would make every parametrised test vacuous."""
    assert len(ROUNDTRIP) >= 10
    assert len(INVALID) >= 10


def test_join_refuses_an_empty_segment_list():
    with pytest.raises(ValueError, match=r"(?i)edit path"):
        join_path([])


def test_join_refuses_an_empty_segment():
    """There is no spelling of an empty segment that split_path would accept back."""
    with pytest.raises(ValueError, match=r"(?i)edit path"):
        join_path(["projects", "", "language"])
