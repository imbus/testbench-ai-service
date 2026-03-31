from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import RedirectResponse

from testbench_ai_service.auth import validate_session_token
from testbench_ai_service.config import AppConfig
from testbench_ai_service.dependencies import get_app_config
from testbench_ai_service.utils.config import get_prompt_config, get_usecase_config
from testbench_ai_service.utils.prompt_utils import (
    get_placeholders_from_blocks,
    get_prompt_definition,
)

router = APIRouter()


@router.get("/", include_in_schema=False)
async def redirect_to_docs(request: Request):
    return RedirectResponse(url=request.app.docs_url)


@router.get("/usecases", dependencies=[Depends(validate_session_token)])
async def get_usecases(
    app_config: AppConfig = Depends(get_app_config),
    enabled: bool | None = Query(None, description="Filter by enabled status"),
    project: str | None = Query(None, description="Filter by project name"),
):
    usecases = [
        {"key": key, **get_usecase_config(key, app_config, project).model_dump()}
        for key in app_config.usecases
    ]

    if enabled is not None:
        usecases = [uc for uc in usecases if uc["enabled"] == enabled]

    return usecases


@router.get("/usecases/{usecase_key}/prompt", dependencies=[Depends(validate_session_token)])
async def get_prompt_details(
    usecase_key: str = Path(description="The usecase key (e.g. 'test_case_set_reviews')"),
    app_config: AppConfig = Depends(get_app_config),
    project: str | None = Query(None, description="Project name for config overrides"),
):
    """Returns available variants and their placeholders."""
    if usecase_key not in app_config.usecases:
        raise HTTPException(status_code=404, detail=f"Usecase '{usecase_key}' not found")

    prompt_config = get_prompt_config(usecase=usecase_key, config=app_config, project_name=project)
    prompt_definition = get_prompt_definition(prompt_config.file, prompt_config.name)

    variants = [
        {
            "name": variant.name,
            "model": variant.model,
            "blocks": variant.blocks,
            "placeholders": get_placeholders_from_blocks(variant.blocks),
        }
        for variant in prompt_definition.variants
    ]

    return {
        "name": prompt_definition.name,
        "file": prompt_config.file,
        "default_variant": prompt_config.variant or prompt_definition.default_variant,
        "variants": variants,
    }
