# Admin Web UI — Phase 1 (Vertical Slice) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a deployable, read-only TestBench AI Service console at `/admin` — TestBench login, service status, and the Service / LLM / Logging configuration displayed but not editable.

**Architecture:** A React + Vite + TypeScript SPA builds into `testbench_ai_service/static/admin/` and is served by the existing FastAPI app through a StaticFiles subclass that falls back to `index.html` so client-side routes survive a reload. A new `testbench_ai_service/webui/` package supplies `/admin/api` routes. Login exchanges TestBench credentials for a server-side session, handing the browser only an opaque session id in an httpOnly cookie plus a readable CSRF token. Phase 1 writes nothing: there is no config write path to get wrong yet.

**Tech Stack:** FastAPI, pydantic v2, pytest (`asyncio_mode = auto`), React 18, Vite, TypeScript, TanStack Query, React Router, Vitest + React Testing Library.

**Spec:** `docs/superpowers/specs/2026-09-08-admin-web-ui-design.md`

## Global Constraints

- Python `>=3.10,<3.15`. Nothing may rely on 3.11+ syntax; `tomllib` is imported with a `tomli` fallback (see `utils/config.py`).
- Backend package is `testbench_ai_service/webui/` — the name the abandoned August attempt used (spec 2.1). Route prefix is `/admin/api`. Static mount is `/admin`.
- Vite `base` is `'/admin/'`; `build.outDir` is `../testbench_ai_service/static/admin`.
- **Never delete `testbench_ai_service/webui/__pycache__/`.** It is the only surviving trace of the August attempt (spec 2.1) and is unrecoverable — it was never committed. Stale bytecode in a `__pycache__` directory cannot be imported without its source, so it is harmless. Leave it until the user says otherwise.
- **No runtime fetch from any third-party origin.** No CDN scripts, no Google Fonts `@import`. Fonts ship as local woff2, CodeMirror comes from npm. An on-prem service may have no outbound access.
- **API-key presence only, never values.** No endpoint may return the contents of an environment variable.
- **Every request-derived filesystem path goes through `resolve_within`** (spec 9.1). Phase 1 introduces the helper before any endpoint that needs it exists.
- Phase 1 exposes **no mutating route**. `require_admin` and the CSRF dependency are built and tested, but the only writes in this phase are the session cookie.
- Existing behaviour is untouched: `routes.py`, the agent routers, and `GET /` → `/docs` all keep working.
- Commit messages follow the repo's house style — capitalized imperative subject, no `type:` prefix (see `git log`).

---

### Task 1: Reclaim the abandoned scaffolds

Removes the dead `frontend/node_modules` and puts the ignore rules in place so the real scaffold in Task 2 lands clean. Preserves the August bytecode.

**Files:**
- Modify: `.gitignore`
- Delete: `frontend/node_modules/` (regenerable)

**Interfaces:**
- Consumes: nothing
- Produces: a `frontend/` directory that is empty and gitignored-correctly, ready for Task 2

- [ ] **Step 1: Confirm what is actually there before deleting anything**

```bash
find frontend -maxdepth 1
ls testbench_ai_service/webui/__pycache__/
```

Expected: `frontend/` contains only `node_modules`. The `webui/__pycache__` listing shows ten `.pyc` files dated 2026-08-17. **Do not delete the second one.**

- [ ] **Step 2: Archive the August bytecode outside the repo**

Cheap insurance before any further work touches that tree.

```bash
mkdir -p ../tbai-webui-august-attempt
cp -r testbench_ai_service/webui/__pycache__ ../tbai-webui-august-attempt/
ls ../tbai-webui-august-attempt/__pycache__/
```

Expected: ten `.pyc` files copied.

- [ ] **Step 3: Delete the orphaned node_modules**

```bash
rm -rf frontend/node_modules
find frontend -maxdepth 1
```

Expected: only `frontend` itself remains.

- [ ] **Step 4: Add the ignore rules**

Append to `.gitignore`:

```gitignore
# Frontend (admin web UI)
node_modules/
frontend/dist/
# Vite build output, generated into the package by `npm run build`
testbench_ai_service/static/
```

- [ ] **Step 5: Verify the ignores actually match**

```bash
mkdir -p frontend/node_modules testbench_ai_service/static/admin
touch frontend/node_modules/x testbench_ai_service/static/admin/y
git status --short
```

Expected: neither path appears. Then clean up: `rm -rf frontend/node_modules testbench_ai_service/static`

- [ ] **Step 6: Commit**

```bash
git add .gitignore
git commit -m "Ignore frontend build artifacts"
```

---

### Task 2: Frontend scaffold that builds into the package

**Files:**
- Create: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/tsconfig.node.json`, `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/App.tsx`
- Create: `frontend/src/App.test.tsx`
- Create: `frontend/vitest.setup.ts`

**Interfaces:**
- Consumes: Task 1's clean `frontend/`
- Produces: `npm run build` writing `testbench_ai_service/static/admin/index.html` plus hashed assets; `npm test` running Vitest. Task 3 mounts that directory; Task 16 invokes that build.

- [ ] **Step 1: Create `frontend/package.json`**

Versions are floors — run `npm install` and commit the resulting `package-lock.json`.

```json
{
  "name": "testbench-ai-service-console",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^7.0.0",
    "@tanstack/react-query": "^5.0.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^5.0.0",
    "typescript": "^5.7.0",
    "vite": "^7.0.0",
    "vitest": "^3.0.0",
    "jsdom": "^26.0.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/jest-dom": "^6.0.0",
    "@testing-library/user-event": "^14.0.0"
  }
}
```

- [ ] **Step 2: Create `frontend/vite.config.ts`**

`base` and `outDir` are the two lines that make FastAPI able to serve this.

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/admin/',
  build: {
    outDir: '../testbench_ai_service/static/admin',
    emptyOutDir: true,
  },
  server: {
    // `npm run dev` talks to a locally running service
    proxy: { '/admin/api': 'http://127.0.0.1:8010' },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
  },
})
```

- [ ] **Step 3: Create the TypeScript config**

`frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noEmit": true,
    "skipLibCheck": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src", "vitest.setup.ts"]
}
```

`frontend/tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "noEmit": true,
    "types": ["node"]
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 4: Create `frontend/vitest.setup.ts`**

```ts
import '@testing-library/jest-dom/vitest'
```

- [ ] **Step 5: Create `frontend/index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>TestBench AI Service</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 6: Write the failing test**

`frontend/src/App.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { App } from './App'

test('renders the service name', () => {
  render(<App />)
  expect(screen.getByText('TestBench AI Service')).toBeInTheDocument()
})
```

- [ ] **Step 7: Install dependencies and run the test to verify it fails**

```bash
cd frontend && npm install && npm test
```

Expected: FAIL — `Failed to resolve import "./App"`.

- [ ] **Step 8: Write the minimal implementation**

`frontend/src/App.tsx`:

```tsx
export function App() {
  return <h1>TestBench AI Service</h1>
}
```

`frontend/src/main.tsx`:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

- [ ] **Step 9: Run the test to verify it passes**

```bash
cd frontend && npm test
```

Expected: PASS, 1 test.

- [ ] **Step 10: Verify the build lands in the package**

```bash
cd frontend && npm run build
ls ../testbench_ai_service/static/admin/
grep -o '/admin/assets/[^"]*' ../testbench_ai_service/static/admin/index.html
```

Expected: `index.html` and an `assets/` directory. The grep must show asset URLs prefixed `/admin/assets/` — if they are bare `/assets/`, `base` is wrong and Task 3 will serve a blank page.

- [ ] **Step 11: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts \
        frontend/tsconfig.json frontend/tsconfig.node.json frontend/index.html \
        frontend/vitest.setup.ts frontend/src
git commit -m "Add React frontend scaffold for the console"
```

---

### Task 3: SPA static mount with index fallback

**Files:**
- Create: `testbench_ai_service/webui/__init__.py`, `testbench_ai_service/webui/static.py`
- Create: `tests/unit/webui/__init__.py`, `tests/unit/webui/test_static.py`

**Interfaces:**
- Consumes: the build output layout from Task 2
- Produces: `mount_spa(app: FastAPI, directory: Path, path: str = "/admin") -> None`, called by Task 4 from `main.py`. Also `STATIC_DIR: Path`, the packaged build location.

- [ ] **Step 1: Write the failing tests**

`tests/unit/webui/test_static.py`:

```python
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from testbench_ai_service.webui.static import mount_spa


@pytest.fixture
def spa_dir(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text("<!doctype html>SPA ROOT", encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log(1)", encoding="utf-8")
    return tmp_path


@pytest.fixture
def client(spa_dir: Path) -> TestClient:
    app = FastAPI()
    mount_spa(app, spa_dir, "/admin")
    return TestClient(app)


def test_serves_index_at_mount_root(client: TestClient):
    response = client.get("/admin/")
    assert response.status_code == 200
    assert "SPA ROOT" in response.text


def test_serves_real_assets(client: TestClient):
    response = client.get("/admin/assets/app.js")
    assert response.status_code == 200
    assert response.text == "console.log(1)"


def test_client_route_falls_back_to_index(client: TestClient):
    """A deep link must survive a page reload."""
    response = client.get("/admin/prompts/de/test_case_set_reviewer")
    assert response.status_code == 200
    assert "SPA ROOT" in response.text


def test_missing_asset_is_404_not_index(client: TestClient):
    """Serving index.html for a missing .js would surface as a syntax error
    in the browser instead of an honest 404."""
    response = client.get("/admin/assets/missing.js")
    assert response.status_code == 404


def test_missing_directory_serves_placeholder(tmp_path: Path):
    """A pip install without a frontend build must not crash at startup."""
    app = FastAPI()
    mount_spa(app, tmp_path / "does-not-exist", "/admin")
    response = TestClient(app).get("/admin/")
    assert response.status_code == 200
    assert "not been built" in response.text
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/unit/webui/test_static.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'testbench_ai_service.webui.static'`.

- [ ] **Step 3: Write the implementation**

`testbench_ai_service/webui/__init__.py`:

```python
"""Web UI (admin console) backend: static hosting and the /admin/api routes."""
```

`testbench_ai_service/webui/static.py`:

```python
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
            if exc.status_code != 404:
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
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/unit/webui/test_static.py -v
```

Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add testbench_ai_service/webui/__init__.py testbench_ai_service/webui/static.py \
        tests/unit/webui/__init__.py tests/unit/webui/test_static.py
git commit -m "Serve the built console as a single-page app"
```

---

### Task 4: `admin_ui` config section and app wiring

**Files:**
- Create: `testbench_ai_service/models/webui.py`
- Modify: `testbench_ai_service/config.py` (add the `admin_ui` field to `AppConfig`)
- Modify: `testbench_ai_service/main.py` (`init_webui`, `config_path`, `started_at`)
- Modify: `testbench_ai_service/utils/config.py` (record the loaded path)
- Modify: `config_example.toml`
- Create: `tests/unit/webui/test_wiring.py`

**Interfaces:**
- Consumes: `mount_spa` from Task 3
- Produces: `AdminUiConfig` with `.enabled: bool` and `.require_loopback: bool`; `AppConfig.admin_ui`; `app.state.config_path: Path`; `app.state.started_at: datetime`. Task 5 reads `require_loopback`; Task 8 reads `started_at`; Tasks 8 and 10 read `config_path`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/webui/test_wiring.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from testbench_ai_service.config import AppConfig
from testbench_ai_service.main import create_app
from testbench_ai_service.models.webui import AdminUiConfig

TB_URL = "https://localhost:9443/api/"


def _app(**config_kwargs):
    with (
        patch("testbench_ai_service.config.validate_tb_server_url"),
        patch("testbench_ai_service.main.LLMFactory") as factory_cls,
    ):
        instance = MagicMock()
        instance.init_clients = MagicMock()
        instance.close_clients = AsyncMock()
        factory_cls.return_value = instance
        return create_app(AppConfig(tb_server_url=TB_URL, **config_kwargs))


def test_admin_ui_enabled_by_default():
    assert AdminUiConfig().enabled is True
    assert AdminUiConfig().require_loopback is False


def test_console_routes_present_when_enabled():
    app = _app()
    paths = {route.path for route in app.routes}
    assert any(path.startswith("/admin") for path in paths)


def test_console_absent_when_disabled():
    app = _app(admin_ui=AdminUiConfig(enabled=False))
    paths = {route.path for route in app.routes}
    assert not any(path.startswith("/admin") for path in paths)
    # The agent API is unaffected.
    assert "/agents" in paths


def test_existing_root_redirect_still_works():
    app = _app()
    with TestClient(app) as client:
        response = client.get("/", follow_redirects=False)
        assert response.status_code in (307, 302)
        assert response.headers["location"] == "/docs"


def test_warns_when_enabled_on_non_loopback_bind(caplog):
    with caplog.at_level("WARNING"):
        _app(host="0.0.0.0")  # noqa: S104 - deliberately testing this case
    assert any("reachable" in record.message.lower() for record in caplog.records)


def test_no_warning_on_loopback_bind(caplog):
    with caplog.at_level("WARNING"):
        _app(host="127.0.0.1")
    assert not any("reachable" in record.message.lower() for record in caplog.records)


def test_app_records_start_time_and_config_path():
    app = _app()
    assert app.state.started_at is not None
    assert app.state.config_path is not None
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/unit/webui/test_wiring.py -v
```

Expected: FAIL — no module `testbench_ai_service.models.webui`.

- [ ] **Step 3: Create the config model**

`testbench_ai_service/models/webui.py`:

```python
from pydantic import BaseModel


class AdminUiConfig(BaseModel):
    """Configuration for the browser console served at /admin."""

    enabled: bool = True
    require_loopback: bool = False
```

- [ ] **Step 4: Add the field to `AppConfig`**

In `testbench_ai_service/config.py`, import the model alongside the existing model imports:

```python
from testbench_ai_service.models.webui import AdminUiConfig
```

and add the field next to `logging`:

```python
    admin_ui: AdminUiConfig = Field(
        default_factory=AdminUiConfig,
        description="Browser console served at /admin",
    )
```

- [ ] **Step 5: Record the loaded config path**

`AppConfig` is loaded from a path that the app then forgets, but the console has to read that same file back. In `testbench_ai_service/utils/config.py`, inside `load_config_from_file`, after the config object is built, record where it came from:

```python
    config.loaded_from = config_file_path
```

and declare it on `AppConfig` in `config.py` as a non-serialised field:

```python
    loaded_from: Path | None = Field(
        default=None,
        exclude=True,
        description="Path this config was loaded from; set by load_config_from_file",
    )
```

`exclude=True` keeps it out of `model_dump()`, so it never leaks into the API payload in Task 10.

- [ ] **Step 6: Wire the console into `create_app`**

In `testbench_ai_service/main.py`, add the imports:

```python
from datetime import datetime, timezone
from ipaddress import ip_address
from pathlib import Path

from testbench_ai_service.log import logger
from testbench_ai_service.webui.static import STATIC_DIR, mount_spa
```

Add the initialiser:

```python
def _is_loopback_bind(host: str) -> bool:
    if host in ("localhost", ""):
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def init_webui(app: FastAPI):
    """Mount the browser console, unless it is disabled in config."""
    if not app.state.config.admin_ui.enabled:
        logger.info("Web console is disabled (admin_ui.enabled = false)")
        return

    if not _is_loopback_bind(app.state.config.host):
        logger.warning(
            "Web console is enabled and the service binds %s, so the console is "
            "reachable from other hosts. Restrict access or set "
            "admin_ui.require_loopback = true.",
            app.state.config.host,
        )

    from testbench_ai_service.webui.routes import router as webui_router

    app.include_router(webui_router)
    mount_spa(app, STATIC_DIR)
```

and call it from `create_app`, after `init_routers(app)` and before `init_services(app)`:

```python
    app.state.config_path = Path(getattr(config, "loaded_from", None) or "config.toml")
    app.state.started_at = datetime.now(timezone.utc)

    init_routers(app)
    init_webui(app)
```

The `mount_spa` call must come **after** `init_routers`, because a mount at `/admin` would otherwise shadow nothing but is clearer last, and the router must be registered before the catch-all static mount.

- [ ] **Step 7: Create a stub router so the import resolves**

Task 7 fills this in. `testbench_ai_service/webui/routes.py`:

```python
from fastapi import APIRouter

router = APIRouter(prefix="/admin/api", tags=["console"])
```

- [ ] **Step 8: Run the tests to verify they pass**

```bash
python -m pytest tests/unit/webui/test_wiring.py -v
```

Expected: PASS, 7 tests.

- [ ] **Step 9: Run the whole suite to confirm nothing regressed**

```bash
python -m pytest tests -q
```

Expected: all pre-existing tests still pass. `tests/unit/test_config.py` and `tests/unit/test_main.py` are the likely places for a surprise — a new `AppConfig` field can break an exact-dict assertion.

- [ ] **Step 10: Document the new section in `config_example.toml`**

Append:

```toml
# Browser console served at /admin
[testbench-ai-service.admin_ui]
enabled = true
# Refuse the console to any client that is not on this host.
# require_loopback = false
```

- [ ] **Step 11: Commit**

```bash
git add testbench_ai_service/models/webui.py testbench_ai_service/config.py \
        testbench_ai_service/main.py testbench_ai_service/utils/config.py \
        testbench_ai_service/webui/routes.py config_example.toml \
        tests/unit/webui/test_wiring.py
git commit -m "Mount the web console behind an admin_ui config section"
```

---

### Task 5: Path containment and the loopback guard

The most security-sensitive module in the feature (spec 9.1). It lands now so that no later task can add a prompt endpoint without it.

**Files:**
- Create: `testbench_ai_service/webui/security.py`
- Create: `tests/unit/webui/test_security.py`

**Interfaces:**
- Consumes: `AdminUiConfig.require_loopback` from Task 4
- Produces:
  - `resolve_within(base: Path, candidate: str | Path) -> Path` — raises `HTTPException(400)` on escape
  - `is_loopback(host: str | None) -> bool`
  - `require_loopback(request: Request, config: AppConfig = Depends(get_app_config)) -> None` — a FastAPI dependency, used by Task 7's router

- [ ] **Step 1: Write the failing tests**

`tests/unit/webui/test_security.py`:

```python
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

from testbench_ai_service.webui.security import is_loopback, resolve_within


@pytest.fixture
def base(tmp_path: Path) -> Path:
    (tmp_path / "de" / "reviewer").mkdir(parents=True)
    (tmp_path / "de" / "reviewer" / "prompt.yaml").write_text("name: x", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("secret", encoding="utf-8")
    return tmp_path / "de"


def test_allows_nested_relative_path(base: Path):
    assert resolve_within(base, "reviewer/prompt.yaml") == (
        base / "reviewer" / "prompt.yaml"
    ).resolve()


def test_allows_the_base_itself(base: Path):
    assert resolve_within(base, ".") == base.resolve()


def test_rejects_parent_traversal(base: Path):
    with pytest.raises(HTTPException) as exc:
        resolve_within(base, "../outside.txt")
    assert exc.value.status_code == 400


def test_rejects_deep_traversal(base: Path):
    with pytest.raises(HTTPException):
        resolve_within(base, "reviewer/../../../../etc/passwd")


def test_rejects_absolute_path_outside_base(base: Path, tmp_path: Path):
    with pytest.raises(HTTPException):
        resolve_within(base, tmp_path / "outside.txt")


def test_accepts_absolute_path_inside_base(base: Path):
    inside = base / "reviewer" / "prompt.yaml"
    assert resolve_within(base, inside) == inside.resolve()


def test_rejects_prefix_sibling_directory(tmp_path: Path):
    """`/prompts-evil` must not pass a containment check against `/prompts`."""
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts-evil").mkdir()
    with pytest.raises(HTTPException):
        resolve_within(tmp_path / "prompts", tmp_path / "prompts-evil")


@pytest.mark.skipif(
    sys.platform == "win32", reason="symlink creation needs privileges on Windows"
)
def test_rejects_symlink_escaping_the_base(base: Path, tmp_path: Path):
    (base / "escape").symlink_to(tmp_path / "outside.txt")
    with pytest.raises(HTTPException):
        resolve_within(base, "escape")


def test_rejects_empty_candidate(base: Path):
    with pytest.raises(HTTPException):
        resolve_within(base, "")


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost", "127.0.0.5"])
def test_loopback_hosts(host: str):
    assert is_loopback(host) is True


@pytest.mark.parametrize("host", ["10.0.0.4", "192.168.1.9", "example.com", None, ""])
def test_non_loopback_hosts(host):
    assert is_loopback(host) is False
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/unit/webui/test_security.py -v
```

Expected: FAIL — no module `testbench_ai_service.webui.security`.

- [ ] **Step 3: Write the implementation**

`testbench_ai_service/webui/security.py`:

```python
"""Containment helpers for the console.

Every filesystem path the console derives from request data goes through
:func:`resolve_within`.  Without it the prompt endpoints would be an arbitrary
file read, and the write endpoints an arbitrary file write.
"""

from ipaddress import ip_address
from pathlib import Path

from fastapi import Depends, HTTPException, Request, status

from testbench_ai_service.config import AppConfig
from testbench_ai_service.dependencies import get_app_config
from testbench_ai_service.log import logger


def resolve_within(base: Path, candidate: str | Path) -> Path:
    """Resolve *candidate* against *base* and require the result to stay inside it.

    Symlinks are resolved before the check, so a link inside *base* that points
    outside it is refused as well.

    Raises:
        HTTPException 400: *candidate* is empty, or escapes *base*.
    """
    if not str(candidate).strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Empty path is not allowed"
        )

    base_resolved = Path(base).resolve()
    candidate_path = Path(candidate)
    target = (
        candidate_path.resolve()
        if candidate_path.is_absolute()
        else (base_resolved / candidate_path).resolve()
    )

    # relative_to on the resolved paths is what rejects both `..` traversal and a
    # sibling directory that merely shares a name prefix.
    try:
        target.relative_to(base_resolved)
    except ValueError:
        logger.warning("Rejected path outside %s: %r", base_resolved, str(candidate))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path is outside the permitted directory",
        ) from None

    return target


def is_loopback(host: str | None) -> bool:
    """Return True if *host* refers to this machine."""
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def require_loopback(
    request: Request, config: AppConfig = Depends(get_app_config)
) -> None:
    """Refuse non-loopback clients when ``admin_ui.require_loopback`` is set."""
    if not config.admin_ui.require_loopback:
        return
    client_host = request.client.host if request.client else None
    if not is_loopback(client_host):
        logger.warning("Refused console request from non-loopback client %s", client_host)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The console is restricted to local access",
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/unit/webui/test_security.py -v
```

Expected: PASS. The symlink test skips on Windows.

- [ ] **Step 5: Commit**

```bash
git add testbench_ai_service/webui/security.py tests/unit/webui/test_security.py
git commit -m "Add path containment and loopback guard for the console"
```

---

### Task 6: Session store

Pure in-memory store with no HTTP involvement, so expiry is tested by injecting a clock rather than sleeping.

**Files:**
- Create: `testbench_ai_service/webui/session.py`
- Create: `tests/unit/webui/test_session.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `Session` dataclass: `.sid`, `.csrf_token`, `.username`, `.roles: list[str]`, `.is_admin`, `.tb_session_token`, `.created_at`, `.last_seen`
  - `SessionStore(idle_timeout: timedelta = IDLE_TIMEOUT, absolute_timeout: timedelta = ABSOLUTE_TIMEOUT, now: Callable[[], datetime] = ...)`
  - `.create(username, roles, is_admin, tb_session_token) -> Session`
  - `.get(sid: str | None) -> Session | None` — refreshes `last_seen`
  - `.revoke(sid: str) -> None`
  - `IDLE_TIMEOUT = timedelta(minutes=60)`, `ABSOLUTE_TIMEOUT = timedelta(hours=8)`
- Task 7 constructs one store per app and reads `.csrf_token` for the CSRF check.

- [ ] **Step 1: Write the failing tests**

`tests/unit/webui/test_session.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest

from testbench_ai_service.webui.session import (
    ABSOLUTE_TIMEOUT,
    IDLE_TIMEOUT,
    SessionStore,
)


class Clock:
    def __init__(self):
        self.now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta):
        self.now += delta


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store(clock: Clock) -> SessionStore:
    return SessionStore(now=clock)


def _create(store: SessionStore, is_admin: bool = True):
    return store.create(
        username="a.mueller",
        roles=["Administrator"] if is_admin else ["ProjectUser"],
        is_admin=is_admin,
        tb_session_token="tb-token-abc",
    )


def test_create_returns_retrievable_session(store: SessionStore):
    session = _create(store)
    assert store.get(session.sid) is session
    assert session.username == "a.mueller"
    assert session.is_admin is True


def test_sid_and_csrf_are_distinct_and_unguessable(store: SessionStore):
    session = _create(store)
    assert session.sid != session.csrf_token
    assert len(session.sid) >= 32
    assert len(session.csrf_token) >= 32


def test_sessions_are_unique(store: SessionStore):
    assert _create(store).sid != _create(store).sid


def test_get_unknown_sid_returns_none(store: SessionStore):
    assert store.get("nope") is None


def test_get_none_returns_none(store: SessionStore):
    assert store.get(None) is None


def test_revoke_removes_the_session(store: SessionStore):
    session = _create(store)
    store.revoke(session.sid)
    assert store.get(session.sid) is None


def test_revoke_is_idempotent(store: SessionStore):
    store.revoke("never-existed")


def test_expires_after_idle_timeout(store: SessionStore, clock: Clock):
    session = _create(store)
    clock.advance(IDLE_TIMEOUT + timedelta(seconds=1))
    assert store.get(session.sid) is None


def test_activity_refreshes_the_idle_timeout(store: SessionStore, clock: Clock):
    session = _create(store)
    for _ in range(4):
        clock.advance(IDLE_TIMEOUT - timedelta(minutes=1))
        assert store.get(session.sid) is not None


def test_expires_at_absolute_cap_despite_activity(store: SessionStore, clock: Clock):
    session = _create(store)
    for _ in range(20):
        clock.advance(IDLE_TIMEOUT - timedelta(minutes=1))
        store.get(session.sid)
    clock.advance(ABSOLUTE_TIMEOUT)
    assert store.get(session.sid) is None


def test_expired_session_is_dropped_not_merely_hidden(store: SessionStore, clock: Clock):
    session = _create(store)
    clock.advance(ABSOLUTE_TIMEOUT + timedelta(seconds=1))
    store.get(session.sid)
    assert session.sid not in store._sessions


def test_defaults_match_the_spec():
    assert IDLE_TIMEOUT == timedelta(minutes=60)
    assert ABSOLUTE_TIMEOUT == timedelta(hours=8)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/unit/webui/test_session.py -v
```

Expected: FAIL — no module `testbench_ai_service.webui.session`.

- [ ] **Step 3: Write the implementation**

`testbench_ai_service/webui/session.py`:

```python
"""Server-side session store for the console.

The browser only ever receives an opaque session id.  The TestBench session
token stays here, so a stolen cookie cannot be replayed against TestBench.

The store is process-local: restarting the service logs everyone out.
"""

import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

IDLE_TIMEOUT = timedelta(minutes=60)
ABSOLUTE_TIMEOUT = timedelta(hours=8)

SESSION_COOKIE = "tbai_admin_session"
CSRF_COOKIE = "tbai_admin_csrf"
CSRF_HEADER = "X-CSRF-Token"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Session:
    """One logged-in console user."""

    sid: str
    csrf_token: str
    username: str
    roles: list[str]
    is_admin: bool
    tb_session_token: str = field(repr=False)
    created_at: datetime
    last_seen: datetime


class SessionStore:
    """In-memory sessions with an idle timeout and an absolute cap."""

    def __init__(
        self,
        idle_timeout: timedelta = IDLE_TIMEOUT,
        absolute_timeout: timedelta = ABSOLUTE_TIMEOUT,
        now: Callable[[], datetime] = _utcnow,
    ):
        self._sessions: dict[str, Session] = {}
        self._idle_timeout = idle_timeout
        self._absolute_timeout = absolute_timeout
        self._now = now

    def create(
        self, username: str, roles: list[str], is_admin: bool, tb_session_token: str
    ) -> Session:
        moment = self._now()
        session = Session(
            sid=secrets.token_urlsafe(32),
            csrf_token=secrets.token_urlsafe(32),
            username=username,
            roles=roles,
            is_admin=is_admin,
            tb_session_token=tb_session_token,
            created_at=moment,
            last_seen=moment,
        )
        self._sessions[session.sid] = session
        return session

    def get(self, sid: str | None) -> Session | None:
        """Return the live session for *sid*, refreshing its idle timer.

        An expired session is discarded rather than merely hidden.
        """
        if not sid:
            return None
        session = self._sessions.get(sid)
        if session is None:
            return None

        moment = self._now()
        if (
            moment - session.last_seen > self._idle_timeout
            or moment - session.created_at > self._absolute_timeout
        ):
            del self._sessions[sid]
            return None

        session.last_seen = moment
        return session

    def revoke(self, sid: str) -> None:
        self._sessions.pop(sid, None)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/unit/webui/test_session.py -v
```

Expected: PASS, 12 tests.

- [ ] **Step 5: Commit**

```bash
git add testbench_ai_service/webui/session.py tests/unit/webui/test_session.py
git commit -m "Add server-side session store for the console"
```

---

### Task 7: Login, logout, and the session endpoint

**Files:**
- Create: `testbench_ai_service/webui/models.py`
- Create: `testbench_ai_service/webui/auth.py`
- Modify: `testbench_ai_service/webui/routes.py`
- Modify: `testbench_ai_service/main.py` (attach the store to `app.state`)
- Create: `tests/unit/webui/conftest.py`, `tests/unit/webui/test_auth_routes.py`

**Interfaces:**
- Consumes: `SessionStore`, `Session`, cookie/header names from Task 6; `require_loopback` from Task 5
- Produces:
  - `current_session(...) -> Session` — dependency, 401 when absent/expired
  - `require_admin(session: Session = Depends(current_session)) -> Session` — 403 for non-admins
  - `require_csrf(...) -> None` — 403 on mismatch
  - `SessionResponse` with `.username`, `.roles`, `.is_admin`, `.tb_server_url`
- Tasks 8, 9 and 10 depend on `current_session`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/webui/conftest.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from testbench_ai_service.config import AppConfig
from testbench_ai_service.main import create_app

TB_URL = "https://localhost:9443/api/"


@pytest.fixture
def make_app():
    """Build a real app with the LLM factory mocked out."""

    def _make(**config_kwargs):
        with (
            patch("testbench_ai_service.config.validate_tb_server_url"),
            patch("testbench_ai_service.main.LLMFactory") as factory_cls,
        ):
            instance = MagicMock()
            instance.init_clients = MagicMock()
            instance.close_clients = AsyncMock()
            factory_cls.return_value = instance
            return create_app(AppConfig(tb_server_url=TB_URL, **config_kwargs))

    return _make


@pytest.fixture
def app(make_app):
    return make_app()


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def tb_connection():
    """A stand-in for testbench_cli_reporter's Connection."""
    conn = MagicMock()
    conn.session_token = "tb-token-abc"
    conn.read_user_roles.return_value = ["Administrator"]
    conn.session = MagicMock()
    return conn


@pytest.fixture
def login(client, tb_connection):
    """Log in and return the response, with TestBench mocked."""

    def _login(username="a.mueller", password="pw", roles=None):
        if roles is not None:
            tb_connection.read_user_roles.return_value = roles
        with patch(
            "testbench_ai_service.webui.auth.TBConnection", return_value=tb_connection
        ):
            return client.post(
                "/admin/api/session", json={"username": username, "password": password}
            )

    return _login
```

`tests/unit/webui/test_auth_routes.py`:

```python
from unittest.mock import patch

import pytest
import requests

from testbench_ai_service.webui.session import (
    CSRF_COOKIE,
    CSRF_HEADER,
    SESSION_COOKIE,
)


def test_login_sets_both_cookies(login):
    response = login()
    assert response.status_code == 200
    assert SESSION_COOKIE in response.cookies
    assert CSRF_COOKIE in response.cookies


def test_login_returns_identity_not_secrets(login):
    body = login().json()
    assert body["username"] == "a.mueller"
    assert body["is_admin"] is True
    assert body["roles"] == ["Administrator"]
    # The TestBench token must never reach the browser.
    assert "tb-token-abc" not in str(body)


def test_session_cookie_is_httponly_and_strict(login):
    response = login()
    header = "".join(
        v for k, v in response.headers.items() if k.lower() == "set-cookie"
    )
    assert "httponly" in header.lower()
    assert "samesite=strict" in header.lower().replace(" ", "")


def test_csrf_cookie_is_readable_by_script(login):
    """The SPA has to read this one to echo it back."""
    response = login()
    cookie_headers = [
        v for k, v in response.headers.items() if k.lower() == "set-cookie"
    ]
    csrf_header = next(h for h in cookie_headers if h.startswith(CSRF_COOKIE))
    assert "httponly" not in csrf_header.lower()


def test_non_admin_login_reports_not_admin(login):
    body = login(roles=["ProjectUser"]).json()
    assert body["is_admin"] is False


def test_project_user_with_space_is_not_admin(login):
    """The TestBench 3 path can answer 'Project User' with a space."""
    assert login(roles=["Project User"]).json()["is_admin"] is False


def test_bad_credentials_return_401(client, tb_connection):
    error = requests.exceptions.HTTPError(response=type("R", (), {"status_code": 401})())
    tb_connection.read_user_roles.side_effect = error
    with patch(
        "testbench_ai_service.webui.auth.TBConnection", return_value=tb_connection
    ):
        response = client.post(
            "/admin/api/session", json={"username": "a", "password": "wrong"}
        )
    assert response.status_code == 401
    assert SESSION_COOKIE not in response.cookies


def test_malformed_server_url_is_a_config_error_not_a_401(client):
    """TBConnection raises ValueError for a URL without an explicit port."""
    with patch(
        "testbench_ai_service.webui.auth.TBConnection",
        side_effect=ValueError("Invalid server URL"),
    ):
        response = client.post(
            "/admin/api/session", json={"username": "a", "password": "pw"}
        )
    assert response.status_code == 500
    assert "configuration" in response.json()["detail"].lower()


def test_get_session_without_cookie_is_401(client):
    assert client.get("/admin/api/session").status_code == 401


def test_get_session_after_login_returns_identity(client, login):
    login()
    response = client.get("/admin/api/session")
    assert response.status_code == 200
    assert response.json()["username"] == "a.mueller"
    assert response.json()["tb_server_url"].endswith("/api/")


def test_logout_revokes_the_session(client, login):
    csrf = login().cookies[CSRF_COOKIE]
    assert client.delete(
        "/admin/api/session", headers={CSRF_HEADER: csrf}
    ).status_code == 204
    assert client.get("/admin/api/session").status_code == 401


def test_logout_without_csrf_header_is_403(client, login):
    login()
    assert client.delete("/admin/api/session").status_code == 403


def test_logout_with_wrong_csrf_token_is_403(client, login):
    login()
    assert (
        client.delete(
            "/admin/api/session", headers={CSRF_HEADER: "not-the-token"}
        ).status_code
        == 403
    )


def test_unknown_session_cookie_is_401(client):
    client.cookies.set(SESSION_COOKIE, "forged")
    assert client.get("/admin/api/session").status_code == 401


def test_meta_is_reachable_without_a_session(client):
    """The login screen must be able to name the TestBench server."""
    response = client.get("/admin/api/meta")
    assert response.status_code == 200
    assert response.json()["tb_server_url"] == "https://localhost:9443/api/"


def test_meta_exposes_nothing_else(client):
    assert set(client.get("/admin/api/meta").json()) == {"tb_server_url"}


def test_require_admin_accepts_an_admin():
    from testbench_ai_service.webui.auth import require_admin
    from testbench_ai_service.webui.session import SessionStore

    session = SessionStore().create(
        username="a", roles=["Administrator"], is_admin=True, tb_session_token="t"
    )
    assert require_admin(session) is session


def test_require_admin_refuses_a_non_admin():
    from fastapi import HTTPException

    from testbench_ai_service.webui.auth import require_admin
    from testbench_ai_service.webui.session import SessionStore

    session = SessionStore().create(
        username="p", roles=["ProjectUser"], is_admin=False, tb_session_token="t"
    )
    with pytest.raises(HTTPException) as exc:
        require_admin(session)
    assert exc.value.status_code == 403


def test_require_loopback_refuses_remote_client(make_app, tb_connection):
    from fastapi.testclient import TestClient

    from testbench_ai_service.models.webui import AdminUiConfig

    app = make_app(admin_ui=AdminUiConfig(require_loopback=True))
    with TestClient(app, client=("10.0.0.9", 5000), raise_server_exceptions=False) as c:
        with patch(
            "testbench_ai_service.webui.auth.TBConnection", return_value=tb_connection
        ):
            response = c.post(
                "/admin/api/session", json={"username": "a", "password": "pw"}
            )
    assert response.status_code == 403
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/unit/webui/test_auth_routes.py -v
```

Expected: FAIL — 404 on `/admin/api/session`, since Task 4's router is still a stub.

- [ ] **Step 3: Write the request/response models**

`testbench_ai_service/webui/models.py`:

```python
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class SessionResponse(BaseModel):
    """Identity of the current console user. Deliberately carries no token."""

    username: str
    roles: list[str]
    is_admin: bool
    tb_server_url: str


class MetaResponse(BaseModel):
    """The only unauthenticated payload: which TestBench this service signs into.

    The login screen needs it before a session can exist. Nothing else belongs
    here — see spec section 8.
    """

    tb_server_url: str
```

- [ ] **Step 4: Write the auth module**

`testbench_ai_service/webui/auth.py`:

```python
"""Console authentication: TestBench login, cookies, CSRF, and role checks."""

import math
import secrets

import requests
from fastapi import Cookie, Depends, Header, HTTPException, Request, Response, status
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.config import AppConfig
from testbench_ai_service.dependencies import get_app_config
from testbench_ai_service.exceptions import TRANSPORT_ERRORS, handle_requests_transport_error
from testbench_ai_service.log import logger
from testbench_ai_service.models.testbench import GlobalHumanRole
from testbench_ai_service.transport import (
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_READ_TIMEOUT,
    harden_connection,
)
from testbench_ai_service.webui.session import (
    CSRF_COOKIE,
    CSRF_HEADER,
    SESSION_COOKIE,
    Session,
    SessionStore,
)


def get_session_store(request: Request) -> SessionStore:
    store: SessionStore = request.app.state.webui_sessions
    return store


def is_admin_role(roles: list[str]) -> bool:
    """True when *roles* grants global administration.

    The role list differs between TestBench 3 and 4 and can contain
    ``"Project User"`` with a space, so only the exact administrator string counts.
    """
    return GlobalHumanRole.Administrator.value in roles


def authenticate(config: AppConfig, username: str, password: str) -> tuple[str, list[str]]:
    """Log in to TestBench and return ``(session_token, roles)``.

    Raises:
        HTTPException 401: TestBench rejected the credentials.
        HTTPException 500: ``tb_server_url`` is not a usable TestBench URL.
        HTTPException 502: TestBench is unreachable.
    """
    conn: TBConnection | None = None
    try:
        conn = TBConnection(
            config.tb_server_url,
            verify=config.tb_ssl_ca_bundle or config.tb_ssl_verify,
            loginname=username,
            password=password,
            connection_timeout_sec=math.ceil(DEFAULT_READ_TIMEOUT),
        )
        harden_connection(
            conn,
            connect_timeout=DEFAULT_CONNECT_TIMEOUT,
            read_timeout=DEFAULT_READ_TIMEOUT,
        )
        roles = conn.read_user_roles(conn.session)
        token = conn.session_token
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
            )
        return token, list(roles)
    except ValueError as e:
        # TBConnection validates the URL shape in __init__.
        logger.error("Cannot log in to TestBench: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"TestBench server URL is not usable, check the configuration: {e}",
        ) from e
    except requests.exceptions.HTTPError as e:
        logger.warning("Console login rejected for user %r", username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        ) from e
    except TRANSPORT_ERRORS as e:
        handle_requests_transport_error(e)
    finally:
        if conn is not None:
            conn.close()


def set_session_cookies(response: Response, session: Session, config: AppConfig) -> None:
    """Attach the opaque session cookie and the readable CSRF cookie."""
    secure = bool(config.ssl_cert and config.ssl_key)
    response.set_cookie(
        SESSION_COOKIE,
        session.sid,
        httponly=True,
        samesite="strict",
        secure=secure,
        path="/admin",
    )
    response.set_cookie(
        CSRF_COOKIE,
        session.csrf_token,
        httponly=False,  # the SPA must read this to echo it back
        samesite="strict",
        secure=secure,
        path="/admin",
    )


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/admin")
    response.delete_cookie(CSRF_COOKIE, path="/admin")


def current_session(
    store: SessionStore = Depends(get_session_store),
    sid: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Session:
    """The live session for this request, or 401."""
    session = store.get(sid)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in"
        )
    return session


def require_admin(session: Session = Depends(current_session)) -> Session:
    """Guard every mutating route: writes require the TestBench admin role."""
    if not session.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires the TestBench Administrator role",
        )
    return session


def require_csrf(
    session: Session = Depends(current_session),
    token: str | None = Header(default=None, alias=CSRF_HEADER),
) -> None:
    """Double-submit check for any state-changing request."""
    if not token or not secrets.compare_digest(token, session.csrf_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Missing or invalid CSRF token"
        )
```

- [ ] **Step 5: Write the routes**

Replace `testbench_ai_service/webui/routes.py`:

```python
from fastapi import APIRouter, Depends, Response, status

from testbench_ai_service.config import AppConfig
from testbench_ai_service.dependencies import get_app_config
from testbench_ai_service.webui.auth import (
    authenticate,
    clear_session_cookies,
    current_session,
    get_session_store,
    is_admin_role,
    require_csrf,
    set_session_cookies,
)
from testbench_ai_service.webui.models import (
    LoginRequest,
    MetaResponse,
    SessionResponse,
)
from testbench_ai_service.webui.security import require_loopback
from testbench_ai_service.webui.session import Session, SessionStore

router = APIRouter(
    prefix="/admin/api",
    tags=["console"],
    dependencies=[Depends(require_loopback)],
)


@router.get("/meta", response_model=MetaResponse)
async def read_meta(config: AppConfig = Depends(get_app_config)) -> MetaResponse:
    """Unauthenticated: the login screen names the server before signing in.

    Deliberately carries nothing but the URL.
    """
    return MetaResponse(tb_server_url=config.tb_server_url)


@router.post("/session", response_model=SessionResponse)
async def sign_in(
    body: LoginRequest,
    response: Response,
    config: AppConfig = Depends(get_app_config),
    store: SessionStore = Depends(get_session_store),
) -> SessionResponse:
    """Exchange TestBench credentials for a console session."""
    token, roles = authenticate(config, body.username, body.password)
    session = store.create(
        username=body.username,
        roles=roles,
        is_admin=is_admin_role(roles),
        tb_session_token=token,
    )
    set_session_cookies(response, session, config)
    return SessionResponse(
        username=session.username,
        roles=session.roles,
        is_admin=session.is_admin,
        tb_server_url=config.tb_server_url,
    )


@router.get("/session", response_model=SessionResponse)
async def read_session(
    session: Session = Depends(current_session),
    config: AppConfig = Depends(get_app_config),
) -> SessionResponse:
    """Who am I — so a page reload does not force a new login."""
    return SessionResponse(
        username=session.username,
        roles=session.roles,
        is_admin=session.is_admin,
        tb_server_url=config.tb_server_url,
    )


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out(
    response: Response,
    session: Session = Depends(current_session),
    store: SessionStore = Depends(get_session_store),
    _: None = Depends(require_csrf),
) -> Response:
    store.revoke(session.sid)
    clear_session_cookies(response)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 6: Attach the store to the app**

In `testbench_ai_service/main.py`, inside `init_webui`, before `app.include_router`:

```python
    from testbench_ai_service.webui.session import SessionStore

    app.state.webui_sessions = SessionStore()
```

- [ ] **Step 7: Run the tests to verify they pass**

```bash
python -m pytest tests/unit/webui/test_auth_routes.py -v
```

Expected: PASS, 15 tests.

- [ ] **Step 8: Commit**

```bash
git add testbench_ai_service/webui/models.py testbench_ai_service/webui/auth.py \
        testbench_ai_service/webui/routes.py testbench_ai_service/main.py \
        tests/unit/webui/conftest.py tests/unit/webui/test_auth_routes.py
git commit -m "Add console login with session cookies and CSRF"
```

---

### Task 8: Status endpoint

**Files:**
- Create: `testbench_ai_service/webui/status.py`
- Modify: `testbench_ai_service/webui/models.py`, `testbench_ai_service/webui/routes.py`
- Create: `tests/unit/webui/test_status.py`

**Interfaces:**
- Consumes: `current_session` (Task 7), `app.state.started_at` (Task 4)
- Produces: `GET /admin/api/status` returning `StatusResponse` with `.service`, `.testbench`, `.api_keys`, `.agents`, `.log_file`. `known_api_key_names(config) -> list[str]` is reused by Task 10's model catalogue in phase 2.

- [ ] **Step 1: Write the failing tests**

`tests/unit/webui/test_status.py`:

```python
import os
from unittest.mock import MagicMock, patch

import requests


def _status(client):
    return client.get("/admin/api/status")


def test_status_requires_a_session(client):
    assert _status(client).status_code == 401


def test_status_reports_service_facts(client, login):
    login()
    body = _status(client).json()
    assert body["service"]["host"] == "127.0.0.1"
    assert body["service"]["port"] == 8010
    assert body["service"]["version"]
    assert body["service"]["uptime_seconds"] >= 0


def test_status_reports_testbench_url_and_reachability(client, login):
    login()
    with patch("testbench_ai_service.webui.status.requests.get") as get:
        get.return_value = MagicMock(status_code=200)
        body = _status(client).json()
    assert body["testbench"]["url"].endswith("/api/")
    assert body["testbench"]["reachable"] is True


def test_unreachable_testbench_is_reported_not_raised(client, login):
    login()
    with patch(
        "testbench_ai_service.webui.status.requests.get",
        side_effect=requests.exceptions.ConnectionError("refused"),
    ):
        response = _status(client)
    assert response.status_code == 200
    assert response.json()["testbench"]["reachable"] is False


def test_api_keys_report_presence_only(client, login, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-super-secret-value")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    login()
    body = _status(client).json()
    keys = {entry["name"]: entry["present"] for entry in body["api_keys"]}
    assert keys["OPENAI_API_KEY"] is True
    assert keys["ANTHROPIC_API_KEY"] is False
    # The value must never appear anywhere in the payload.
    assert "sk-super-secret-value" not in str(body)


def test_agent_summary_counts_enabled_and_overrides(client, login):
    login()
    body = _status(client).json()
    assert body["agents"]["total"] == 3
    assert body["agents"]["enabled"] == 3
    assert body["agents"]["project_overrides"] == 0


def test_log_file_name_is_reported(client, login):
    login()
    assert _status(client).json()["log_file"] == "testbench-ai-service.log"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/unit/webui/test_status.py -v
```

Expected: FAIL — 404 on `/admin/api/status`.

- [ ] **Step 3: Add the response models**

Append to `testbench_ai_service/webui/models.py`:

```python
class ServiceStatus(BaseModel):
    version: str
    host: str
    port: int
    debug: bool
    uptime_seconds: float
    language: str


class TestBenchStatus(BaseModel):
    url: str
    reachable: bool
    detail: str | None = None


class ApiKeyStatus(BaseModel):
    """Whether a provider credential is configured. Never its value."""

    name: str
    present: bool


class AgentSummary(BaseModel):
    total: int
    enabled: int
    project_overrides: int
    projects: int


class StatusResponse(BaseModel):
    service: ServiceStatus
    testbench: TestBenchStatus
    api_keys: list[ApiKeyStatus]
    agents: AgentSummary
    log_file: str
```

- [ ] **Step 4: Write the status probes**

`testbench_ai_service/webui/status.py`:

```python
"""Read-only operational probes for the console's Status screen."""

import os
from datetime import datetime, timezone

import requests

from testbench_ai_service import __version__
from testbench_ai_service.config import AppConfig
from testbench_ai_service.log import logger
from testbench_ai_service.webui.models import (
    AgentSummary,
    ApiKeyStatus,
    ServiceStatus,
    StatusResponse,
    TestBenchStatus,
)

#: Provider credentials the service understands. Presence is reported, never values.
API_KEY_NAMES = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "AZURE_TENANT_ID",
    "AZURE_CLIENT_ID",
    "AZURE_CLIENT_SECRET",
)

_PROBE_TIMEOUT = 3.0


def known_api_key_names(config: AppConfig) -> list[str]:
    """The credential names worth reporting, most relevant provider first."""
    del config  # reserved for provider-specific narrowing in a later phase
    return list(API_KEY_NAMES)


def api_key_statuses(config: AppConfig) -> list[ApiKeyStatus]:
    return [
        ApiKeyStatus(name=name, present=bool(os.environ.get(name)))
        for name in known_api_key_names(config)
    ]


def probe_testbench(config: AppConfig) -> TestBenchStatus:
    """Check that the TestBench REST API answers, without authenticating."""
    verify: bool | str = config.tb_ssl_ca_bundle or config.tb_ssl_verify
    try:
        response = requests.get(
            f"{config.tb_server_url}1/version",
            verify=verify,
            timeout=_PROBE_TIMEOUT,
        )
    except requests.exceptions.RequestException as e:
        logger.debug("TestBench probe failed: %s", e)
        return TestBenchStatus(
            url=config.tb_server_url, reachable=False, detail=type(e).__name__
        )
    # Any HTTP answer means the server is up; 401 is expected without credentials.
    return TestBenchStatus(
        url=config.tb_server_url,
        reachable=True,
        detail=f"HTTP {response.status_code}",
    )


def agent_summary(config: AppConfig) -> AgentSummary:
    overrides = sum(
        len(project.agents or {}) + (1 if project.language else 0)
        for project in config.projects.values()
    )
    return AgentSummary(
        total=len(config.agents),
        enabled=sum(1 for agent in config.agents.values() if agent.enabled),
        project_overrides=overrides,
        projects=len(config.projects),
    )


def build_status(config: AppConfig, started_at: datetime) -> StatusResponse:
    uptime = (datetime.now(timezone.utc) - started_at).total_seconds()
    return StatusResponse(
        service=ServiceStatus(
            version=__version__,
            host=config.host,
            port=config.port,
            debug=config.debug,
            uptime_seconds=max(uptime, 0.0),
            language=config.language.value,
        ),
        testbench=probe_testbench(config),
        api_keys=api_key_statuses(config),
        agents=agent_summary(config),
        log_file=config.logging.file.file_name,
    )
```

- [ ] **Step 5: Add the route**

Append to `testbench_ai_service/webui/routes.py` (and extend the imports):

```python
@router.get("/status", response_model=StatusResponse)
async def read_status(
    request: Request,
    _: Session = Depends(current_session),
    config: AppConfig = Depends(get_app_config),
) -> StatusResponse:
    return build_status(config, request.app.state.started_at)
```

Imports to add: `Request` from `fastapi`, `StatusResponse` from `.models`, `build_status` from `.status`.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
python -m pytest tests/unit/webui/test_status.py -v
```

Expected: PASS, 7 tests.

- [ ] **Step 7: Commit**

```bash
git add testbench_ai_service/webui/status.py testbench_ai_service/webui/models.py \
        testbench_ai_service/webui/routes.py tests/unit/webui/test_status.py
git commit -m "Add console status endpoint"
```

---

### Task 9: Log tail endpoint

**Files:**
- Create: `testbench_ai_service/webui/logs.py`
- Modify: `testbench_ai_service/webui/models.py`, `testbench_ai_service/webui/routes.py`
- Create: `tests/unit/webui/test_logs.py`

**Interfaces:**
- Consumes: `current_session` (Task 7)
- Produces: `GET /admin/api/logs?limit=` returning `list[LogLine]` with `.timestamp`, `.level`, `.source`, `.message`, `.raw`. `tail_lines(path, limit)` and `parse_log_line(text)` are exported for reuse.

- [ ] **Step 1: Write the failing tests**

`tests/unit/webui/test_logs.py`:

```python
from pathlib import Path

import pytest

from testbench_ai_service.webui.logs import parse_log_line, tail_lines

SAMPLE = (
    "2026-09-08 10:11:50,123 -     INFO - auth - JWT validated for a.mueller\n"
    "2026-09-08 10:12:03,000 -  WARNING - llm.openai - request timed out\n"
)


def test_tail_returns_last_n_lines(tmp_path: Path):
    log = tmp_path / "svc.log"
    log.write_text("\n".join(f"line {i}" for i in range(100)), encoding="utf-8")
    assert tail_lines(log, 5) == [f"line {i}" for i in range(95, 100)]


def test_tail_handles_fewer_lines_than_requested(tmp_path: Path):
    log = tmp_path / "svc.log"
    log.write_text("only one", encoding="utf-8")
    assert tail_lines(log, 50) == ["only one"]


def test_tail_of_missing_file_is_empty(tmp_path: Path):
    assert tail_lines(tmp_path / "absent.log", 10) == []


def test_tail_of_empty_file_is_empty(tmp_path: Path):
    log = tmp_path / "svc.log"
    log.write_text("", encoding="utf-8")
    assert tail_lines(log, 10) == []


def test_parses_the_default_file_format():
    line = parse_log_line(SAMPLE.splitlines()[0])
    assert line.level == "INFO"
    assert line.source == "auth"
    assert line.message == "JWT validated for a.mueller"
    assert line.timestamp == "2026-09-08 10:11:50"


def test_unparseable_line_is_returned_raw():
    line = parse_log_line("  Traceback (most recent call last):")
    assert line.level is None
    assert line.raw == "  Traceback (most recent call last):"
    assert line.message == "  Traceback (most recent call last):"


def test_endpoint_requires_a_session(client):
    assert client.get("/admin/api/logs").status_code == 401


def test_endpoint_returns_newest_first(client, login, tmp_path, monkeypatch):
    log = tmp_path / "svc.log"
    log.write_text(SAMPLE, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    client.app.state.config.logging.file.file_name = "svc.log"
    login()
    body = client.get("/admin/api/logs?limit=10").json()
    assert body[0]["level"] == "WARNING"
    assert body[1]["level"] == "INFO"


def test_limit_is_bounded(client, login):
    login()
    assert client.get("/admin/api/logs?limit=100000").status_code == 422
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/unit/webui/test_logs.py -v
```

Expected: FAIL — no module `testbench_ai_service.webui.logs`.

- [ ] **Step 3: Add the model**

Append to `testbench_ai_service/webui/models.py`:

```python
class LogLine(BaseModel):
    """One parsed log record. Unparseable lines keep only ``raw``."""

    raw: str
    timestamp: str | None = None
    level: str | None = None
    source: str | None = None
    message: str
```

- [ ] **Step 4: Write the implementation**

`testbench_ai_service/webui/logs.py`:

```python
"""Tail and parse the service log for the console's Status screen."""

import re
from collections import deque
from pathlib import Path

from testbench_ai_service.log import logger
from testbench_ai_service.webui.models import LogLine

MAX_LIMIT = 500

# Matches the default file log_format:
#   %(asctime)s - %(levelname)8s - %(name)s - %(message)s
_LINE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:,\d+)?"
    r"\s*-\s*(?P<level>[A-Z]+)"
    r"\s*-\s*(?P<source>\S+)"
    r"\s*-\s*(?P<message>.*)$"
)


def tail_lines(path: Path, limit: int) -> list[str]:
    """Return at most *limit* trailing lines of *path*, oldest first.

    A missing or unreadable log file yields an empty list: the Status screen
    should still render when logging to file is switched off.
    """
    try:
        with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
            return [line.rstrip("\n") for line in deque(handle, maxlen=limit) if line.strip()]
    except OSError as e:
        logger.debug("Cannot read log file %s: %s", path, e)
        return []


def parse_log_line(text: str) -> LogLine:
    match = _LINE.match(text)
    if match is None:
        return LogLine(raw=text, message=text)
    return LogLine(
        raw=text,
        timestamp=match.group("ts"),
        level=match.group("level"),
        source=match.group("source"),
        message=match.group("message"),
    )


def read_log(path: Path, limit: int) -> list[LogLine]:
    """Newest first, which is the order the Status screen displays."""
    return [parse_log_line(line) for line in reversed(tail_lines(path, limit))]
```

- [ ] **Step 5: Add the route**

Append to `testbench_ai_service/webui/routes.py`:

```python
@router.get("/logs", response_model=list[LogLine])
async def read_logs(
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
    _: Session = Depends(current_session),
    config: AppConfig = Depends(get_app_config),
) -> list[LogLine]:
    return read_log(Path(config.logging.file.file_name), limit)
```

Imports to add: `Query` from `fastapi`, `Path` from `pathlib`, `LogLine` from `.models`, `MAX_LIMIT` and `read_log` from `.logs`.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
python -m pytest tests/unit/webui/test_logs.py -v
```

Expected: PASS, 9 tests.

- [ ] **Step 7: Commit**

```bash
git add testbench_ai_service/webui/logs.py testbench_ai_service/webui/models.py \
        testbench_ai_service/webui/routes.py tests/unit/webui/test_logs.py
git commit -m "Add log tail endpoint for the console"
```

---

### Task 10: Read-only config endpoint

**Files:**
- Create: `testbench_ai_service/webui/config_io.py`
- Modify: `testbench_ai_service/webui/models.py`, `testbench_ai_service/webui/routes.py`
- Create: `tests/unit/webui/test_config_io.py`

**Interfaces:**
- Consumes: `current_session` (Task 7), `app.state.config_path` (Task 4)
- Produces: `GET /admin/api/config` returning `ConfigResponse` with `.running: dict`, `.disk: dict`, `.config_path: str`, `.in_sync: bool`. `read_config_file(path) -> dict` is the function phase 2's write path builds on.

- [ ] **Step 1: Write the failing tests**

`tests/unit/webui/test_config_io.py`:

```python
from pathlib import Path

import pytest

from testbench_ai_service.webui.config_io import CONFIG_PREFIX, read_config_file

SAMPLE = """
[testbench-ai-service]
# A comment an operator wrote and expects to keep
tb_server_url = "https://tb.example.com:9443/api/"
port = 9999
language = "en"

[testbench-ai-service.llm_config]
provider = "anthropic"
"""


def test_reads_the_prefixed_section(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(SAMPLE, encoding="utf-8")
    data = read_config_file(path)
    assert data["port"] == 9999
    assert data["llm_config"]["provider"] == "anthropic"


def test_missing_file_yields_empty_dict(tmp_path: Path):
    assert read_config_file(tmp_path / "absent.toml") == {}


def test_malformed_toml_raises_a_400(tmp_path: Path):
    from fastapi import HTTPException

    path = tmp_path / "config.toml"
    path.write_text("this is [not valid toml", encoding="utf-8")
    with pytest.raises(HTTPException) as exc:
        read_config_file(path)
    assert exc.value.status_code == 400


def test_endpoint_requires_a_session(client):
    assert client.get("/admin/api/config").status_code == 401


def test_endpoint_returns_running_config(client, login):
    login()
    body = client.get("/admin/api/config").json()
    assert body["running"]["port"] == 8010
    assert body["running"]["llm_config"]["provider"] == "openai"
    assert "test_case_set_reviewer" in body["running"]["agents"]


def test_endpoint_never_leaks_the_loaded_from_path_field(client, login):
    """`loaded_from` is excluded from the model dump; the path is reported once,
    explicitly, as config_path."""
    login()
    body = client.get("/admin/api/config").json()
    assert "loaded_from" not in body["running"]
    assert body["config_path"]


def test_non_admin_may_read_config(client, login):
    """Phase 1 is read-only for everyone; only writes need admin."""
    login(roles=["ProjectUser"])
    assert client.get("/admin/api/config").status_code == 200
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/unit/webui/test_config_io.py -v
```

Expected: FAIL — no module `testbench_ai_service.webui.config_io`.

- [ ] **Step 3: Add the model**

Append to `testbench_ai_service/webui/models.py`:

```python
class ConfigResponse(BaseModel):
    """The service's configuration, as loaded and as stored.

    ``running`` is what the process is using; ``disk`` is what the file says.
    They differ when the file was edited since startup — phase 2 turns that into
    the "restart needed" banner.
    """

    running: dict
    disk: dict
    config_path: str
    in_sync: bool
```

- [ ] **Step 4: Write the implementation**

`testbench_ai_service/webui/config_io.py`:

```python
"""Reading the service's TOML configuration for the console.

Phase 1 only reads.  The write path in phase 2 builds on ``read_config_file`` and
adds a comment-preserving ``tomlkit`` round trip.
"""

from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from testbench_ai_service.config import AppConfig
from testbench_ai_service.log import logger
from testbench_ai_service.utils.config import CONFIG_PREFIX
from testbench_ai_service.webui.models import ConfigResponse

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]


def read_config_file(path: Path) -> dict[str, Any]:
    """Return the ``[testbench-ai-service]`` table from *path*.

    An absent file yields ``{}`` — the service can run on defaults alone.

    Raises:
        HTTPException 400: the file exists but is not valid TOML.
    """
    file_path = Path(path)
    if not file_path.is_file():
        logger.debug("No config file at %s", file_path)
        return {}
    try:
        with file_path.open("rb") as handle:
            document = tomllib.load(handle)
    except tomllib.TOMLDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{file_path} is not valid TOML: {e}",
        ) from e
    return dict(document.get(CONFIG_PREFIX, {}))


def running_config(config: AppConfig) -> dict[str, Any]:
    """The in-memory config as JSON-safe primitives."""
    return config.model_dump(mode="json")


def build_config_response(config: AppConfig, path: Path) -> ConfigResponse:
    disk = read_config_file(path)
    running = running_config(config)
    # Compare only the keys the file actually sets: defaults are not drift.
    drift = any(disk.get(key) != running.get(key) for key in disk)
    return ConfigResponse(
        running=running,
        disk=disk,
        config_path=str(Path(path).resolve()),
        in_sync=not drift,
    )
```

Check that `CONFIG_PREFIX` is importable from `utils/config.py` — `load_config_from_file` takes it as a default argument, so it exists there. If it is private, promote it rather than duplicating the string.

- [ ] **Step 5: Add the route**

Append to `testbench_ai_service/webui/routes.py`:

```python
@router.get("/config", response_model=ConfigResponse)
async def read_config(
    request: Request,
    _: Session = Depends(current_session),
    config: AppConfig = Depends(get_app_config),
) -> ConfigResponse:
    return build_config_response(config, request.app.state.config_path)
```

Imports to add: `ConfigResponse` from `.models`, `build_config_response` from `.config_io`.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
python -m pytest tests/unit/webui/test_config_io.py -v
```

Expected: PASS, 7 tests.

- [ ] **Step 7: Run the full backend suite**

```bash
python -m pytest tests -q
```

Expected: everything passes. This is the last backend task, so the whole `/admin/api` surface for phase 1 is now green.

- [ ] **Step 8: Commit**

```bash
git add testbench_ai_service/webui/config_io.py testbench_ai_service/webui/models.py \
        testbench_ai_service/webui/routes.py tests/unit/webui/test_config_io.py
git commit -m "Add read-only config endpoint for the console"
```

---

### Task 11: Design system, theme, and i18n

**Files:**
- Create: `frontend/src/styles/industry.css`, `frontend/src/styles/brand.css`, `frontend/src/styles/fonts.css`
- Create: `frontend/src/styles/fonts/` (four woff2 files)
- Create: `frontend/src/theme.ts`, `frontend/src/theme.test.ts`
- Create: `frontend/src/i18n/index.ts`, `frontend/src/i18n/de.ts`, `frontend/src/i18n/en.ts`, `frontend/src/i18n/i18n.test.ts`

**Interfaces:**
- Consumes: nothing
- Produces: `applyTheme(theme: Theme, brand?: Brand): void`, `type Theme = 'light' | 'dark'`; `useTranslations(lang: Lang): Translations`, `type Lang = 'de' | 'en'`. Tasks 12–15 import these.

- [ ] **Step 1: Copy the design system CSS**

Copy the artboard's design-system stylesheet verbatim into `frontend/src/styles/industry.css`. It is the file

```
_ds/industry-2f5fb3df-596f-4801-bb74-facd877366da/styles.css
```

in Claude Design project `474074a4-dc03-4e6f-b0c9-3b36a780a114` ("Testbench AI Service Configuration"), readable with the design MCP's `get_file`. It is ~250 lines of plain CSS — custom-property tokens (`--color-*`, `--space-*`, `--radius-*`, `--shadow-*`, `--font-*`) followed by component classes (`.btn`, `.input`, `.card`, `.blueprint`, `.corner`, `.tag`, `.seg`, `.radio`, `.table`, `.dialog`, `.text-muted`). No build step, no JavaScript.

**Then delete its first `@import` line** — the Google Fonts import. It is replaced by `fonts.css`. Leaving it in violates the no-third-party-origin constraint and makes the console render in a fallback font on an air-gapped host.

- [ ] **Step 2: Extract the brand tokens**

Copy the `<style>` block from the artboard's `<helmet>` into `frontend/src/styles/brand.css` — the `[data-brand=testbench]`, `[data-brand=testbench][data-theme=dark]`, `:root:not([data-brand=testbench])` and `[data-corners=soft]` rules, which carry the TestBench green (`#128a5e`) and orange (`#f28c00`).

- [ ] **Step 3: Self-host the fonts**

Download Barlow 400/500/700 and Barlow Condensed 600 as woff2 into `frontend/src/styles/fonts/`, then write `frontend/src/styles/fonts.css`:

```css
/* Self-hosted so the console works with no outbound network access. */
@font-face {
  font-family: 'Barlow';
  font-style: normal;
  font-weight: 400;
  font-display: swap;
  src: url('./fonts/barlow-400.woff2') format('woff2');
}
@font-face {
  font-family: 'Barlow';
  font-style: normal;
  font-weight: 500;
  font-display: swap;
  src: url('./fonts/barlow-500.woff2') format('woff2');
}
@font-face {
  font-family: 'Barlow';
  font-style: normal;
  font-weight: 700;
  font-display: swap;
  src: url('./fonts/barlow-700.woff2') format('woff2');
}
@font-face {
  font-family: 'Barlow Condensed';
  font-style: normal;
  font-weight: 600;
  font-display: swap;
  src: url('./fonts/barlow-condensed-600.woff2') format('woff2');
}
```

- [ ] **Step 4: Write the failing theme test**

`frontend/src/theme.test.ts`:

```ts
import { applyTheme, preferredTheme } from './theme'

test('applyTheme stamps the root element', () => {
  applyTheme('dark')
  expect(document.documentElement.dataset.theme).toBe('dark')
  expect(document.documentElement.dataset.brand).toBe('testbench')
  expect(document.documentElement.dataset.corners).toBe('soft')
})

test('applyTheme can switch back to light', () => {
  applyTheme('dark')
  applyTheme('light')
  expect(document.documentElement.dataset.theme).toBe('light')
})

test('preferredTheme falls back to light when the media query is unavailable', () => {
  expect(preferredTheme()).toBe('light')
})
```

- [ ] **Step 5: Write the failing i18n test**

`frontend/src/i18n/i18n.test.ts`:

```ts
import { de } from './de'
import { en } from './en'

test('both languages define exactly the same keys', () => {
  expect(Object.keys(de).sort()).toEqual(Object.keys(en).sort())
})

test('no translation is left empty', () => {
  for (const [key, value] of Object.entries({ ...de, ...en })) {
    expect(value, `empty translation for ${key}`).not.toBe('')
  }
})

test('German is the default service language, matching the backend', () => {
  expect(de.status).toBe('Status')
  expect(de.service).toBe('Dienst')
})
```

- [ ] **Step 6: Run both tests to verify they fail**

```bash
cd frontend && npm test
```

Expected: FAIL — cannot resolve `./theme` or `./i18n/de`.

- [ ] **Step 7: Write the theme module**

`frontend/src/theme.ts`:

```ts
export type Theme = 'light' | 'dark'
export type Brand = 'testbench' | 'industry'

const STORAGE_KEY = 'tbai-console-theme'

/** The viewer's OS preference, defaulting to light where unknown. */
export function preferredTheme(): Theme {
  if (typeof window === 'undefined' || !window.matchMedia) return 'light'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function storedTheme(): Theme | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value === 'light' || value === 'dark' ? value : null
  } catch {
    return null
  }
}

/** Stamp the root element so the design system's token blocks apply. */
export function applyTheme(theme: Theme, brand: Brand = 'testbench'): void {
  const root = document.documentElement
  root.dataset.theme = theme
  root.dataset.brand = brand
  root.dataset.corners = 'soft'
  try {
    localStorage.setItem(STORAGE_KEY, theme)
  } catch {
    // A private window or blocked storage must not break theming.
  }
}
```

- [ ] **Step 8: Write the i18n modules**

The keys below are exactly the ones Phase 1's screens use, taken verbatim from the artboard's `I18N` dictionary. The dictionary's remaining keys belong to screens that do not exist yet, so they are ported in the phase that introduces them — adding them now would create translations no test covers and no screen renders.

`frontend/src/i18n/de.ts`:

```ts
export const de = {
  status: 'Status',
  service: 'Dienst',
  llm: 'LLM-Anbieter',
  logging: 'Protokollierung',
  agents: 'Agenten',
  projects: 'Projekte',
  prompts: 'Prompts',
  raw: 'config.toml (roh)',
  login: 'Anmelden',
  username: 'Benutzername',
  password: 'Passwort',
  server: 'TestBench-Server',
  signIn: 'Mit TestBench anmelden',
  logout: 'Abmelden',
  running: 'Läuft',
  connected: 'Verbunden',
  apiKeys: 'API-Schlüssel (.env)',
  recentLog: 'Letzte Protokolleinträge',
  general: 'Allgemein',
  tbConn: 'TestBench-Verbindung',
  tls: 'HTTPS / TLS',
  proxy: 'Reverse Proxy',
  console: 'Konsole',
  file: 'Datei',
  language: 'Sprache',
  admin: 'Administrator',
  testManager: 'Testmanager',
  readOnly: 'Nur lesend — Änderungen erfordern die Administrator-Rolle.',
  agentsOn: 'aktiv',
  overrides: 'Überschreibungen',
  keySet: 'Schlüssel gesetzt',
  keyMissing: 'Schlüssel fehlt',
} as const

export type Translations = typeof de
```

`frontend/src/i18n/en.ts` mirrors it with the English strings from the artboard.

`frontend/src/i18n/index.ts`:

```ts
import { de } from './de'
import { en } from './en'
import type { Translations } from './de'

export type Lang = 'de' | 'en'
export type { Translations }

const DICTIONARIES: Record<Lang, Translations> = { de, en }

export function useTranslations(lang: Lang): Translations {
  return DICTIONARIES[lang]
}
```

- [ ] **Step 9: Run the tests to verify they pass**

```bash
cd frontend && npm test
```

Expected: PASS. The key-parity test is what keeps `de` and `en` from drifting.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/styles frontend/src/theme.ts frontend/src/theme.test.ts frontend/src/i18n
git commit -m "Add console design system, theming and translations"
```

---

### Task 12: API client and login screen

**Files:**
- Create: `frontend/src/api/client.ts`, `frontend/src/api/client.test.ts`
- Create: `frontend/src/api/types.ts`
- Create: `frontend/src/api/queries.ts`
- Create: `frontend/src/state/session.tsx`
- Create: `frontend/src/screens/Login.tsx`, `frontend/src/screens/Login.test.tsx`

**Interfaces:**
- Consumes: `useTranslations` (Task 11); the `/admin/api/session` contract (Task 7)
- Produces:
  - `apiFetch<T>(path: string, init?: RequestInit): Promise<T>` — prefixes `/admin/api`, attaches `X-CSRF-Token`, throws `ApiError` with `.status`
  - `ApiError`
  - `SessionProvider`, `useSession(): { session, signIn, signOut, loading }`
  - `useMeta()` — the query hook for the unauthenticated `/meta` route
  - `Login` component — presentational; it takes `serverUrl` as a prop and does no fetching of its own
- Tasks 13–15 consume `useSession` and `apiFetch`. Task 14 extends `api/queries.ts` with `useStatus`, `useLogs` and `useConfig`.

- [ ] **Step 1: Write the failing client tests**

`frontend/src/api/client.test.ts`:

```ts
import { ApiError, apiFetch } from './client'

const okResponse = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })

beforeEach(() => {
  document.cookie = 'tbai_admin_csrf=csrf-token-value; path=/'
  vi.restoreAllMocks()
})

test('prefixes the admin api path', async () => {
  const fetchMock = vi.fn().mockResolvedValue(okResponse({ ok: true }))
  vi.stubGlobal('fetch', fetchMock)
  await apiFetch('/status')
  expect(fetchMock.mock.calls[0][0]).toBe('/admin/api/status')
})

test('sends cookies with every request', async () => {
  const fetchMock = vi.fn().mockResolvedValue(okResponse({}))
  vi.stubGlobal('fetch', fetchMock)
  await apiFetch('/status')
  expect(fetchMock.mock.calls[0][1].credentials).toBe('same-origin')
})

test('attaches the CSRF header on mutating requests', async () => {
  const fetchMock = vi.fn().mockResolvedValue(okResponse({}))
  vi.stubGlobal('fetch', fetchMock)
  await apiFetch('/session', { method: 'DELETE' })
  const headers = new Headers(fetchMock.mock.calls[0][1].headers)
  expect(headers.get('X-CSRF-Token')).toBe('csrf-token-value')
})

test('omits the CSRF header on GET', async () => {
  const fetchMock = vi.fn().mockResolvedValue(okResponse({}))
  vi.stubGlobal('fetch', fetchMock)
  await apiFetch('/status')
  const headers = new Headers(fetchMock.mock.calls[0][1].headers)
  expect(headers.get('X-CSRF-Token')).toBeNull()
})

test('throws ApiError carrying the status and detail', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Invalid credentials' }), { status: 401 }),
    ),
  )
  await expect(apiFetch('/session', { method: 'POST' })).rejects.toMatchObject({
    status: 401,
    message: 'Invalid credentials',
  })
})

test('handles a 204 with no body', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
  await expect(apiFetch('/session', { method: 'DELETE' })).resolves.toBeNull()
})

test('surfaces a network failure as an ApiError', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('failed to fetch')))
  await expect(apiFetch('/status')).rejects.toBeInstanceOf(ApiError)
})
```

- [ ] **Step 2: Write the failing login screen test**

`frontend/src/screens/Login.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Login } from './Login'

const props = {
  serverUrl: 'https://tb.example.com:9443/api/',
  lang: 'de' as const,
  onSignIn: vi.fn(),
  error: null,
  busy: false,
}

beforeEach(() => vi.clearAllMocks())

test('shows the configured server read-only', () => {
  render(<Login {...props} />)
  const field = screen.getByLabelText('TestBench-Server')
  expect(field).toHaveValue('https://tb.example.com:9443/api/')
  expect(field).toHaveAttribute('readonly')
})

test('submits the credentials', async () => {
  render(<Login {...props} />)
  await userEvent.type(screen.getByLabelText('Benutzername'), 'a.mueller')
  await userEvent.type(screen.getByLabelText('Passwort'), 'secret')
  await userEvent.click(screen.getByRole('button', { name: 'Mit TestBench anmelden' }))
  await waitFor(() =>
    expect(props.onSignIn).toHaveBeenCalledWith('a.mueller', 'secret'),
  )
})

test('does not submit an empty form', async () => {
  render(<Login {...props} />)
  await userEvent.click(screen.getByRole('button', { name: 'Mit TestBench anmelden' }))
  expect(props.onSignIn).not.toHaveBeenCalled()
})

test('shows a sign-in error', () => {
  render(<Login {...props} error="Invalid credentials" />)
  expect(screen.getByRole('alert')).toHaveTextContent('Invalid credentials')
})

test('has no role selector', () => {
  /** The prototype's role picker was labelled "(demo)"; roles come from TestBench. */
  render(<Login {...props} />)
  expect(screen.queryByLabelText(/rolle/i)).toBeNull()
})

test('disables the button while signing in', () => {
  render(<Login {...props} busy />)
  expect(screen.getByRole('button', { name: 'Mit TestBench anmelden' })).toBeDisabled()
})
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cd frontend && npm test
```

Expected: FAIL — cannot resolve `./client` or `./Login`.

- [ ] **Step 4: Write the API types**

`frontend/src/api/types.ts`:

```ts
export interface SessionInfo {
  username: string
  roles: string[]
  is_admin: boolean
  tb_server_url: string
}

export interface ServiceStatus {
  version: string
  host: string
  port: number
  debug: boolean
  uptime_seconds: number
  language: string
}

export interface TestBenchStatus {
  url: string
  reachable: boolean
  detail: string | null
}

export interface ApiKeyStatus {
  name: string
  present: boolean
}

export interface AgentSummary {
  total: number
  enabled: number
  project_overrides: number
  projects: number
}

export interface StatusResponse {
  service: ServiceStatus
  testbench: TestBenchStatus
  api_keys: ApiKeyStatus[]
  agents: AgentSummary
  log_file: string
}

export interface LogLine {
  raw: string
  timestamp: string | null
  level: string | null
  source: string | null
  message: string
}

export interface ConfigResponse {
  running: Record<string, unknown>
  disk: Record<string, unknown>
  config_path: string
  in_sync: boolean
}

export interface MetaResponse {
  tb_server_url: string
}
```

- [ ] **Step 4b: Write the meta query hook**

`frontend/src/api/queries.ts` — Task 14 adds the rest:

```ts
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from './client'
import type { MetaResponse } from './types'

/** Unauthenticated: lets the login screen name the TestBench server. */
export function useMeta() {
  return useQuery({
    queryKey: ['meta'],
    queryFn: () => apiFetch<MetaResponse>('/meta'),
    staleTime: Infinity,
  })
}
```

- [ ] **Step 5: Write the client**

`frontend/src/api/client.ts`:

```ts
const BASE = '/admin/api'
const CSRF_COOKIE = 'tbai_admin_csrf'
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

/**
 * Call the console API.
 *
 * The session cookie is httpOnly, so it travels automatically; the CSRF token is
 * readable by design and echoed back on anything that changes state.
 */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase()
  const headers = new Headers(init.headers)

  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (!SAFE_METHODS.has(method)) {
    const csrf = readCookie(CSRF_COOKIE)
    if (csrf) headers.set('X-CSRF-Token', csrf)
  }

  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      method,
      headers,
      credentials: 'same-origin',
    })
  } catch (cause) {
    throw new ApiError(
      cause instanceof Error ? cause.message : 'Network request failed',
      0,
    )
  }

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`
    try {
      const body = await response.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      // A non-JSON error body leaves the default message in place.
    }
    throw new ApiError(detail, response.status)
  }

  if (response.status === 204) return null as T
  return (await response.json()) as T
}
```

- [ ] **Step 6: Write the session state**

`frontend/src/state/session.tsx`:

```tsx
import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { ApiError, apiFetch } from '../api/client'
import type { SessionInfo } from '../api/types'

interface SessionState {
  session: SessionInfo | null
  loading: boolean
  error: string | null
  busy: boolean
  signIn: (username: string, password: string) => Promise<void>
  signOut: () => Promise<void>
}

const SessionContext = createContext<SessionState | null>(null)

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<SessionInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // A page reload still has the cookie; ask who we are rather than forcing a login.
  useEffect(() => {
    apiFetch<SessionInfo>('/session')
      .then(setSession)
      .catch(() => setSession(null))
      .finally(() => setLoading(false))
  }, [])

  const signIn = useCallback(async (username: string, password: string) => {
    setBusy(true)
    setError(null)
    try {
      setSession(
        await apiFetch<SessionInfo>('/session', {
          method: 'POST',
          body: JSON.stringify({ username, password }),
        }),
      )
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Sign-in failed')
      throw cause
    } finally {
      setBusy(false)
    }
  }, [])

  const signOut = useCallback(async () => {
    try {
      await apiFetch('/session', { method: 'DELETE' })
    } finally {
      setSession(null)
    }
  }, [])

  return (
    <SessionContext.Provider
      value={{ session, loading, busy, error, signIn, signOut }}
    >
      {children}
    </SessionContext.Provider>
  )
}

export function useSession(): SessionState {
  const value = useContext(SessionContext)
  if (!value) throw new Error('useSession must be used inside a SessionProvider')
  return value
}
```

- [ ] **Step 7: Write the login screen**

`frontend/src/screens/Login.tsx`:

```tsx
import { useState } from 'react'
import { useTranslations, type Lang } from '../i18n'

interface LoginProps {
  serverUrl: string
  lang: Lang
  busy: boolean
  error: string | null
  onSignIn: (username: string, password: string) => void
}

export function Login({ serverUrl, lang, busy, error, onSignIn }: LoginProps) {
  const t = useTranslations(lang)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        padding: 'var(--space-6)',
      }}
    >
      <form
        className="card blueprint"
        style={{ width: 'min(380px, 100%)', padding: 'var(--space-6)', gap: 'var(--space-4)' }}
        onSubmit={(event) => {
          event.preventDefault()
          if (!username || !password) return
          onSignIn(username, password)
        }}
      >
        <i className="corner tl" />
        <i className="corner tr" />
        <i className="corner bl" />
        <i className="corner br" />
        <h2 style={{ margin: 0 }}>{t.login}</h2>

        <div className="field">
          <label htmlFor="login-server">{t.server}</label>
          {/* One service, one TestBench: prefilled from config and not editable. */}
          <input
            id="login-server"
            className="input"
            value={serverUrl}
            readOnly
            style={{ opacity: 0.7 }}
          />
        </div>

        <div className="field">
          <label htmlFor="login-user">{t.username}</label>
          <input
            id="login-user"
            className="input"
            autoComplete="username"
            autoFocus
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="login-pass">{t.password}</label>
          <input
            id="login-pass"
            className="input"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>

        {error && (
          <div role="alert" style={{ color: '#c0392b', fontSize: 13 }}>
            {error}
          </div>
        )}

        <button className="btn btn-primary btn-block" type="submit" disabled={busy}>
          {t.signIn}
        </button>
      </form>
    </div>
  )
}
```

- [ ] **Step 8: Run the tests to verify they pass**

```bash
cd frontend && npm test
```

Expected: PASS, 13 new tests.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/api frontend/src/state frontend/src/screens/Login.tsx \
        frontend/src/screens/Login.test.tsx
git commit -m "Add console API client and sign-in screen"
```

---

### Task 13: App shell, routing, and role gating

**Files:**
- Create: `frontend/src/components/TopBar.tsx`, `frontend/src/components/NavRail.tsx`, `frontend/src/components/NavRail.test.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/App.test.tsx`, `frontend/src/main.tsx`

**Interfaces:**
- Consumes: `useSession` (Task 12), `useTranslations`/`applyTheme` (Task 11)
- Produces: `NAV_ITEMS` (key, labelKey, icon path, adminOnly); `NavRail`; `TopBar`; an `App` that renders `Login` when unauthenticated and the shell with routes otherwise. Tasks 14–15 add screens behind those routes.

- [ ] **Step 1: Write the failing nav tests**

`frontend/src/components/NavRail.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { NavRail } from './NavRail'

const renderNav = (isAdmin: boolean) =>
  render(
    <MemoryRouter initialEntries={['/admin/status']}>
      <NavRail lang="de" isAdmin={isAdmin} />
    </MemoryRouter>,
  )

test('renders every phase 1 destination', () => {
  renderNav(true)
  for (const label of ['Status', 'Dienst', 'LLM-Anbieter', 'Protokollierung']) {
    expect(screen.getByRole('link', { name: new RegExp(label) })).toBeInTheDocument()
  }
})

test('marks restricted destinations for a non-admin', () => {
  renderNav(false)
  const link = screen.getByRole('link', { name: /Dienst/ })
  expect(link).toHaveAttribute('aria-disabled', 'true')
})

test('leaves Status open to a non-admin', () => {
  renderNav(false)
  expect(screen.getByRole('link', { name: /Status/ })).not.toHaveAttribute(
    'aria-disabled',
    'true',
  )
})

test('an admin has nothing disabled', () => {
  renderNav(true)
  for (const link of screen.getAllByRole('link')) {
    expect(link).not.toHaveAttribute('aria-disabled', 'true')
  }
})
```

- [ ] **Step 2: Replace `App.test.tsx` with shell tests**

`frontend/src/App.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import { App } from './App'
import * as sessionState from './state/session'

const asSession = (session: unknown, loading = false) =>
  vi.spyOn(sessionState, 'useSession').mockReturnValue({
    session,
    loading,
    busy: false,
    error: null,
    signIn: vi.fn(),
    signOut: vi.fn(),
  } as never)

afterEach(() => vi.restoreAllMocks())

test('shows the sign-in screen when there is no session', async () => {
  asSession(null)
  render(<App />)
  await waitFor(() =>
    expect(screen.getByRole('button', { name: /anmelden/i })).toBeInTheDocument(),
  )
})

test('shows the shell when signed in', async () => {
  asSession({
    username: 'a.mueller',
    roles: ['Administrator'],
    is_admin: true,
    tb_server_url: 'https://tb.example.com:9443/api/',
  })
  render(<App />)
  await waitFor(() => expect(screen.getByRole('navigation')).toBeInTheDocument())
  expect(screen.getByText('a.mueller')).toBeInTheDocument()
})

test('shows a read-only notice to a non-admin', async () => {
  asSession({
    username: 'p.user',
    roles: ['ProjectUser'],
    is_admin: false,
    tb_server_url: 'https://tb.example.com:9443/api/',
  })
  render(<App />)
  await waitFor(() =>
    expect(screen.getByText(/nur lesend/i)).toBeInTheDocument(),
  )
})

test('renders nothing decisive while the session is still loading', () => {
  asSession(null, true)
  render(<App />)
  expect(screen.queryByRole('button', { name: /anmelden/i })).toBeNull()
})
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cd frontend && npm test
```

Expected: FAIL — cannot resolve `./components/NavRail`; `App` renders only an `<h1>`.

- [ ] **Step 4: Write the nav rail**

`frontend/src/components/NavRail.tsx`:

```tsx
import { NavLink } from 'react-router-dom'
import { useTranslations, type Lang, type Translations } from '../i18n'

interface NavItem {
  key: string
  path: string
  labelKey: keyof Translations
  icon: string
  adminOnly: boolean
}

/** Icon paths are lifted from the source design's ICONS map. */
export const NAV_ITEMS: NavItem[] = [
  {
    key: 'status',
    path: '/admin/status',
    labelKey: 'status',
    icon: 'M22 12h-4l-3 9L9 3l-3 9H2',
    adminOnly: false,
  },
  {
    key: 'service',
    path: '/admin/service',
    labelKey: 'service',
    icon: 'M6 2h12a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zM6 12h12a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2zM6 6h.01M6 16h.01',
    adminOnly: true,
  },
  {
    key: 'llm',
    path: '/admin/llm',
    labelKey: 'llm',
    icon: 'M9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2M6 4h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zM9 9h6v6H9z',
    adminOnly: true,
  },
  {
    key: 'logging',
    path: '/admin/logging',
    labelKey: 'logging',
    icon: 'M8 21h12a2 2 0 0 0 2-2v-2H10v2a2 2 0 1 1-4 0V5a2 2 0 1 0-4 0v3h4M19 17V5a2 2 0 0 0-2-2H4M15 8h-5M15 12h-5',
    adminOnly: true,
  },
]

export function NavRail({ lang, isAdmin }: { lang: Lang; isAdmin: boolean }) {
  const t = useTranslations(lang)
  return (
    <nav
      aria-label="Console sections"
      style={{
        width: 200,
        flex: 'none',
        borderRight: '1px solid var(--color-divider)',
        padding: '12px 0',
        display: 'flex',
        flexDirection: 'column',
        gap: 2,
      }}
    >
      {NAV_ITEMS.map((item) => {
        const restricted = item.adminOnly && !isAdmin
        return (
          <NavLink
            key={item.key}
            to={item.path}
            aria-disabled={restricted || undefined}
            style={({ isActive }) => ({
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '8px 14px',
              margin: '0 8px',
              color: 'inherit',
              textDecoration: 'none',
              fontSize: 14,
              borderLeft: `2px solid ${isActive ? 'var(--color-accent)' : 'transparent'}`,
              background: isActive ? 'var(--color-accent-100)' : 'transparent',
              opacity: restricted ? 0.5 : isActive ? 1 : 0.8,
            })}
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              aria-hidden="true"
              style={{ flex: 'none', opacity: 0.8 }}
            >
              <path d={item.icon} />
            </svg>
            <span style={{ flex: 1 }}>{t[item.labelKey]}</span>
            {restricted && (
              <svg
                width="13"
                height="13"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                aria-hidden="true"
              >
                <rect x="4" y="11" width="16" height="10" />
                <path d="M8 11V7a4 4 0 0 1 8 0v4" />
              </svg>
            )}
          </NavLink>
        )
      })}
    </nav>
  )
}
```

- [ ] **Step 5: Write the top bar**

`frontend/src/components/TopBar.tsx`:

```tsx
import { useTranslations, type Lang } from '../i18n'
import type { Theme } from '../theme'
import type { SessionInfo } from '../api/types'

interface TopBarProps {
  session: SessionInfo
  lang: Lang
  theme: Theme
  onToggleTheme: () => void
  onSetLang: (lang: Lang) => void
  onSignOut: () => void
}

export function TopBar({
  session,
  lang,
  theme,
  onToggleTheme,
  onSetLang,
  onSignOut,
}: TopBarProps) {
  const t = useTranslations(lang)
  return (
    <header
      style={{
        height: 52,
        flex: 'none',
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-4)',
        padding: '0 var(--space-4)',
        borderBottom: '1px solid var(--color-divider)',
      }}
    >
      <span className="nav-brand">TestBench AI Service</span>
      <div style={{ flex: 1 }} />
      <div className="seg" role="group" aria-label={t.language}>
        {(['de', 'en'] as const).map((code) => (
          <label key={code} className="seg-opt">
            <input
              type="radio"
              name="console-lang"
              checked={lang === code}
              onChange={() => onSetLang(code)}
            />
            {code}
          </label>
        ))}
      </div>
      <button
        className="btn btn-secondary btn-icon"
        onClick={onToggleTheme}
        aria-label={theme === 'light' ? 'Dark theme' : 'Light theme'}
      >
        {theme === 'light' ? '◐' : '◑'}
      </button>
      <span style={{ fontSize: 13 }}>{session.username}</span>
      <span className="tag tag-neutral">
        {session.is_admin ? t.admin : t.testManager}
      </span>
      <button className="btn btn-ghost" onClick={onSignOut}>
        {t.logout}
      </button>
    </header>
  )
}
```

- [ ] **Step 6: Write the app shell**

`frontend/src/App.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { NavRail } from './components/NavRail'
import { TopBar } from './components/TopBar'
import { Login } from './screens/Login'
import { useMeta } from './api/queries'
import { useSession } from './state/session'
import { useTranslations, type Lang } from './i18n'
import { applyTheme, preferredTheme, storedTheme, type Theme } from './theme'

export function App() {
  const { session, loading, busy, error, signIn, signOut } = useSession()
  const meta = useMeta()
  const [lang, setLang] = useState<Lang>('de')
  const [theme, setTheme] = useState<Theme>(() => storedTheme() ?? preferredTheme())
  const t = useTranslations(lang)

  useEffect(() => applyTheme(theme), [theme])

  if (loading) return null

  if (!session) {
    return (
      <Login
        // From the unauthenticated /meta route: the operator should see which
        // TestBench they are signing into before they type a password.
        serverUrl={meta.data?.tb_server_url ?? ''}
        lang={lang}
        busy={busy}
        error={error}
        onSignIn={(username, password) => {
          void signIn(username, password).catch(() => undefined)
        }}
      />
    )
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <TopBar
        session={session}
        lang={lang}
        theme={theme}
        onToggleTheme={() => setTheme(theme === 'light' ? 'dark' : 'light')}
        onSetLang={setLang}
        onSignOut={() => void signOut()}
      />
      {!session.is_admin && (
        <div
          style={{
            padding: '8px var(--space-4)',
            fontSize: 13,
            background: 'var(--color-surface)',
            borderBottom: '1px solid var(--color-divider)',
          }}
        >
          {t.readOnly}
        </div>
      )}
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <NavRail lang={lang} isAdmin={session.is_admin} />
        <main style={{ flex: 1, minWidth: 0 }}>
          <Routes>
            <Route path="/admin" element={<Navigate to="/admin/status" replace />} />
            <Route path="/" element={<Navigate to="/admin/status" replace />} />
            <Route path="/admin/status" element={<div />} />
            <Route path="/admin/service" element={<div />} />
            <Route path="/admin/llm" element={<div />} />
            <Route path="/admin/logging" element={<div />} />
            <Route path="*" element={<Navigate to="/admin/status" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}
```

The empty `<div />` route elements are filled in by Tasks 14 and 15.

- [ ] **Step 7: Wire the providers in `main.tsx`**

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App } from './App'
import { SessionProvider } from './state/session'
import './styles/fonts.css'
import './styles/industry.css'
import './styles/brand.css'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <SessionProvider>
          <App />
        </SessionProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
```

Note the stylesheet import order: fonts, then the design system, then the brand overrides.

- [ ] **Step 8: Wrap `App` tests in a router**

`App` uses both `Routes` and `useMeta`, so its test needs a router *and* a query client. Add to `App.test.tsx` above the tests:

```tsx
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify({ tb_server_url: 'https://tb:9443/api/' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    ),
  )
})

const renderApp = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/admin/status']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}
```

and replace each `render(<App />)` with `renderApp()`.

Add one test for the wiring the `/meta` fix introduced:

```tsx
test('the login screen shows the server from /meta', async () => {
  asSession(null)
  renderApp()
  await waitFor(() =>
    expect(screen.getByLabelText('TestBench-Server')).toHaveValue(
      'https://tb:9443/api/',
    ),
  )
})
```

- [ ] **Step 9: Run the tests to verify they pass**

```bash
cd frontend && npm test
```

Expected: PASS, all suites.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/main.tsx \
        frontend/src/components
git commit -m "Add console shell with routing and role gating"
```

---

### Task 14: Status screen

**Files:**
- Create: `frontend/src/screens/Status.tsx`, `frontend/src/screens/Status.test.tsx`
- Modify: `frontend/src/api/queries.ts` (add `useStatus`, `useLogs`, `useConfig`)
- Modify: `frontend/src/App.tsx` (mount the route)

**Interfaces:**
- Consumes: `apiFetch` and the types from Task 12; `GET /status` and `GET /logs` from Tasks 8–9
- Produces: `useStatus()`, `useLogs(limit)`, `useConfig()`, `useMeta()` query hooks; `Status` component. Task 15 uses `useConfig`; Task 13 uses `useMeta` for the login screen's server field.

- [ ] **Step 1: Write the failing tests**

`frontend/src/screens/Status.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Status } from './Status'
import type { LogLine, StatusResponse } from '../api/types'

const STATUS: StatusResponse = {
  service: {
    version: '1.0.1',
    host: '127.0.0.1',
    port: 8010,
    debug: false,
    uptime_seconds: 8040,
    language: 'de',
  },
  testbench: { url: 'https://tb.example.com:9443/api/', reachable: true, detail: 'HTTP 401' },
  api_keys: [
    { name: 'OPENAI_API_KEY', present: true },
    { name: 'ANTHROPIC_API_KEY', present: false },
  ],
  agents: { total: 3, enabled: 2, project_overrides: 4, projects: 2 },
  log_file: 'testbench-ai-service.log',
}

const LOGS: LogLine[] = [
  {
    raw: 'x',
    timestamp: '2026-09-08 10:12:03',
    level: 'ERROR',
    source: 'testbench.client',
    message: 'GET /projects failed',
  },
  {
    raw: 'y',
    timestamp: '2026-09-08 10:11:51',
    level: 'INFO',
    source: 'auth',
    message: 'token validated',
  },
]

function renderStatus() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <Status lang="de" />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      Promise.resolve(
        new Response(JSON.stringify(url.includes('/logs') ? LOGS : STATUS), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    ),
  )
})

afterEach(() => vi.restoreAllMocks())

test('shows the service card', async () => {
  renderStatus()
  await waitFor(() => expect(screen.getByText(/127\.0\.0\.1:8010/)).toBeInTheDocument())
  expect(screen.getByText(/1\.0\.1/)).toBeInTheDocument()
})

test('formats uptime readably', async () => {
  renderStatus()
  await waitFor(() => expect(screen.getByText(/2h 14m/)).toBeInTheDocument())
})

test('shows the TestBench url and connected state', async () => {
  renderStatus()
  await waitFor(() =>
    expect(screen.getByText('https://tb.example.com:9443/api/')).toBeInTheDocument(),
  )
  expect(screen.getByText('Verbunden')).toBeInTheDocument()
})

test('lists api keys by presence, never a value', async () => {
  renderStatus()
  await waitFor(() => expect(screen.getByText('OPENAI_API_KEY')).toBeInTheDocument())
  expect(screen.getByText('ANTHROPIC_API_KEY')).toBeInTheDocument()
})

test('summarises agents and overrides', async () => {
  renderStatus()
  await waitFor(() => expect(screen.getByText(/2 aktiv/)).toBeInTheDocument())
  expect(screen.getByText(/4 Überschreibungen/)).toBeInTheDocument()
})

test('renders recent log lines newest first', async () => {
  renderStatus()
  await waitFor(() => expect(screen.getByText('GET /projects failed')).toBeInTheDocument())
  const rows = screen.getAllByTestId('log-line')
  expect(rows[0]).toHaveTextContent('ERROR')
})

test('reports an unreachable TestBench', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      Promise.resolve(
        new Response(
          JSON.stringify(
            url.includes('/logs')
              ? []
              : { ...STATUS, testbench: { ...STATUS.testbench, reachable: false } },
          ),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    ),
  )
  renderStatus()
  await waitFor(() => expect(screen.getByTestId('tb-state')).toHaveTextContent(/nicht/i))
})
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd frontend && npm test -- Status
```

Expected: FAIL — cannot resolve `./Status`.

- [ ] **Step 3: Write the query hooks**

Extend `frontend/src/api/queries.ts` (created in Task 12, which already holds `useMeta`) — add the imports for `ConfigResponse`, `LogLine` and `StatusResponse` alongside the existing `MetaResponse` import:

```ts
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from './client'
import type { ConfigResponse, LogLine, MetaResponse, StatusResponse } from './types'

export function useStatus() {
  return useQuery({
    queryKey: ['status'],
    queryFn: () => apiFetch<StatusResponse>('/status'),
    refetchInterval: 15_000,
  })
}

export function useLogs(limit = 25) {
  return useQuery({
    queryKey: ['logs', limit],
    queryFn: () => apiFetch<LogLine[]>(`/logs?limit=${limit}`),
    refetchInterval: 15_000,
  })
}

export function useConfig() {
  return useQuery({
    queryKey: ['config'],
    queryFn: () => apiFetch<ConfigResponse>('/config'),
  })
}
```

- [ ] **Step 4: Write the screen**

`frontend/src/screens/Status.tsx`:

```tsx
import { useLogs, useStatus } from '../api/queries'
import { useTranslations, type Lang } from '../i18n'

const LEVEL_COLORS: Record<string, string> = {
  ERROR: '#c0392b',
  CRITICAL: '#c0392b',
  WARNING: '#b8860b',
}

export function formatUptime(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  const days = Math.floor(total / 86400)
  const hours = Math.floor((total % 86400) / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  if (days) return `${days}d ${hours}h`
  if (hours) return `${hours}h ${minutes}m`
  return `${minutes}m`
}

function Card({ kicker, children }: { kicker: string; children: React.ReactNode }) {
  return (
    <div className="card blueprint" style={{ padding: 16 }}>
      <i className="corner tl" />
      <i className="corner tr" />
      <i className="corner bl" />
      <i className="corner br" />
      <div className="card-kicker">{kicker}</div>
      {children}
    </div>
  )
}

function Dot({ ok }: { ok: boolean }) {
  return (
    <span
      aria-hidden="true"
      style={{
        width: 8,
        height: 8,
        borderRadius: '50%',
        background: ok ? '#2e9e6b' : '#c0392b',
        display: 'inline-block',
      }}
    />
  )
}

export function Status({ lang }: { lang: Lang }) {
  const t = useTranslations(lang)
  const status = useStatus()
  const logs = useLogs()

  if (status.isLoading) return <div style={{ padding: 28 }}>…</div>
  if (status.isError || !status.data) {
    return (
      <div role="alert" style={{ padding: 28 }}>
        {(status.error as Error)?.message ?? 'Failed to load status'}
      </div>
    )
  }

  const { service, testbench, api_keys, agents, log_file } = status.data

  return (
    <div
      style={{
        padding: '28px 32px',
        display: 'flex',
        flexDirection: 'column',
        gap: 24,
        maxWidth: 1200,
      }}
    >
      <h2 style={{ margin: 0, fontSize: 30 }}>{t.status}</h2>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: 20,
        }}
      >
        <Card kicker={t.service}>
          <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Dot ok />
            {t.running}
          </div>
          <div className="card-meta">
            {service.host}:{service.port} · v{service.version} ·{' '}
            {formatUptime(service.uptime_seconds)}
          </div>
        </Card>

        <Card kicker="TestBench">
          <div
            className="card-title"
            data-testid="tb-state"
            style={{ display: 'flex', alignItems: 'center', gap: 8 }}
          >
            <Dot ok={testbench.reachable} />
            {testbench.reachable
              ? t.connected
              : lang === 'de'
                ? 'Nicht verbunden'
                : 'Not connected'}
          </div>
          <div className="card-meta" style={{ fontFamily: 'ui-monospace, Menlo, monospace' }}>
            {testbench.url}
          </div>
        </Card>

        <Card kicker={t.apiKeys}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {api_keys.map((key) => (
              <div
                key={key.name}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  fontSize: 12,
                  opacity: key.present ? 1 : 0.6,
                }}
              >
                <Dot ok={key.present} />
                <span style={{ fontFamily: 'ui-monospace, Menlo, monospace' }}>{key.name}</span>
                <span className="text-muted">{key.present ? t.keySet : t.keyMissing}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card kicker={t.agents}>
          <div className="card-title">
            {agents.total} {t.agents}
          </div>
          <div className="card-meta">
            {agents.enabled} {t.agentsOn} · {agents.project_overrides} {t.overrides}
          </div>
        </Card>
      </div>

      <div>
        <h4 style={{ margin: '0 0 8px' }}>{t.recentLog}</h4>
        <div className="card blueprint" style={{ padding: 12 }}>
          <i className="corner tl" />
          <i className="corner tr" />
          <i className="corner bl" />
          <i className="corner br" />
          <div className="card-meta" style={{ marginBottom: 8 }}>
            {log_file}
          </div>
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 2,
              fontFamily: 'ui-monospace, Menlo, monospace',
              fontSize: 12,
              overflowX: 'auto',
            }}
          >
            {(logs.data ?? []).map((line, index) => (
              <div
                key={index}
                data-testid="log-line"
                style={{ display: 'flex', gap: 10, whiteSpace: 'pre' }}
              >
                <span className="text-muted">{line.timestamp?.slice(11) ?? ''}</span>
                <span
                  style={{
                    color: LEVEL_COLORS[line.level ?? ''] ?? 'var(--color-accent-700)',
                    minWidth: 62,
                  }}
                >
                  {line.level ?? ''}
                </span>
                <span className="text-muted" style={{ minWidth: 160 }}>
                  {line.source ?? ''}
                </span>
                <span>{line.message}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Mount the route**

In `frontend/src/App.tsx`, import `Status` and replace the status route:

```tsx
<Route path="/admin/status" element={<Status lang={lang} />} />
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd frontend && npm test
```

Expected: PASS, 7 new tests.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/queries.ts frontend/src/screens/Status.tsx \
        frontend/src/screens/Status.test.tsx frontend/src/App.tsx
git commit -m "Add console status screen"
```

---

### Task 15: Read-only Service, LLM and Logging screens

**Files:**
- Create: `frontend/src/components/ReadOnlyField.tsx`
- Create: `frontend/src/screens/ConfigSection.tsx`, `frontend/src/screens/ConfigSection.test.tsx`
- Create: `frontend/src/screens/fields.ts`, `frontend/src/screens/fields.test.ts`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `useConfig` (Task 14); `GET /config` (Task 10)
- Produces: `FieldSpec { key, labelPath, type, hint, options? }`; `SERVICE_TABS`, `LLM_FIELDS`, `LOGGING_FIELDS`; `valueAt(config, path)`; `ConfigSection` component. Phase 2 turns these specs into editable inputs.

- [ ] **Step 1: Write the failing field-spec tests**

`frontend/src/screens/fields.test.ts`:

```ts
import { LLM_FIELDS, LOGGING_FIELDS, SERVICE_TABS, valueAt } from './fields'

const CONFIG = {
  host: '127.0.0.1',
  port: 8010,
  debug: false,
  tb_ssl_verify: true,
  llm_config: { provider: 'openai', model: null },
  logging: { console: { log_level: 'INFO' }, file: { file_name: 'svc.log' } },
}

test('reads a top-level value', () => {
  expect(valueAt(CONFIG, 'host')).toBe('127.0.0.1')
})

test('reads a nested value', () => {
  expect(valueAt(CONFIG, 'logging.console.log_level')).toBe('INFO')
})

test('missing paths read as undefined, not a crash', () => {
  expect(valueAt(CONFIG, 'llm_config.azure_endpoint')).toBeUndefined()
  expect(valueAt(CONFIG, 'nope.nested.deep')).toBeUndefined()
})

test('null is preserved so the UI can show "no override"', () => {
  expect(valueAt(CONFIG, 'llm_config.model')).toBeNull()
})

test('the service tabs match the source design', () => {
  expect(SERVICE_TABS.map((tab) => tab.key)).toEqual(['general', 'tb', 'tls', 'proxy'])
})

test('general tab covers the documented service fields', () => {
  const keys = SERVICE_TABS[0].fields.map((field) => field.key)
  expect(keys).toContain('tb_server_url')
  expect(keys).toContain('host')
  expect(keys).toContain('port')
  expect(keys).toContain('language')
  expect(keys).toContain('prompts_dir')
  // templates_dir is in AppConfig but was missing from the prototype (spec 11.4).
  expect(keys).toContain('templates_dir')
})

test('deployment_mapping is deliberately absent from the LLM fields', () => {
  /** Spec 11.3: the backend has no notion of it, so no control pretends to. */
  expect(LLM_FIELDS.map((field) => field.key)).not.toContain(
    'llm_config.deployment_mapping',
  )
})

test('logging covers both sinks', () => {
  const keys = LOGGING_FIELDS.map((field) => field.key)
  expect(keys).toContain('logging.console.log_level')
  expect(keys).toContain('logging.file.file_name')
})
```

- [ ] **Step 2: Write the failing screen tests**

`frontend/src/screens/ConfigSection.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ConfigSection } from './ConfigSection'

const CONFIG = {
  running: {
    tb_server_url: 'https://tb.example.com:9443/api/',
    host: '127.0.0.1',
    port: 8010,
    debug: false,
    language: 'de',
    prompts_dir: 'prompts',
    templates_dir: null,
    tb_ssl_verify: true,
    tb_ssl_ca_bundle: null,
    tb_connect_timeout: 10.0,
    tb_read_timeout: 120.0,
    tb_max_retries: 3,
    ssl_cert: null,
    ssl_key: null,
    ssl_ca_cert: null,
    trusted_proxies: [],
    llm_config: { provider: 'openai', model: null },
    logging: {
      console: { log_level: 'INFO', log_format: '%(levelname)s: %(message)s' },
      file: { file_name: 'svc.log', log_level: 'DEBUG', log_format: '%(message)s' },
    },
  },
  disk: {},
  config_path: 'C:\\svc\\config.toml',
  in_sync: true,
}

function renderSection(section: 'service' | 'llm' | 'logging') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ConfigSection section={section} lang="de" />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify(CONFIG), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    ),
  )
})

afterEach(() => vi.restoreAllMocks())

test('shows service values from the running config', async () => {
  renderSection('service')
  await waitFor(() =>
    expect(screen.getByText('https://tb.example.com:9443/api/')).toBeInTheDocument(),
  )
  expect(screen.getByText('8010')).toBeInTheDocument()
})

test('every value is read-only in phase 1', async () => {
  renderSection('service')
  await waitFor(() => expect(screen.getByText('127.0.0.1')).toBeInTheDocument())
  expect(screen.queryAllByRole('textbox')).toHaveLength(0)
  expect(screen.queryAllByRole('checkbox')).toHaveLength(0)
  expect(screen.queryAllByRole('combobox')).toHaveLength(0)
})

test('switching tabs shows the TestBench connection fields', async () => {
  renderSection('service')
  await waitFor(() => expect(screen.getByText('127.0.0.1')).toBeInTheDocument())
  await userEvent.click(screen.getByRole('tab', { name: 'TestBench-Verbindung' }))
  expect(screen.getByText('120')).toBeInTheDocument()
})

test('booleans render as true/false rather than an empty control', async () => {
  renderSection('service')
  await waitFor(() => expect(screen.getByText('false')).toBeInTheDocument())
})

test('an unset value renders as a dash, not "null"', async () => {
  renderSection('service')
  await waitFor(() => expect(screen.getByText('127.0.0.1')).toBeInTheDocument())
  expect(screen.queryByText('null')).toBeNull()
  expect(screen.getAllByText('—').length).toBeGreaterThan(0)
})

test('the llm section shows the provider', async () => {
  renderSection('llm')
  await waitFor(() => expect(screen.getByText('openai')).toBeInTheDocument())
})

test('the logging section shows both sinks', async () => {
  renderSection('logging')
  await waitFor(() => expect(screen.getByText('svc.log')).toBeInTheDocument())
  expect(screen.getByText('INFO')).toBeInTheDocument()
})

test('the config path is shown so the operator knows which file this is', async () => {
  renderSection('service')
  await waitFor(() =>
    expect(screen.getByText(/config\.toml/)).toBeInTheDocument(),
  )
})
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cd frontend && npm test
```

Expected: FAIL — cannot resolve `./fields` or `./ConfigSection`.

- [ ] **Step 4: Write the field specs**

`frontend/src/screens/fields.ts`:

```ts
export type FieldType = 'text' | 'number' | 'bool' | 'select' | 'list'

export interface FieldSpec {
  /** Dotted path into the config object returned by GET /config. */
  key: string
  type: FieldType
  hint: string
  options?: string[]
}

export interface ServiceTab {
  key: string
  /** Translation key for the tab label. */
  labelKey: 'general' | 'tbConn' | 'tls' | 'proxy'
  fields: FieldSpec[]
}

const LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

export const SERVICE_TABS: ServiceTab[] = [
  {
    key: 'general',
    labelKey: 'general',
    fields: [
      { key: 'tb_server_url', type: 'text', hint: 'Base URL of the TestBench REST API' },
      { key: 'host', type: 'text', hint: 'Bind address' },
      { key: 'port', type: 'number', hint: 'Port to listen on' },
      { key: 'debug', type: 'bool', hint: 'Verbose logging, auto-reload' },
      {
        key: 'language',
        type: 'select',
        options: ['de', 'en'],
        hint: 'Default language for prompt resolution and localization',
      },
      { key: 'prompts_dir', type: 'text', hint: 'Directory with prompt YAML files' },
      { key: 'templates_dir', type: 'text', hint: 'Directory with output templates' },
    ],
  },
  {
    key: 'tb',
    labelKey: 'tbConn',
    fields: [
      { key: 'tb_ssl_verify', type: 'bool', hint: 'Verify the TestBench TLS certificate' },
      { key: 'tb_ssl_ca_bundle', type: 'text', hint: 'Path to a CA bundle' },
      { key: 'tb_connect_timeout', type: 'number', hint: 'Seconds to wait while connecting' },
      { key: 'tb_read_timeout', type: 'number', hint: 'Seconds to wait for data' },
      {
        key: 'tb_max_retries',
        type: 'number',
        hint: 'Retries after connection errors — idempotent methods only',
      },
    ],
  },
  {
    key: 'tls',
    labelKey: 'tls',
    fields: [
      { key: 'ssl_cert', type: 'text', hint: 'Certificate file' },
      { key: 'ssl_key', type: 'text', hint: 'Private key file' },
      {
        key: 'ssl_ca_cert',
        type: 'text',
        hint: 'CA certificate — when set, client certificates are required (mTLS)',
      },
    ],
  },
  {
    key: 'proxy',
    labelKey: 'proxy',
    fields: [
      { key: 'trusted_proxies', type: 'list', hint: 'Trusted proxy IP addresses' },
    ],
  },
]

export const LLM_FIELDS: FieldSpec[] = [
  {
    key: 'llm_config.provider',
    type: 'select',
    options: ['openai', 'azure_openai', 'anthropic', 'custom'],
    hint: 'gpt-*/o-series route to OpenAI, claude-* to Anthropic, regardless of this setting',
  },
  {
    key: 'llm_config.model',
    type: 'text',
    hint: "Global override. When empty, each prompt variant's model is used.",
  },
  { key: 'llm_config.auth_method', type: 'text', hint: 'Azure only: api_key or entra_id' },
  { key: 'llm_config.azure_endpoint', type: 'text', hint: 'Required for Azure' },
  { key: 'llm_config.api_version', type: 'text', hint: 'Required for Azure' },
  { key: 'llm_config.class_path', type: 'text', hint: 'Custom LLMClient subclass' },
]

export const LOGGING_FIELDS: FieldSpec[] = [
  { key: 'logging.console.log_level', type: 'select', options: LOG_LEVELS, hint: 'Console' },
  { key: 'logging.console.log_format', type: 'text', hint: 'Python logging format string' },
  { key: 'logging.file.file_name', type: 'text', hint: 'Relative paths resolve from the CWD' },
  { key: 'logging.file.log_level', type: 'select', options: LOG_LEVELS, hint: 'File' },
  { key: 'logging.file.log_format', type: 'text', hint: 'Python logging format string' },
]

/** Read a dotted path out of the config object, tolerating absent branches. */
export function valueAt(config: Record<string, unknown>, path: string): unknown {
  return path.split('.').reduce<unknown>((node, key) => {
    if (node === null || typeof node !== 'object') return undefined
    return (node as Record<string, unknown>)[key]
  }, config)
}
```

- [ ] **Step 5: Write the read-only field renderer**

`frontend/src/components/ReadOnlyField.tsx`:

```tsx
import type { FieldSpec } from '../screens/fields'

/** Renders one config value as text. Phase 2 replaces this with real inputs. */
export function ReadOnlyField({ spec, value }: { spec: FieldSpec; value: unknown }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(180px, 260px) 1fr',
        gap: 16,
        padding: '10px 0',
        borderBottom: '1px solid var(--color-divider)',
      }}
    >
      <div>
        <div style={{ fontSize: 13, fontFamily: 'ui-monospace, Menlo, monospace' }}>
          {spec.key.split('.').pop()}
        </div>
        <div className="text-muted" style={{ fontSize: 11 }}>
          {spec.hint}
        </div>
      </div>
      <div style={{ fontSize: 14, wordBreak: 'break-word' }}>{display(value)}</div>
    </div>
  )
}

function display(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (Array.isArray(value)) return value.length ? value.join(', ') : '—'
  return String(value)
}
```

- [ ] **Step 6: Write the section screen**

`frontend/src/screens/ConfigSection.tsx`:

```tsx
import { useState } from 'react'
import { useConfig } from '../api/queries'
import { ReadOnlyField } from '../components/ReadOnlyField'
import { useTranslations, type Lang } from '../i18n'
import { LLM_FIELDS, LOGGING_FIELDS, SERVICE_TABS, valueAt, type FieldSpec } from './fields'

type Section = 'service' | 'llm' | 'logging'

const TITLE_KEY: Record<Section, 'service' | 'llm' | 'logging'> = {
  service: 'service',
  llm: 'llm',
  logging: 'logging',
}

const TOML_SECTION: Record<Section, string> = {
  service: '[testbench-ai-service]',
  llm: '[testbench-ai-service.llm_config]',
  logging: '[testbench-ai-service.logging.console] · [.file]',
}

export function ConfigSection({ section, lang }: { section: Section; lang: Lang }) {
  const t = useTranslations(lang)
  const config = useConfig()
  const [tab, setTab] = useState(SERVICE_TABS[0].key)

  if (config.isLoading) return <div style={{ padding: 28 }}>…</div>
  if (config.isError || !config.data) {
    return (
      <div role="alert" style={{ padding: 28 }}>
        {(config.error as Error)?.message ?? 'Failed to load configuration'}
      </div>
    )
  }

  const running = config.data.running
  let fields: FieldSpec[]
  if (section === 'service') {
    fields = (SERVICE_TABS.find((entry) => entry.key === tab) ?? SERVICE_TABS[0]).fields
  } else {
    fields = section === 'llm' ? LLM_FIELDS : LOGGING_FIELDS
  }

  return (
    <div
      style={{
        padding: '28px 32px',
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
        maxWidth: 900,
      }}
    >
      <div>
        <h2 style={{ margin: 0, fontSize: 30 }}>{t[TITLE_KEY[section]]}</h2>
        <div
          className="text-muted"
          style={{ fontSize: 12, fontFamily: 'ui-monospace, Menlo, monospace' }}
        >
          {TOML_SECTION[section]} · {config.data.config_path}
        </div>
      </div>

      {section === 'service' && (
        <div role="tablist" style={{ display: 'flex', gap: 18 }}>
          {SERVICE_TABS.map((entry) => (
            <button
              key={entry.key}
              role="tab"
              aria-selected={tab === entry.key}
              onClick={() => setTab(entry.key)}
              style={{
                background: 'none',
                border: 0,
                borderBottom: `2px solid ${tab === entry.key ? 'var(--color-accent)' : 'transparent'}`,
                padding: '6px 0',
                font: 'inherit',
                fontSize: 14,
                color: 'inherit',
                opacity: tab === entry.key ? 1 : 0.7,
                cursor: 'pointer',
              }}
            >
              {t[entry.labelKey]}
            </button>
          ))}
        </div>
      )}

      <div>
        {fields.map((spec) => (
          <ReadOnlyField key={spec.key} spec={spec} value={valueAt(running, spec.key)} />
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 7: Mount the routes**

In `frontend/src/App.tsx`:

```tsx
<Route path="/admin/service" element={<ConfigSection section="service" lang={lang} />} />
<Route path="/admin/llm" element={<ConfigSection section="llm" lang={lang} />} />
<Route path="/admin/logging" element={<ConfigSection section="logging" lang={lang} />} />
```

- [ ] **Step 8: Run the whole frontend suite**

```bash
cd frontend && npm test && npm run build
```

Expected: all tests PASS, and the build succeeds — `tsc -b` is part of `npm run build`, so this is also the type check.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/ReadOnlyField.tsx frontend/src/screens/fields.ts \
        frontend/src/screens/fields.test.ts frontend/src/screens/ConfigSection.tsx \
        frontend/src/screens/ConfigSection.test.tsx frontend/src/App.tsx
git commit -m "Add read-only service, LLM and logging screens"
```

---

### Task 16: Build the frontend into the binary

**Files:**
- Modify: `build_binary.py`
- Create: `tests/unit/test_build_binary.py`

**Interfaces:**
- Consumes: the `npm run build` contract from Task 2
- Produces: `build_frontend(frontend_dir: Path, *, skip: bool = False) -> None`, called before PyInstaller

- [ ] **Step 1: Read the existing script before changing it**

```bash
sed -n '1,60p' build_binary.py
grep -n "def \|__main__" build_binary.py
```

Note the existing entry point and argument handling so the new step slots in rather than bolting on.

- [ ] **Step 2: Write the failing tests**

`tests/unit/test_build_binary.py`:

```python
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from build_binary import build_frontend


@pytest.fixture
def frontend(tmp_path: Path) -> Path:
    directory = tmp_path / "frontend"
    directory.mkdir()
    (directory / "package.json").write_text("{}", encoding="utf-8")
    return directory


def test_runs_ci_then_build(frontend: Path):
    with patch("build_binary.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0)
        build_frontend(frontend)
    commands = [call.args[0] for call in run.call_args_list]
    assert any("ci" in command for command in commands)
    assert any("build" in command for command in commands)


def test_skip_flag_runs_nothing(frontend: Path):
    with patch("build_binary.subprocess.run") as run:
        build_frontend(frontend, skip=True)
    run.assert_not_called()


def test_missing_node_fails_loudly(frontend: Path):
    with patch("build_binary.subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(SystemExit) as exc:
            build_frontend(frontend)
    assert "Node" in str(exc.value)


def test_failing_build_aborts(frontend: Path):
    error = subprocess.CalledProcessError(1, ["npm", "run", "build"])
    with patch("build_binary.subprocess.run", side_effect=error):
        with pytest.raises(SystemExit):
            build_frontend(frontend)


def test_absent_frontend_directory_aborts(tmp_path: Path):
    with pytest.raises(SystemExit):
        build_frontend(tmp_path / "nope")
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
python -m pytest tests/unit/test_build_binary.py -v
```

Expected: FAIL — `ImportError: cannot import name 'build_frontend'`.

- [ ] **Step 4: Add the build step**

Add to `build_binary.py`:

```python
import shutil
import subprocess
import sys
from pathlib import Path

FRONTEND_DIR = Path(__file__).parent / "frontend"


def build_frontend(frontend_dir: Path = FRONTEND_DIR, *, skip: bool = False) -> None:
    """Build the web console into ``testbench_ai_service/static/admin``.

    PyInstaller sweeps that directory up via ``collect_data_files``, so the binary
    must never be built with stale or missing console assets — a silent skip would
    ship a binary whose /admin serves a placeholder.
    """
    if skip:
        print("Skipping frontend build (--skip-frontend)")
        return

    if not (frontend_dir / "package.json").is_file():
        sys.exit(f"No package.json in {frontend_dir}; cannot build the web console.")

    npm = shutil.which("npm") or "npm"
    for command in (["ci"], ["run", "build"]):
        print(f"Running npm {' '.join(command)} in {frontend_dir}")
        try:
            subprocess.run([npm, *command], cwd=frontend_dir, check=True)  # noqa: S603
        except FileNotFoundError:
            sys.exit(
                "Node.js and npm are required to build the web console. "
                "Install Node 20+, or pass --skip-frontend to build without it."
            )
        except subprocess.CalledProcessError as e:
            sys.exit(f"Frontend build failed (npm {' '.join(command)}): {e}")
```

Then call it from the script's main flow before PyInstaller runs, and register the flag on the existing argument parser:

```python
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="Do not rebuild the web console; use whatever is already in "
        "testbench_ai_service/static/admin.",
    )
```

```python
    build_frontend(skip=args.skip_frontend)
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python -m pytest tests/unit/test_build_binary.py -v
```

Expected: PASS, 5 tests.

- [ ] **Step 6: Verify the real build end to end**

```bash
python -m pytest tests -q
cd frontend && npm run build && cd ..
python -c "from testbench_ai_service.webui.static import STATIC_DIR; print(STATIC_DIR, STATIC_DIR.is_dir())"
```

Expected: the suite passes and `STATIC_DIR` reports `True`.

- [ ] **Step 7: Commit**

```bash
git add build_binary.py tests/unit/test_build_binary.py
git commit -m "Build the web console into the binary"
```

---

### Task 17: Documentation and changelog

**Files:**
- Create: `docs/web-console.md`
- Modify: `docs/configuration.md`, `CHANGELOG.md`, `README.md`, `CONTRIBUTING.md`

**Interfaces:**
- Consumes: everything above
- Produces: no code

- [ ] **Step 1: Check how the docs are indexed**

```bash
cat docs/_category_.json 2>/dev/null
ls docs/
grep -n "sidebar_position\|^---" docs/configuration.md | head
```

The docs are Docusaurus-style (`_category_.json`, front matter). Match the front matter of a sibling page so the new page slots into the sidebar.

- [ ] **Step 2: Write `docs/web-console.md`**

Cover, in this order:

1. What the console is and the URL — `http://<host>:<port>/admin`.
2. Signing in with TestBench credentials; that the server is fixed by `tb_server_url`.
3. Roles: the TestBench `Administrator` global role is required to change anything; everyone else gets a read-only console.
4. The `[testbench-ai-service.admin_ui]` section: `enabled` and `require_loopback`, with the security note that binding a non-loopback `host` makes the console reachable off-box.
5. That phase 1 is read-only — editing arrives in a later release. Do not document endpoints that do not exist yet.
6. Troubleshooting: the placeholder page means the frontend was not built; `npm ci && npm run build` in `frontend/`, or use a release binary.

- [ ] **Step 3: Cross-reference from `docs/configuration.md`**

Add the `admin_ui` section to whatever table or list of config sections that page already maintains, linking to `web-console.md`.

- [ ] **Step 4: Add the changelog entry**

Match the existing `CHANGELOG.md` format exactly — check the top entry first:

```bash
sed -n '1,30p' CHANGELOG.md
```

The entry should say: a read-only web console at `/admin`, TestBench sign-in, service status, and configuration display; note that it is disabled with `admin_ui.enabled = false`.

- [ ] **Step 5: Mention it in `README.md`**

Add one bullet to the Features list, in the established style:

```markdown
- **Web console:** read-only service status and configuration at `/admin`, signed in with TestBench credentials
```

- [ ] **Step 6: Document the frontend workflow in `CONTRIBUTING.md`**

Add a short section after the existing test instructions: `cd frontend && npm install`, `npm run dev` (proxies `/admin/api` to a locally running service), `npm test`, `npm run build`.

- [ ] **Step 7: Verify and commit**

```bash
python -m pytest tests -q
cd frontend && npm test && cd ..
git add docs/web-console.md docs/configuration.md CHANGELOG.md README.md CONTRIBUTING.md
git commit -m "Document the web console"
```

---

## Phase 1 Completion Checklist

Run before declaring the phase done. Per `superpowers:verification-before-completion`, paste the actual output — do not assert from memory.

- [ ] `python -m pytest tests -q` — all backend tests pass, including the pre-existing suite
- [ ] `cd frontend && npm test` — all frontend tests pass
- [ ] `cd frontend && npm run build` — type check and build succeed
- [ ] `python -m ruff check .` and `python -m mypy testbench_ai_service` — clean, matching `.pre-commit-config.yaml`
- [ ] Manual smoke test against a real service:
  ```bash
  testbench-ai-service start
  ```
  then open `http://127.0.0.1:8010/admin`, sign in with real TestBench credentials, and confirm: Status shows the service and TestBench cards; the log panel lists real lines; Service/LLM/Logging show real config values; a page reload on `/admin/llm` stays on that screen rather than 404ing; sign-out returns to the login screen.
- [ ] `GET /` still redirects to `/docs`, and the agent endpoints still work
- [ ] With `admin_ui.enabled = false`, `/admin` and `/admin/api/session` both 404
- [ ] Spec section 16's open items confirmed against the live TestBench — especially that an admin's role list really contains `Administrator`

## Deferred to Later Phases

Recorded here so nothing silently disappears between plans:

- **Phase 2:** config editing, `POST /config/preview` diff, `POST /config/apply`, atomic writes with `.bak`, `tomlkit` round-trip, hot reload, restart-required banner, in-flight task registry, raw `config.toml` view, `LLMConfig.timeout`/`max_retries`
- **Phase 3:** Agents list and matrix, agent detail with inherit/override, Projects screen, `GET /projects`, `PromptConfig.vars` widening, prompt "fork" for per-project overrides
- **Phase 4:** prompt editor, CodeMirror from npm, `POST /prompts/lint` and `/render` on real Jinja2, variables and variants — all of which must route filesystem access through `resolve_within` from Task 5
- **Phase 5:** agent test run
