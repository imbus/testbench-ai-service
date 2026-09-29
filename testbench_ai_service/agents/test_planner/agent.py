import asyncio

from pydantic import ValidationError
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.agents.base import Agent
from testbench_ai_service.agents.test_planner.collector import collect_test_cases
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
    """Suggests the most diverse test selection of a cycle and logs it as a preview."""

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
        }
    )
    ALLOWED_ROLES = frozenset({ProjectRole.TestManager})

    def __init__(self, args: TestPlannerArgs | None = None):
        super().__init__(args)
        # load_agent builds a new instance per request, so the data collected in
        # precheck() can be handed to run() on the instance instead of exporting
        # the report twice.
        self._params: PlannerRunParams | None = None
        self._test_cases: list[PlannerTestCase] = []
        self._warnings: list[str] = []

    async def precheck(self, context: ExecutionContext, conn: TBConnection) -> PrecheckResult:
        if unsupported_version := check_min_testbench_version(context, conn):
            return unsupported_version
        language = context.language
        if not context.tov_key:
            return _failed(get_translation("shared.precheck.missing_tov_key", language))
        if not context.cycle_key:
            return _failed(get_translation("shared.precheck.missing_cycle_key", language))
        if not is_json_based_tov(conn, context.project_key, context.tov_key):
            return _failed(
                get_translation("test_planner.precheck.unsupported_tov_format", language)
            )

        try:
            params = parse_run_params(context.prompt_config)
        except UnknownVariantError as e:
            return _failed(
                get_translation("test_planner.precheck.unknown_variant", language, variant=e.variant)
            )
        except ValidationError as e:
            details = "; ".join(error["msg"] for error in e.errors())
            return _failed(
                get_translation("test_planner.precheck.invalid_vars", language, details=details)
            )

        test_cases = await asyncio.to_thread(collect_test_cases, conn, context)
        candidates = [case for case in test_cases if not case.executed]
        if len(candidates) < MIN_TEST_CASES:
            return _failed(
                get_translation(
                    "test_planner.precheck.too_few_test_cases", language, count=len(candidates)
                )
            )

        self._params = params
        self._test_cases = test_cases
        self._warnings = _data_warnings(params, candidates, language)
        return PrecheckResult(
            passed=True,
            warnings=self._warnings,
            items=[case.unique_id for case in candidates],
        )

    async def run(
        self,
        context: ExecutionContext,
        conn: TBConnection,
        llm_client: LLMClient,
        item_ids: list[str],
    ) -> None:
        params = self._params
        if params is None:
            raise RuntimeError("run() needs the data of a passed precheck()")

        embedding_args = self.args.embedding
        client = create_embedding_client(embedding_args, context.llm_config, context.project_name)
        try:
            cache = EmbeddingCache(
                embedding_args.cache_dir, embedding_args.provider.value, embedding_args.model
            )
            embeddings = await embed_with_cache(
                client, cache, [case.text for case in self._test_cases], embedding_args.batch_size
            )
        finally:
            await client.close()

        result, notes = build_plan(
            self._test_cases,
            normalize(embeddings),
            params,
            self.args.mandatory_tag,
            self.args.cluster_threshold,
        )
        result.warnings = [*self._warnings, *(_note_text(note, params, context.language) for note in notes)]
        logger.info(
            "Test planner preview | project='%s' | cycle='%s' | mode=%s | selected=%d/%d\n%s",
            context.project_name,
            context.cycle_key,
            params.mode.value,
            result.selected,
            result.total,
            result.model_dump_json(indent=2),
        )


def _failed(message: str) -> PrecheckResult:
    return PrecheckResult(passed=False, warnings=[message])


def _data_warnings(
    params: PlannerRunParams, candidates: list[PlannerTestCase], language: LanguageOption
) -> list[str]:
    total = len(candidates)
    if params.mode == CutoffMode.COVERAGE:
        missing = sum(1 for case in candidates if not case.requirement_keys)
        if missing:
            return [
                get_translation(
                    "test_planner.precheck.missing_requirement_links",
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
                    "test_planner.precheck.missing_durations",
                    language,
                    missing=missing,
                    total=total,
                )
            ]
    return []


def _note_text(note: CutoffNote, params: PlannerRunParams, language: LanguageOption) -> str:
    return get_translation(
        f"test_planner.run.{note.value}",
        language,
        count=params.count,
        budget=params.budget_minutes,
    )
