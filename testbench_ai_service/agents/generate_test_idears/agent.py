"""Generates test ideas for the requirements of a test theme and writes them into it.

The trigger names a test theme -- ``ExecutionContext.root_uid`` in the test structure
tree. The requirements assigned below that theme are loaded from the TOV (or cycle),
and the ideas generated for them are written into the theme's description.

``precheck`` deliberately gates nothing; every check lives in ``run``. That means the
endpoint has already answered 202 by the time anything can fail, so each abort path
below logs specifically enough to diagnose from the log alone. Moving these gates
into ``precheck`` later, to get a 409 instead, touches no other module.
"""

from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.agents.base import Agent
from testbench_ai_service.agents.generate_test_idears.context import (
    RequirementAgentData,
    assemble_context,
)
from testbench_ai_service.agents.generate_test_idears.model import (
    Requirement,
    RequirementAgentArgs,
    TestIdeaResult,
    ThemeContext,
    apply_guardrails,
)
from testbench_ai_service.agents.generate_test_idears.utils import (
    fetch_requirement_details,
    get_test_theme,
    get_theme_spec,
    load_requirements,
    patch_generated_test_ideas,
    patch_generation_failed,
    patch_generation_started,
    render_test_ideas,
)
from testbench_ai_service.llm.base import LLMClient
from testbench_ai_service.log import logger
from testbench_ai_service.models.agent import ExecutionContext, PrecheckResult
from testbench_ai_service.models.testbench import (
    PermissionWithCode,
    ProjectRole,
    RequirementAssignment,
    TestStructureTree,
    TestThemeNode,
    TestThemeSpecification,
)
from testbench_ai_service.utils.html_utils import strip_html_body_tags
from testbench_ai_service.utils.testbench import (
    post_project_tov_structure,
)


class RequirementAgent(Agent):
    AGENT_DATA_CLASS = RequirementAgentData
    ARGS_CLASS = RequirementAgentArgs
    args: RequirementAgentArgs
    REQUIRED_PERMISSIONS = frozenset(
        {
            PermissionWithCode.ReadOwnUserDetails,
            PermissionWithCode.ReadProjectDetails,
            PermissionWithCode.ReadTestThemeTree,
            PermissionWithCode.ReadTestCaseSetDetails,
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
        # TODO: needs to be implemented
        return PrecheckResult(passed=True)

    async def run(
        self,
        context: ExecutionContext,
        conn: TBConnection,
        llm_client: LLMClient,
        item_ids: list[str],
    ) -> None:
        """Generate test ideas for the requirements of the triggered test theme.

        Args:
            context: The resolved execution context; ``root_uid`` names the
                test theme.
            conn: TestBench connection for reading and writing back.
            llm_client: Initialised LLM client.
            item_ids: Unused -- ``precheck`` returns no items.
        """
        if not context.tov_key or not context.root_uid:
            logger.error(
                "Test ideas need a TOV and a test theme (tov_key=%r, root_uid=%r); nothing to do",
                context.tov_key,
                context.root_uid,
            )
            return

        tov = post_project_tov_structure(
            conn=conn,
            project_key=context.project_key,
            tov_key=context.tov_key,
            root_uid=context.root_uid,
        )
        theme = tov.root
        if not isinstance(theme, TestThemeNode):
            logger.error(
                "root_uid '%s' is not a test theme (got %s); nothing to do",
                context.root_uid,
                type(theme).__name__,
            )
            return

        if theme.spec is None:
            logger.warning("Theme '%s' has no specification to write into", theme.base.name)
            return
        locker = theme.spec.locker
        if locker is not None and locker.key != context.user_key:
            logger.warning("Theme '%s' is locked by another user; skipping it", theme.base.name)
            return

        assignments = await self._load_assignments(theme.base.name, context, conn)
        if assignments is None:
            return

        try:
            spec = await get_theme_spec(conn, context.project_key, theme)
        except Exception as error:
            logger.error("Could not read test theme '%s': %r", theme.base.name, error)
            return

        try:
            await self._generate_for_theme(
                tree=tov,
                theme=theme,
                spec=spec,
                assignments=assignments,
                context=context,
                conn=conn,
                llm_client=llm_client,
            )
        except Exception as error:
            logger.error(
                "Test idea generation failed for theme '%s' | requirements=%s | error=%r",
                theme.base.name,
                [assignment.extendedId for assignment in assignments],
                error,
            )

    async def _load_assignments(
        self, theme_name: str, context: ExecutionContext, conn: TBConnection
    ) -> list[RequirementAssignment] | None:
        """Load the theme's requirements from the TOV and check there are some to generate for.

        Args:
            theme_name: Name of the theme, for the log.
            context: The resolved execution context.
            conn: TestBench connection.

        Returns:
            The requirements to generate for, or ``None`` if generation should not go
            ahead; the reason is logged then.
        """
        try:
            assignments = await load_requirements(
                conn,
                context.project_key,
                context.root_uid,
                context.tov_key,
                cycle_key=context.cycle_key,
                filtering=context.filtering,
            )
        except Exception as error:
            logger.error(
                "Could not load the requirements of test theme '%s': %r", theme_name, error
            )
            return None

        if not self._requirements_fit(theme_name, assignments):
            return None
        return assignments

    async def _fetch_requirements(
        self,
        assignments: list[RequirementAssignment],
        context: ExecutionContext,
        conn: TBConnection,
    ) -> list[Requirement]:
        """Complete the loaded requirements with their details from the RM service.

        Args:
            assignments: The requirements loaded from the TOV.
            context: The resolved execution context.
            conn: TestBench connection.

        Returns:
            One requirement per assignment, in the same order.
        """
        details = await fetch_requirement_details(conn, self.args, context.tov_key, assignments)
        return [
            Requirement.from_details(assignment, extended)
            for assignment, extended in zip(assignments, details, strict=True)
        ]

    def _requirements_fit(self, theme_name: str, requirements: list[RequirementAssignment]) -> bool:
        """Whether a theme has requirements at all, and no more than ``max_requirements``.

        Args:
            theme_name: Name of the theme, for the log.
            requirements: The requirements assigned below the theme.

        Returns:
            ``True`` if generation should go ahead; the reason is logged otherwise.
        """
        if not requirements:
            logger.info(
                "No requirements are assigned below test theme '%s'; nothing to do", theme_name
            )
            return False
        max_requirements = self.args.max_requirements
        if max_requirements is not None and len(requirements) > max_requirements:
            logger.error(
                "Test theme '%s' has %d requirements, more than max_requirements=%d; skipping it",
                theme_name,
                len(requirements),
                max_requirements,
            )
            return False
        return True

    async def _generate_for_theme(
        self,
        *,
        tree: TestStructureTree,
        theme: TestThemeNode,
        spec: TestThemeSpecification,
        assignments: list[RequirementAssignment],
        context: ExecutionContext,
        conn: TBConnection,
        llm_client: LLMClient,
    ) -> None:
        """Mark the theme as in progress, then gather, generate and write, rolling back on failure.

        All requirements of the theme go into a single prompt, so the model sees
        them together and is asked once per theme rather than once per requirement.

        Args:
            tree: The test structure tree loaded below the theme.
            theme: The theme node to write into.
            spec: The theme's specification, read before it is marked as in progress.
            assignments: The requirements loaded from the TOV.
            context: The resolved execution context.
            conn: TestBench connection.
            llm_client: Initialised LLM client.

        Raises:
            Exception: Whatever gathering, generation or write-back raised, after the
                previous description has been restored.
        """
        previous_description = strip_html_body_tags(spec.description)

        await patch_generation_started(
            conn=conn,
            project_key=context.project_key,
            spec_key=spec.key,
            previous_description=previous_description,
            language=context.language,
            user_key=context.user_key,
            templates_dir=context.templates_dir,
        )

        try:
            requirements = await self._fetch_requirements(assignments, context, conn)
            theme_context = await get_test_theme(
                conn=conn,
                project_key=context.project_key,
                tree=tree,
                theme=theme,
                spec=spec,
                requirements=requirements,
            )
            test_ideas = await self._generate_test_ideas(
                theme=theme,
                theme_context=theme_context,
                context=context,
                llm_client=llm_client,
            )
            print(test_ideas.model_dump_json())
            await patch_generated_test_ideas(
                conn=conn,
                project_key=context.project_key,
                spec_key=spec.key,
                test_ideas=render_test_ideas(test_ideas, requirements, context.language),
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
                    spec_key=spec.key,
                    previous_description=previous_description,
                    language=context.language,
                    user_key=context.user_key,
                    templates_dir=context.templates_dir,
                )
            except Exception as rollback_error:
                logger.error(
                    "Restoring the previous description of theme '%s' also failed: %r",
                    theme.base.name,
                    rollback_error,
                )
            raise error

    async def _generate_test_ideas(
        self,
        *,
        theme: TestThemeNode,
        theme_context: ThemeContext,
        context: ExecutionContext,
        llm_client: LLMClient,
    ) -> TestIdeaResult:
        """Ask the AI, in one prompt, for test ideas for all requirements of a theme.

        The model answers with JSON; its grouping is then normalised by
        :func:`apply_guardrails` rather than trusted to follow the prompt.

        Args:
            theme: The theme the ideas are for.
            theme_context: The theme's requirements and what is already below it.
            context: The resolved execution context.
            llm_client: Initialised LLM client.

        Returns:
            The generated test ideas, possibly none.

        Raises:
            StructuredOutputError: The answer was invalid even after the repair retry.
        """
        agent_data = assemble_context(theme_context)
        result = await self.get_structured_ai_response(
            llm_client, context.llm_config, context.prompt_config, TestIdeaResult, agent_data
        )
        ideas = apply_guardrails(
            result,
            allowed_requirements={
                requirement.external_ref or requirement.key
                for requirement in theme_context.requirements
            },
            existing_theme_names={
                path.rsplit("/", 1)[-1] for path in theme_context.existing_subthemes
            },
            max_ideas=self.args.max_ideas_per_theme,
        )
        logger.debug(
            "Test ideas for requirements %s into theme '%s' (%d of %d kept):\n\t%s",
            [requirement.external_ref for requirement in theme_context.requirements],
            theme.base.name,
            len(ideas.ideas),
            len(result.ideas),
            ideas.model_dump_json(),
        )
        return ideas
