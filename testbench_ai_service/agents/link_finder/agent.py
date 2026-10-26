"""Finds test case sets that test a requirement but are not linked to it.

Triggered on a single requirement; the search space is every unlinked set of the
TOV. A generous prefilter picks candidates from titles, paths and short
descriptions; the interpretation reads the candidates' test steps against the
requirement's aspects; the code turns the evidence into a confidence. Candidates
from ``min_confidence_for_comment`` up get a marked block in their review comment,
and the full result goes into the log. Links are never set: every candidate is a
hint for a human to decide on.
"""

import asyncio
from collections.abc import Mapping
from typing import ClassVar

from pydantic import ValidationError
from testbench2robotframework.json_reader import TestCaseSet
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.agents.base import Agent
from testbench_ai_service.agents.link_finder.formatting import (
    headings,
    render_candidate_block,
    render_report,
)
from testbench_ai_service.agents.link_finder.model import (
    LinkCandidate,
    LinkFinderArgs,
    LinkFinderData,
    LinkFinderResult,
    LinkFinderRunOptions,
    at_least,
    resolve_run_options,
)
from testbench_ai_service.agents.link_finder.prefilter import (
    LlmPrefilter,
    PrefilterData,
    summarize,
)
from testbench_ai_service.agents.link_finder.scoring import (
    confidence,
    covered_aspect_ids,
    rank_key,
)
from testbench_ai_service.jobs.handle import current_job
from testbench_ai_service.llm.base import LLMClient
from testbench_ai_service.log import logger
from testbench_ai_service.models.agent import (
    AgentData,
    ElementType,
    ExecutionContext,
    PrecheckResult,
)
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.testbench import (
    PermissionWithCode,
    ProjectRole,
    RequirementAssignment,
)
from testbench_ai_service.utils.agent import check_min_testbench_version
from testbench_ai_service.utils.html_utils import has_visible_text
from testbench_ai_service.utils.i18n import get_translation
from testbench_ai_service.utils.rm_service import Requirement
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
    RequirementNotFoundError,
    find_requirement,
    linked_test_cases,
    load_requirement,
    load_unassigned_requirement,
    test_case_set_detail,
)
from testbench_ai_service.utils.traceability.interpretation import (
    InterpretationData,
    interpret_set,
)
from testbench_ai_service.utils.traceability.models import (
    AskStep,
    Aspect,
    AspectEvidence,
    T,
    TestCaseSetDetail,
)
from testbench_ai_service.utils.traceability.review_writer import (
    WriteOutcome,
    block_pattern,
    remove_review_block,
    write_review_block,
)


def _refused(language, key: str, **values) -> PrecheckResult:
    message = get_translation(f"link_finder.precheck.{key}", language, **values)
    return PrecheckResult(passed=False, warnings=[message])


def unlinked_set_keys(catalog: Mapping[str, TestCaseSet], requirement_key: str) -> list[str]:
    """Keys of the sets linked neither as a whole nor through a test case, sorted by path."""
    unlinked = [
        test_case_set
        for test_case_set in catalog.values()
        if not any(linked_test_cases(test_case_set, requirement_key))
    ]
    return [tcs.details.key for tcs in sorted(unlinked, key=lambda tcs: tcs.details.path)]


def other_requirements(
    test_case_set: TestCaseSet, requirement_key: str, refs: Mapping[str, str]
) -> list[str]:
    """How users know the other requirements the set or one of its test cases links."""
    keys = {reference.key for reference in test_case_set.details.spec.requirements}
    for test_case in test_case_set.test_cases.values():
        keys.update(reference.key for reference in test_case.spec.requirements)
    keys.discard(requirement_key)
    return sorted(refs.get(key, key) for key in keys)


class LinkFinder(Agent):
    AGENT_DATA_CLASS = LinkFinderData
    STEP_DATA_CLASSES: ClassVar[dict[str, type[AgentData]]] = {
        "aspects": AspectsData,
        "prefilter": PrefilterData,
        "interpretation": InterpretationData,
    }
    ARGS_CLASS = LinkFinderArgs
    args: LinkFinderArgs
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

    # The route runs precheck and run on one instance per trigger, so the catalog the
    # precheck loaded (a full-TOV JSON report) can be reused by the run.
    _catalog: dict[str, TestCaseSet] | None = None
    # Likewise the requirement the precheck found in the RM service when the TOV does
    # not assign it.
    _unassigned: Requirement | None = None

    async def precheck(self, context: ExecutionContext, conn: TBConnection) -> PrecheckResult:
        """Refuse anything but a requirement of a TOV with sets left to search.

        A requirement the TOV does not assign (no test is linked to it) is looked up
        in the RM service; without one, or if it does not know the requirement either,
        the trigger is refused.

        Returns:
            On success the keys of the unlinked sets as ``items``, and a warning when
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
        self._catalog = catalog

        assignment = find_requirement(assignments, context.root_key, context.root_uid)
        if assignment is not None:
            requirement_key = assignment.key
            label = assignment.extendedId or assignment.key
        else:
            self._unassigned = await load_unassigned_requirement(
                conn, self.args, context.tov_key, context.root_key, context.root_uid
            )
            if self._unassigned is None:
                return _refused(
                    language,
                    "requirement_not_found",
                    requirement=context.root_key or context.root_uid,
                )
            requirement_key = self._unassigned.key
            label = self._unassigned.external_ref or self._unassigned.key
        search_space = unlinked_set_keys(catalog, requirement_key)
        if refusal := self._check_search_space(search_space, label, language):
            return refusal

        warnings = []
        if self.args.rm_service_url is None:
            warnings.append(get_translation("link_finder.precheck.reduced_mode", language))
        warnings.append(
            get_translation(
                "link_finder.precheck.search_size",
                language,
                requirement=label,
                count=len(search_space),
            )
        )
        return PrecheckResult(passed=True, warnings=warnings, items=search_space)

    def _check_search_space(
        self, search_space: list[str], label: str, language: LanguageOption
    ) -> PrecheckResult | None:
        """Refuse an empty search space, or one larger than ``max_sets_searched``."""
        if not search_space:
            return _refused(language, "nothing_to_search", requirement=label)
        # The prefilter reads every set of the search space, so its size sets the cost.
        if len(search_space) > self.args.max_sets_searched:
            return _refused(
                language,
                "too_many_sets",
                requirement=label,
                count=len(search_space),
                max=self.args.max_sets_searched,
            )
        return None

    def _refuse_trigger(self, context: ExecutionContext) -> PrecheckResult | None:
        """Refuse a trigger that is not a requirement of a TOV or has invalid prompt vars."""
        language = context.language
        if (
            context.element_type != ElementType.REQUIREMENT
            or not context.tov_key
            or not (context.root_key or context.root_uid)
        ):
            logger.warning(
                "The link finder needs a requirement of a TOV; got element_type=%r, "
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
        """Search the link candidates and log the report and the full result."""
        result = await self.find_links(context, conn, llm_client, item_ids)
        if result is None:
            return
        logger.info("%s\n%s", render_report(result), result.model_dump_json(indent=2))
        await current_job().set_report("link_finder", result)

    async def find_links(
        self,
        context: ExecutionContext,
        conn: TBConnection,
        llm_client: LLMClient,
        item_ids: list[str],
    ) -> LinkFinderResult | None:
        """Build the candidate list and write it into the candidates' review comments.

        Args:
            item_ids: Keys of the sets to search, as the precheck found them.

        Returns:
            The result, or ``None`` if the search had to stop; the reason is logged.
        """
        if not item_ids or not context.tov_key:
            logger.info("No unlinked test case sets to search; nothing to do")
            await self._fail_job(context, "nothing_to_search")
            return None
        options = resolve_run_options(context.prompt_config.vars, self.args)

        loaded = await self._load_search_space(context, conn)
        if loaded is None:
            await self._fail_job(
                context, "load_failed", requirement=context.root_key or context.root_uid
            )
            return None
        requirement, assignments, catalog = loaded
        ref = requirement.external_ref or requirement.key
        summaries = summarize(catalog, item_ids)
        if not summaries:
            logger.warning(
                "None of the test case sets %s to search for requirement '%s' could be loaded",
                item_ids,
                ref,
            )
            await self._fail_job(context, "no_sets_loaded", requirement=ref)
            return None

        ask = self._ask(context, llm_client)
        await current_job().progress(0, 3, self._job_text(context, "progress.aspects"))
        try:
            aspects = await decompose(ask, requirement, self.args.max_aspects)
        except Exception as error:
            logger.error(
                "Splitting requirement '%s' into aspects failed; nothing is written: %r",
                ref,
                error,
            )
            await self._fail_job(context, "decompose_failed", requirement=ref)
            return None

        rendered = render_requirement(requirement)
        await current_job().progress(1, 3, self._job_text(context, "progress.prefilter"))
        prefilter = LlmPrefilter(
            ask,
            self.args.prefilter_batch_size,
            self.args.max_candidates,
            self.args.max_parallel_sets,
        )
        screened = await prefilter.run(rendered, aspects, summaries)
        by_key = {tcs.details.key: tcs for tcs in catalog.values()}
        details = [test_case_set_detail(by_key[hit.set_key]) for hit in screened.hits]
        await current_job().progress(2, 3, self._job_text(context, "progress.candidates"))
        interpreted = await self._interpret_candidates(ask, rendered, aspects, details)

        refs = {
            assignment.key: assignment.extendedId or assignment.key for assignment in assignments
        }
        reduced_mode = not has_visible_text(requirement.description or "")
        candidates, empty_sets, failed_sets = self._score(
            aspects, interpreted, by_key, requirement.key, refs, reduced_mode
        )
        result = LinkFinderResult(
            requirement_key=ref,
            aspects={aspect.id: aspect.statement for aspect in aspects},
            candidates=candidates,
            sets_screened=screened.sets_screened,
            sets_detailed=len(details),
            empty_sets=empty_sets,
            failed_sets=failed_sets,
            reduced_mode=reduced_mode,
            incomplete=screened.incomplete or bool(failed_sets),
            set_paths={detail.key: detail.path for detail in details},
        )
        await current_job().progress(3, 3, self._job_text(context, "progress.comments"))
        if options.write_review_comments:
            # This run says nothing about these sets, so their blocks are not outdated.
            not_evaluated = {*screened.unscreened, *failed_sets}
            skipped = await self._write_comments(
                context, conn, catalog, details, result, options, not_evaluated
            )
            result = result.model_copy(update={"skipped_comments": skipped})
        return result

    async def _load_search_space(
        self, context: ExecutionContext, conn: TBConnection
    ) -> tuple[Requirement, list[RequirementAssignment], Mapping[str, TestCaseSet]] | None:
        """The requirement with its RM description, all assignments and the catalog."""
        try:
            try:
                requirement, assignments = await load_requirement(
                    conn,
                    self.args,
                    context.project_key,
                    context.tov_key,
                    context.root_key,
                    context.root_uid,
                )
            except RequirementNotFoundError:
                unassigned = self._unassigned or await load_unassigned_requirement(
                    conn, self.args, context.tov_key, context.root_key, context.root_uid
                )
                if unassigned is None:
                    raise
                requirement = unassigned
                assignments = await asyncio.to_thread(
                    get_requirements, conn, context.project_key, None, context.tov_key
                )
            catalog = self._catalog
            if catalog is None:
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
                "Could not load requirement %r or the tests of TOV '%s': %r",
                context.root_key or context.root_uid,
                context.tov_key,
                error,
            )
            return None
        return requirement, assignments, catalog

    @staticmethod
    def _job_text(context: ExecutionContext, key: str, **values: str | None) -> str:
        text: str = get_translation(f"link_finder.job.{key}", context.language, **values)
        return text

    async def _fail_job(self, context: ExecutionContext, key: str, **values: str | None) -> None:
        await current_job().fail(self._job_text(context, key, **values))

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

    async def _interpret_candidates(
        self,
        ask: AskStep,
        requirement: str,
        aspects: list[Aspect],
        candidates: list[TestCaseSetDetail],
    ) -> list[tuple[TestCaseSetDetail, list[AspectEvidence] | None]]:
        """Interpret the candidates in parallel; ``None`` for a candidate that failed."""
        semaphore = asyncio.Semaphore(self.args.max_parallel_sets)

        async def interpret(
            candidate: TestCaseSetDetail,
        ) -> tuple[TestCaseSetDetail, list[AspectEvidence] | None]:
            async with semaphore:
                try:
                    evidence = await interpret_set(
                        ask, requirement, aspects, candidate, self.args.max_test_cases_per_call
                    )
                except Exception as error:
                    logger.error(
                        "Interpreting candidate test case set '%s' failed: %r",
                        candidate.path,
                        error,
                    )
                    evidence = None
            return candidate, evidence

        return list(await asyncio.gather(*(interpret(c) for c in candidates)))

    def _score(
        self,
        aspects: list[Aspect],
        interpreted: list[tuple[TestCaseSetDetail, list[AspectEvidence] | None]],
        by_key: Mapping[str, TestCaseSet],
        requirement_key: str,
        refs: Mapping[str, str],
        reduced_mode: bool,
    ) -> tuple[list[LinkCandidate], list[str], list[str]]:
        """The ranked candidates, the empty sets and the sets that could not be read."""
        candidates: list[LinkCandidate] = []
        empty_sets: list[str] = []
        failed_sets: list[str] = []
        for detail, evidence in interpreted:
            if not detail.test_cases:
                empty_sets.append(detail.key)
                continue
            if evidence is None:
                failed_sets.append(detail.key)
                continue
            level = confidence(aspects, evidence, self.args.high_confidence_ratio, reduced_mode)
            if level is None:
                continue
            candidates.append(
                LinkCandidate(
                    set_key=detail.key,
                    set_title=detail.title,
                    path=detail.path,
                    spec_status=detail.spec_status,
                    confidence=level,
                    covered_aspect_ids=covered_aspect_ids(aspects, evidence),
                    evidence=evidence,
                    already_linked_to=other_requirements(by_key[detail.key], requirement_key, refs),
                )
            )
        candidates.sort(key=lambda c: rank_key(c.confidence, len(c.covered_aspect_ids), c.path))
        return candidates, empty_sets, failed_sets

    async def _write_comments(
        self,
        context: ExecutionContext,
        conn: TBConnection,
        catalog: Mapping[str, TestCaseSet],
        details: list[TestCaseSetDetail],
        result: LinkFinderResult,
        options: LinkFinderRunOptions,
        not_evaluated: set[str],
    ) -> list[str]:
        """Write the blocks of the commented candidates and remove this requirement's
        stale blocks everywhere else, except in the sets in *not_evaluated*.

        Returns:
            The keys of the candidates whose block was not written.
        """
        semaphore = asyncio.Semaphore(self.args.max_parallel_sets)
        pattern = block_pattern(headings(), result.requirement_key)
        timestamp = current_time()
        detail_of = {detail.key: detail for detail in details}
        commented = [
            candidate
            for candidate in result.candidates
            if at_least(candidate.confidence, options.min_confidence_for_comment)
        ]
        commented_keys = {candidate.set_key for candidate in commented}

        async def write(candidate: LinkCandidate) -> tuple[str, WriteOutcome]:
            try:
                block = render_candidate_block(result, candidate, context.language, timestamp)
            except Exception as error:
                logger.error(
                    "Rendering the review block of test case set '%s' failed: %r",
                    candidate.path,
                    error,
                )
                return candidate.set_key, WriteOutcome.FAILED
            async with semaphore:
                outcome = await write_review_block(
                    conn,
                    context.project_key,
                    context.tov_key,
                    context.user_key,
                    detail_of[candidate.set_key],
                    pattern,
                    block,
                )
            return candidate.set_key, outcome

        async def remove(test_case_set: TestCaseSet) -> None:
            stale = test_case_set_detail(test_case_set)
            async with semaphore:
                outcome = await remove_review_block(
                    conn, context.project_key, context.tov_key, context.user_key, stale, pattern
                )
            if outcome != WriteOutcome.WRITTEN:
                logger.warning(
                    "The outdated link candidate block for '%s' in test case set '%s' "
                    "was not removed (%s)",
                    result.requirement_key,
                    stale.path,
                    outcome.value,
                )

        stale_sets = [
            tcs
            for tcs in catalog.values()
            if tcs.details.key not in commented_keys
            and tcs.details.key not in not_evaluated
            and pattern.search(tcs.details.spec.reviewComment or "")
        ]
        outcomes, _ = await asyncio.gather(
            asyncio.gather(*(write(candidate) for candidate in commented)),
            asyncio.gather(*(remove(tcs) for tcs in stale_sets)),
        )
        return [key for key, outcome in outcomes if outcome != WriteOutcome.WRITTEN]
