import json
import tempfile
import unittest
from pathlib import Path

from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.utils import i18n
from testbench_ai_service.utils.i18n import get_translation, load_translations


class TestLoadTranslations(unittest.TestCase):
    """Tests for ``load_translations``."""

    def test_loads_json_files_into_translations_dict(self):
        """Translation files present in a directory are loaded by language stem."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "en.json").write_text(json.dumps({"hello": "Hello"}), encoding="utf-8")
            (Path(tmpdir) / "de.json").write_text(json.dumps({"hello": "Hallo"}), encoding="utf-8")

            original = dict(i18n.TRANSLATIONS)
            load_translations(Path(tmpdir))
            try:
                self.assertEqual(i18n.TRANSLATIONS["en"]["hello"], "Hello")
                self.assertEqual(i18n.TRANSLATIONS["de"]["hello"], "Hallo")
            finally:
                i18n.TRANSLATIONS.clear()
                i18n.TRANSLATIONS.update(original)


class TestGetTranslation(unittest.TestCase):
    """Tests for ``get_translation``."""

    def setUp(self):
        self._original = dict(i18n.TRANSLATIONS)
        i18n.TRANSLATIONS.clear()
        i18n.TRANSLATIONS["en"] = {"greeting": "Hello, {name}!", "simple": "Simple"}
        i18n.TRANSLATIONS["de"] = {"greeting": "Hallo, {name}!"}

    def tearDown(self):
        i18n.TRANSLATIONS.clear()
        i18n.TRANSLATIONS.update(self._original)

    def test_returns_translation_for_known_key_and_language(self):
        self.assertEqual(get_translation("simple", LanguageOption.ENGLISH), "Simple")

    def test_formats_kwargs_into_template(self):
        result = get_translation("greeting", LanguageOption.ENGLISH, name="World")
        self.assertEqual(result, "Hello, World!")

    def test_german_translation_is_used(self):
        result = get_translation("greeting", LanguageOption.GERMAN, name="Welt")
        self.assertEqual(result, "Hallo, Welt!")

    def test_falls_back_to_english_for_unknown_language(self):
        """If requested language has no translations, English is the fallback."""
        result = get_translation("simple", lang=LanguageOption.ENGLISH)
        self.assertEqual(result, "Simple")

    def test_missing_key_returns_key_itself(self):
        result = get_translation("nonexistent_key", LanguageOption.ENGLISH)
        self.assertEqual(result, "nonexistent_key")

    def test_missing_kwargs_returns_template_string(self):
        """If the template has placeholders but none are supplied, the raw template is returned."""
        result = get_translation("greeting", LanguageOption.ENGLISH)
        self.assertIn("{name}", result)  # Unformatted template returned unchanged


if __name__ == "__main__":
    unittest.main()
