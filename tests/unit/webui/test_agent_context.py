from dataclasses import dataclass
from pathlib import Path
from typing import Optional, TypedDict

from pydantic import BaseModel

from testbench_ai_service.models.config import AgentConfig, PromptConfig
from testbench_ai_service.webui.agent_context import (
    MAX_DEPTH,
    agent_context_sample,
    agent_data_sample,
    describe,
)


@dataclass
class Spec:
    description: str
    priority: int | None


@dataclass
class Case:
    uniqueID: str
    spec: Spec
    tags: list[str]


class Owner(BaseModel):
    name: str


class Data(TypedDict, total=False):
    text: str
    maybe: Optional[str]  # noqa: UP045 -- typing.Union, not types.UnionType
    case: Case
    cases: dict[str, Case]
    owner: Owner


@dataclass
class Node:
    name: str
    parent: "Node | None"


class TestDescribe:
    def test_leaves_name_their_type(self):
        assert describe(str) == "<str>"
        assert describe(int | None) == "<int | None>"
        assert describe(Optional[str]) == "<str | None>"  # noqa: UP045

    def test_a_list_samples_one_item(self):
        assert describe(list[str]) == ["<str>"]

    def test_a_mapping_samples_one_key(self):
        assert describe(dict[str, int]) == {"<key>": "<int>"}

    def test_a_dataclass_expands_its_fields(self):
        assert describe(Spec) == {"description": "<str>", "priority": "<int | None>"}

    def test_a_recursive_type_stops_at_itself(self):
        assert describe(Node) == {"name": "<str>", "parent": "<Node | None>"}

    def test_nesting_past_the_depth_limit_is_summarised(self):
        assert describe(Spec, depth=MAX_DEPTH) == "<Spec>"


def test_the_agent_data_sample_walks_every_kind():
    assert agent_data_sample(Data) == {
        "text": "<str>",
        "maybe": "<str | None>",
        "case": {
            "uniqueID": "<str>",
            "spec": {"description": "<str>", "priority": "<int | None>"},
            "tags": ["<str>"],
        },
        "cases": {
            "<key>": {
                "uniqueID": "<str>",
                "spec": {"description": "<str>", "priority": "<int | None>"},
                "tags": ["<str>"],
            }
        },
        "owner": {"name": "<str>"},
    }


def _agent(class_path: str, file: str) -> AgentConfig:
    return AgentConfig(
        enabled=True,
        endpoint_path="/x",
        class_path=class_path,
        prompt=PromptConfig(file=Path(file)),
    )


REVIEWER = "testbench_ai_service.agents.test_case_set_reviewer.agent.TestCaseSetReviewer"


class TestAgentContextSample:
    def test_reads_the_agent_data_class_of_the_prompts_agent(self):
        sample = agent_context_sample({"r": _agent(REVIEWER, "reviewer/prompt.yaml")}, "reviewer")
        assert sample["test_case_set"] == "<str>"
        assert sample["test_case_set_obj"]["details"]["uniqueID"] == "<str>"

    def test_a_windows_separator_still_names_the_directory(self):
        sample = agent_context_sample({"r": _agent(REVIEWER, r"reviewer\prompt.yaml")}, "reviewer")
        assert "test_case_set" in sample

    def test_an_agent_on_another_prompt_contributes_nothing(self):
        assert agent_context_sample({"r": _agent(REVIEWER, "other/prompt.yaml")}, "reviewer") == {}

    def test_an_unimportable_class_contributes_nothing(self):
        agents = {"r": _agent("no.such.module.Agent", "reviewer/prompt.yaml")}
        assert agent_context_sample(agents, "reviewer") == {}
