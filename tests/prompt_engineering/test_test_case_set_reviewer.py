import os
import textwrap
from pathlib import Path

import pytest
from dotenv import load_dotenv

from testbench_ai_service.agents.test_case_set_reviewer.agent import TestCaseSetReviewer
from testbench_ai_service.config import DEFAULT_AGENTS, PROMPTS_DIR, LLMConfig, PromptConfig
from testbench_ai_service.llm.openai import OpenAIClient

load_dotenv()


@pytest.mark.prompt_engineering
class TestTestCaseSetReviewerPromptingEnglish:
    @pytest.fixture(autouse=True)
    async def setup(self):
        api_key = os.getenv("OPENAI_API_KEY")
        self.llm_config = LLMConfig()
        self.llm_client = OpenAIClient(api_key=api_key)
        self.reviewer = TestCaseSetReviewer()
        self.default_prompt_config: PromptConfig = DEFAULT_AGENTS["test_case_set_reviewer"].prompt
        self.prompt_file = Path(PROMPTS_DIR / "en" / self.default_prompt_config.file)
        self.prompt_config = PromptConfig(
            file=self.prompt_file,
            variant=self.default_prompt_config.variant,
        )
        self.glossary = textwrap.dedent(
            """
            - 'Set': Used for text fields, checkboxes, or similar elements. Examples: Set Login, Set Description
            - 'Click': Used for buttons, icons, or similar elements. Examples: Click Ok, Click Update
            - 'Select': Used for radio buttons, tab pages, menu entries, or similar elements. Examples: Select Project Tab, Select Project Tree Element
            - 'Remove': Used for checkboxes, specific assignments, or similar elements. Examples: Remove Rights Option, Remove Checkbox, Remove Requirements Assignment
            - 'Open': Used for dialogs, context menus, or similar elements; not used for application startups. Examples: openProjectManagement, openProjectTreeContextMenu
            - 'Check': Used for verifying the state of any component. Examples: Check Rights Allocation Is Editable, Check Activity Status
            - 'Create': Used for creating business-related entities. Examples: Create Test Topic, Create User Assignment
            - 'Delete': Used for deleting business-related entities. Examples: Delete Test Topic, Delete User
            - 'Close': Used for closing dialogs or business-related processes. Examples: Close Variant Management, Close Issue List
            - 'Expand' for tree structures. Examples: Expand project tree, Expand folder
            - 'Collapse' for tree structures. Examples: Collapse project tree, Collapse folder
            """
        ).strip()
        yield
        await self.llm_client.client.close()

    async def test_review_tcs_with_bad_tc_name_en(self):
        test_case = textwrap.dedent(
            """
            ITB-UC-124-TC112
                Start Web Itorx With CarConfig Report    step_type:flow
                Navigate To And Activate Verdict Overlay    step_type:flow
                Set Verdict Via Hovered Verdict Bar    param:tree_item    param:verdict    step_type:flow
                Check Tree Item Verdict    param:tree_item    param:verdict    step_type:check
            """
        ).strip()

        response = await self.reviewer._get_ai_response(
            llm_client=self.llm_client,
            llm_config=self.llm_config,
            prompt_config=self.prompt_config,
            agent_data={"test_case": test_case},
        )

        assert isinstance(response.result, str)
        assert response.result != ""
        assert "Review successful! No findings." not in response.result

    async def test_review_tcs_with_non_imperative_steps_en(self):
        test_case = textwrap.dedent(
            """
            Discard Unsaved Changes
                Start Web Itorx    step_type:flow
                Open Empty Report Via Header    step_type:flow
                Check Tree Item Exists    param:tree_item    step_type:check
                Sets Tree Item Verdict Via Main Content    param:tree_item    param:verdict    step_type:flow
                Check Tree Item Verdict    param:tree_item    param:verdict    step_type:check
                Open Report And Discard Changes    param:report    step_type:flow
                Check Tree Item Exists    param:tree_item    step_type:check
                Opening Empty Report Via Header    step_type:flow
                Check Tree Item Verdict    param:tree_item    param:verdict    step_type:check
            """
        ).strip()

        response = await self.reviewer._get_ai_response(
            llm_client=self.llm_client,
            llm_config=self.llm_config,
            prompt_config=self.prompt_config,
            agent_data={"test_case": test_case},
        )

        assert isinstance(response.result, str)
        assert response.result != ""
        assert "Review successful! No findings." not in response.result

    async def test_review_tcs_with_spelling_mistakes_en(self):
        test_case = textwrap.dedent(
            """
            Start Web Itorx With CarConfig Report
                Start program    param:path    step_type:flow
                Navigate To And Active Loading Overlaye    step_type:flow
                Select Report    param:tree_item    step_type:flow
                Check Page URL    param:url    step_type:check
            """
        ).strip()

        response = await self.reviewer._get_ai_response(
            llm_client=self.llm_client,
            llm_config=self.llm_config,
            prompt_config=self.prompt_config,
            agent_data={"test_case": test_case},
        )

        assert isinstance(response.result, str)
        assert response.result != ""
        assert "Review successful! No findings." not in response.result

    async def test_review_tcs_with_missing_validation_step_en(self):
        test_case = textwrap.dedent(
            """
            Start Web Itorx With CarConfig Report
                Start program    param:path    step_type:flow
                Navigate To And Activate Loading Overlay    step_type:flow
                Select Report    param:tree_item    step_type:flow
            """
        ).strip()

        response = await self.reviewer._get_ai_response(
            llm_client=self.llm_client,
            llm_config=self.llm_config,
            prompt_config=self.prompt_config,
            agent_data={"test_case": test_case},
        )

        assert isinstance(response.result, str)
        assert response.result != ""
        assert "Review successful! No findings." not in response.result

    async def test_review_tcs_with_incorrect_description_en(self):
        test_case = textwrap.dedent(
            """
            Delete User
                Start TestBench    step_type:flow
                Navigate To Login Page    step_type:flow
                Enter Credentials    param:username    param:password    step_type:flow
                Navigate To Dashboard    step_type:flow
                Open Permission Settings    step_type:flow
                Select User    param:temp_username    step_type:flow
                Delete Selected User    step_type:flow
                Check No Error Message Visible    step_type:check
                Check User Not In List  param:temp_username    step_type:check
            """
        ).strip()
        test_case_set_description = "Checks if temporary user accounts can delete admin accounts."

        response = await self.reviewer._get_ai_response(
            llm_client=self.llm_client,
            llm_config=self.llm_config,
            prompt_config=self.prompt_config,
            agent_data={
                "test_case_set_description": test_case_set_description,
                "test_case": test_case,
            },
        )

        assert isinstance(response.result, str)
        assert response.result != ""
        assert "Review successful! No findings." not in response.result

    async def test_review_tcs_with_non_glossary_synonyms_en(self):
        test_case = textwrap.dedent(
            """
            Login And Delete Temporary User
                Start TestBench    step_type:flow
                Navigate To Login Page    step_type:flow
                Enter Credentials    param:username    param:password    step_type:flow
                Navigate To Dashboard    step_type:flow
                Maximize Tree Item Structure    step_type:flow
                Open Permission Settings    step_type:flow
                Select User    param:temp_username    step_type:flow
                Remove Selected User    step_type:flow
                Check No Error Message Visible    step_type:check
                Validate User Not In List  param:temp_username    step_type:check
            """
        ).strip()

        prompt_config = PromptConfig(
            file=self.prompt_config.file,
            variant=self.prompt_config.variant,
            vars={"glossary": self.glossary},
        )

        response = await self.reviewer._get_ai_response(
            llm_client=self.llm_client,
            llm_config=self.llm_config,
            prompt_config=prompt_config,
            agent_data={"test_case": test_case},
        )

        assert isinstance(response.result, str)
        assert response.result != ""
        assert "Review successful! No findings." not in response.result


@pytest.mark.prompt_engineering
class TestTestCaseSetReviewerPromptingGerman:
    @pytest.fixture(autouse=True)
    async def setup(self):
        api_key = os.getenv("OPENAI_API_KEY")
        self.llm_config = LLMConfig()
        self.llm_client = OpenAIClient(api_key=api_key)
        self.reviewer = TestCaseSetReviewer()
        self.default_prompt_config: PromptConfig = DEFAULT_AGENTS["test_case_set_reviewer"].prompt
        self.prompt_file = Path(PROMPTS_DIR / "de" / self.default_prompt_config.file)
        self.prompt_config = PromptConfig(
            file=self.prompt_file,
            variant=self.default_prompt_config.variant,
        )
        self.glossary = textwrap.dedent(
            """
            - "Setze" für Textfelder, Checkboxen oder Ähnliches. Beispiele: Setze Login, Setze Beschreibung
            - "Drücke" für Buttons, Icons oder Ähnliches. Beispiele: Drücke Ok, Drücke Aktualisieren
            - "Wähle" für Radiobuttons, Tabkarten, Menüeinträge oder Ähnliches. Beispiele: Wähle Projekttabkarte, Wähle Projektbaumelement
            - "Entferne" für Checkboxen, Zuordnungen oder Ähnliches. Beispiele: Entferne Admin-Rechte, Entferne Checkbox, Entferne Anforderungszuordnung
            - "Öffne" für Dialoge, Kontextmenüs oder Ähnliches. Beispiele: Öffne Projektverwaltung, Öffne Projektbaumelement-Kontextmenü
            - "Prüfe" für sämtliche Komponenten. Beispiele: Prüfe Rechteoption Editierbarkeit, Prüfe Aktivitätsstatus
            - "Erstelle" für sämtliche fachliche Vorgänge. Beispiele: Erstelle Testthema, Erstelle Nutzerzuordnung
            - "Lösche" für sämtliche fachliche Vorgänge. Beispiele: Lösche Testthema, Lösche Benutzer
            - "Schließe" für Dialoge oder fachliche Vorgänge. Beispiele: Schließe Variantenverwaltung, Schließe Meldungsliste
            - "Expandiere" für Baumstrukturen. Beispiele: Expandiere Projektbaum, Expandiere Ordner
            - "Kollabiere" für Baumstrukturen. Beispiele: Kollabiere Projektbaum, Kollabiere Ordner
            """
        ).strip()
        yield
        await self.llm_client.client.close()

    async def test_review_tcs_with_bad_tc_name_de(self):
        test_case = textwrap.dedent(
            """
            ITB-UC-124-TC112
                Starte Web Itorx mit CarConfig-Bericht    step_type:flow
                Navigiere zu und öffne Verdict Overlay    step_type:flow
                Setze Verdict per Hovered Verdict Bar    param:tree_item    param:verdict    step_type:flow
                Prüfe Baumelement Verdict    param:tree_item    param:verdict    step_type:check
            """
        ).strip()

        response = await self.reviewer._get_ai_response(
            llm_client=self.llm_client,
            llm_config=self.llm_config,
            prompt_config=self.prompt_config,
            agent_data={"test_case": test_case},
        )

        assert isinstance(response.result, str)
        assert response.result != ""
        assert "Review erfolgreich! Keine Befunde." not in response.result

    async def test_review_tcs_with_non_imperative_steps_de(self):
        test_case = textwrap.dedent(
            """
            Nicht gespeicherte Änderungen verwerfen
                Starte Web Itorx    step_type:flow
                Öffne leeren Bericht per Header    step_type:flow
                Prüfe Baumelement existiert    param:tree_item    step_type:check
                Setzt Baumelement Verdict per Main Content    param:tree_item    param:verdict    step_type:flow
                Prüfe Baumelement Verdict    param:tree_item    param:verdict    step_type:check
                Öffne Bericht und setze Änderungen zurück    param:report    step_type:flow
                Prüfe Baumelement existiert    param:tree_item    step_type:check
                Leeren Bericht per Header öffnen    step_type:flow
                Prüfe Baumelement Verdict    param:tree_item    param:verdict    step_type:check
            """
        ).strip()

        response = await self.reviewer._get_ai_response(
            llm_client=self.llm_client,
            llm_config=self.llm_config,
            prompt_config=self.prompt_config,
            agent_data={"test_case": test_case},
        )

        assert isinstance(response.result, str)
        assert response.result != ""
        assert "Review erfolgreich! Keine Befunde." not in response.result

    async def test_review_tcs_with_spelling_mistakes_de(self):
        test_case = textwrap.dedent(
            """
            Web-Itorx Baum-Verdict
                Starte Web-Itorx mit CarConfig-Bericht    step_type:flow
                Navigiere zu und aktivire Verdict Overlay    step_type:flow
                Setze Verdict per Hovered Verdict Bar    param:tree_item    param:verdict    step_type:flow
                Prüfe Baumelement Verdict    param:tree_item    param:verdict    step_type:check
            """
        ).strip()

        response = await self.reviewer._get_ai_response(
            llm_client=self.llm_client,
            llm_config=self.llm_config,
            prompt_config=self.prompt_config,
            agent_data={"test_case": test_case},
        )

        assert isinstance(response.result, str)
        assert response.result != ""
        assert "Review erfolgreich! Keine Befunde." not in response.result

    async def test_review_tcs_with_missing_validation_step_de(self):
        test_case = textwrap.dedent(
            """
            Web Itorx mit CarConfig Report starten
                Starte Programm    param:path    step_type:flow
                Navigiere zu und aktiviere Lade-Overlay    step_type:flow
                Wähle Report    param:tree_item    step_type:flow
            """
        ).strip()

        response = await self.reviewer._get_ai_response(
            llm_client=self.llm_client,
            llm_config=self.llm_config,
            prompt_config=self.prompt_config,
            agent_data={"test_case": test_case},
        )

        assert isinstance(response.result, str)
        assert response.result != ""
        assert "Review erfolgreich! Keine Befunde." not in response.result

    async def test_review_tcs_with_incorrect_description_de(self):
        test_case = textwrap.dedent(
            """
            Temporären Nutzer löschen
                Starte TestBench    step_type:flow
                Navigiere zur Login-Maske    step_type:flow
                Setze Credentials    param:username    param:password    step_type:flow
                Navigiere zum Dashboard    step_type:flow
                Öffne Accountverwaltung    step_type:flow
                Wähle Nutzer    param:temp_username    step_type:flow
                Lösche ausgewählten Nutzer    step_type:flow
                Prüfe Fehlermeldung nicht vorhanden    step_type:check
                Prüfe Nutzer nicht in Liste    param:temp_username    step_type:check
            """
        ).strip()
        test_case_set_description = (
            "Prüft, ob ein Admin durch einen temporären Nutzer gelöscht werden kann."
        )

        response = await self.reviewer._get_ai_response(
            llm_client=self.llm_client,
            llm_config=self.llm_config,
            prompt_config=self.prompt_config,
            agent_data={
                "test_case_set_description": test_case_set_description,
                "test_case": test_case,
            },
        )

        assert isinstance(response.result, str)
        assert response.result != ""
        assert "Review erfolgreich! Keine Befunde." not in response.result

    async def test_review_tcs_with_non_glossary_synonyms_de(self):
        test_case = textwrap.dedent(
            """
            Login And Delete Temporary User
                Starte TestBench    step_type:flow
                Navigiere zu Login-Maske    step_type:flow
                Setze Credentials    param:username    param:password    step_type:flow
                Navigiere zu Dashboard    step_type:flow
                Maximiere Baum    step_type:flow
                Öffne Account-Einstellungen    step_type:flow
                Wähle Nutzer    param:temp_username    step_type:flow
                Entferne ausgewählten Nutzer    step_type:flow
                Prüfe Fehlermeldung nicht vorhanden    step_type:check
                Validiere Nutzer nicht in Liste    param:temp_username    step_type:check
            """
        ).strip()

        prompt_config = PromptConfig(
            file=self.prompt_config.file,
            variant=self.prompt_config.variant,
            vars={"glossary": self.glossary},
        )

        response = await self.reviewer._get_ai_response(
            llm_client=self.llm_client,
            llm_config=self.llm_config,
            prompt_config=prompt_config,
            agent_data={"test_case": test_case},
        )

        assert isinstance(response.result, str)
        assert response.result != ""
        assert "Review erfolgreich! Keine Befunde." not in response.result
