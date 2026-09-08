"""Generates test ideas for a requirement and writes them into a test theme.

The trigger names a requirement -- ``ExecutionContext.root_uid`` in the REQUIREMENTS
tree -- while the output belongs in the test structure tree, so the agent bridges
the two through the requirement links TestBench keeps on theme specifications.

``precheck`` deliberately gates nothing; every check lives in ``run``. That means the
endpoint has already answered 202 by the time anything can fail, so each abort path
below logs specifically enough to diagnose from the log alone. Moving these gates
into ``precheck`` later, to get a 409 instead, touches no other module.

A requirement that no theme links is not one of those abort paths: the ideas are
still generated, without the theme tiers, and logged instead of written. Every
write-back helper needs a theme's ``spec.key``, so an unlinked requirement has no
destination in TestBench -- what it should be is still open.
"""

import asyncio

from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.agents.base import Agent
from testbench_ai_service.agents.requirement.context import (
    RequirementAgentData,
    TokenBudget,
    assemble_context,
)
from testbench_ai_service.agents.requirement.linking import collect_theme_contexts
from testbench_ai_service.agents.requirement.model import Baseline, Requirement, ThemeContext
from testbench_ai_service.agents.requirement.ranking import (
    LexicalRanker,
    LlmRerankRanker,
    Ranker,
)
from testbench_ai_service.agents.requirement.tree import (
    ancestors,
    find_requirement,
    siblings,
    subtree,
)
from testbench_ai_service.agents.requirement.utils import (
    load_current_baseline,
    patch_generated_test_ideas,
    patch_generation_failed,
    patch_generation_started,
)
from testbench_ai_service.llm.base import LLMClient
from testbench_ai_service.log import logger
from testbench_ai_service.models.agent import ExecutionContext, PrecheckResult
from testbench_ai_service.models.testbench import (
    PermissionWithCode,
    ProjectRole,
    TestThemeNode,
)
from testbench_ai_service.utils.html_utils import strip_html_body_tags

#: Whether the related-requirements tier is reordered by a model.
#:
#: The lexical prefilter runs either way -- a baseline of thousands of requirements
#: fits in no selector call, so reranking without it is not an option. Turning this
#: on buys better tier-6 selection for one extra cheap call per theme.
USE_LLM_RERANK = False


class RequirementAgent(Agent):
    AGENT_DATA_CLASS = RequirementAgentData
    REQUIRED_PERMISSIONS = frozenset(
        {
            PermissionWithCode.ReadOwnUserDetails,
            PermissionWithCode.ReadProjectDetails,
            PermissionWithCode.ReadTestThemeTree,
            PermissionWithCode.ModifySpecifications,
            PermissionWithCode.ModifySpecManagementInfo,
        }
    )
    ALLOWED_ROLES = frozenset(
        {
            ProjectRole.TestManager,
            ProjectRole.TestDesigner,
        }
    )

    async def precheck(
        self,
        context: ExecutionContext,
        conn: TBConnection,
    ) -> PrecheckResult:
        """Pass unconditionally; all validation happens in :meth:`run`.

        Args:
            context: The resolved execution context.
            conn: TestBench connection, unused here.

        Returns:
            A passing result with no items, so ``run`` works from
            ``context.root_uid`` rather than from a precheck item list.
        """
        return PrecheckResult(passed=True)

    async def run(
        self,
        context: ExecutionContext,
        conn: TBConnection,
        llm_client: LLMClient,
        item_ids: list[str],
    ) -> None:
        """Generate test ideas for the triggered requirement.

        Args:
            context: The resolved execution context; ``root_uid`` names the
                requirement.
            conn: TestBench connection for reading and writing back.
            llm_client: Initialised LLM client.
            item_ids: Unused -- ``precheck`` returns no items.
        """
        if not context.tov_key or not context.root_uid:
            logger.error(
                "Cannot generate test ideas without both a tov_key and a root_uid "
                "(tov_key=%r, root_uid=%r)",
                context.tov_key,
                context.root_uid,
            )
            return

        try:
            baseline = await load_current_baseline(conn, context.tov_key)
        except Exception as error:
            logger.error(
                "Could not load the current baseline of TOV '%s': %r", context.tov_key, error
            )
            return

        target = find_requirement(baseline.children, context.root_uid)
        if target is None:
            logger.error(
                "root_uid '%s' names no requirement in baseline '%s'; nothing to do",
                context.root_uid,
                baseline.name,
            )
            return

        theme_contexts = await collect_theme_contexts(
            conn,
            project_key=context.project_key,
            tov_key=context.tov_key,
            cycle_key=context.cycle_key,
            target=target,
            core_requirements=_structural_core(baseline, target),
        )
        ranker = _build_ranker(llm_client, context)

        if not theme_contexts:
            await self._generate_without_theme(
                baseline=baseline,
                target=target,
                context=context,
                llm_client=llm_client,
                ranker=ranker,
            )
            return

        writable = [
            (theme, theme_context)
            for theme, theme_context in theme_contexts
            if _is_writable(theme, context.user_key)
        ]
        if not writable:
            logger.warning(
                "Every theme linking requirement '%s' is locked by another user", target.extendedID
            )
            return

        results = await asyncio.gather(
            *(
                self._generate_for_theme(
                    theme=theme,
                    theme_context=theme_context,
                    baseline=baseline,
                    target=target,
                    context=context,
                    conn=conn,
                    llm_client=llm_client,
                    ranker=ranker,
                )
                for theme, theme_context in writable
            ),
            return_exceptions=True,
        )

        for (theme, _), result in zip(writable, results, strict=True):
            if isinstance(result, BaseException):
                logger.error(
                    "Test idea generation failed for theme '%s' | requirement='%s' | error=%r",
                    theme.base.name,
                    target.extendedID,
                    result,
                )

    async def _generate_without_theme(
        self,
        *,
        baseline: Baseline,
        target: Requirement,
        context: ExecutionContext,
        llm_client: LLMClient,
        ranker: Ranker,
    ) -> None:
        """Generate test ideas for a requirement no theme links, and log them.

        The ideas are logged rather than written back: every write-back helper needs
        a theme's ``spec.key``, and an unlinked requirement offers none. Where the
        output should go in that case is still open, so nothing in TestBench is
        touched -- which also means there is no lock to take and no description to
        restore, hence none of the patch calls :meth:`_generate_for_theme` makes.

        The two theme tiers are simply absent from the context: ``assemble_context``
        renders them empty for a ``None`` theme context, and the templates already
        put that into words.

        Args:
            baseline: The loaded baseline.
            target: The target requirement.
            context: The resolved execution context.
            llm_client: Initialised LLM client.
            ranker: Strategy for ordering the related-requirements tier.
        """
        try:
            agent_data = await assemble_context(
                baseline=baseline,
                target=target,
                theme_context=None,
                ranker=ranker,
                budget=TokenBudget(),
            )
            response = await self.get_ai_response(
                llm_client, context.llm_config, context.prompt_config, agent_data
            )
        except Exception as error:
            logger.error(
                "Test idea generation failed for unlinked requirement '%s' | error=%r",
                target.extendedID,
                error,
            )
            return

        logger.info(
            "No test theme links requirement '%s', so these test ideas were generated "
            "but not written back:\n\t%s",
            target.extendedID,
            response.result,
        )

    async def _generate_for_theme(
        self,
        *,
        theme: TestThemeNode,
        theme_context: ThemeContext,
        baseline: Baseline,
        target: Requirement,
        context: ExecutionContext,
        conn: TBConnection,
        llm_client: LLMClient,
        ranker: Ranker,
    ) -> None:
        """Generate and write test ideas for one theme, rolling back on failure.

        Args:
            theme: The theme node to write into.
            theme_context: Test-side context for that theme.
            baseline: The loaded baseline.
            target: The target requirement.
            context: The resolved execution context.
            conn: TestBench connection.
            llm_client: Initialised LLM client.
            ranker: Strategy for ordering the related-requirements tier.

        Raises:
            Exception: Whatever generation or write-back raised, after the previous
                description has been restored.
        """
        spec_key = theme.spec.key
        previous_description = strip_html_body_tags(theme_context.description)

        await patch_generation_started(
            conn=conn,
            project_key=context.project_key,
            spec_key=spec_key,
            previous_description=previous_description,
            language=context.language,
            user_key=context.user_key,
            templates_dir=context.templates_dir,
        )

        try:
            agent_data = await assemble_context(
                baseline=baseline,
                target=target,
                theme_context=theme_context,
                ranker=ranker,
                budget=TokenBudget(),
            )
            response = await self.get_ai_response(
                llm_client, context.llm_config, context.prompt_config, agent_data
            )
            logger.debug(
                "Test ideas for requirement '%s' into theme '%s':\n\t%s",
                target.extendedID,
                theme.base.name,
                response.result,
            )
            await patch_generated_test_ideas(
                conn=conn,
                project_key=context.project_key,
                spec_key=spec_key,
                test_ideas=response.result,
                previous_description=previous_description,
                language=context.language,
                user_key=context.user_key,
                templates_dir=context.templates_dir,
            )
        except Exception as error:
            try:
                await patch_generation_failed(
                    conn=conn,
                    project_key=context.project_key,
                    spec_key=spec_key,
                    previous_description=previous_description,
                    language=context.language,
                    user_key=context.user_key,
                    templates_dir=context.templates_dir,
                )
            except Exception as rollback_error:
                # Reported here and swallowed, so the original cause is what
                # propagates rather than the failure to clean up after it.
                logger.error(
                    "Restoring the previous description of theme '%s' also failed: %r",
                    theme.base.name,
                    rollback_error,
                )
            raise error


def _structural_core(baseline: Baseline, target: Requirement) -> list[Requirement]:
    """Return the requirements whose linked tests are worth fetching.

    Bounded by the shape of one subtree rather than by baseline size, which is what
    keeps the theme lookup from scaling with a baseline of thousands.

    Args:
        baseline: The loaded baseline.
        target: The target requirement.

    Returns:
        The target's ancestors, siblings and descendants.
    """
    return [
        *ancestors(baseline.children, target),
        *siblings(baseline.children, target),
        *(node for _, node in subtree(target)),
    ]


def _is_writable(theme: TestThemeNode, user_key: str) -> bool:
    """Report whether a theme's specification can be patched by this user.

    Args:
        theme: The theme node from the structure tree.
        user_key: The triggering user.

    Returns:
        ``True`` unless the specification is missing or locked by someone else.
    """
    if theme.spec is None:
        logger.warning("Theme '%s' has no specification to write into", theme.base.name)
        return False

    locker = theme.spec.locker
    if locker is not None and locker.key != user_key:
        logger.warning("Theme '%s' is locked by another user; skipping it", theme.base.name)
        return False

    return True


def _build_ranker(llm_client: LLMClient, context: ExecutionContext) -> Ranker:
    """Return the configured tier-6 ranking strategy.

    Args:
        llm_client: Client used when reranking is enabled.
        context: The resolved execution context, for the model to rerank with.

    Returns:
        A :class:`LlmRerankRanker` when :data:`USE_LLM_RERANK` is set, otherwise a
        :class:`LexicalRanker`.
    """
    if not USE_LLM_RERANK:
        return LexicalRanker()
    return LlmRerankRanker(llm_client, model=context.llm_config.model or "gpt-4.1-mini")
