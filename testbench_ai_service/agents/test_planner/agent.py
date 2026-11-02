import asyncio

from pydantic import ValidationError
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.agents.base import Agent
from testbench_ai_service.agents.test_planner.collector import (
    load_catalog,
    test_cases_from_catalog,
)
from testbench_ai_service.agents.test_planner.cutoff import CutoffNote
from testbench_ai_service.agents.test_planner.distance import normalize
from testbench_ai_service.agents.test_planner.embeddings.cache import (
    EmbeddingCache,
    embed_with_cache,
)
from testbench_ai_service.agents.test_planner.embeddings.factory import create_embedding_client
from testbench_ai_service.agents.test_planner.model import (
    CutoffMode,
    PlannerRunParams,
    PlannerTestCase,
    TestPlannerArgs,
)
from testbench_ai_service.agents.test_planner.params import UnknownVariantError, parse_run_params
from testbench_ai_service.agents.test_planner.planner import build_plan
from testbench_ai_service.agents.test_planner.writeback import plan_test_cases
from testbench_ai_service.jobs.handle import current_job
from testbench_ai_service.llm.base import LLMClient
from testbench_ai_service.log import logger
from testbench_ai_service.models.agent import AgentData, ExecutionContext, PrecheckResult
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.testbench import PermissionWithCode, ProjectRole
from testbench_ai_service.utils.agent import check_min_testbench_version
from testbench_ai_service.utils.i18n import get_translation
from testbench_ai_service.utils.testbench import is_json_based_tov

MIN_TEST_CASES = 2


class TestPlannerAgentData(AgentData, total=False):
    """The planner renders no prompt, so it offers no template variables."""


class TestPlannerAgent(Agent):
    """Plans the most diverse test selection of a cycle and sets it to planned in TestBench."""

    __test__ = False  # not a pytest test class

    AGENT_DATA_CLASS = TestPlannerAgentData
    ARGS_CLASS = TestPlannerArgs
    args: TestPlannerArgs
    USES_LLM = False
    REQUIRED_PERMISSIONS = frozenset(
        {
            PermissionWithCode.ReadOwnUserDetails,
            PermissionWithCode.ReadProjectDetails,
            PermissionWithCode.ReadTovReport,
            PermissionWithCode.ReadCycleReport,
            PermissionWithCode.ReadReportingJobDetails,
            PermissionWithCode.DownloadReportFile,
            PermissionWithCode.ReadTestThemeTree,
            PermissionWithCode.ReadTestCaseSetDetails,
            PermissionWithCode.ImportExecutionResults,
        }
    )
    ALLOWED_ROLES = frozenset({ProjectRole.TestManager})

    async def precheck(self, context: ExecutionContext, conn: TBConnection) -> PrecheckResult:
        """Refuse anything but a cycle of a JSON-based TOV with valid parameters.

        The test cases are collected by the run: that needs the cycle's JSON report,
        which is too slow for the request.

        Returns:
            On success the cycle's key as the only item.
        """
        if failure := await _check_scope(context, conn):
            return failure
        params = _parse_params(context)
        if isinstance(params, PrecheckResult):
            return params
        return PrecheckResult(passed=True, items=[context.cycle_key])

    async def run(
        self,
        context: ExecutionContext,
        conn: TBConnection,
        llm_client: LLMClient,
        item_ids: list[str],
    ) -> None:
        """Collect the cycle's test cases, plan the selection and set it to planned.

        ``item_ids`` holds only the cycle; the test cases are collected here.
        """
        language = context.language
        params = parse_run_params(context.prompt_config)
        catalog = await asyncio.to_thread(load_catalog, conn, context)
        test_cases = test_cases_from_catalog(catalog)
        candidates = [case for case in test_cases if not case.executed]
        logger.info(
            "Test planner looked at %d test cases, %d of them in the cycle, "
            "%d of them not executed yet | cycle='%s'",
            sum(len(test_case_set.test_cases) for test_case_set in catalog.values()),
            len(test_cases),
            len(candidates),
            context.cycle_key,
        )
        if len(candidates) < MIN_TEST_CASES:
            await current_job().fail(
                get_translation(
                    "test_planner.run.too_few_test_cases", language, count=len(candidates)
                )
            )
            return
        data_warnings = _data_warnings(params, candidates, language)
        for warning in data_warnings:
            await current_job().warn(warning)

        embedding_args = self.args.embedding
        client = create_embedding_client(embedding_args, context.llm_config, context.project_name)
        try:
            cache = EmbeddingCache(
                embedding_args.cache_dir, embedding_args.provider.value, embedding_args.model
            )
            embeddings = await embed_with_cache(
                client, cache, [case.text for case in test_cases], embedding_args.batch_size
            )
        finally:
            await client.close()

        # CPU-bound for large suites; a worker thread keeps the service responsive.
        result, notes = await asyncio.to_thread(
            build_plan,
            test_cases,
            normalize(embeddings),
            params,
            self.args.mandatory_tag,
            self.args.cluster_threshold,
        )
        result.warnings = [
            *data_warnings,
            *(_note_text(note, params, language) for note in notes),
        ]
        logger.info(
            "Test planner selection | project='%s' | cycle='%s' | mode=%s | selected=%d/%d\n%s",
            context.project_name,
            context.cycle_key,
            params.mode.value,
            result.selected,
            result.total,
            result.model_dump_json(indent=2),
        )

        planned = await plan_test_cases(
            conn, context, catalog, [entry.unique_id for entry in result.selection]
        )
        logger.info(
            "Test planner set %d of %d selected test cases to planned | cycle='%s'",
            planned,
            result.selected,
            context.cycle_key,
        )


def _failed(message: str) -> PrecheckResult:
    return PrecheckResult(passed=False, warnings=[message])


async def _check_scope(context: ExecutionContext, conn: TBConnection) -> PrecheckResult | None:
    """A failed result if server version, TOV or cycle do not fit, else ``None``."""
    if unsupported_version := check_min_testbench_version(context, conn):
        return unsupported_version
    language = context.language
    if not context.tov_key:
        return _failed(get_translation("shared.precheck.missing_tov_key", language))
    if not context.cycle_key:
        return _failed(get_translation("shared.precheck.missing_cycle_key", language))
    if not await asyncio.to_thread(is_json_based_tov, conn, context.project_key, context.tov_key):
        return _failed(get_translation("test_planner.precheck.unsupported_tov_format", language))
    return None


def _parse_params(context: ExecutionContext) -> PlannerRunParams | PrecheckResult:
    """The run parameters, or a failed result explaining why they are invalid."""
    language = context.language
    try:
        return parse_run_params(context.prompt_config)
    except UnknownVariantError as e:
        return _failed(
            get_translation("test_planner.precheck.unknown_variant", language, variant=e.variant)
        )
    except ValidationError as e:
        details = "; ".join(error["msg"] for error in e.errors())
        return _failed(
            get_translation("test_planner.precheck.invalid_vars", language, details=details)
        )


def _data_warnings(
    params: PlannerRunParams, candidates: list[PlannerTestCase], language: LanguageOption
) -> list[str]:
    total = len(candidates)
    if params.mode == CutoffMode.COVERAGE:
        missing = sum(1 for case in candidates if not case.requirement_keys)
        if missing:
            return [
                get_translation(
                    "test_planner.run.missing_requirement_links",
                    language,
                    missing=missing,
                    total=total,
                )
            ]
    if params.mode == CutoffMode.BUDGET:
        missing = sum(1 for case in candidates if case.planned_minutes <= 0)
        if missing:
            return [
                get_translation(
                    "test_planner.run.missing_durations",
                    language,
                    missing=missing,
                    total=total,
                )
            ]
    return []


def _note_text(note: CutoffNote, params: PlannerRunParams, language: LanguageOption) -> str:
    text: str = get_translation(
        f"test_planner.run.{note.value}",
        language,
        count=params.count,
        budget=params.budget_minutes,
    )
    return text
