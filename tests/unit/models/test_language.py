from testbench_ai_service.models.language import LanguageOption


class TestLanguageOption:
    """Tests for the ``LanguageOption`` enum."""

    def test_english_value_is_en(self):
        assert LanguageOption.ENGLISH.value == "en"

    def test_german_value_is_de(self):
        assert LanguageOption.GERMAN.value == "de"

    def test_str_returns_value(self):
        """__str__ should return the language code, not the enum name."""
        assert str(LanguageOption.ENGLISH) == "en"
        assert str(LanguageOption.GERMAN) == "de"

    def test_string_comparison_with_raw_code(self):
        """LanguageOption inherits from str, so it should compare equal to its value."""
        assert LanguageOption.ENGLISH == "en"
        assert LanguageOption.GERMAN == "de"

    def test_can_construct_from_string_value(self):
        assert LanguageOption("en") is LanguageOption.ENGLISH
        assert LanguageOption("de") is LanguageOption.GERMAN
