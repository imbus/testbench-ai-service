from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def isolated_usage_file(tmp_path):
    """Keep every app a test builds from writing usage.sqlite into the repo.

    create_app() places the file next to the config, and a test config has
    no file of its own -- so it would land in the working directory.
    """
    path = tmp_path / "usage.sqlite"
    with patch("testbench_ai_service.main.resolve_usage_file", return_value=path):
        yield path
