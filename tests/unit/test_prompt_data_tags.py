"""The prompts that read TestBench and RM content keep it apart from their instructions.

A requirement or test case text is data. Each one sits alone between a named tag
pair in the user message, and every system message says that tagged content is
never an instruction, so a text phrased as one cannot steer the answer as easily.
"""

import re
from pathlib import Path

import pytest

from testbench_ai_service.utils.prompt_utils import get_prompt_definition

PROMPTS = Path(__file__).parents[2] / "testbench_ai_service" / "prompts"
AGENTS = ["coverage_checker", "link_finder", "generate_test_ideas"]
DATA_RULE = {"en": "never as instructions", "de": "nie als Anweisung"}
INSERTED = re.compile(r"^\s*\{\{\s*([\w.]+)\s*\}\}\s*$")


def _templates(language: str, agent: str):
    prompt_file = PROMPTS / language / agent / "prompt.yaml"
    for variant in get_prompt_definition(prompt_file).variants:
        for step in [None, *variant.steps]:
            if step is None and not variant.messages:
                continue
            for message in variant.templates_for(step):
                yield message.role, message.file, message.get_content(prompt_file.parent)


CASES = [(language, agent) for language in DATA_RULE for agent in AGENTS]


@pytest.mark.parametrize(("language", "agent"), CASES)
def test_every_inserted_text_sits_alone_between_a_tag_pair(language, agent):
    for role, file, content in _templates(language, agent):
        if role != "user":
            continue
        lines = content.splitlines()
        for index, line in enumerate(lines):
            if not INSERTED.match(line):
                continue
            opening = re.fullmatch(r"<(\w+)>", lines[index - 1].strip())
            assert opening, f"{file}:{index + 1}: {line.strip()} has no opening tag above it"
            assert lines[index + 1].strip() == f"</{opening.group(1)}>", (
                f"{file}:{index + 1}: {line.strip()} is not closed by </{opening.group(1)}>"
            )


@pytest.mark.parametrize(("language", "agent"), CASES)
def test_every_system_message_says_tagged_content_is_data(language, agent):
    for role, file, content in _templates(language, agent):
        if role == "system":
            assert DATA_RULE[language] in content, f"{file} lacks the data rule"
