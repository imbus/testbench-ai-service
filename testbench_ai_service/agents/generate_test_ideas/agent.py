"""Generates test ideas for the requirements of a test theme and writes them into it.

The trigger names a test theme -- ``ExecutionContext.root_uid`` in the test structure
tree. The requirements assigned below that theme are loaded from the TOV (or cycle),
and the ideas generated for them are written into the theme's description.

``precheck`` refuses a trigger that cannot produce ideas (not a test theme, locked by
someone else, no or too many requirements) with a translated warning, so the user
sees why (409) instead of an accepted run that silently writes nothing. What it loaded
is handed to ``run`` on the instance: ``load_agent`` builds one per request.
"""

import asyncio

from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.agents.base import Agent
from testbench_ai_service.agents.generate_test_ideas.context import (
    RequirementAgentData,
    assemble_context,
)
from testbench_ai_service.agents.generate_test_ideas.model import (
    Requirement,
    RequirementAgentArgs,
    TestIdeaResult,
    ThemeContext,
    apply_guardrails,
)
from testbench_ai_service.agents.generate_test_ideas.utils import (
    CREATE_TEST_CASE_SETS_MIN_VERSION,
    CreatedTestCaseSet,
    TestCaseSetCreationForbiddenError,
    create_test_case_sets,
    delete_test_case_sets,
    get_test_theme,
    get_theme_spec,
    load_requirements,
    patch_generated_test_ideas,
    patch_generation_failed,
    patch_generation_started,
    patch_previous_description,
    render_test_ideas,
)
from testbench_ai_service.jobs.handle import current_job
from testbench_ai_service.llm.base import LLMClient
from testbench_ai_service.log import logger
from testbench_ai_service.models.agent import ExecutionContext, PrecheckResult
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.testbench import (
    PermissionWithCode,
    ProjectRole,
    RequirementAssignment,
    TestStructureTree,
    TestThemeNode,
    TestThemeSpecification,
)
from testbench_ai_service.utils.agent import check_min_testbench_version
from testbench_ai_service.utils.html_utils import strip_html_body_tags
from testbench_ai_service.utils.i18n import get_translation
from testbench_ai_service.utils.rm_service import fetch_requirement_details
from testbench_ai_service.utils.testbench import (
    post_project_tov_structure,
)


class RequirementAgent(Agent):
    AGENT_DATA_CLASS = RequirementAgentData
    ARGS_CLASS = RequirementAgentArgs
    args: RequirementAgentArgs
    # ModifyTestStructureElements (creating the test case sets, TestBench 5.0) is
    # deliberately missing: a token of an older TestBench cannot carry it, and
    # without it the run falls back to writing the ideas as text only.
    REQUIRED_PERMISSIONS = frozenset(
        {
            PermissionWithCode.ReadOwnUserDetails,
            PermissionWithCode.ReadProjectDetails,
            PermissionWithCode.ReadTestThemeTree,
            PermissionWithCode.ReadTovRequirements,
            PermissionWithCode.ReadTestThemeDetails,
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

    def __init__(self, args: RequirementAgentArgs | None = None):
        super().__init__(args)
        # Loaded by precheck() and used by run(); see the module docstring.
        self._tree: TestStructureTree | None = None
        self._theme: TestThemeNode | None = None
        self._assignments: list[RequirementAssignment] = []

    async def precheck(
        self,
        context: ExecutionContext,
        conn: TBConnection,
    ) -> PrecheckResult:
        """Check the triggered test theme can take test ideas, and load what ``run`` needs.

        Read-only. A TestBench error while loading (e.g. a 403 for a missing
        permission) is raised, so the route answers with TestBench's own status.

        Args:
            context: The resolved execution context; ``root_uid`` names the test theme.
            conn: TestBench connection.

        Returns:
            A passing result with the theme's UID as the only item, or a failed one
            with the reason as a translated warning.
        """
        if unsupported_version := check_min_testbench_version(context, conn):
            return unsupported_version
        language = context.language
        if not context.tov_key or not context.root_uid:
            return _refused(language, "requirement.precheck.not_a_test_theme")

        tree = await asyncio.to_thread(
            post_project_tov_structure,
            conn=conn,
            project_key=context.project_key,
            tov_key=context.tov_key,
            root_uid=context.root_uid,
        )
        theme = tree.root
        if refusal := _check_theme(theme, context):
            return refusal

        assignments = await load_requirements(
            conn,
            context.project_key,
            context.root_uid,
            context.tov_key,
            cycle_key=context.cycle_key,
            filtering=context.filtering,
        )
        if refusal := self._check_requirements(theme.base.name, assignments, language):
            return refusal

        self._tree, self._theme, self._assignments = tree, theme, assignments
        return PrecheckResult(passed=True, items=[context.root_uid])

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
            item_ids: The theme's UID, from :meth:`precheck`.

        Raises:
            RuntimeError: :meth:`precheck` has not passed on this instance.
        """
        tree, theme, assignments = self._tree, self._theme, self._assignments
        if tree is None or theme is None:
            raise RuntimeError("run() needs the data of a passed precheck()")

        try:
            spec = await get_theme_spec(conn, context.project_key, theme)
        except Exception as error:
            logger.error("Could not read test theme '%s': %r", theme.base.name, error)
            await _fail_job(context, "theme_unreadable", theme=theme.base.name)
            return

        try:
            await self._generate_for_theme(
                tree=tree,
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
            # The theme shows the failure notice; the job must not report success.
            await _fail_job(context, "generation_failed", theme=theme.base.name)

    def _check_requirements(
        self, theme_name: str, assignments: list[RequirementAssignment], language: LanguageOption
    ) -> PrecheckResult | None:
        """A failed result if the theme has no requirements or more than ``max_requirements``."""
        if not assignments:
            return _refused(language, "requirement.precheck.no_requirements", theme=theme_name)
        max_requirements = self.args.max_requirements
        if max_requirements is not None and len(assignments) > max_requirements:
            return _refused(
                language,
                "requirement.precheck.too_many_requirements",
                theme=theme_name,
                count=len(assignments),
                max=max_requirements,
            )
        return None

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
        # A theme the user had locked stays locked for them after the run (precheck
        # refuses a theme locked by anyone else). The details carry no locker; the
        # structure node read in precheck does.
        keep_locked = theme.spec is not None and theme.spec.locker is not None
        created: list[CreatedTestCaseSet] = []

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
            if self._creates_test_case_sets(conn):
                await self._create_test_case_sets(
                    test_ideas=test_ideas,
                    theme=theme,
                    context=context,
                    conn=conn,
                    created=created,
                )
            if created:
                # The ideas live in the new test case sets; the theme keeps only
                # the description it had before the run.
                await patch_previous_description(
                    conn=conn,
                    project_key=context.project_key,
                    spec_key=spec.key,
                    previous_description=previous_description,
                    user_key=context.user_key,
                    keep_locked=keep_locked,
                )
            else:
                await patch_generated_test_ideas(
                    conn=conn,
                    project_key=context.project_key,
                    spec_key=spec.key,
                    test_ideas=render_test_ideas(test_ideas, requirements, context.language),
                    previous_description=previous_description,
                    language=context.language,
                    user_key=context.user_key,
                    templates_dir=context.templates_dir,
                    keep_locked=keep_locked,
                )
        except Exception as error:
            if created:
                await delete_test_case_sets(conn, context.project_key, created, context.user_key)
            try:
                await patch_generation_failed(
                    conn=conn,
                    project_key=context.project_key,
                    spec_key=spec.key,
                    previous_description=previous_description,
                    language=context.language,
                    user_key=context.user_key,
                    templates_dir=context.templates_dir,
                    keep_locked=keep_locked,
                )
            except Exception as rollback_error:
                logger.error(
                    "Restoring the previous description of theme '%s' also failed: %r",
                    theme.base.name,
                    rollback_error,
                )
            raise error

    def _creates_test_case_sets(self, conn: TBConnection) -> bool:
        """Whether ideas also become test case sets: switched on and TestBench 5.0+."""
        return (
            self.args.create_test_case_sets
            and conn.server_version >= CREATE_TEST_CASE_SETS_MIN_VERSION
        )

    async def _create_test_case_sets(
        self,
        *,
        test_ideas: TestIdeaResult,
        theme: TestThemeNode,
        context: ExecutionContext,
        conn: TBConnection,
        created: list[CreatedTestCaseSet],
    ) -> None:
        """Create a test case set per idea below the theme, or warn if not permitted.

        A 403 on the first set (typically a JWT without ``ModifyTestStructureElements``)
        is no failure: the ideas are still written into the theme, and the job
        carries a warning. Any other error is raised for the rollback.

        Args:
            test_ideas: The ideas after :func:`apply_guardrails`.
            theme: The theme the sets are created under.
            context: The resolved execution context.
            conn: TestBench connection.
            created: Receives every set created, for the rollback.
        """
        if not test_ideas.ideas or context.tov_key is None:
            return
        try:
            await create_test_case_sets(
                conn=conn,
                project_key=context.project_key,
                tov_key=context.tov_key,
                theme_key=theme.base.key,
                result=test_ideas,
                language=context.language,
                templates_dir=context.templates_dir,
                created=created,
            )
        except TestCaseSetCreationForbiddenError as error:
            logger.warning(
                "Not permitted to create test case sets below theme '%s' (TestBench: %s); "
                "writing text only. A JWT needs the permission ModifyTestStructureElements "
                "(code %d) in the plugin's permission list.",
                theme.base.name,
                error,
                PermissionWithCode.ModifyTestStructureElements.value,
            )
            await current_job().warn(
                get_translation("requirement.job.test_case_sets_not_permitted", context.language)
            )

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


def _check_theme(theme: object, context: ExecutionContext) -> PrecheckResult | None:
    """A failed result if the root is no test theme, has no spec, or is locked by someone else."""
    language = context.language
    if not isinstance(theme, TestThemeNode):
        return _refused(language, "requirement.precheck.not_a_test_theme")
    name = theme.base.name
    if theme.spec is None:
        return _refused(language, "requirement.precheck.no_specification", theme=name)
    locker = theme.spec.locker
    if locker is not None and locker.key != context.user_key:
        return _refused(language, "requirement.precheck.locked", theme=name)
    return None


def _refused(language: LanguageOption, key: str, **kwargs: object) -> PrecheckResult:
    """A failed precheck whose only warning is the translation of ``key``."""
    message = get_translation(key, language, **kwargs)
    logger.info("Test idea generation refused: %s", message)
    return PrecheckResult(passed=False, warnings=[message])


async def _fail_job(context: ExecutionContext, key: str, **values: str) -> None:
    """End the run's job as failed, with the translation of ``requirement.job.<key>``."""
    await current_job().fail(get_translation(f"requirement.job.{key}", context.language, **values))
