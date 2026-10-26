"""The defect explainer prompt honours its boolean variable as the plugin sends it."""

from pathlib import Path

import pytest

from testbench_ai_service.utils.build_prompt_utils import build_messages
from testbench_ai_service.utils.prompt_utils import get_prompt_definition

PROMPTS = Path(__file__).parents[4] / "testbench_ai_service" / "prompts"
SELF_CHECK = {"en": "# Self-Check Before Output", "de": "# Selbstprüfung vor Ausgabe"}


@pytest.mark.parametrize("language", ["en", "de"])
@pytest.mark.parametrize(
    ("value", "expected"), [("true", True), ("false", False), (True, True), (False, False)]
)
def test_validate_output_follows_the_switch(language, value, expected):
    # A trigger sends strings ("false" must not count as on); a config.toml
    # preset and the console's preview send real booleans.
    prompt_file = PROMPTS / language / "defect_explainer" / "prompt.yaml"
    variant = get_prompt_definition(prompt_file).variants[0]

    messages = build_messages(variant.messages, {}, {"validate_output": value}, prompt_file.parent)

    assert (SELF_CHECK[language] in messages[0].content) is expected
