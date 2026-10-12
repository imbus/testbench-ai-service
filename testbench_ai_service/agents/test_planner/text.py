"""The text a test case is embedded as."""


def build_embedding_text(
    set_name: str, description: str, steps: list[str], parameters: dict[str, str]
) -> str:
    """
    Join the parts that describe a test case into one line-based text.

    The order is fixed and parameters are sorted, so equal input gives a
    byte-equal text; the embedding cache relies on that.

    Args:
        set_name: Name of the test case set.
        description: Plain-text description of the test case set.
        steps: One formatted line per keyword call of the test sequence.
        parameters: Parameter values of this test case, by parameter name.

    Returns:
        The non-empty parts, one per line.
    """
    lines = [
        set_name.strip(),
        description.strip(),
        *(step.strip() for step in steps),
        *(f"{name}={value}" for name, value in sorted(parameters.items())),
    ]
    return "\n".join(line for line in lines if line)
