from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Query, Request
from fastapi.responses import RedirectResponse
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.auth import validate_session_token
from testbench_ai_service.config import AppConfig
from testbench_ai_service.dependencies import get_app_config, get_llm_factory, get_tb_connection
from testbench_ai_service.llm.factory import LLMFactory
from testbench_ai_service.models.prompt import PromptDetailsResponse, PromptVariantResponse
from testbench_ai_service.models.usecase import (
    TriggerUseCaseRequest,
    TriggerUseCaseResponse,
    UseCaseDetailsResponse,
)
from testbench_ai_service.usecases.base import UseCase
from testbench_ai_service.usecases.routes import (
    TRIGGER_USECASE_ROUTE_KWARGS,
    trigger_usecase_execution,
)
from testbench_ai_service.utils.config import get_prompt_config, get_usecase_config
from testbench_ai_service.utils.import_utils import load_class_from_path
from testbench_ai_service.utils.prompt_utils import (
    get_placeholders_from_blocks,
    get_prompt_definition,
)
from testbench_ai_service.utils.testbench import get_project_name

router = APIRouter()


def _resolve_project_name(conn: TBConnection, project_key: str | None) -> str | None:
    """Resolves a project key to a project name. Returns None silently if not found."""
    if project_key is None:
        return None
    try:
        return get_project_name(conn, project_key)
    except Exception:
        return None


@router.get("/", include_in_schema=False)
async def redirect_to_docs(request: Request):
    return RedirectResponse(url=request.app.docs_url)


@router.get(
    "/usecases",
    dependencies=[Depends(validate_session_token)],
    response_model=list[UseCaseDetailsResponse],
)
async def get_usecases(
    app_config: AppConfig = Depends(get_app_config),
    conn: TBConnection = Depends(get_tb_connection),
    enabled: bool | None = Query(None, description="Filter by enabled status"),
    project_key: str | None = Query(None, description="Filter by project key"),
) -> list[UseCaseDetailsResponse]:
    project_name = _resolve_project_name(conn, project_key)
    usecases = [
        UseCaseDetailsResponse(
            key=key, **get_usecase_config(key, app_config, project_name).model_dump()
        )
        for key in app_config.usecases
    ]

    if enabled is not None:
        usecases = [uc for uc in usecases if uc.enabled == enabled]

    return usecases


@router.get(
    "/usecases/{usecase_key}",
    dependencies=[Depends(validate_session_token)],
    response_model=UseCaseDetailsResponse,
)
async def get_usecase_details(
    usecase_key: str = Path(description="The usecase key (e.g. 'test_case_set_reviews')"),
    app_config: AppConfig = Depends(get_app_config),
    conn: TBConnection = Depends(get_tb_connection),
    project_key: str | None = Query(None, description="Filter by project key"),
) -> UseCaseDetailsResponse:
    if usecase_key not in app_config.usecases:
        raise HTTPException(status_code=404, detail=f"Usecase '{usecase_key}' not found")

    project_name = _resolve_project_name(conn, project_key)
    return UseCaseDetailsResponse(
        key=usecase_key, **get_usecase_config(usecase_key, app_config, project_name).model_dump()
    )


@router.get(
    "/usecases/{usecase_key}/prompt",
    dependencies=[Depends(validate_session_token)],
    response_model=PromptDetailsResponse,
)
async def get_prompt_details(
    usecase_key: str = Path(description="The usecase key (e.g. 'test_case_set_reviews')"),
    app_config: AppConfig = Depends(get_app_config),
    conn: TBConnection = Depends(get_tb_connection),
    project_key: str | None = Query(None, description="Filter by project key"),
) -> PromptDetailsResponse:
    """Returns available variants and their placeholders."""
    if usecase_key not in app_config.usecases:
        raise HTTPException(status_code=404, detail=f"Usecase '{usecase_key}' not found")

    project_name = _resolve_project_name(conn, project_key)
    prompt_config = get_prompt_config(
        usecase=usecase_key, config=app_config, project_name=project_name
    )
    prompt_definition = get_prompt_definition(prompt_config.file, prompt_config.name)
    usecase_class: type[UseCase] = load_class_from_path(app_config.usecases[usecase_key].class_path)
    generated_placeholders = usecase_class.GENERATED_PLACEHOLDERS

    variants = [
        PromptVariantResponse(
            name=variant.name,
            description=variant.description,
            model=variant.model,
            placeholders=(all_placeholders := get_placeholders_from_blocks(variant.blocks)),
            user_placeholders=sorted(set(all_placeholders) - generated_placeholders),
        )
        for variant in prompt_definition.variants
    ]

    return PromptDetailsResponse(
        name=prompt_definition.name,
        file=prompt_config.file,
        generated_placeholders=sorted(generated_placeholders),
        default_variant=prompt_config.variant or prompt_definition.default_variant,
        variants=variants,
    )


@router.post(
    "/usecases/{usecase_key}/trigger",
    dependencies=[Depends(validate_session_token)],
    summary="Trigger a usecase by key",
    description="Trigger a usecase execution by providing the usecase key and necessary parameters.",
    **TRIGGER_USECASE_ROUTE_KWARGS,
)
async def trigger_usecase(
    trigger_request: TriggerUseCaseRequest,
    background_tasks: BackgroundTasks,
    usecase_key: str = Path(description="The usecase key (e.g. 'test_case_set_reviews')"),
    conn: TBConnection = Depends(get_tb_connection),
    llm_factory: LLMFactory = Depends(get_llm_factory),
    app_config: AppConfig = Depends(get_app_config),
) -> TriggerUseCaseResponse:
    return await trigger_usecase_execution(
        usecase=usecase_key,
        trigger_request=trigger_request,
        background_tasks=background_tasks,
        conn=conn,
        llm_factory=llm_factory,
        app_config=app_config,
    )
