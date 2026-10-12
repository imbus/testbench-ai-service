import sys

import pytest
from fastapi import HTTPException

from testbench_ai_service.webui.prompts import resolve_template_file


@pytest.fixture
def tree(tmp_path):
    """prompts_dir/de/agent/prompt.yaml with a sibling template."""
    agent = tmp_path / "de" / "agent"
    agent.mkdir(parents=True)
    (agent / "prompt.yaml").write_text("name: x", encoding="utf-8")
    (agent / "system.jinja").write_text("hello", encoding="utf-8")
    return tmp_path


def test_resolves_a_sibling_template(tree):
    prompt = tree / "de" / "agent" / "prompt.yaml"
    assert (
        resolve_template_file(tree, prompt, "system.jinja")
        == (tree / "de" / "agent" / "system.jinja").resolve()
    )


def test_resolves_relative_to_the_prompt_not_the_language_dir(tree):
    """MessageTemplate.get_content uses the prompt's own parent as base_path."""
    other = tree / "de" / "shared.jinja"
    other.write_text("shared", encoding="utf-8")
    prompt = tree / "de" / "agent" / "prompt.yaml"
    assert resolve_template_file(tree, prompt, "../shared.jinja") == other.resolve()


def test_refuses_traversal_out_of_prompts_dir(tree):
    prompt = tree / "de" / "agent" / "prompt.yaml"
    with pytest.raises(HTTPException) as e:
        resolve_template_file(tree, prompt, "../../../secrets.jinja")
    assert e.value.status_code == 400


def test_refuses_an_absolute_path_outside_prompts_dir(tree, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "evil.jinja"
    outside.write_text("x", encoding="utf-8")
    prompt = tree / "de" / "agent" / "prompt.yaml"
    with pytest.raises(HTTPException) as e:
        resolve_template_file(tree, prompt, str(outside))
    assert e.value.status_code == 400


def test_refuses_a_non_allowlisted_suffix(tree):
    (tree / "de" / "agent" / "notes.txt").write_text("x", encoding="utf-8")
    prompt = tree / "de" / "agent" / "prompt.yaml"
    with pytest.raises(HTTPException) as e:
        resolve_template_file(tree, prompt, "notes.txt")
    assert e.value.status_code == 400


@pytest.mark.parametrize(
    "ref",
    [
        pytest.param(
            "system.jinja.",
            marks=pytest.mark.skipif(
                sys.platform == "win32",
                reason=(
                    "Windows strips a trailing dot from an existing filename before "
                    "this module ever sees it: Path('system.jinja.').resolve() is "
                    "indistinguishable from Path('system.jinja').resolve() once "
                    "system.jinja exists, so it resolves to the same legitimately "
                    "suffixed file rather than to something with suffix '.'. There is "
                    "no bypass -- the request just gets canonicalized to the real "
                    "file -- but the POSIX distinction this case exercises does not "
                    "exist on this platform."
                ),
            ),
        ),
        "system.jinja:evil",
    ],
)
def test_refuses_suffix_evasion_spellings(tree, ref):
    """security.py's docstring: allowlist the RESOLVED path's suffix."""
    prompt = tree / "de" / "agent" / "prompt.yaml"
    with pytest.raises(HTTPException) as e:
        resolve_template_file(tree, prompt, ref)
    assert e.value.status_code == 400


def test_refuses_an_empty_reference(tree):
    prompt = tree / "de" / "agent" / "prompt.yaml"
    with pytest.raises(HTTPException) as e:
        resolve_template_file(tree, prompt, "  ")
    assert e.value.status_code == 400


def test_missing_template_is_404_not_400(tree):
    prompt = tree / "de" / "agent" / "prompt.yaml"
    with pytest.raises(HTTPException) as e:
        resolve_template_file(tree, prompt, "absent.jinja")
    assert e.value.status_code == 404


def test_refuses_a_symlink_pointing_outside(tree, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "evil.jinja"
    outside.write_text("x", encoding="utf-8")
    link = tree / "de" / "agent" / "link.jinja"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted on this machine")
    prompt = tree / "de" / "agent" / "prompt.yaml"
    with pytest.raises(HTTPException) as e:
        resolve_template_file(tree, prompt, "link.jinja")
    assert e.value.status_code == 400
