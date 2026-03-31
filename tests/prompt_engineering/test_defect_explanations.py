import os
import textwrap
import unittest

from dotenv import load_dotenv

from testbench_ai_service.config import PROMPTS_DIR, LLMConfig, PromptConfig
from testbench_ai_service.llm.openai import OpenAIClient
from testbench_ai_service.usecases.defect_explanations.service import DefectExplainer

load_dotenv()


class TestDefectExplanationsPromptingEnglish(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        api_key = os.getenv("OPENAI_API_KEY")

        self.llm_config = LLMConfig()
        self.llm_client = OpenAIClient(api_key=api_key)
        self.explainer = DefectExplainer()
        self.prompt_file = (PROMPTS_DIR / "en" / "defect_explanations.yaml").resolve()
        self.prompt_name = "DefectExplanations"
        self.prompt_variant = "DEU"

    async def asyncTearDown(self):
        await self.llm_client.client.close()

    async def test_explain_element_not_found_en(self):
        failed_test_case = textwrap.dedent(
            """
            Update Tree Element Verdict (hovering element)
                ►[Pass]          Start Web Itorx With CarConfig Report
                ►[Pass]          Navigate To And Open Verdict Overlay
                ►[Pass]          Set Verdict Via Hovered Verdict Bar    tree_item=Rolo    verdict=Fail
                ►[Fail]          Check Tree Item Verdict    tree_item=Rolo    verdict=Fail
            """
        )

        prompt_config = PromptConfig(
            file=self.prompt_file,
            name=self.prompt_name,
            variant=self.prompt_variant,
            placeholder_data={
                "failed_test_case": failed_test_case,
                "error_message": "Element with identifier 'Verdict Badge' not found on the page",
            },
        )

        response = await self.explainer._get_ai_response(
            llm_client=self.llm_client,
            llm_config=self.llm_config,
            prompt_config=prompt_config,
        )

        self.assertIsInstance(response.result, str)
        self.assertNotEqual(response.result, "")
        self.assertNotIn("\n", response.result)
        self.assertLess(len(response.result), 500)

    async def test_explain_value_mismatch_en(self):
        failed_test_case = textwrap.dedent(
            """
            Start Web Itorx With CarConfig Report
                ►[Pass]          Start Program    path=/usr/local/bin/web-itorx
                ►[Pass]          Navigate To And Activate Loading Overlay
                ►[Pass]          Select Report    tree_item=CarConfig_Annual_Report
                ►[Fail]          Check Page URL    url=https://carconfig.example.com/report/123
            """
        )

        prompt_config = PromptConfig(
            file=self.prompt_file,
            name=self.prompt_name,
            variant=self.prompt_variant,
            placeholder_data={
                "failed_test_case": failed_test_case,
                "error_message": "Expected: 'https://carconfig.example.com/report/123', but was: 'https://carconfig.example.com/dashboard'",
            },
        )

        response = await self.explainer._get_ai_response(
            llm_client=self.llm_client,
            llm_config=self.llm_config,
            prompt_config=prompt_config,
        )

        self.assertIsInstance(response.result, str)
        self.assertNotEqual(response.result, "")
        self.assertNotIn("\n", response.result)
        self.assertLess(len(response.result), 500)

    async def test_explain_early_failure_with_cascade_en(self):
        failed_test_case = textwrap.dedent(
            """
            Expand Next Element
                ▼[Fail]          Start Web Itorx
                ►[Skipped]       Navigate To And Deactivate Leaf Only Mode
                ►[Skipped]       Open CarConfig Report Via Open Report Button
                ►[Skipped]       Select Tree Item    tree_item=Rolo
                ►[Skipped]       Check Element Tree Item Descendants Display    tree_item=Rolo    descendants_names=Minigolf
            """
        )

        prompt_config = PromptConfig(
            file=self.prompt_file,
            name=self.prompt_name,
            variant=self.prompt_variant,
            placeholder_data={
                "failed_test_case": failed_test_case,
                "error_message": "Timeout after 30000 ms while waiting for browser context",
            },
        )

        response = await self.explainer._get_ai_response(
            llm_client=self.llm_client,
            llm_config=self.llm_config,
            prompt_config=prompt_config,
        )

        self.assertIsInstance(response.result, str)
        self.assertNotEqual(response.result, "")
        self.assertNotIn("\n", response.result)
        self.assertLess(len(response.result), 500)


class TestDefectExplanationsPromptingGerman(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        api_key = os.getenv("OPENAI_API_KEY")

        self.llm_config = LLMConfig()
        self.llm_client = OpenAIClient(api_key=api_key)
        self.explainer = DefectExplainer()
        self.prompt_file = (PROMPTS_DIR / "de" / "defect_explanations.yaml").resolve()
        self.prompt_name = "DefectExplanations"
        self.prompt_variant = "DEU"

    async def asyncTearDown(self):
        await self.llm_client.client.close()

    async def test_explain_element_not_found_de(self):
        failed_test_case = textwrap.dedent(
            """
            Baumelement-Verdict per Hover aktualisieren
                ►[Pass]          Web Itorx mit CarConfig-Bericht starten
                ►[Pass]          Zu Verdict-Overlay navigieren und öffnen
                ►[Pass]          Verdict per Hovered Verdict Bar setzen    tree_item=Rolo    verdict=Fail
                ►[Fail]          Baumelement-Verdict prüfen    tree_item=Rolo    verdict=Fail
            """
        )

        prompt_config = PromptConfig(
            file=self.prompt_file,
            name=self.prompt_name,
            variant=self.prompt_variant,
            placeholder_data={
                "failed_test_case": failed_test_case,
                "error_message": "Element mit der Bezeichnung 'Verdict Badge' wurde auf der Seite nicht gefunden",
            },
        )

        response = await self.explainer._get_ai_response(
            llm_client=self.llm_client,
            llm_config=self.llm_config,
            prompt_config=prompt_config,
        )

        self.assertIsInstance(response.result, str)
        self.assertNotEqual(response.result, "")
        self.assertNotIn("\n", response.result)
        self.assertLess(len(response.result), 500)

    async def test_explain_value_mismatch_de(self):
        failed_test_case = textwrap.dedent(
            """
            Web Itorx mit CarConfig Report starten
                ►[Pass]          Programm starten    path=/usr/local/bin/web-itorx
                ►[Pass]          Zu Lade-Overlay navigieren und aktivieren
                ►[Pass]          Report auswählen    tree_item=CarConfig_Jahresbericht
                ►[Fail]          Seiten-URL prüfen    url=https://carconfig.example.com/report/123
            """
        )

        prompt_config = PromptConfig(
            file=self.prompt_file,
            name=self.prompt_name,
            variant=self.prompt_variant,
            placeholder_data={
                "failed_test_case": failed_test_case,
                "error_message": "Erwartet: 'https://carconfig.example.com/report/123', aber war: 'https://carconfig.example.com/dashboard'",
            },
        )

        response = await self.explainer._get_ai_response(
            llm_client=self.llm_client,
            llm_config=self.llm_config,
            prompt_config=prompt_config,
        )

        self.assertIsInstance(response.result, str)
        self.assertNotEqual(response.result, "")
        self.assertNotIn("\n", response.result)
        self.assertLess(len(response.result), 500)

    async def test_explain_early_failure_with_cascade_de(self):
        failed_test_case = textwrap.dedent(
            """
            Nachfolgende Baumelemente expandieren
                ▼[Fail]          Den Web Itorx starten
                ►[Skipped]       Zum Leaf-Only-Modus navigieren und deaktivieren
                ►[Skipped]       Auto-Konfigurationsbericht öffnen
                ►[Skipped]       Baumelement wählen    tree_item=Rolo
                ►[Skipped]       Baumstruktur-Nachfolger prüfen    tree_item=Rolo    descendants_names=Minigolf
            """
        )

        prompt_config = PromptConfig(
            file=self.prompt_file,
            name=self.prompt_name,
            variant=self.prompt_variant,
            placeholder_data={
                "failed_test_case": failed_test_case,
                "error_message": "Zeitüberschreitung nach 30000 ms beim Warten auf Browser-Kontext",
            },
        )

        response = await self.explainer._get_ai_response(
            llm_client=self.llm_client,
            llm_config=self.llm_config,
            prompt_config=prompt_config,
        )

        self.assertIsInstance(response.result, str)
        self.assertNotEqual(response.result, "")
        self.assertNotIn("\n", response.result)
        self.assertLess(len(response.result), 500)
