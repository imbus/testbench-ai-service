import pytest

from testbench_ai_service.agent_packages import loaded


@pytest.fixture(autouse=True)
def reset_loaded_agent_packages():
    """Agent packages put on ``sys.path`` are process-global; undo them after each test."""
    yield
    loaded.reset()
