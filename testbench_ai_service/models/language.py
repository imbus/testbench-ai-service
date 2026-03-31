from enum import Enum


class LanguageOption(str, Enum):
    ENGLISH = "en"
    GERMAN = "de"

    def __str__(self):
        return self.value
