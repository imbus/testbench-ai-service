"""A small example agent: it renders a write-back template into the job report.

It uses no LLM (``USES_LLM = False``), so the package runs without an API key. An agent that
asks a model would call ``self.get_ai_response`` or ``self.get_structured_ai_response`` in
``run()``.
"""

from __future__ import annotations

from jinja2 import Template

from testbench_ai_service.agents.base import Agent
from testbench_ai_service.jobs.handle import current_job
from testbench_ai_service.models.agent import AgentData, PrecheckResult
from testbench_ai_service.utils.template_utils import resolve_template_path


class RaterData(AgentData):
    """The fields the prompt may use as ``{{ agent.<name> }}``."""

    title: str


class RaterAgent(Agent):
    AGENT_DATA_CLASS = RaterData
    USES_LLM = False

    async def precheck(self, context, conn):
        return PrecheckResult(passed=True, items=[context.root_uid or "item"])

    async def run(self, context, conn, llm_client, item_ids):
        # The agent may be registered under another key than "acme_rater". Resolving the
        # template with context.agent_key finds the files copied for that key.
        path = resolve_template_path(
            "template.jinja",
            templates_dir=context.templates_dir,
            language=context.language,
            agent_key=context.agent_key,
        )
        html = Template(path.read_text(encoding="utf-8")).render(result="rated")
        await current_job().set_report("rater", {"html": html})
