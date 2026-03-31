import unittest

from testbench_ai_service.usecases.test_case_set_reviews.models import (
    DEFAULT_ENGLISH_GLOSSARY,
    DEFAULT_GERMAN_GLOSSARY,
)


class TestDefaultEnglishGlossary(unittest.TestCase):
    def test_is_a_non_empty_string(self):
        self.assertIsInstance(DEFAULT_ENGLISH_GLOSSARY, str)
        self.assertTrue(DEFAULT_ENGLISH_GLOSSARY.strip())

    def test_contains_common_action_keywords(self):
        for keyword in ("Start", "Click", "Check", "Create", "Delete"):
            with self.subTest(keyword=keyword):
                self.assertIn(keyword, DEFAULT_ENGLISH_GLOSSARY)

    def test_does_not_contain_german_words(self):
        # Basic sanity: the English glossary should not contain obvious German-only terms
        self.assertNotIn("Drücke", DEFAULT_ENGLISH_GLOSSARY)
        self.assertNotIn("Wähle", DEFAULT_ENGLISH_GLOSSARY)


class TestDefaultGermanGlossary(unittest.TestCase):
    def test_is_a_non_empty_string(self):
        self.assertIsInstance(DEFAULT_GERMAN_GLOSSARY, str)
        self.assertTrue(DEFAULT_GERMAN_GLOSSARY.strip())

    def test_contains_common_german_action_keywords(self):
        for keyword in ("Starte", "Drücke", "Prüfe", "Erstelle", "Lösche"):
            with self.subTest(keyword=keyword):
                self.assertIn(keyword, DEFAULT_GERMAN_GLOSSARY)

    def test_does_not_contain_english_only_keywords(self):
        # The German glossary must not contain purely English action keywords.
        # "Check" is intentionally excluded from this assertion because the German
        # glossary legitimately uses the compound word "Checkboxen".
        self.assertNotIn("'Click'", DEFAULT_GERMAN_GLOSSARY)
        self.assertNotIn("'Create'", DEFAULT_GERMAN_GLOSSARY)


class TestGlossariesAreDistinct(unittest.TestCase):
    def test_english_and_german_glossaries_differ(self):
        self.assertNotEqual(DEFAULT_ENGLISH_GLOSSARY, DEFAULT_GERMAN_GLOSSARY)


if __name__ == "__main__":
    unittest.main()
