import pytest
from fastapi import HTTPException

from testbench_ai_service.webui.config_io import REDACTED_SENTINEL
from testbench_ai_service.webui.edits import (
    MAX_EDITS,
    merge_edits,
    validate_edit_paths,
)


def test_a_scalar_edit_sets_a_top_level_key():
    assert merge_edits({"port": 8010}, {"port": 9999}) == {"port": 9999}


def test_a_dotted_edit_sets_a_nested_key_without_disturbing_siblings():
    base = {"llm_config": {"provider": "openai", "model": "gpt-4o"}}

    merged = merge_edits(base, {"llm_config.model": "gpt-4.1"})

    assert merged == {"llm_config": {"provider": "openai", "model": "gpt-4.1"}}


def test_a_dotted_edit_creates_missing_intermediate_tables():
    assert merge_edits({}, {"logging.file.log_level": "DEBUG"}) == {
        "logging": {"file": {"log_level": "DEBUG"}}
    }


def test_a_none_value_removes_the_key():
    base = {"llm_config": {"provider": "openai", "model": "gpt-4o"}}

    merged = merge_edits(base, {"llm_config.model": None})

    assert merged == {"llm_config": {"provider": "openai"}}


def test_removing_an_absent_key_is_not_an_error():
    assert merge_edits({}, {"llm_config.model": None}) == {}


def test_the_base_dict_is_never_mutated():
    """The caller diffs against the disk config it passed in."""
    base = {"llm_config": {"provider": "openai"}}

    merge_edits(base, {"llm_config.provider": "anthropic", "port": 1})

    assert base == {"llm_config": {"provider": "openai"}}


def test_a_list_value_survives_intact():
    merged = merge_edits({}, {"trusted_proxies": ["10.0.0.1", "10.0.0.2"]})

    assert merged == {"trusted_proxies": ["10.0.0.1", "10.0.0.2"]}


def test_the_redaction_sentinel_is_refused():
    """GET /config redacts credentials; posting one back must never write it."""
    with pytest.raises(HTTPException) as exc:
        validate_edit_paths({"llm_config.api_key": REDACTED_SENTINEL})

    assert exc.value.status_code == 400
    assert "redacted" in exc.value.detail.lower()


def test_the_redaction_sentinel_is_refused_inside_a_nested_value():
    with pytest.raises(HTTPException) as exc:
        validate_edit_paths({"projects": {"P": {"llm_config": {"api_key": REDACTED_SENTINEL}}}})

    assert exc.value.status_code == 400


def test_the_redaction_sentinel_is_refused_inside_a_list():
    with pytest.raises(HTTPException) as exc:
        validate_edit_paths({"trusted_proxies": ["10.0.0.1", REDACTED_SENTINEL]})

    assert exc.value.status_code == 400


@pytest.mark.parametrize(
    "path",
    [
        "",
        " ",
        ".",
        "..",
        "port.",
        ".port",
        "llm_config..model",
        "a.b.c.d.e.f.g.h.i",
        "port\x00",
    ],
)
def test_a_malformed_path_is_refused(path: str):
    with pytest.raises(HTTPException) as exc:
        validate_edit_paths({path: 1})

    assert exc.value.status_code == 400


def test_a_well_formed_path_is_accepted():
    validate_edit_paths(
        {
            "port": 8010,
            "llm_config.model": "gpt-4o",
            "logging.file.log_level": "DEBUG",
            "projects.My Project.language": "en",
            "trusted_proxies": None,
        }
    )


def test_too_many_edits_are_refused():
    with pytest.raises(HTTPException) as exc:
        validate_edit_paths({f"key_{index}": index for index in range(MAX_EDITS + 1)})

    assert exc.value.status_code == 400


# Fix 1: Reject when existing parent is not a dict (data destruction)
def test_merge_refuses_to_destroy_a_scalar_value():
    """A path like 'port.sub' conflicts with existing scalar 'port'."""
    with pytest.raises(HTTPException) as exc:
        merge_edits({"port": 8010}, {"port.sub": 1})

    assert exc.value.status_code == 400
    assert "conflicts" in exc.value.detail.lower()
    assert "port" in exc.value.detail.lower()


def test_absent_parent_still_builds_intermediate_tables():
    """Regression: absent parent must still create intermediate dicts."""
    assert merge_edits({}, {"logging.file.log_level": "DEBUG"}) == {
        "logging": {"file": {"log_level": "DEBUG"}}
    }


def test_existing_dict_parent_is_still_reused():
    """Regression: existing dict parent must not be replaced."""
    assert merge_edits({"logging": {"file": {}}}, {"logging.file.log_level": "DEBUG"}) == {
        "logging": {"file": {"log_level": "DEBUG"}}
    }


# Fix 2: Reject path prefix collisions (ambiguous merge order)
def test_validate_refuses_path_and_its_prefix():
    """Paths 'a' and 'a.b' conflict due to insertion order ambiguity."""
    with pytest.raises(HTTPException) as exc:
        validate_edit_paths({"a": "scalar", "a.b": 1})

    assert exc.value.status_code == 400
    assert "conflict" in exc.value.detail.lower()


def test_validate_refuses_path_and_its_prefix_reverse_order():
    """Same conflict regardless of insertion order."""
    with pytest.raises(HTTPException) as exc:
        validate_edit_paths({"a.b": 1, "a": "scalar"})

    assert exc.value.status_code == 400


def test_validate_refuses_deeper_prefix_collision():
    """Three-level collision: logging, logging.file, logging.file.log_level."""
    with pytest.raises(HTTPException) as exc:
        validate_edit_paths({"logging.file": {}, "logging.file.log_level": "DEBUG"})

    assert exc.value.status_code == 400


def test_validate_accepts_leaf_only_overlay():
    """Real UI sends only leaf paths; all leaves are accepted."""
    validate_edit_paths(
        {
            "port": 1,
            "llm_config.model": "x",
            "logging.file.log_level": "DEBUG",
        }
    )


# Fix 3: Reject sentinel in set and frozenset
def test_the_redaction_sentinel_is_refused_inside_a_set():
    with pytest.raises(HTTPException) as exc:
        validate_edit_paths({"some_set": {"item1", REDACTED_SENTINEL}})

    assert exc.value.status_code == 400


def test_the_redaction_sentinel_is_refused_inside_a_frozenset():
    with pytest.raises(HTTPException) as exc:
        validate_edit_paths({"some_frozenset": frozenset(["item1", REDACTED_SENTINEL])})

    assert exc.value.status_code == 400


# Fix 4: Reject segments with leading/trailing whitespace
def test_validate_refuses_segment_with_leading_whitespace():
    with pytest.raises(HTTPException) as exc:
        validate_edit_paths({" port": 1})

    assert exc.value.status_code == 400


def test_validate_refuses_segment_with_trailing_whitespace():
    with pytest.raises(HTTPException) as exc:
        validate_edit_paths({"port ": 1})

    assert exc.value.status_code == 400


def test_validate_refuses_segment_with_both_spaces():
    with pytest.raises(HTTPException) as exc:
        validate_edit_paths({" port ": 1})

    assert exc.value.status_code == 400
