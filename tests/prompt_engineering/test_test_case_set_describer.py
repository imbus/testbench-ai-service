import os
import textwrap
from pathlib import Path

import pytest
from dotenv import load_dotenv

from testbench_ai_service.agents.test_case_set_describer.agent import TestCaseSetDescriber
from testbench_ai_service.config import DEFAULT_AGENTS, PROMPTS_DIR, LLMConfig, PromptConfig
from testbench_ai_service.llm.openai import OpenAIClient

load_dotenv()


@pytest.mark.prompt_engineering
class TestTestCaseSetDescriberPromptingEnglish:
    @pytest.fixture(autouse=True)
    async def setup(self):
        api_key = os.getenv("OPENAI_API_KEY")
        self.llm_config = LLMConfig()
        self.llm_client = OpenAIClient(api_key=api_key)
        self.default_prompt_config: PromptConfig = DEFAULT_AGENTS["test_case_set_describer"].prompt
        self.prompt_file = Path(PROMPTS_DIR / "en" / self.default_prompt_config.file)
        self.prompt_config = PromptConfig(
            file=self.prompt_file,
            variant=self.default_prompt_config.variant,
        )
        self.describer = TestCaseSetDescriber()
        yield
        await self.llm_client.client.close()

    async def test_describe_test_case_set_en(self):
        step_sequence = textwrap.dedent(
            """
            Update Tree Element Verdict (hovering element)
                Start Web Itorx With CarConfig Report
                Navigate To And Open Verdict Overlay
                Set Verdict Via Hovered Verdict Bar    param:tree_item    param:verdict
                Check Tree Item Verdict    param:tree_item    param:verdict
            """
        )
        parameter_combinations = textwrap.dedent(
            """\
            | uniqueID | tree_item | verdict |
            |-----------|----------|---------|
            | TC-001 | Rolo | Pass |
            | TC-002 | Minigolf | Fail |
            """
        )

        response = await self.describer._get_ai_response(
            llm_client=self.llm_client,
            llm_config=self.llm_config,
            prompt_config=self.prompt_config,
            agent_data={
                "step_sequence": step_sequence,
                "parameter_combinations": parameter_combinations,
            },
        )

        assert isinstance(response.result, str)
        assert response.result != ""
        assert len(response.result) > 100

    async def test_describe_minimal_test_case_en(self):
        step_sequence = textwrap.dedent(
            """
            Delete User
                Open User Management
                Select User    param:username
                Delete Selected User
            """
        )
        parameter_combinations = textwrap.dedent(
            """\
            | uniqueID | username |
            |-----------|----------|
            | TC-001 | admin |
            | TC-002 | testuser |
            """
        )

        response = await self.describer._get_ai_response(
            llm_client=self.llm_client,
            llm_config=self.llm_config,
            prompt_config=self.prompt_config,
            agent_data={
                "step_sequence": step_sequence,
                "parameter_combinations": parameter_combinations,
            },
        )

        assert isinstance(response.result, str)
        assert response.result != ""
        assert len(response.result) > 100


@pytest.mark.prompt_engineering
class TestTestCaseSetDescriberPromptingGerman:
    @pytest.fixture(autouse=True)
    async def setup(self):
        api_key = os.getenv("OPENAI_API_KEY")
        self.llm_config = LLMConfig()
        self.llm_client = OpenAIClient(api_key=api_key)
        self.default_prompt_config: PromptConfig = DEFAULT_AGENTS["test_case_set_describer"].prompt
        self.prompt_file = Path(PROMPTS_DIR / "de" / self.default_prompt_config.file)
        self.prompt_config = PromptConfig(
            file=self.prompt_file,
            variant=self.default_prompt_config.variant,
        )
        self.describer = TestCaseSetDescriber()
        yield
        await self.llm_client.client.close()

    async def test_describe_test_case_set_de(self):
        step_sequence = textwrap.dedent(
            """
            Baumelement-Verdict per Hover aktualisieren
                Web Itorx mit CarConfig-Bericht starten
                Zu Verdict-Overlay navigieren und öffnen
                Verdict per Hovered Verdict Bar setzen    param:tree_item    param:verdict
                Baumelement-Verdict prüfen    param:tree_item    param:verdict
            """
        )
        parameter_combinations = textwrap.dedent(
            """\
            | uniqueID | tree_item | verdict |
            |-----------|----------|---------|
            | TC-001 | Rolo | Bestanden |
            | TC-002 | Minigolf | Fehlgeschlagen |
            """
        )

        response = await self.describer._get_ai_response(
            llm_client=self.llm_client,
            llm_config=self.llm_config,
            prompt_config=self.prompt_config,
            agent_data={
                "step_sequence": step_sequence,
                "parameter_combinations": parameter_combinations,
            },
        )

        assert isinstance(response.result, str)
        assert response.result != ""
        assert len(response.result) > 100

    async def test_describe_minimal_test_case_de(self):
        step_sequence = textwrap.dedent(
            """
            Benutzer löschen
                Benutzerverwaltung öffnen
                Nutzer auswählen    param:username
                Ausgewählten Nutzer löschen
            """
        )
        parameter_combinations = textwrap.dedent(
            """\
            | uniqueID | username |
            |-----------|----------|
            | TC-001 | admin |
            | TC-002 | testbenutzer |
            """
        )

        response = await self.describer._get_ai_response(
            llm_client=self.llm_client,
            llm_config=self.llm_config,
            prompt_config=self.prompt_config,
            agent_data={
                "step_sequence": step_sequence,
                "parameter_combinations": parameter_combinations,
            },
        )

        assert isinstance(response.result, str)
        assert response.result != ""
        assert len(response.result) > 100
