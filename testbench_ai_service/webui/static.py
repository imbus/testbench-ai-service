"""Static hosting for the built React console.

The console is a single-page app: every client-side route must return
``index.html`` so a deep link survives a page reload.  Requests that look like
asset requests are exempt, because answering a missing ``.js`` with HTML turns a
deploy mistake into a confusing browser syntax error.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from testbench_ai_service.log import logger

STATIC_DIR = (Path(__file__).parent.parent / "static" / "admin").resolve()

_NOT_FOUND = 404

_PLACEHOLDER = (
    "<!doctype html><meta charset=utf-8>"
    "<title>TestBench AI Service</title>"
    "<h1>TestBench AI Service</h1>"
    "<p>The web console has not been built for this installation.</p>"
    "<p>Run <code>npm ci &amp;&amp; npm run build</code> in <code>frontend/</code>, "
    "or use the packaged release binary.</p>"
)


class _SpaStaticFiles(StaticFiles):
    """StaticFiles that falls back to ``index.html`` for client-side routes."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != _NOT_FOUND:
                raise
            # Anything with a file extension was meant to be a real file.
            if Path(path).suffix:
                raise
            return await super().get_response("index.html", scope)


def mount_spa(app: FastAPI, directory: Path = STATIC_DIR, path: str = "/admin") -> None:
    """Mount the built console at *path*.

    When *directory* is absent — a source checkout with no frontend build, or a
    wheel installed without one — a placeholder page is served instead of
    raising at startup, so the API stays usable.
    """
    if not directory.is_dir():
        logger.warning(
            "Web console assets not found at %s; serving a placeholder page. "
            "Build the frontend or install a packaged release.",
            directory,
        )

        @app.get(path, include_in_schema=False)
        @app.get(path + "/{_rest:path}", include_in_schema=False)
        async def _placeholder(_rest: str = "") -> HTMLResponse:
            return HTMLResponse(_PLACEHOLDER)

        return

    app.mount(path, _SpaStaticFiles(directory=str(directory), html=True), name="admin-console")
