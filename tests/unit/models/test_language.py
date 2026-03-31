import unittest

from testbench_ai_service.models.language import LanguageOption


class TestLanguageOption(unittest.TestCase):
    """Tests for the ``LanguageOption`` enum."""

    def test_english_value_is_en(self):
        self.assertEqual(LanguageOption.ENGLISH.value, "en")

    def test_german_value_is_de(self):
        self.assertEqual(LanguageOption.GERMAN.value, "de")

    def test_str_returns_value(self):
        """__str__ should return the language code, not the enum name."""
        self.assertEqual(str(LanguageOption.ENGLISH), "en")
        self.assertEqual(str(LanguageOption.GERMAN), "de")

    def test_string_comparison_with_raw_code(self):
        """LanguageOption inherits from str, so it should compare equal to its value."""
        self.assertEqual(LanguageOption.ENGLISH, "en")
        self.assertEqual(LanguageOption.GERMAN, "de")

    def test_can_construct_from_string_value(self):
        self.assertIs(LanguageOption("en"), LanguageOption.ENGLISH)
        self.assertIs(LanguageOption("de"), LanguageOption.GERMAN)


if __name__ == "__main__":
    unittest.main()
