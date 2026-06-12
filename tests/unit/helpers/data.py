"""Utilities for resolving paths to shared test data files."""

from pathlib import Path

# Absolute path to tests/unit/data/
_DATA_DIR = Path(__file__).parent.parent / "data"


def get_test_data_path(name: str) -> Path:
    """Return the absolute path of a file in ``tests/unit/data/``.

    Args:
        name: Filename relative to the shared data directory
              (e.g. ``"cycle_report.zip"``).

    Returns:
        Absolute ``Path`` to the requested file.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    path = _DATA_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Test data file not found: {path}")
    return path
