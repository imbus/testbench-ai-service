import json
from pathlib import Path

from testbench_ai_service.models.language import LanguageOption

LOCALES_DIR = Path(__file__).parent.parent / "locales"

TRANSLATIONS: dict[str, dict] = {}


def load_translations(locales_dir: Path = LOCALES_DIR):
    """
    Load all JSON translation files into the TRANSLATIONS dictionary.

    Args:
        locales_dir (Path): Directory containing translation files (e.g., "en.json", "de.json")
    """
    for file_path in locales_dir.glob("*.json"):
        lang = file_path.stem
        with file_path.open(encoding="utf-8") as file:
            TRANSLATIONS[lang] = json.load(file)


def get_translation(key: str, lang: LanguageOption = LanguageOption.ENGLISH, **kwargs):
    """
    Retrieve a translated message by key and language, with optional formatting.

    Args:
        key (str): Translation key (e.g., "review_started_message")
        lang (LanguageOption): Language of translation
        **kwargs: Variables to format into the translation string

    Returns:
        str: Translated and formatted message
    """
    messages = TRANSLATIONS.get(lang.value, TRANSLATIONS.get(LanguageOption.ENGLISH.value, {}))
    template: str = messages.get(key, key)
    try:
        return template.format(**kwargs)
    except KeyError:
        return template
