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


# Phase 3: project-scoped paths quote segments that a bare split would
# mis-address. A TestBench project name is an arbitrary string.


def test_a_quoted_segment_addresses_a_project_name_containing_a_dot():
    merged = merge_edits({}, {'projects."Release 2.0".language': "en"})

    assert merged == {"projects": {"Release 2.0": {"language": "en"}}}


def test_a_quoted_segment_removes_a_key_under_a_dotted_project_name():
    base = {"projects": {"a.b": {"language": "en", "agents": {}}}}

    merged = merge_edits(base, {'projects."a.b".language': None})

    assert merged == {"projects": {"a.b": {"agents": {}}}}


def test_a_dotted_project_name_is_not_confused_with_a_nested_table():
    """'projects."a.b".x' and 'projects.a.b.x' address different things."""
    merged = merge_edits(
        {},
        {
            'projects."a.b".language': "en",
            "projects.a.b.language": "de",
        },
    )

    assert merged == {
        "projects": {
            "a.b": {"language": "en"},
            "a": {"b": {"language": "de"}},
        }
    }


def test_a_quoted_path_and_its_quoted_prefix_still_collide():
    with pytest.raises(HTTPException) as exc:
        validate_edit_paths(
            {
                'projects."Release 2.0"': {"language": "en"},
                'projects."Release 2.0".language': "de",
            }
        )

    assert exc.value.status_code == 400
    assert "conflict" in exc.value.detail.lower()


def test_a_dotted_project_name_does_not_collide_with_its_bare_lookalike():
    validate_edit_paths(
        {
            'projects."a.b".language': "en",
            "projects.a.b.language": "de",
        }
    )


def test_two_spellings_of_one_address_collide():
    """Same key, two spellings, two values -- and one of them would be lost.

    The prefix check exists so an overlay cannot carry both a table and a key
    inside it. The same reasoning applies to the exact duplicate: whichever
    entry merge_edits happens to see last wins, silently, and the operator
    approved a diff built from only one of them.
    """
    with pytest.raises(HTTPException) as exc:
        validate_edit_paths(
            {
                "projects.My Project.language": "de",
                'projects."My Project".language': "en",
            }
        )

    assert exc.value.status_code == 400
    assert "conflict" in exc.value.detail.lower()


def test_deepest_real_path_is_within_the_segment_limit():
    validate_edit_paths({'projects."Release 2.0".agents.reviewer.prompt.vars.max_findings': 10})


def test_a_quoted_segment_may_contain_whitespace_at_its_edges():
    merged = merge_edits({}, {'projects." padded ".language': "en"})

    assert merged == {"projects": {" padded ": {"language": "en"}}}


@pytest.mark.parametrize(
    "path",
    [
        'projects."unterminated.language',
        'projects."a"b.language',
        r'projects."bad\escape".language',
        '""',
        'projects."".language',
    ],
)
def test_a_malformed_quoted_path_is_refused(path: str):
    with pytest.raises(HTTPException) as exc:
        validate_edit_paths({path: 1})

    assert exc.value.status_code == 400


def test_a_quoted_path_that_is_too_deep_is_still_refused():
    path = 'a."b".c."d".e."f".g."h".i'

    with pytest.raises(HTTPException) as exc:
        validate_edit_paths({path: 1})

    assert exc.value.status_code == 400
