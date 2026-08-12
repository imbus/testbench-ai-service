import re


def normalize_project_name(project_name: str) -> str:
    """
    Normalize a TestBench project name for use in environment variable names.

    Replaces every run of non-alphanumeric characters with a single underscore
    and uppercases the result, e.g. "Car Configurator" -> "CAR_CONFIGURATOR".
    """
    return re.sub(r"\W+", "_", project_name).upper()
