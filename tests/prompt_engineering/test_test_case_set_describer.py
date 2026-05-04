import os
import textwrap
import unittest

from dotenv import load_dotenv

from testbench_ai_service.agents.test_case_set_describer.agent import TestCaseSetDescriber
from testbench_ai_service.config import PROMPTS_DIR, LLMConfig, PromptConfig
from testbench_ai_service.llm.openai import OpenAIClient

load_dotenv()


class TestTestCaseSetDescriberPromptingEnglish(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        api_key = os.getenv("OPENAI_API_KEY")

        self.llm_config = LLMConfig()
        self.llm_client = OpenAIClient(api_key=api_key)
        self.describer = TestCaseSetDescriber()
        self.prompt_file = (PROMPTS_DIR / "en" / "test_case_set_describer.yaml").resolve()
        self.prompt_name = "TestCaseSetDescriber"
        self.prompt_variant = "full-description"

    async def asyncTearDown(self):
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

        prompt_config = PromptConfig(
            file=self.prompt_file,
            name=self.prompt_name,
            variant=self.prompt_variant,
            placeholder_data={
                "step_sequence": step_sequence,
                "parameter_combinations": parameter_combinations,
            },
        )

        response = await self.describer._get_ai_response(
            llm_client=self.llm_client,
            llm_config=self.llm_config,
            prompt_config=prompt_config,
        )

        self.assertIsInstance(response.result, str)
        self.assertNotEqual(response.result, "")
        self.assertGreater(len(response.result), 100)

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

        prompt_config = PromptConfig(
            file=self.prompt_file,
            name=self.prompt_name,
            variant=self.prompt_variant,
            placeholder_data={
                "step_sequence": step_sequence,
                "parameter_combinations": parameter_combinations,
            },
        )

        response = await self.describer._get_ai_response(
            llm_client=self.llm_client,
            llm_config=self.llm_config,
            prompt_config=prompt_config,
        )

        self.assertIsInstance(response.result, str)
        self.assertNotEqual(response.result, "")
        self.assertGreater(len(response.result), 100)


class TestTestCaseSetDescriberPromptingGerman(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        api_key = os.getenv("OPENAI_API_KEY")

        self.llm_config = LLMConfig()
        self.llm_client = OpenAIClient(api_key=api_key)
        self.describer = TestCaseSetDescriber()
        self.prompt_file = (PROMPTS_DIR / "de" / "test_case_set_describer.yaml").resolve()
        self.prompt_name = "TestCaseSetDescriber"
        self.prompt_variant = "full-description"

    async def asyncTearDown(self):
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

        prompt_config = PromptConfig(
            file=self.prompt_file,
            name=self.prompt_name,
            variant=self.prompt_variant,
            placeholder_data={
                "step_sequence": step_sequence,
                "parameter_combinations": parameter_combinations,
            },
        )

        response = await self.describer._get_ai_response(
            llm_client=self.llm_client,
            llm_config=self.llm_config,
            prompt_config=prompt_config,
        )

        self.assertIsInstance(response.result, str)
        self.assertNotEqual(response.result, "")
        self.assertGreater(len(response.result), 100)

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

        prompt_config = PromptConfig(
            file=self.prompt_file,
            name=self.prompt_name,
            variant=self.prompt_variant,
            placeholder_data={
                "step_sequence": step_sequence,
                "parameter_combinations": parameter_combinations,
            },
        )

        response = await self.describer._get_ai_response(
            llm_client=self.llm_client,
            llm_config=self.llm_config,
            prompt_config=prompt_config,
        )

        self.assertIsInstance(response.result, str)
        self.assertNotEqual(response.result, "")
        self.assertGreater(len(response.result), 100)
