"""Checks whether the tests linked to a requirement prove all of its aspects.

Triggered on a single requirement. The model splits the requirement into aspects,
reads each linked set against them and explains the gaps; the code builds the
matrix and assigns each aspect its status. The result goes into a marked block in
the review comment of every linked set and, in full, into the log. Links and test
elements are never changed.
"""

import asyncio
from typing import ClassVar

from pydantic import ValidationError
from testbench2robotframework.json_reader import TestCaseSet
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.agents.base import Agent
from testbench_ai_service.agents.coverage_checker.formatting import (
    headings,
    render_report,
    render_set_block,
)
from testbench_ai_service.agents.coverage_checker.gaps import GapsData, explain_gaps
from testbench_ai_service.agents.coverage_checker.matrix import SetResult, build_matrix
from testbench_ai_service.agents.coverage_checker.model import (
    CoverageCheckerArgs,
    CoverageCheckerData,
    CoverageResult,
    resolve_run_options,
)
from testbench_ai_service.llm.base import LLMClient
from testbench_ai_service.log import logger
from testbench_ai_service.models.agent import (
    AgentData,
    ElementType,
    ExecutionContext,
    PrecheckResult,
)
from testbench_ai_service.models.testbench import (
    PermissionWithCode,
    ProjectRole,
    RequirementAssignment,
)
from testbench_ai_service.utils.agent import check_min_testbench_version
from testbench_ai_service.utils.i18n import get_translation
from testbench_ai_service.utils.testbench import (
    get_requirements,
    get_test_case_set_catalog,
    is_json_based_tov,
)
from testbench_ai_service.utils.time_utils import current_time
from testbench_ai_service.utils.traceability.aspects import (
    AspectsData,
    decompose,
    render_requirement,
)
from testbench_ai_service.utils.traceability.context import (
    find_requirement,
    has_linked_test_case,
    linked_set_keys,
    load_requirement_context,
)
from testbench_ai_service.utils.traceability.interpretation import (
    InterpretationData,
    interpret_set,
)
from testbench_ai_service.utils.traceability.models import (
    AskStep,
    Aspect,
    LinkedSet,
    RequirementContext,
    T,
)
from testbench_ai_service.utils.traceability.review_writer import (
    WriteOutcome,
    block_pattern,
    write_review_block,
)


def _refused(language, key: str, **values) -> PrecheckResult:
    message = get_translation(f"coverage_checker.precheck.{key}", language, **values)
    return PrecheckResult(passed=False, warnings=[message])


class CoverageChecker(Agent):
    AGENT_DATA_CLASS = CoverageCheckerData
    STEP_DATA_CLASSES: ClassVar[dict[str, type[AgentData]]] = {
        "aspects": AspectsData,
        "interpretation": InterpretationData,
        "gaps": GapsData,
    }
    ARGS_CLASS = CoverageCheckerArgs
    args: CoverageCheckerArgs
    REQUIRED_PERMISSIONS = frozenset(
        {
            PermissionWithCode.ReadOwnUserDetails,
            PermissionWithCode.ReadProjectDetails,
            PermissionWithCode.ReadTovRequirements,
            PermissionWithCode.ReadTovReport,
            PermissionWithCode.ReadReportingJobDetails,
            PermissionWithCode.DownloadReportFile,
            PermissionWithCode.ReadTestThemeTree,
            PermissionWithCode.ReadTestCaseSetDetails,
            PermissionWithCode.ModifySpecifications,
        }
    )
    ALLOWED_ROLES = frozenset({ProjectRole.TestManager, ProjectRole.TestDesigner})

    async def precheck(self, context: ExecutionContext, conn: TBConnection) -> PrecheckResult:
        """Refuse anything but a requirement of a TOV with linked test cases.

        Returns:
            On success the keys of the linked sets as ``items``, and a warning when
            no RM service is configured (the aspects then rest on the title alone).
        """
        if unsupported_version := check_min_testbench_version(context, conn):
            return unsupported_version
        language = context.language
        if refusal := self._refuse_trigger(context):
            return refusal
        loaded = await self._load_tov(context, conn)
        if isinstance(loaded, PrecheckResult):
            return loaded
        assignments, catalog = loaded

        assignment = find_requirement(assignments, context.root_key, context.root_uid)
        if assignment is None:
            return _refused(
                language, "requirement_not_found", requirement=context.root_key or context.root_uid
            )
        if not has_linked_test_case(catalog, assignment.key):
            return _refused(
                language, "no_linked_tests", requirement=assignment.extendedId or assignment.key
            )

        warnings = []
        if self.args.rm_service_url is None:
            warnings.append(get_translation("coverage_checker.precheck.reduced_mode", language))
        return PrecheckResult(
            passed=True, warnings=warnings, items=linked_set_keys(catalog, assignment.key)
        )

    def _refuse_trigger(self, context: ExecutionContext) -> PrecheckResult | None:
        """Refuse a trigger that is not a requirement of a TOV or has invalid prompt vars."""
        language = context.language
        if (
            context.element_type != ElementType.REQUIREMENT
            or not context.tov_key
            or not (context.root_key or context.root_uid)
        ):
            logger.warning(
                "Coverage check needs a requirement of a TOV; got element_type=%r, "
                "tree_type=%r, tov_key=%r, root_key=%r, root_uid=%r",
                context.element_type,
                context.tree_type,
                context.tov_key,
                context.root_key,
                context.root_uid,
            )
            return _refused(language, "not_a_requirement")
        try:
            resolve_run_options(context.prompt_config.vars, self.args)
        except ValidationError as error:
            details = "; ".join(str(err["msg"]) for err in error.errors())
            return _refused(language, "invalid_vars", details=details)
        return None

    async def _load_tov(
        self, context: ExecutionContext, conn: TBConnection
    ) -> PrecheckResult | tuple[list[RequirementAssignment], dict[str, TestCaseSet]]:
        """Load requirements and test case set catalog, or the refusal if that is impossible."""
        try:
            if not await asyncio.to_thread(
                is_json_based_tov, conn, context.project_key, context.tov_key
            ):
                return _refused(context.language, "unsupported_tov_format")
            assignments = await asyncio.to_thread(
                get_requirements, conn, context.project_key, None, context.tov_key
            )
            catalog = await asyncio.to_thread(
                get_test_case_set_catalog,
                conn,
                context.project_key,
                context.tov_key,
                None,
                None,
                None,
            )
        except Exception as error:
            logger.error(
                "Could not load the requirements or tests of TOV '%s': %r", context.tov_key, error
            )
            return _refused(context.language, "load_failed")
        return assignments, catalog

    async def run(
        self,
        context: ExecutionContext,
        conn: TBConnection,
        llm_client: LLMClient,
        item_ids: list[str],
    ) -> None:
        """Check the coverage and log the report and the full result."""
        result = await self.check_coverage(context, conn, llm_client, item_ids)
        if result is None:
            return
        logger.info("%s\n%s", render_report(result), result.model_dump_json(indent=2))

    async def check_coverage(
        self,
        context: ExecutionContext,
        conn: TBConnection,
        llm_client: LLMClient,
        item_ids: list[str],
    ) -> CoverageResult | None:
        """Build the coverage result and write it into the linked sets' review comments.

        Returns:
            The result, or ``None`` if the check had to stop; the reason is logged.
        """
        if not item_ids or not context.tov_key:
            logger.info("No linked test case sets to check; nothing to do")
            return None
        options = resolve_run_options(context.prompt_config.vars, self.args)

        try:
            loaded = await load_requirement_context(
                conn,
                self.args,
                context.project_key,
                context.tov_key,
                context.root_key,
                context.root_uid,
                item_ids,
            )
        except Exception as error:
            logger.error(
                "Could not load requirement %r of TOV '%s': %r",
                context.root_key or context.root_uid,
                context.tov_key,
                error,
            )
            return None

        ask = self._ask(context, llm_client)
        try:
            aspects = await decompose(ask, loaded.requirement, self.args.max_aspects)
        except Exception as error:
            logger.error(
                "Splitting requirement '%s' into aspects failed; nothing is written: %r",
                loaded.requirement_ref,
                error,
            )
            return None

        set_results = await self._interpret_sets(ask, loaded, aspects)
        coverages, without = build_matrix(aspects, set_results, options.counting_spec_status)
        try:
            coverages = await explain_gaps(
                ask,
                render_requirement(loaded.requirement),
                coverages,
                [f"{linked_set.title} ({linked_set.path})" for linked_set in loaded.linked_sets],
            )
        except Exception as error:
            logger.error(
                "Explaining the coverage gaps of requirement '%s' failed; "
                "writing the matrix without them: %r",
                loaded.requirement_ref,
                error,
            )

        result = CoverageResult(
            requirement_key=loaded.requirement_ref,
            aspects=coverages,
            sets_without_evidence=without,
            reduced_mode=loaded.reduced_mode,
            incomplete=any(set_result.evidence is None for set_result in set_results),
            set_paths={linked_set.key: linked_set.path for linked_set in loaded.linked_sets},
        )
        if options.write_review_comments:
            skipped = await self._write_comments(context, conn, loaded.linked_sets, result)
            result = result.model_copy(update={"skipped_comments": skipped})
        return result

    def _ask(self, context: ExecutionContext, llm_client: LLMClient) -> AskStep:
        async def ask(step: str, schema: type[T], agent_data: AgentData) -> T:
            return await self.get_structured_ai_response(
                llm_client,
                context.llm_config,
                context.prompt_config,
                schema,
                agent_data,
                step=step,
            )

        return ask

    async def _interpret_sets(
        self, ask: AskStep, loaded: RequirementContext, aspects: list[Aspect]
    ) -> list[SetResult]:
        """Interpret the linked sets in parallel; a failing set does not stop the others."""
        semaphore = asyncio.Semaphore(self.args.max_parallel_sets)
        requirement = render_requirement(loaded.requirement)

        async def interpret(linked_set: LinkedSet) -> SetResult:
            async with semaphore:
                try:
                    evidence = await interpret_set(
                        ask, requirement, aspects, linked_set, self.args.max_test_cases_per_call
                    )
                except Exception as error:
                    logger.error(
                        "Interpreting test case set '%s' failed: %r", linked_set.path, error
                    )
                    evidence = None
            return SetResult(
                set_key=linked_set.key,
                spec_status=linked_set.spec_status,
                has_test_cases=bool(linked_set.test_cases),
                evidence=evidence,
            )

        return list(await asyncio.gather(*(interpret(s) for s in loaded.linked_sets)))

    async def _write_comments(
        self,
        context: ExecutionContext,
        conn: TBConnection,
        linked_sets: list[LinkedSet],
        result: CoverageResult,
    ) -> list[str]:
        """Write each set's block; return the keys of the sets that were not written."""
        semaphore = asyncio.Semaphore(self.args.max_parallel_sets)
        pattern = block_pattern(headings(), result.requirement_key)
        timestamp = current_time()

        async def write(linked_set: LinkedSet) -> tuple[str, WriteOutcome]:
            block = render_set_block(result, linked_set.key, context.language, timestamp)
            async with semaphore:
                outcome = await write_review_block(
                    conn,
                    context.project_key,
                    context.tov_key,
                    context.user_key,
                    linked_set,
                    pattern,
                    block,
                )
            return linked_set.key, outcome

        outcomes = await asyncio.gather(*(write(s) for s in linked_sets))
        return [key for key, outcome in outcomes if outcome != WriteOutcome.WRITTEN]
