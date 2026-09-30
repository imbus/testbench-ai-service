"""Guards the contract between the agent's data class and its prompt templates.

``validate_template_and_agent_vars`` runs at request time, so a template referring to
an ``{{ agent.* }}`` variable the data class does not declare turns every trigger into
a 422 before ``run`` is ever reached. Checking it here fails in CI instead.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from testbench_ai_service.agents.generate_test_idears.agent import RequirementAgent
from testbench_ai_service.agents.routes import validate_template_and_agent_vars

PROMPTS = Path(__file__).parents[4] / "testbench_ai_service" / "prompts"


@pytest.mark.parametrize("language", ["en", "de"])
def test_every_template_variable_is_declared_by_the_agent_data_class(language):
    context = SimpleNamespace(
        prompt_config=SimpleNamespace(
            file=PROMPTS / language / "requirement" / "prompt.yaml",
            variant=None,
        )
    )

    validate_template_and_agent_vars(context, RequirementAgent())
