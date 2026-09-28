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
from testbench_ai_service.agents.requirement.context import (
    RequirementAgentData,
    assemble_context,
)
from testbench_ai_service.agents.requirement.linking import test_case_set_names
from testbench_ai_service.agents.requirement.model import (
    ExtendedRequirement,
    RequirementAgentArgs,
    ThemeContext,
)
from testbench_ai_service.agents.requirement.utils import (
    load_requirements,
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
from testbench_ai_service.utils.testbench import (
    get_test_theme_details,
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

        try:
            requirements = await load_requirements(
                conn,
                self.args,
                context.project_key,
                context.root_uid,
                context.tov_key,
                cycle_key=context.cycle_key,
                filtering=context.filtering,
            )
        except Exception as error:
            logger.error(
                "Could not load the requirements of test theme '%s': %r", theme.base.name, error
            )
            return

        test_theme_details = get_test_theme_details(
            conn=conn, project_key=context.project_key, test_theme_key=theme.base.key
        )
        theme_context = ThemeContext(
            theme_name=theme.base.name,
            description=test_theme_details.spec.description,
            test_case_sets=test_case_set_names(tov, theme),
        )

        try:
            await self._generate_for_theme(
                theme=theme,
                spec_key=theme.spec.key,
                theme_context=theme_context,
                targets=requirements,
                context=context,
                conn=conn,
                llm_client=llm_client,
            )
        except Exception as error:
            logger.error(
                "Test idea generation failed for theme '%s' | requirements=%s | error=%r",
                theme.base.name,
                [requirement.extendedId for requirement in requirements],
                error,
            )

    async def _generate_for_theme(
        self,
        *,
        theme: TestThemeNode,
        spec_key: str,
        theme_context: ThemeContext,
        targets: list[ExtendedRequirement],
        context: ExecutionContext,
        conn: TBConnection,
        llm_client: LLMClient,
    ) -> None:
        """Generate and write test ideas for one theme, rolling back on failure.

        All requirements of the theme go into a single prompt, so the model sees
        them together and is asked once per theme rather than once per requirement.

        Args:
            theme: The theme node to write into.
            spec_key: Key of the theme's specification, which is patched.
            theme_context: Test-side context for that theme.
            targets: The requirements assigned below the theme.
            context: The resolved execution context.
            conn: TestBench connection.
            llm_client: Initialised LLM client.

        Raises:
            Exception: Whatever generation or write-back raised, after the previous
                description has been restored.
        """
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
            test_ideas = await self._generate_test_ideas(
                theme=theme,
                theme_context=theme_context,
                targets=targets,
                context=context,
                llm_client=llm_client,
            )
            await patch_generated_test_ideas(
                conn=conn,
                project_key=context.project_key,
                spec_key=spec_key,
                test_ideas=test_ideas,
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

    async def _generate_test_ideas(
        self,
        *,
        theme: TestThemeNode,
        theme_context: ThemeContext,
        targets: list[ExtendedRequirement],
        context: ExecutionContext,
        llm_client: LLMClient,
    ) -> str:
        """Ask the AI, in one prompt, for test ideas for all requirements of a theme.

        Args:
            theme: The theme the ideas are for.
            theme_context: Test-side context for that theme.
            targets: The requirements to generate ideas for.
            context: The resolved execution context.
            llm_client: Initialised LLM client.

        Returns:
            The generated test ideas.
        """
        agent_data = assemble_context(targets=targets, theme_context=theme_context)
        response = await self.get_ai_response(
            llm_client, context.llm_config, context.prompt_config, agent_data
        )
        logger.debug(
            "Test ideas for requirements %s into theme '%s':\n\t%s",
            [target.extendedId for target in targets],
            theme.base.name,
            response.result,
        )
        return response.result
