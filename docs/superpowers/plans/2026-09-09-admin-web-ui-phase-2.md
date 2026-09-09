# Admin Web UI — Phase 2 (Config Write Path) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `/admin` console able to change the service's configuration — edit the Service, LLM and Logging forms, review a real unified diff, write `config.toml` atomically without losing the operator's comments, and hot-reload the running service.

**Architecture:** The browser holds a **sparse edit overlay** — a map of dotted config paths to new values — not a whole config document. `POST /config/preview` and `POST /config/apply` merge that overlay into the config **freshly read from disk**, validate the result by constructing the real `AppConfig`, render it back through a `tomlkit` document so comments and key order survive, and diff the rendered text against the file on disk. Apply writes atomically (temp file in the same directory, `os.replace`, previous contents kept as `.bak`), then hot-swaps `app.state.config`, rebuilds the LLM clients and re-applies logging. Changes a live swap genuinely cannot cover raise a "restart needed" banner instead.

**Tech Stack:** FastAPI, pydantic v2, `tomlkit` (new), `difflib`, pytest (`asyncio_mode = auto`), React 18, Vite, TypeScript, TanStack Query, React Router, Vitest + React Testing Library.

**Spec:** `docs/superpowers/specs/2026-09-08-admin-web-ui-design.md` (sections 3.1, 6, 7, 7.1, 8, 11, 12, 13, 14)

## Global Constraints

- Python `>=3.10,<3.15`. Nothing may rely on 3.11+ syntax; `tomllib` is imported with a `tomli` fallback (see `testbench_ai_service/utils/config.py` and `webui/config_io.py`).
- Backend package is `testbench_ai_service/webui/`. Route prefix is `/admin/api`. Static mount is `/admin`.
- **Never delete `testbench_ai_service/webui/__pycache__/`.** It is the only surviving trace of the August attempt (spec 2.1) and was never committed. Stale bytecode without its source cannot be imported, so it is harmless.
- **No runtime fetch from any third-party origin.** No CDN scripts, no Google Fonts `@import`. An on-prem service may have no outbound access.
- **API-key presence only, never values.** No endpoint may return the contents of an environment variable.
- **Every request-derived filesystem path goes through `resolve_within`** (spec 9.1). Phase 2 adds no new path-taking endpoint, but `config_io` writes only to `app.state.config_path`, which is process state and never request data — assert that in review.
- **Writes are Administrator-only** (spec 3.1.1). Every mutating route carries `Depends(require_admin)` *and* `Depends(require_csrf)`. Both already exist in `webui/auth.py`.
- **The redaction sentinel must never be written back.** `GET /config` replaces credential-named values with `***REDACTED***` (`REDACTED_SENTINEL` in `webui/config_io.py`). A submitted edit whose value is that sentinel is rejected with 400 — see Task 3. This is the single most important safety property of the sparse-overlay design.
- `deployment_mapping` stays out of the UI (spec 3.1.4 / 11.3). Do not add a field for it.
- There is **no self-restart button** (spec 3.1.3 / 7). The banner tells the operator to restart; it never restarts anything.
- Commit messages follow the repo's house style — capitalized imperative subject, no `type:` prefix. Check `git log --oneline -20` before the first commit.
- Run `ruff check .`, `ruff format --check .` and `mypy testbench_ai_service` before each backend commit; `npm test` and `npm run build` (in `frontend/`) before each frontend commit.

## Why a sparse overlay rather than a whole-document draft

Spec 6.1 says the draft lives in the browser. It does not say what shape crosses the wire, and the obvious reading — POST the whole config back — is unsafe and lossy here:

1. `GET /config` redacts credential-named keys, so a whole-config POST would write `***REDACTED***` into `config.toml` as a literal value.
2. `running` is the *fully defaulted* `AppConfig.model_dump()`. Writing it back would expand a five-line hand-written `config.toml` into every default the model has, which is exactly the regression `tomlkit` was chosen to avoid.
3. Merging a sparse overlay into a freshly-read disk config is what gives spec 6.1's concurrency property for free: the second writer's diff shows the first writer's changes rather than silently reverting them.

So the wire format is `{"edits": {"<dotted.path>": <value>, ...}}`, where a `null` value means "remove this key and fall back to the model default". The browser still keeps the whole draft in `localStorage`; it just keeps it *as* the overlay.

## File structure

**Backend — new files**

| File | Responsibility |
|---|---|
| `testbench_ai_service/webui/edits.py` | The overlay: parse/validate dotted paths, merge an overlay into a plain dict, reject the redaction sentinel. Pure functions, no I/O. |
| `testbench_ai_service/webui/document.py` | `tomlkit` document handling: load, apply an overlay in place, render to text. Knows about comments and the `[testbench-ai-service]` prefix; knows nothing about HTTP. |
| `testbench_ai_service/webui/atomic.py` | `write_atomic` — temp file in the target directory, `os.replace`, `.bak` of the previous contents. |
| `testbench_ai_service/webui/validate.py` | `validate_config_dict` — construct `AppConfig`, turn a `ValidationError` into field-addressed `ConfigIssue`s. |
| `testbench_ai_service/webui/diff.py` | `file_diff` — unified diff of two texts, `None` when identical. |
| `testbench_ai_service/webui/reload.py` | `restart_required` classification and `hot_reload`. |
| `testbench_ai_service/webui/inflight.py` | `TaskRegistry` — how many agent runs are in flight. |

**Backend — modified files**

| File | Change |
|---|---|
| `testbench_ai_service/models/config.py` | `LLMConfig.timeout` / `max_retries` become declared fields (spec 11.2). |
| `testbench_ai_service/llm/factory.py` | `_get_common_client_kwargs` reads the declared fields, not `model_extra`. |
| `testbench_ai_service/webui/models.py` | `ConfigIssue`, `FileDiff`, `ConfigEditsRequest`, `PreviewResponse`, `ApplyResponse`. |
| `testbench_ai_service/webui/routes.py` | `POST /config/preview`, `POST /config/apply`. |
| `testbench_ai_service/webui/status.py` + `models.py` | `StatusResponse.in_flight_tasks`. |
| `testbench_ai_service/main.py` | Create the `TaskRegistry` on `app.state`. |
| `testbench_ai_service/agents/routes.py` | Wrap the background agent run in the registry. |
| `pyproject.toml` | Add `tomlkit`. |

**Frontend — new files**

| File | Responsibility |
|---|---|
| `frontend/src/state/draft.tsx` | `DraftProvider` / `useDraft`: the overlay, `localStorage` persistence, `setValue`, `unset`, `reset`, `changedPaths`. |
| `frontend/src/api/mutations.ts` | `usePreview`, `useApply`. |
| `frontend/src/components/Field.tsx` | One editable field for a `FieldSpec` — text, number, bool, select, list. |
| `frontend/src/components/PendingBanner.tsx` | "N unapplied changes · view diff · discard · apply". |
| `frontend/src/components/RestartBanner.tsx` | "restart needed" strip. |
| `frontend/src/components/DiffDialog.tsx` | The diff + validation-issue modal with the Apply button. |
| `frontend/src/screens/Raw.tsx` | Generated `config.toml`, read-only, copy to clipboard. |

**Frontend — modified files**: `App.tsx` (provider, banners, `/admin/raw` route), `screens/ConfigSection.tsx` (editable), `components/NavRail.tsx` (Raw entry), `i18n/en.ts` + `i18n/de.ts`, `api/types.ts`.

**Docs**: `docs/web-console.md` (drop the read-only notice, document editing), `CHANGELOG.md`.

---

### Task 1: `LLMConfig.timeout` and `max_retries` become real fields

Spec 11.2. `LLMConfig` has `extra="allow"`, so these two keys are accepted, stashed in `model_extra`, and passed to the clients by `LLMFactory._get_common_client_kwargs`. That works by accident and is invisible to the console: an undeclared field cannot be rendered as a form field or validated. Declaring them is a prerequisite for the LLM form becoming editable in Task 15.

**Files:**
- Modify: `testbench_ai_service/models/config.py` (`LLMConfig`)
- Modify: `testbench_ai_service/llm/factory.py` (`_get_common_client_kwargs`)
- Test: `tests/unit/test_models_config.py`, `tests/unit/llm/test_factory.py`

**Interfaces:**
- Consumes: nothing
- Produces: `LLMConfig.timeout: float | None`, `LLMConfig.max_retries: int | None`. Task 15 renders both as number fields.

- [ ] **Step 1: Find the existing tests so the new ones land beside them**

```bash
ls tests/unit/llm/
grep -rn "_get_common_client_kwargs\|timeout" tests/unit/llm/test_factory.py | head -20
grep -rn "class LLMConfig" -A 3 tests/unit/*.py | head
```

Expected: `tests/unit/llm/test_factory.py` exists. Note whether a `test_models_config.py` exists; if not, create it in Step 2.

- [ ] **Step 2: Write the failing tests**

Append to `tests/unit/llm/test_factory.py`:

```python
def test_declared_timeout_and_max_retries_reach_the_client_kwargs():
    """timeout/max_retries are declared fields now, not model_extra."""
    factory = LLMFactory()
    config = LLMConfig(provider=LLMProvider.OPENAI, timeout=42.5, max_retries=7)

    assert config.timeout == 42.5
    assert config.max_retries == 7
    assert factory._get_common_client_kwargs(config) == {"timeout": 42.5, "max_retries": 7}


def test_unset_timeout_and_max_retries_are_omitted_from_client_kwargs():
    """An unset field must not become an explicit None the SDK would honour."""
    factory = LLMFactory()

    assert factory._get_common_client_kwargs(LLMConfig(provider=LLMProvider.OPENAI)) == {}


def test_strict_response_validation_still_comes_from_extra():
    """The private SDK flag stays undeclared; it is not a config surface."""
    factory = LLMFactory()
    config = LLMConfig(provider=LLMProvider.OPENAI, _strict_response_validation=False)

    assert factory._get_common_client_kwargs(config) == {"_strict_response_validation": False}
```

Add the imports that file needs if they are missing (`LLMConfig` from `testbench_ai_service.models.config`, `LLMProvider` from `testbench_ai_service.llm.base`, `LLMFactory` from `testbench_ai_service.llm.factory`).

- [ ] **Step 3: Run the tests to verify they fail**

```bash
pytest tests/unit/llm/test_factory.py -k "timeout or strict_response" -v
```

Expected: FAIL. `config.timeout` raises `AttributeError` (it is in `model_extra`, not an attribute), or `_get_common_client_kwargs` returns `{}` because the declared value never lands in `model_extra`.

- [ ] **Step 4: Declare the fields**

In `testbench_ai_service/models/config.py`, inside `LLMConfig`, after `class_path`:

```python
    timeout: float | None = Field(
        default=None,
        gt=0,
        description="Seconds to wait for an LLM response before giving up. Unset uses the provider SDK's own default.",
    )
    max_retries: int | None = Field(
        default=None,
        ge=0,
        description="How often the provider SDK retries a failed request. Unset uses the SDK's own default.",
    )
```

`Field` is already imported? Check the top of the file — it currently imports `BaseModel, ConfigDict, model_validator` from pydantic. Add `Field`:

```python
from pydantic import BaseModel, ConfigDict, Field, model_validator
```

- [ ] **Step 5: Read the declared fields in the factory**

Replace `_get_common_client_kwargs` in `testbench_ai_service/llm/factory.py`:

```python
    def _get_common_client_kwargs(self, config: LLMConfig) -> dict[str, Any]:
        """Kwargs passed to every provider SDK client.

        'timeout' and 'max_retries' are declared fields (the console renders
        them), so they are read off the model. Only an explicitly-set value is
        forwarded: passing None would override the SDK's own default with
        nothing. '_strict_response_validation' stays undeclared -- it is a
        private SDK flag, not a configuration surface -- so it still comes from
        model_extra.
        """
        kwargs: dict[str, Any] = {}
        if config.timeout is not None:
            kwargs["timeout"] = config.timeout
        if config.max_retries is not None:
            kwargs["max_retries"] = config.max_retries

        extra = config.model_extra or {}
        if "_strict_response_validation" in extra:
            kwargs["_strict_response_validation"] = extra["_strict_response_validation"]
        return kwargs
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
pytest tests/unit/llm/test_factory.py -v
pytest tests/unit -q
```

Expected: PASS. The full unit run must stay green — a config that previously carried `timeout` in `model_extra` now carries it as a field, and any test asserting on `model_extra` contents needs updating. If one fails, fix the *test's* expectation, not the field.

- [ ] **Step 7: Document the two new options**

In `docs/configuration.md`, find the `[testbench-ai-service.llm_config]` option table and add two rows in the same style as the existing ones:

```markdown
| `timeout`     | Float   | Seconds to wait for an LLM response before giving up. Unset uses the provider SDK's default. | _unset_ |
| `max_retries` | Integer | How often the provider SDK retries a failed request. Unset uses the SDK's default.           | _unset_ |
```

- [ ] **Step 8: Lint, type-check, commit**

```bash
ruff check . && ruff format --check . && mypy testbench_ai_service
git add testbench_ai_service/models/config.py testbench_ai_service/llm/factory.py tests/unit/llm/test_factory.py docs/configuration.md
git commit -m "Declare LLM timeout and max_retries as config fields"
```

---

### Task 2: `tomlkit` dependency and the comment-preserving document

`config.toml` is hand-edited and heavily commented. `tomli_w` (already a dependency, used by `utils/config.py` for `init`) cannot preserve comments, so a console save through it would silently delete an operator's notes. `tomlkit` edits the existing document in place.

**Files:**
- Modify: `pyproject.toml`
- Create: `testbench_ai_service/webui/document.py`
- Test: `tests/unit/webui/test_document.py`

**Interfaces:**
- Consumes: `CONFIG_PREFIX` from `testbench_ai_service.utils.config`
- Produces:
  - `load_document(path: Path) -> tomlkit.TOMLDocument` — the whole file; an absent file yields a document with an empty `[testbench-ai-service]` table
  - `render_document(document: tomlkit.TOMLDocument) -> str`
  - `service_table(document: tomlkit.TOMLDocument) -> tomlkit.items.Table` — the `[testbench-ai-service]` table, created if absent

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`, in the `dependencies` list, after the `tomli-w` line:

```toml
  # config.toml is hand-edited and commented; tomlkit round-trips comments and
  # key order, which tomli_w cannot. The console must not delete an operator's
  # notes on first save.
  "tomlkit>=0.13.2,<1.0.0",
```

Then install it:

```bash
pip install -e ".[dev]"
python -c "import tomlkit; print(tomlkit.__version__)"
```

Expected: a version `>=0.13.2`.

- [ ] **Step 2: Write the failing test**

Create `tests/unit/webui/test_document.py`:

```python
from pathlib import Path

import pytest
import tomlkit

from testbench_ai_service.webui.document import (
    load_document,
    render_document,
    service_table,
)

COMMENTED = """\
# Top-of-file note the operator wrote.
[testbench-ai-service]
# Which TestBench we talk to.
tb_server_url = "https://tb.example.com:9443/api/"
port = 8010

[testbench-ai-service.llm_config]
provider = "openai"  # trailing note
"""


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(COMMENTED, encoding="utf-8")
    return path


def test_untouched_document_round_trips_byte_for_byte(config_file: Path):
    """The baseline every other guarantee rests on."""
    assert render_document(load_document(config_file)) == COMMENTED


def test_editing_one_value_keeps_every_comment(config_file: Path):
    document = load_document(config_file)
    service_table(document)["port"] = 9999

    rendered = render_document(document)

    assert "port = 9999" in rendered
    assert "# Top-of-file note the operator wrote." in rendered
    assert "# Which TestBench we talk to." in rendered
    assert "# trailing note" in rendered


def test_absent_file_yields_an_empty_service_table(tmp_path: Path):
    """The service runs on defaults alone; the console must still be able to save."""
    document = load_document(tmp_path / "nothing.toml")

    assert service_table(document) == {}
    assert render_document(document).strip() == "[testbench-ai-service]"


def test_service_table_is_created_when_the_file_has_other_sections(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text('[tool.other]\nkey = "value"\n', encoding="utf-8")

    document = load_document(path)
    service_table(document)["port"] = 8010

    rendered = render_document(document)
    assert '[tool.other]' in rendered
    assert 'key = "value"' in rendered
    assert "[testbench-ai-service]" in rendered
    assert "port = 8010" in rendered


def test_invalid_toml_is_a_400(tmp_path: Path):
    from fastapi import HTTPException

    path = tmp_path / "config.toml"
    path.write_text("this is = = not toml", encoding="utf-8")

    with pytest.raises(HTTPException) as exc:
        load_document(path)
    assert exc.value.status_code == 400


def test_service_table_returns_the_live_table_not_a_copy(config_file: Path):
    """Callers mutate what service_table hands back; a copy would silently no-op."""
    document = load_document(config_file)
    service_table(document)["new_key"] = "new_value"

    assert 'new_key = "new_value"' in render_document(document)
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
pytest tests/unit/webui/test_document.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'testbench_ai_service.webui.document'`.

- [ ] **Step 4: Write the implementation**

Create `testbench_ai_service/webui/document.py`:

```python
"""The console's ``config.toml`` document.

``config.toml`` is a hand-edited, commented file. Every console write goes
through a ``tomlkit`` document so that comments, key order and formatting
survive a save -- ``tomli_w``, which the ``init`` command uses, cannot preserve
any of them, and losing an operator's notes on first save would be a serious
regression.

This module knows about TOML and about the ``[testbench-ai-service]`` prefix.
It knows nothing about HTTP request shapes; see ``edits.py`` for those.
"""

from pathlib import Path

import tomlkit
from fastapi import HTTPException, status
from tomlkit.exceptions import TOMLKitError
from tomlkit.items import Table

from testbench_ai_service.log import logger
from testbench_ai_service.utils.config import CONFIG_PREFIX


def load_document(path: Path) -> tomlkit.TOMLDocument:
    """Parse *path* into an editable TOML document.

    An absent file yields a document holding nothing but an empty
    ``[testbench-ai-service]`` table: the service can run entirely on defaults,
    and the console must still be able to write the operator's first change.

    Raises:
        HTTPException 400: the file exists but is not valid TOML, is not
            readable, or is not decodable as UTF-8.
    """
    file_path = Path(path)
    if not file_path.is_file():
        logger.debug("No config file at %s; starting a fresh document", file_path)
        document = tomlkit.document()
        document[CONFIG_PREFIX] = tomlkit.table()
        return document
    try:
        text = file_path.read_text(encoding="utf-8")
        return tomlkit.parse(text)
    except (TOMLKitError, OSError, UnicodeDecodeError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{file_path} is not valid TOML: {e}",
        ) from e


def render_document(document: tomlkit.TOMLDocument) -> str:
    """Serialize *document* back to TOML text."""
    return tomlkit.dumps(document)


def service_table(document: tomlkit.TOMLDocument) -> Table:
    """Return the live ``[testbench-ai-service]`` table, creating it if absent.

    The returned table is the one inside *document*, not a copy -- callers
    mutate it in place and then render the document.
    """
    existing = document.get(CONFIG_PREFIX)
    if isinstance(existing, Table):
        return existing
    table = tomlkit.table()
    document[CONFIG_PREFIX] = table
    return table
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
pytest tests/unit/webui/test_document.py -v
```

Expected: PASS, all seven.

- [ ] **Step 6: Confirm the PyInstaller build still sees the new dependency**

`tomlkit` is a pure-Python package that PyInstaller's modulegraph picks up from the import in `document.py`, so no `.spec` change is expected. Verify the import is reachable from the entry point:

```bash
python -c "import testbench_ai_service.main; import tomlkit; print('reachable')"
grep -n "hiddenimports" testbench-ai-service.spec
```

Expected: prints `reachable`. If `hiddenimports` lists other pure-Python deps explicitly, add `"tomlkit"` there for consistency; if it does not, change nothing.

- [ ] **Step 7: Lint, type-check, commit**

```bash
ruff check . && ruff format --check . && mypy testbench_ai_service
git add pyproject.toml testbench_ai_service/webui/document.py tests/unit/webui/test_document.py
git commit -m "Add a comment-preserving config document for the console"
```

---

### Task 3: The edit overlay

The wire format. Pure dict work: no TOML, no HTTP, no filesystem — which is what makes it the cheapest place to enforce the redaction-sentinel rule and the dotted-path rules.

**Files:**
- Create: `testbench_ai_service/webui/edits.py`
- Test: `tests/unit/webui/test_edits.py`

**Interfaces:**
- Consumes: `REDACTED_SENTINEL` from `testbench_ai_service.webui.config_io`
- Produces:
  - `ConfigEdits = dict[str, object]` — dotted path to new value; `None` means "remove the key"
  - `validate_edit_paths(edits: ConfigEdits) -> None` — raises `HTTPException` 400
  - `merge_edits(base: dict, edits: ConfigEdits) -> dict` — a new dict, *base* untouched
  - `MAX_EDITS = 500`, `MAX_PATH_SEGMENTS = 8`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/webui/test_edits.py`:

```python
import pytest
from fastapi import HTTPException

from testbench_ai_service.webui.config_io import REDACTED_SENTINEL
from testbench_ai_service.webui.edits import (
    MAX_EDITS,
    merge_edits,
    validate_edit_paths,
)


def test_a_scalar_edit_sets_a_top_level_key():
    assert merge_edits({"port": 8010}, {"port": 9999}) == {"port": 9999}


def test_a_dotted_edit_sets_a_nested_key_without_disturbing_siblings():
    base = {"llm_config": {"provider": "openai", "model": "gpt-4o"}}

    merged = merge_edits(base, {"llm_config.model": "gpt-4.1"})

    assert merged == {"llm_config": {"provider": "openai", "model": "gpt-4.1"}}


def test_a_dotted_edit_creates_missing_intermediate_tables():
    assert merge_edits({}, {"logging.file.log_level": "DEBUG"}) == {
        "logging": {"file": {"log_level": "DEBUG"}}
    }


def test_a_none_value_removes_the_key():
    base = {"llm_config": {"provider": "openai", "model": "gpt-4o"}}

    merged = merge_edits(base, {"llm_config.model": None})

    assert merged == {"llm_config": {"provider": "openai"}}


def test_removing_an_absent_key_is_not_an_error():
    assert merge_edits({}, {"llm_config.model": None}) == {}


def test_the_base_dict_is_never_mutated():
    """The caller diffs against the disk config it passed in."""
    base = {"llm_config": {"provider": "openai"}}

    merge_edits(base, {"llm_config.provider": "anthropic", "port": 1})

    assert base == {"llm_config": {"provider": "openai"}}


def test_a_list_value_survives_intact():
    merged = merge_edits({}, {"trusted_proxies": ["10.0.0.1", "10.0.0.2"]})

    assert merged == {"trusted_proxies": ["10.0.0.1", "10.0.0.2"]}


def test_the_redaction_sentinel_is_refused():
    """GET /config redacts credentials; posting one back must never write it."""
    with pytest.raises(HTTPException) as exc:
        validate_edit_paths({"llm_config.api_key": REDACTED_SENTINEL})

    assert exc.value.status_code == 400
    assert "redacted" in exc.value.detail.lower()


def test_the_redaction_sentinel_is_refused_inside_a_nested_value():
    with pytest.raises(HTTPException) as exc:
        validate_edit_paths({"projects": {"P": {"llm_config": {"api_key": REDACTED_SENTINEL}}}})

    assert exc.value.status_code == 400


def test_the_redaction_sentinel_is_refused_inside_a_list():
    with pytest.raises(HTTPException) as exc:
        validate_edit_paths({"trusted_proxies": ["10.0.0.1", REDACTED_SENTINEL]})

    assert exc.value.status_code == 400


@pytest.mark.parametrize(
    "path",
    [
        "",
        " ",
        ".",
        "..",
        "port.",
        ".port",
        "llm_config..model",
        "a.b.c.d.e.f.g.h.i",
        "port\x00",
    ],
)
def test_a_malformed_path_is_refused(path: str):
    with pytest.raises(HTTPException) as exc:
        validate_edit_paths({path: 1})

    assert exc.value.status_code == 400


def test_a_well_formed_path_is_accepted():
    validate_edit_paths(
        {
            "port": 8010,
            "llm_config.model": "gpt-4o",
            "logging.file.log_level": "DEBUG",
            'projects.My Project.language': "en",
            "trusted_proxies": None,
        }
    )


def test_too_many_edits_are_refused():
    with pytest.raises(HTTPException) as exc:
        validate_edit_paths({f"key_{index}": index for index in range(MAX_EDITS + 1)})

    assert exc.value.status_code == 400
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest tests/unit/webui/test_edits.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'testbench_ai_service.webui.edits'`.

- [ ] **Step 3: Write the implementation**

Create `testbench_ai_service/webui/edits.py`:

```python
"""The console's edit overlay.

The browser does not post a whole configuration document back. It posts a
sparse map of dotted paths to new values, which the server merges into the
config it reads *fresh off disk* at preview and apply time. Three reasons:

- ``GET /config`` redacts credential-named values, so a whole-config round trip
  would write the literal string ``***REDACTED***`` into the file;
- the ``running`` snapshot is fully defaulted, so writing it back would expand a
  five-line hand-written ``config.toml`` into every default the model has;
- merging into a freshly-read disk config means a second operator's diff shows
  the first operator's changes rather than silently reverting them.

Everything here is a pure function over plain dicts. No TOML, no filesystem, no
request objects -- which is what makes it the right place to enforce the
sentinel and path rules once, for both preview and apply.
"""

from typing import Any

from fastapi import HTTPException, status

from testbench_ai_service.webui.config_io import REDACTED_SENTINEL

ConfigEdits = dict[str, Any]

# Bounds, not policy: they exist so a malformed or hostile payload cannot make
# the server walk an unbounded structure. The real config is nowhere near
# either limit -- the deepest legitimate path is
# 'projects.<name>.agents.<key>.prompt.vars.<var>' at six segments.
MAX_EDITS = 500
MAX_PATH_SEGMENTS = 8


def _reject(detail: str) -> None:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _contains_sentinel(value: Any) -> bool:
    """True if *value* holds the redaction sentinel anywhere inside it."""
    if isinstance(value, str):
        return value == REDACTED_SENTINEL
    if isinstance(value, dict):
        return any(_contains_sentinel(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_sentinel(item) for item in value)
    return False


def validate_edit_paths(edits: ConfigEdits) -> None:
    """Check every path and value in *edits* before anything acts on them.

    Raises:
        HTTPException 400: too many edits, a malformed dotted path, or a value
            that is (or contains) the redaction sentinel.
    """
    if len(edits) > MAX_EDITS:
        _reject(f"Too many edits in one request (limit {MAX_EDITS})")

    for path, value in edits.items():
        if not isinstance(path, str) or not path.strip():
            _reject("An edit path must be a non-empty string")
        if "\x00" in path:
            _reject("An edit path may not contain a NUL byte")
        segments = path.split(".")
        if len(segments) > MAX_PATH_SEGMENTS:
            _reject(f"Edit path {path!r} is nested deeper than {MAX_PATH_SEGMENTS} levels")
        if any(not segment.strip() for segment in segments):
            _reject(f"Edit path {path!r} has an empty segment")
        if _contains_sentinel(value):
            # The console shows credential-named values as REDACTED_SENTINEL.
            # Writing that string back would replace a real secret with a
            # placeholder, or plant the placeholder as a value. Neither is ever
            # what the operator meant.
            _reject(
                f"Edit path {path!r} carries the redacted placeholder. "
                "Credential values cannot be set from the console."
            )


def merge_edits(base: dict[str, Any], edits: ConfigEdits) -> dict[str, Any]:
    """Return a deep copy of *base* with *edits* applied.

    A ``None`` value removes the key, so the model default takes over again.
    Removing an absent key is a no-op, not an error: two operators can discard
    the same setting without the second one getting a 400.

    *base* is never mutated -- the caller still needs it to diff against.
    """
    merged = _deep_copy(base)
    for path, value in edits.items():
        segments = path.split(".")
        if value is None:
            _remove_at(merged, segments)
        else:
            _set_at(merged, segments, value)
    return merged


def _deep_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _deep_copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_deep_copy(item) for item in value]
    return value


def _set_at(target: dict[str, Any], segments: list[str], value: Any) -> None:
    node = target
    for segment in segments[:-1]:
        child = node.get(segment)
        if not isinstance(child, dict):
            child = {}
            node[segment] = child
        node = child
    node[segments[-1]] = _deep_copy(value)


def _remove_at(target: dict[str, Any], segments: list[str]) -> None:
    node: Any = target
    for segment in segments[:-1]:
        if not isinstance(node, dict) or segment not in node:
            return
        node = node[segment]
    if isinstance(node, dict):
        node.pop(segments[-1], None)
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
pytest tests/unit/webui/test_edits.py -v
```

Expected: PASS, all of them including the thirteen parametrized malformed paths.

- [ ] **Step 5: Check for an import cycle**

`edits.py` imports from `config_io.py`. Confirm `config_io` does not import `edits`:

```bash
python -c "from testbench_ai_service.webui import edits, config_io; print('no cycle')"
grep -n "^from\|^import" testbench_ai_service/webui/config_io.py
```

Expected: prints `no cycle`, and `config_io.py`'s imports do not mention `edits`.

- [ ] **Step 6: Lint, type-check, commit**

```bash
ruff check . && ruff format --check . && mypy testbench_ai_service
git add testbench_ai_service/webui/edits.py tests/unit/webui/test_edits.py
git commit -m "Add the console's config edit overlay"
```

---

### Task 4: Apply the overlay to the TOML document

Tasks 2 and 3 meet here: the overlay drives edits into the `tomlkit` document so the rendered file keeps its comments.

**Files:**
- Modify: `testbench_ai_service/webui/document.py`
- Test: `tests/unit/webui/test_document.py`

**Interfaces:**
- Consumes: `service_table`, `load_document`, `render_document` (Task 2); `ConfigEdits` (Task 3)
- Produces: `apply_edits(document: tomlkit.TOMLDocument, edits: ConfigEdits) -> None` — mutates *document* in place

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/webui/test_document.py`:

```python
from testbench_ai_service.webui.document import apply_edits


def test_apply_edits_changes_a_scalar_and_keeps_the_comments(config_file: Path):
    document = load_document(config_file)

    apply_edits(document, {"port": 9999})

    rendered = render_document(document)
    assert "port = 9999" in rendered
    assert "# Which TestBench we talk to." in rendered
    assert "# trailing note" in rendered


def test_apply_edits_reaches_a_nested_table(config_file: Path):
    document = load_document(config_file)

    apply_edits(document, {"llm_config.provider": "anthropic"})

    rendered = render_document(document)
    assert 'provider = "anthropic"' in rendered
    # tomlkit keeps the trailing comment attached to the value it annotated.
    assert "# trailing note" in rendered


def test_apply_edits_creates_a_missing_nested_table(config_file: Path):
    document = load_document(config_file)

    apply_edits(document, {"logging.file.log_level": "DEBUG"})

    rendered = render_document(document)
    assert "[testbench-ai-service.logging.file]" in rendered
    assert 'log_level = "DEBUG"' in rendered


def test_apply_edits_removes_a_key_on_none(config_file: Path):
    document = load_document(config_file)

    apply_edits(document, {"port": None})

    rendered = render_document(document)
    assert "port" not in rendered
    assert "# Top-of-file note the operator wrote." in rendered


def test_apply_edits_removing_an_absent_key_is_a_no_op(config_file: Path):
    document = load_document(config_file)

    apply_edits(document, {"llm_config.model": None})

    assert render_document(document) == COMMENTED


def test_apply_edits_writes_a_list_as_a_toml_array(config_file: Path):
    document = load_document(config_file)

    apply_edits(document, {"trusted_proxies": ["10.0.0.1", "10.0.0.2"]})

    rendered = render_document(document)
    assert 'trusted_proxies = ["10.0.0.1", "10.0.0.2"]' in rendered


def test_apply_edits_writes_a_project_name_that_needs_quoting(tmp_path: Path):
    """Project keys are TestBench project names: spaces, dots, anything."""
    path = tmp_path / "config.toml"
    path.write_text("[testbench-ai-service]\nport = 8010\n", encoding="utf-8")
    document = load_document(path)

    apply_edits(document, {'projects.My Project.language': "en"})

    rendered = render_document(document)
    assert 'language = "en"' in rendered
    # Re-parsing is the real assertion: the key must round-trip, however
    # tomlkit chose to quote it.
    reparsed = tomlkit.parse(rendered)
    assert reparsed["testbench-ai-service"]["projects"]["My Project"]["language"] == "en"


def test_apply_edits_is_idempotent(config_file: Path):
    first = load_document(config_file)
    apply_edits(first, {"port": 9999})
    once = render_document(first)

    second = load_document(config_file)
    apply_edits(second, {"port": 9999})
    apply_edits(second, {"port": 9999})

    assert render_document(second) == once


def test_apply_edits_result_reparses_to_the_merged_dict(config_file: Path):
    """The document path and the dict path must agree."""
    from testbench_ai_service.webui.config_io import read_config_file
    from testbench_ai_service.webui.edits import merge_edits

    edits = {"port": 9999, "llm_config.model": "gpt-4.1", "logging.file.log_level": "DEBUG"}

    document = load_document(config_file)
    apply_edits(document, edits)
    from_document = tomlkit.parse(render_document(document))["testbench-ai-service"]

    from_dict = merge_edits(read_config_file(config_file), edits)

    assert dict(from_document) == from_dict
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest tests/unit/webui/test_document.py -k apply_edits -v
```

Expected: FAIL — `ImportError: cannot import name 'apply_edits'`.

- [ ] **Step 3: Write the implementation**

Append to `testbench_ai_service/webui/document.py` (and add `from typing import Any` plus `from testbench_ai_service.webui.edits import ConfigEdits` to its imports):

```python
def apply_edits(document: tomlkit.TOMLDocument, edits: ConfigEdits) -> None:
    """Drive *edits* into *document* in place, under ``[testbench-ai-service]``.

    A ``None`` value removes the key so the model default takes over again;
    removing an absent key is a no-op. Intermediate tables are created as
    needed. Editing an existing value replaces the value alone, which is what
    keeps its comment attached.

    The paths in *edits* must already have been through
    :func:`~testbench_ai_service.webui.edits.validate_edit_paths`.
    """
    root = service_table(document)
    for path, value in edits.items():
        segments = path.split(".")
        if value is None:
            _remove_key(root, segments)
        else:
            _set_key(root, segments, value)


def _child_table(node: Any, key: str) -> Any:
    """Return *node*'s child table at *key*, creating a real table if needed."""
    child = node.get(key)
    # An existing inline table or dict is edited in place; anything else
    # (a scalar left over from an older config, or nothing at all) is replaced
    # by a fresh table, because a scalar has no sub-keys to set.
    if isinstance(child, (Table, InlineTable, dict)):
        return child
    child = tomlkit.table()
    node[key] = child
    return child


def _set_key(root: Any, segments: list[str], value: Any) -> None:
    node = root
    for segment in segments[:-1]:
        node = _child_table(node, segment)
    node[segments[-1]] = _toml_value(value)


def _remove_key(root: Any, segments: list[str]) -> None:
    node: Any = root
    for segment in segments[:-1]:
        child = node.get(segment) if hasattr(node, "get") else None
        if child is None:
            return
        node = child
    if hasattr(node, "get") and segments[-1] in node:
        del node[segments[-1]]


def _toml_value(value: Any) -> Any:
    """Convert a JSON-decoded value into a tomlkit item.

    ``tomlkit.item()`` handles scalars, lists and dicts. ``Path`` reaches here
    from nothing the browser sends, but a caller reusing this module with a
    pydantic dump would otherwise get an unserializable object, so it is
    stringified rather than left to fail at render time.
    """
    if isinstance(value, Path):
        return tomlkit.item(str(value))
    return tomlkit.item(value)
```

Extend the import line for tomlkit items:

```python
from tomlkit.items import InlineTable, Table
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
pytest tests/unit/webui/test_document.py -v
```

Expected: PASS, all sixteen. `test_apply_edits_result_reparses_to_the_merged_dict` is the important one — it pins the document path and the dict path to the same semantics, which is what lets Task 6 validate the dict and Task 12 write the document without them drifting apart.

- [ ] **Step 5: Lint, type-check, commit**

```bash
ruff check . && ruff format --check . && mypy testbench_ai_service
git add testbench_ai_service/webui/document.py tests/unit/webui/test_document.py
git commit -m "Apply console edits to the config document"
```

---

### Task 5: Atomic write with a `.bak`

Spec 6.4. A half-written `config.toml` is a service that will not restart. Serialize to a temp file in the *same* directory (so `os.replace` stays on one filesystem and is therefore atomic), keep the previous contents as `.bak`, then replace.

**Files:**
- Create: `testbench_ai_service/webui/atomic.py`
- Test: `tests/unit/webui/test_atomic.py`

**Interfaces:**
- Consumes: nothing
- Produces: `write_atomic(path: Path, text: str) -> Path | None` — returns the `.bak` path it wrote, or `None` when there was no previous file

- [ ] **Step 1: Write the failing test**

Create `tests/unit/webui/test_atomic.py`:

```python
import os
from pathlib import Path

import pytest
from fastapi import HTTPException

from testbench_ai_service.webui.atomic import write_atomic


def test_writing_a_new_file_creates_it_and_reports_no_backup(tmp_path: Path):
    target = tmp_path / "config.toml"

    backup = write_atomic(target, "port = 8010\n")

    assert backup is None
    assert target.read_text(encoding="utf-8") == "port = 8010\n"


def test_overwriting_keeps_the_previous_contents_as_bak(tmp_path: Path):
    target = tmp_path / "config.toml"
    target.write_text("port = 1\n", encoding="utf-8")

    backup = write_atomic(target, "port = 2\n")

    assert backup == tmp_path / "config.toml.bak"
    assert backup.read_text(encoding="utf-8") == "port = 1\n"
    assert target.read_text(encoding="utf-8") == "port = 2\n"


def test_a_second_write_replaces_the_bak_rather_than_stacking_them(tmp_path: Path):
    target = tmp_path / "config.toml"
    target.write_text("port = 1\n", encoding="utf-8")

    write_atomic(target, "port = 2\n")
    write_atomic(target, "port = 3\n")

    assert (tmp_path / "config.toml.bak").read_text(encoding="utf-8") == "port = 2\n"
    assert not (tmp_path / "config.toml.bak.bak").exists()
    assert target.read_text(encoding="utf-8") == "port = 3\n"


def test_no_temp_files_are_left_behind(tmp_path: Path):
    target = tmp_path / "config.toml"
    target.write_text("port = 1\n", encoding="utf-8")

    write_atomic(target, "port = 2\n")

    assert sorted(entry.name for entry in tmp_path.iterdir()) == [
        "config.toml",
        "config.toml.bak",
    ]


def test_the_temp_file_lands_in_the_target_directory(tmp_path: Path, monkeypatch):
    """os.replace is only atomic within one filesystem, so the temp file must
    be a sibling of the target -- never in the system temp dir."""
    import tempfile as tempfile_module

    target = tmp_path / "config.toml"
    seen: list[str] = []
    real_mkstemp = tempfile_module.mkstemp

    def spy(*args, **kwargs):
        seen.append(str(kwargs.get("dir")))
        return real_mkstemp(*args, **kwargs)

    monkeypatch.setattr("testbench_ai_service.webui.atomic.tempfile.mkstemp", spy)
    write_atomic(target, "port = 8010\n")

    assert seen == [str(tmp_path)]


def test_utf8_content_round_trips(tmp_path: Path):
    target = tmp_path / "config.toml"

    write_atomic(target, 'note = "Pruefstand — groesser"\n')

    assert target.read_text(encoding="utf-8") == 'note = "Pruefstand — groesser"\n'


def test_the_file_is_written_with_lf_only(tmp_path: Path):
    """A CRLF-translating write would change every line of the diff on Windows."""
    target = tmp_path / "config.toml"

    write_atomic(target, "a = 1\nb = 2\n")

    assert target.read_bytes() == b"a = 1\nb = 2\n"


def test_a_missing_parent_directory_is_a_400(tmp_path: Path):
    target = tmp_path / "nope" / "config.toml"

    with pytest.raises(HTTPException) as exc:
        write_atomic(target, "port = 8010\n")

    assert exc.value.status_code == 400


def test_a_failed_replace_leaves_the_original_intact_and_no_temp_file(tmp_path: Path, monkeypatch):
    target = tmp_path / "config.toml"
    target.write_text("port = 1\n", encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", boom)

    with pytest.raises(HTTPException):
        write_atomic(target, "port = 2\n")

    assert target.read_text(encoding="utf-8") == "port = 1\n"
    assert [entry.name for entry in tmp_path.iterdir()] == ["config.toml"]
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest tests/unit/webui/test_atomic.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'testbench_ai_service.webui.atomic'`.

- [ ] **Step 3: Write the implementation**

Create `testbench_ai_service/webui/atomic.py`:

```python
"""Atomic file replacement for the console's writes.

A half-written ``config.toml`` is a service that will not start again. Every
console write therefore goes to a temp file in the *target's own directory*
-- ``os.replace`` is only atomic within a single filesystem, so a system temp
dir would silently give up the guarantee -- and the previous contents are kept
alongside as ``.bak`` before the replace.
"""

import os
import tempfile
from pathlib import Path

from fastapi import HTTPException, status

from testbench_ai_service.log import logger


def write_atomic(path: Path, text: str) -> Path | None:
    """Replace *path*'s contents with *text* atomically.

    The previous contents, if any, are copied to ``<path>.bak`` first. The
    backup is overwritten on each write rather than rotated: it exists so an
    operator can undo the last console save, not as a history.

    Returns:
        The backup path, or ``None`` when *path* did not exist.

    Raises:
        HTTPException 400: the directory does not exist, or the write, backup
            or replace failed (a permissions problem, a full disk, a file held
            open by another process on Windows).
    """
    target = Path(path)
    directory = target.parent
    if not directory.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot write {target}: {directory} is not a directory",
        )

    backup: Path | None = None
    handle: int | None = None
    temp_path: Path | None = None
    try:
        handle, temp_name = tempfile.mkstemp(
            dir=str(directory), prefix=f".{target.name}.", suffix=".tmp"
        )
        temp_path = Path(temp_name)
        # newline="" keeps the text exactly as rendered: on Windows the default
        # would translate every "\n" to "\r\n", which changes every line of the
        # next diff and rewrites the whole file on a one-key edit.
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as file:
            handle = None  # fdopen owns the descriptor now
            file.write(text)
            file.flush()
            os.fsync(file.fileno())

        if target.exists():
            backup = target.with_name(f"{target.name}.bak")
            backup.write_bytes(target.read_bytes())

        os.replace(temp_path, target)
        temp_path = None
    except OSError as e:
        logger.error("Atomic write to %s failed: %s", target, e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot write {target}: {e}",
        ) from e
    finally:
        if handle is not None:
            os.close(handle)
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)

    logger.info("Wrote %s (backup: %s)", target, backup)
    return backup
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
pytest tests/unit/webui/test_atomic.py -v
```

Expected: PASS, all nine. If `test_the_temp_file_lands_in_the_target_directory` fails on the monkeypatch target, confirm the module does `import tempfile` rather than `from tempfile import mkstemp` — the test patches the attribute on the module object.

- [ ] **Step 5: Lint, type-check, commit**

```bash
ruff check . && ruff format --check . && mypy testbench_ai_service
git add testbench_ai_service/webui/atomic.py tests/unit/webui/test_atomic.py
git commit -m "Write console config changes atomically"
```

---

### Task 6: Validate a merged config into field-addressed issues

Spec 6.3. The console must be incapable of writing a config the service could not boot with, and when it refuses it must say *which field*. `AppConfig` is the same model the service boots with, so constructing it is the validation.

**Files:**
- Create: `testbench_ai_service/webui/validate.py`
- Modify: `testbench_ai_service/webui/models.py`
- Test: `tests/unit/webui/test_validate.py`

**Interfaces:**
- Consumes: `AppConfig`, `CONFIG_PREFIX`
- Produces:
  - `ConfigIssue` pydantic model with `path: str`, `message: str`, `toml_section: str`
  - `validate_config_dict(data: dict) -> tuple[AppConfig | None, list[ConfigIssue]]` — the model on success, the issues on failure; never both

- [ ] **Step 1: Add the response model**

Append to `testbench_ai_service/webui/models.py`:

```python
class ConfigIssue(BaseModel):
    """One validation failure, addressed to the field that caused it.

    ``path`` is the dotted config path the console's form fields are keyed by,
    so the UI can mark the offending input. ``toml_section`` is the same
    location spelled the way it appears in ``config.toml``, for the operator
    who would rather fix the file by hand.
    """

    path: str
    message: str
    toml_section: str
```

- [ ] **Step 2: Write the failing test**

Create `tests/unit/webui/test_validate.py`:

```python
from unittest.mock import patch

import pytest

from testbench_ai_service.webui.validate import validate_config_dict

TB_URL = "https://localhost:9443/api/"


@pytest.fixture(autouse=True)
def no_url_probe():
    """validate_tb_server_url is about the URL's shape, not this module's job."""
    with patch("testbench_ai_service.config.validate_tb_server_url"):
        yield


def test_a_valid_config_returns_a_model_and_no_issues():
    config, issues = validate_config_dict({"tb_server_url": TB_URL, "port": 8010})

    assert issues == []
    assert config is not None
    assert config.port == 8010


def test_an_empty_config_is_valid_because_the_service_runs_on_defaults():
    config, issues = validate_config_dict({})

    assert issues == []
    assert config is not None


def test_a_wrong_type_is_addressed_to_the_field():
    _, issues = validate_config_dict({"tb_server_url": TB_URL, "port": "not a number"})

    assert len(issues) == 1
    assert issues[0].path == "port"
    assert issues[0].toml_section == "[testbench-ai-service]"
    assert issues[0].message


def test_no_model_is_returned_when_there_are_issues():
    config, issues = validate_config_dict({"port": "not a number"})

    assert config is None
    assert issues


def test_a_nested_failure_is_addressed_to_its_dotted_path():
    _, issues = validate_config_dict(
        {"tb_server_url": TB_URL, "logging": {"file": {"log_level": "LOUD"}}}
    )

    assert [issue.path for issue in issues] == ["logging.file.log_level"]
    assert issues[0].toml_section == "[testbench-ai-service.logging.file]"


def test_an_out_of_range_number_is_reported():
    _, issues = validate_config_dict({"tb_server_url": TB_URL, "tb_max_retries": -1})

    assert [issue.path for issue in issues] == ["tb_max_retries"]


def test_a_missing_ssl_file_is_reported_against_its_field():
    _, issues = validate_config_dict(
        {"tb_server_url": TB_URL, "ssl_cert": "/definitely/not/here.pem"}
    )

    assert [issue.path for issue in issues] == ["ssl_cert"]
    assert "not found" in issues[0].message


def test_every_failure_is_reported_not_just_the_first():
    _, issues = validate_config_dict({"port": "nope", "tb_max_retries": -1})

    assert {issue.path for issue in issues} == {"port", "tb_max_retries"}


def test_an_agent_failure_is_reported_rather_than_raising():
    _, issues = validate_config_dict(
        {
            "tb_server_url": TB_URL,
            "agents": {
                "test_case_set_reviewer": {
                    "enabled": True,
                    "endpoint_path": "/x",
                    "class_path": "nonexistent.module.Class",
                    "prompt": {"file": "test_case_set_reviewer/prompt.yaml"},
                }
            },
        }
    )

    assert issues


def test_a_non_dict_where_a_table_belongs_is_reported():
    _, issues = validate_config_dict({"llm_config": "not a table"})

    assert issues
    assert issues[0].path.startswith("llm_config")


def test_an_unexpected_error_becomes_a_root_issue():
    """A model validator can raise something that is not a ValidationError."""
    with patch(
        "testbench_ai_service.webui.validate.AppConfig",
        side_effect=RuntimeError("kaboom"),
    ):
        config, issues = validate_config_dict({})

    assert config is None
    assert len(issues) == 1
    assert issues[0].path == ""
    assert "kaboom" in issues[0].message
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
pytest tests/unit/webui/test_validate.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'testbench_ai_service.webui.validate'`.

- [ ] **Step 4: Write the implementation**

Create `testbench_ai_service/webui/validate.py`:

```python
"""Validating a candidate configuration before anything is written.

The console must be incapable of writing a ``config.toml`` the service could
not boot with, so validation *is* constructing the very model the service boots
with -- ``AppConfig``. That gets the whole existing rule set for free: the URL
shape, the SSL files existing, agent class paths importing, prompt files
resolving, the Entra-ID-implies-Azure invariant.

Failures come back addressed to a field so the UI can mark the offending
input, in both the dotted spelling the console's forms use and the
``[section]`` spelling ``config.toml`` uses.
"""

from typing import Any

from pydantic import ValidationError

from testbench_ai_service.config import AppConfig
from testbench_ai_service.log import logger
from testbench_ai_service.utils.config import CONFIG_PREFIX
from testbench_ai_service.webui.models import ConfigIssue


def _toml_section(location: tuple[Any, ...]) -> str:
    """Spell a pydantic error location as the TOML section it lives in.

    The last element of a location is the key itself, so the section is
    everything before it. Integer elements (list indices) are dropped: TOML has
    no section for the third element of an array.
    """
    parts = [str(part) for part in location[:-1] if not isinstance(part, int)]
    return f"[{'.'.join([CONFIG_PREFIX, *parts])}]"


def _issue_path(location: tuple[Any, ...]) -> str:
    return ".".join(str(part) for part in location)


def validate_config_dict(data: dict[str, Any]) -> tuple[AppConfig | None, list[ConfigIssue]]:
    """Construct :class:`AppConfig` from *data*.

    Returns:
        ``(config, [])`` when *data* is a configuration the service could boot
        with, or ``(None, issues)`` when it is not. Never both.
    """
    try:
        return AppConfig(**data), []
    except ValidationError as e:
        issues = [
            ConfigIssue(
                path=_issue_path(error["loc"]),
                message=str(error.get("msg", "Invalid value")),
                toml_section=_toml_section(error["loc"]),
            )
            for error in e.errors()
        ]
        logger.info("Rejected a console config draft with %d issue(s)", len(issues))
        return None, issues
    except Exception as e:
        # AppConfig's model validators reach into the import system (agent
        # class paths) and the filesystem (prompt files). A failure there can
        # surface as something other than a ValidationError, and a 500 would
        # tell the operator nothing, so it becomes a root-addressed issue.
        logger.exception("Unexpected failure validating a console config draft")
        return None, [ConfigIssue(path="", message=str(e), toml_section=f"[{CONFIG_PREFIX}]")]
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
pytest tests/unit/webui/test_validate.py -v
```

Expected: PASS, all eleven. `test_a_missing_ssl_file_is_reported_against_its_field` asserts the substring `not found`, which is what `AppConfig.validate_ssl_files_exist` emits — if the message has since changed, match the real one rather than loosening the assertion away.

- [ ] **Step 6: Check ruff's opinion of the broad except**

```bash
ruff check testbench_ai_service/webui/validate.py
```

Expected: clean. If ruff flags the bare `except Exception` (rule `BLE001`), add `# noqa: BLE001` on that line with the comment already there explaining why it is deliberate.

- [ ] **Step 7: Lint, type-check, commit**

```bash
ruff check . && ruff format --check . && mypy testbench_ai_service
git add testbench_ai_service/webui/validate.py testbench_ai_service/webui/models.py tests/unit/webui/test_validate.py
git commit -m "Validate console config drafts into field-addressed issues"
```

---

### Task 7: Unified diff of the rendered file against disk

Spec 6.1 / 8. The diff is what the operator approves. It is computed against the file *as it is on disk right now*, so a second operator sees the first one's changes rather than silently reverting them.

**Files:**
- Create: `testbench_ai_service/webui/diff.py`
- Modify: `testbench_ai_service/webui/models.py`
- Test: `tests/unit/webui/test_diff.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `FileDiff` pydantic model with `path: str`, `diff: str`, `added: int`, `removed: int`
  - `file_diff(path: str, current: str, proposed: str) -> FileDiff | None` — `None` when the texts are identical

- [ ] **Step 1: Add the response model**

Append to `testbench_ai_service/webui/models.py`:

```python
class FileDiff(BaseModel):
    """A unified diff for one file the console proposes to write."""

    path: str
    diff: str
    added: int
    removed: int
```

- [ ] **Step 2: Write the failing test**

Create `tests/unit/webui/test_diff.py`:

```python
from testbench_ai_service.webui.diff import file_diff


def test_identical_text_yields_no_diff():
    assert file_diff("config.toml", "a = 1\n", "a = 1\n") is None


def test_a_changed_line_is_reported_as_one_added_and_one_removed():
    result = file_diff("config.toml", "port = 8010\n", "port = 9999\n")

    assert result is not None
    assert result.path == "config.toml"
    assert result.added == 1
    assert result.removed == 1
    assert "-port = 8010" in result.diff
    assert "+port = 9999" in result.diff


def test_an_added_line_is_reported_as_added_only():
    result = file_diff("config.toml", "a = 1\n", "a = 1\nb = 2\n")

    assert result is not None
    assert (result.added, result.removed) == (1, 0)
    assert "+b = 2" in result.diff


def test_a_removed_line_is_reported_as_removed_only():
    result = file_diff("config.toml", "a = 1\nb = 2\n", "a = 1\n")

    assert result is not None
    assert (result.added, result.removed) == (0, 1)
    assert "-b = 2" in result.diff


def test_a_new_file_diffs_against_empty_text():
    result = file_diff("config.toml", "", "port = 8010\n")

    assert result is not None
    assert (result.added, result.removed) == (1, 0)


def test_the_diff_carries_the_path_in_its_headers():
    result = file_diff("config.toml", "a = 1\n", "a = 2\n")

    assert result is not None
    assert result.diff.startswith("--- config.toml")
    assert "+++ config.toml" in result.diff


def test_the_file_header_markers_are_not_counted_as_changes():
    """'--- a' and '+++ b' start with the same characters as real changes."""
    result = file_diff("config.toml", "a = 1\n", "a = 2\n")

    assert result is not None
    assert (result.added, result.removed) == (1, 1)


def test_context_lines_are_included_around_a_change():
    current = "".join(f"key_{index} = {index}\n" for index in range(20))
    proposed = current.replace("key_10 = 10", "key_10 = 999")

    result = file_diff("config.toml", current, proposed)

    assert result is not None
    assert "key_8 = 8" in result.diff
    assert "key_12 = 12" in result.diff
    # Not the whole file: a 20-line file with one change must not diff as 20.
    assert "key_0 = 0" not in result.diff


def test_utf8_content_diffs_without_mangling():
    result = file_diff("config.toml", 'note = "a"\n', 'note = "Pruefstand"\n')

    assert result is not None
    assert "Pruefstand" in result.diff


def test_a_trailing_newline_difference_is_a_real_diff():
    result = file_diff("config.toml", "a = 1", "a = 1\n")

    assert result is not None
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
pytest tests/unit/webui/test_diff.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'testbench_ai_service.webui.diff'`.

- [ ] **Step 4: Write the implementation**

Create `testbench_ai_service/webui/diff.py`:

```python
"""Unified diffs for the console's apply dialog.

The diff is what the operator actually approves, so it is computed against the
file as it is on disk at that moment -- not against whatever the browser
happened to load earlier. Two operators editing at once therefore see each
other's changes in the diff instead of silently reverting them.
"""

import difflib

from testbench_ai_service.webui.models import FileDiff

# Enough context to recognise which part of the file a change lands in, without
# turning a one-key edit into a diff of the whole file.
CONTEXT_LINES = 3


def file_diff(path: str, current: str, proposed: str) -> FileDiff | None:
    """Diff *current* against *proposed*.

    Returns:
        A :class:`FileDiff`, or ``None`` when the two texts are identical --
        which is how the caller decides a file needs no write at all.
    """
    if current == proposed:
        return None

    lines = list(
        difflib.unified_diff(
            current.splitlines(keepends=True),
            proposed.splitlines(keepends=True),
            fromfile=path,
            tofile=path,
            n=CONTEXT_LINES,
        )
    )

    # The first two lines are the '---'/'+++' file headers, which start with the
    # same characters as real changes. Counting skips them by position rather
    # than by a longer prefix test: a genuine removed line reading '--- note'
    # is perfectly possible in a commented TOML file.
    body = lines[2:]
    added = sum(1 for line in body if line.startswith("+"))
    removed = sum(1 for line in body if line.startswith("-"))

    return FileDiff(path=path, diff="".join(lines), added=added, removed=removed)
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
pytest tests/unit/webui/test_diff.py -v
```

Expected: PASS, all ten.

- [ ] **Step 6: Lint, type-check, commit**

```bash
ruff check . && ruff format --check . && mypy testbench_ai_service
git add testbench_ai_service/webui/diff.py testbench_ai_service/webui/models.py tests/unit/webui/test_diff.py
git commit -m "Add unified diffs for the console apply dialog"
```

---

### Task 8: Classify which changes need a restart

Spec 7. A live swap covers most of the config. It cannot cover anything uvicorn or the middleware stack fixed at boot, and it cannot cover the agent routers, which `init_routers()` registers exactly once at startup. Those changes get written and then raise the "restart needed" banner.

**Files:**
- Create: `testbench_ai_service/webui/reload.py`
- Test: `tests/unit/webui/test_reload.py`

**Interfaces:**
- Consumes: `AppConfig`
- Produces:
  - `RESTART_FIELDS: tuple[str, ...]` — the boot-fixed top-level fields
  - `restart_required(old: AppConfig, new: AppConfig) -> list[str]` — dotted paths of changes a live swap cannot cover, sorted, empty when there are none

- [ ] **Step 1: Write the failing test**

Create `tests/unit/webui/test_reload.py`:

```python
from pathlib import Path
from unittest.mock import patch

import pytest

from testbench_ai_service.config import AppConfig
from testbench_ai_service.models.config import AgentConfig, PromptConfig
from testbench_ai_service.webui.reload import restart_required

TB_URL = "https://localhost:9443/api/"


@pytest.fixture(autouse=True)
def no_url_probe():
    with patch("testbench_ai_service.config.validate_tb_server_url"):
        yield


def make_config(**kwargs) -> AppConfig:
    return AppConfig(tb_server_url=TB_URL, **kwargs)


def agent(endpoint_path="/reviews", class_path=None, enabled=True) -> AgentConfig:
    return AgentConfig(
        enabled=enabled,
        endpoint_path=endpoint_path,
        class_path=class_path
        or "testbench_ai_service.agents.test_case_set_reviewer.agent.TestCaseSetReviewer",
        prompt=PromptConfig(file=Path("test_case_set_reviewer/prompt.yaml")),
    )


def test_an_unchanged_config_needs_no_restart():
    assert restart_required(make_config(), make_config()) == []


def test_a_hot_swappable_change_needs_no_restart():
    """language, llm_config and logging are all re-applied in process."""
    old = make_config(language="de")
    new = make_config(language="en")

    assert restart_required(old, new) == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("host", "0.0.0.0"),
        ("port", 9999),
        ("trusted_proxies", ["10.0.0.1"]),
    ],
)
def test_a_boot_fixed_field_needs_a_restart(field: str, value):
    new = make_config(**{field: value})

    assert restart_required(make_config(), new) == [field]


def test_a_tls_change_needs_a_restart(tmp_path: Path):
    """ssl_cert/ssl_key/ssl_ca_cert are handed to uvicorn at boot."""
    cert = tmp_path / "cert.pem"
    cert.write_text("x", encoding="utf-8")

    new = make_config(ssl_cert=str(cert))

    assert restart_required(make_config(), new) == ["ssl_cert"]


def test_several_boot_fixed_changes_are_all_reported_and_sorted():
    new = make_config(host="0.0.0.0", port=9999)

    assert restart_required(make_config(), new) == ["host", "port"]


def test_a_changed_agent_endpoint_path_needs_a_restart():
    """init_routers registers the agent routers once, at startup."""
    old = make_config(agents={"reviewer": agent(endpoint_path="/a")})
    new = make_config(agents={"reviewer": agent(endpoint_path="/b")})

    assert restart_required(old, new) == ["agents.reviewer.endpoint_path"]


def test_a_changed_agent_class_path_needs_a_restart():
    old = make_config(agents={"reviewer": agent()})
    new = make_config(
        agents={
            "reviewer": agent(
                class_path="testbench_ai_service.agents.defect_explainer.agent.DefectExplainer"
            )
        }
    )

    assert restart_required(old, new) == ["agents.reviewer.class_path"]


def test_toggling_an_agent_enabled_flag_does_not_need_a_restart():
    """The router exists either way; 'enabled' is checked per request."""
    old = make_config(agents={"reviewer": agent(enabled=True)})
    new = make_config(agents={"reviewer": agent(enabled=False)})

    assert restart_required(old, new) == []


def test_a_new_agent_needs_a_restart():
    old = make_config(agents={"reviewer": agent()})
    new = make_config(
        agents={
            "reviewer": agent(),
            "explainer": AgentConfig(
                enabled=True,
                endpoint_path="/defect-explanations",
                class_path="testbench_ai_service.agents.defect_explainer.agent.DefectExplainer",
                prompt=PromptConfig(file=Path("defect_explainer/prompt.yaml")),
            ),
        }
    )

    assert restart_required(old, new) == ["agents.explainer"]


def test_a_removed_agent_needs_a_restart():
    old = make_config(agents={"reviewer": agent()})
    new = make_config(agents={})

    assert restart_required(old, new) == ["agents.reviewer"]


def test_changing_an_agent_prompt_file_does_not_need_a_restart():
    """The prompt is resolved per request, not baked into the router."""
    old = make_config(agents={"reviewer": agent()})
    changed = agent()
    changed.prompt = PromptConfig(file=Path("test_case_set_reviewer/prompt.yaml"), variant="quick")
    new = make_config(agents={"reviewer": changed})

    assert restart_required(old, new) == []
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest tests/unit/webui/test_reload.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'testbench_ai_service.webui.reload'`.

- [ ] **Step 3: Write the implementation**

Create `testbench_ai_service/webui/reload.py`:

```python
"""Hot reload, and what a hot reload cannot cover.

Most of the configuration can be swapped in a running process: every request
reads ``app.state.config`` through ``get_app_config``, the LLM clients can be
closed and rebuilt, translations and logging can be re-applied.

Two things cannot:

- ``host``, ``port``, the three TLS paths and ``trusted_proxies`` are handed to
  uvicorn and the middleware stack at boot and are never consulted again;
- an agent's ``endpoint_path`` and ``class_path`` are consumed by
  ``init_routers()`` exactly once, at startup, so adding, removing, moving or
  re-classing an agent cannot change the live routing table.

Those changes are still written to disk. They just raise the console's
"restart needed" banner rather than pretending to take effect. There is no
self-restart button: re-execing only works under a supervisor and would kill a
bare terminal process outright (spec 7).
"""

from testbench_ai_service.config import AppConfig

# Fixed at boot by uvicorn or by the middleware stack.
RESTART_FIELDS: tuple[str, ...] = (
    "host",
    "port",
    "ssl_cert",
    "ssl_key",
    "ssl_ca_cert",
    "trusted_proxies",
)

# Consumed once by init_routers(); a change cannot reach the live router table.
RESTART_AGENT_FIELDS: tuple[str, ...] = ("endpoint_path", "class_path")


def restart_required(old: AppConfig, new: AppConfig) -> list[str]:
    """Dotted paths of changes between *old* and *new* that a live swap cannot cover.

    An empty list means the whole change set can be applied in process.
    """
    changed: list[str] = []

    for field in RESTART_FIELDS:
        if getattr(old, field) != getattr(new, field):
            changed.append(field)

    old_keys = set(old.agents)
    new_keys = set(new.agents)
    # An added or removed agent is reported as the agent itself rather than as
    # its fields: there is no old (or new) value to name, and the operator's
    # takeaway is the same either way.
    changed.extend(f"agents.{key}" for key in old_keys ^ new_keys)

    for key in sorted(old_keys & new_keys):
        for field in RESTART_AGENT_FIELDS:
            if getattr(old.agents[key], field) != getattr(new.agents[key], field):
                changed.append(f"agents.{key}.{field}")

    return sorted(changed)
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
pytest tests/unit/webui/test_reload.py -v
```

Expected: PASS, all fourteen (three of them parametrized).

- [ ] **Step 5: Lint, type-check, commit**

```bash
ruff check . && ruff format --check . && mypy testbench_ai_service
git add testbench_ai_service/webui/reload.py tests/unit/webui/test_reload.py
git commit -m "Classify which config changes need a service restart"
```

---

### Task 9: The in-flight agent task registry

Spec 7.1. Agent executions run as untracked FastAPI `BackgroundTasks`, so today there is nothing to wait on before a reload. A tiny registry lets apply report how many runs are in flight, so the operator can decide whether to reload now or wait.

**Files:**
- Create: `testbench_ai_service/webui/inflight.py`
- Modify: `testbench_ai_service/main.py`, `testbench_ai_service/agents/routes.py`
- Modify: `testbench_ai_service/webui/models.py`, `testbench_ai_service/webui/status.py`, `testbench_ai_service/webui/routes.py`
- Test: `tests/unit/webui/test_inflight.py`, `tests/unit/webui/test_status.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `TaskRegistry` with `count: int`, `track(label: str)` (an async context manager), and `labels() -> list[str]`
  - `get_task_registry(request: Request) -> TaskRegistry` — reads `app.state.task_registry`
  - `StatusResponse.in_flight_tasks: int`

- [ ] **Step 1: See how the agent background task is dispatched today**

```bash
grep -n "BackgroundTasks\|add_task\|run_agent" testbench_ai_service/agents/routes.py
```

Expected: an `add_task(run_agent, ...)` call. Note the exact argument list — Step 5 wraps this call and must pass the same arguments through.

- [ ] **Step 2: Write the failing test**

Create `tests/unit/webui/test_inflight.py`:

```python
import asyncio

import pytest

from testbench_ai_service.webui.inflight import TaskRegistry


async def test_a_fresh_registry_is_empty():
    registry = TaskRegistry()

    assert registry.count == 0
    assert registry.labels() == []


async def test_a_tracked_task_is_counted_while_it_runs():
    registry = TaskRegistry()
    inside = asyncio.Event()
    release = asyncio.Event()

    async def work():
        async with registry.track("reviewer"):
            inside.set()
            await release.wait()

    task = asyncio.create_task(work())
    await inside.wait()

    assert registry.count == 1
    assert registry.labels() == ["reviewer"]

    release.set()
    await task

    assert registry.count == 0
    assert registry.labels() == []


async def test_concurrent_tasks_are_counted_independently():
    registry = TaskRegistry()
    release = asyncio.Event()

    async def work(label: str):
        async with registry.track(label):
            await release.wait()

    tasks = [asyncio.create_task(work(f"agent_{index}")) for index in range(3)]
    await asyncio.sleep(0)  # let them enter the context manager

    assert registry.count == 3
    assert sorted(registry.labels()) == ["agent_0", "agent_1", "agent_2"]

    release.set()
    await asyncio.gather(*tasks)

    assert registry.count == 0


async def test_a_failing_task_still_decrements():
    """A leaked count would make the restart banner permanent."""
    registry = TaskRegistry()

    with pytest.raises(RuntimeError):
        async with registry.track("reviewer"):
            raise RuntimeError("agent blew up")

    assert registry.count == 0


async def test_the_same_label_twice_is_counted_twice():
    registry = TaskRegistry()
    release = asyncio.Event()

    async def work():
        async with registry.track("reviewer"):
            await release.wait()

    tasks = [asyncio.create_task(work()) for _ in range(2)]
    await asyncio.sleep(0)

    assert registry.count == 2
    assert registry.labels() == ["reviewer", "reviewer"]

    release.set()
    await asyncio.gather(*tasks)
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
pytest tests/unit/webui/test_inflight.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'testbench_ai_service.webui.inflight'`.

- [ ] **Step 4: Write the implementation**

Create `testbench_ai_service/webui/inflight.py`:

```python
"""How many agent runs are in flight.

Agent executions are dispatched as FastAPI background tasks, which the
framework does not track. Before the console reloads the configuration under a
running service, the operator deserves to know whether anything is mid-flight
-- a reload that swaps the LLM clients out from under a running agent is
recoverable, but it is not a surprise anyone wants.

The registry is deliberately a counter with labels, not a task manager: it
never cancels, joins or owns anything. Being wrong about the count is the worst
it can do, and the ``finally`` in :meth:`TaskRegistry.track` is what keeps even
that from happening.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Request


class TaskRegistry:
    """A count of the agent runs currently executing in this process."""

    def __init__(self) -> None:
        self._labels: list[str] = []

    @property
    def count(self) -> int:
        return len(self._labels)

    def labels(self) -> list[str]:
        """The agent key of each in-flight run, in the order they started.

        Duplicates are real: two concurrent runs of the same agent are two
        entries.
        """
        return list(self._labels)

    @asynccontextmanager
    async def track(self, label: str) -> AsyncIterator[None]:
        """Count one run of *label* for the duration of the block.

        The decrement is in a ``finally``: an agent that raises must not leave
        a phantom count behind, or the console would report an in-flight task
        forever.
        """
        self._labels.append(label)
        try:
            yield
        finally:
            # remove(), not pop(): concurrent runs finish out of order.
            self._labels.remove(label)


def get_task_registry(request: Request) -> TaskRegistry:
    """FastAPI dependency: the process's task registry."""
    registry: TaskRegistry = request.app.state.task_registry
    return registry
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
pytest tests/unit/webui/test_inflight.py -v
```

Expected: PASS, all five.

- [ ] **Step 6: Create the registry on app state**

In `testbench_ai_service/main.py`, add the import:

```python
from testbench_ai_service.webui.inflight import TaskRegistry
```

and in `create_app`, immediately after `app.state.started_at = ...`:

```python
    # Created unconditionally, not inside init_webui: the agent routes track
    # into it whether or not the console is enabled, and a missing attribute
    # would be an AttributeError on the request path.
    app.state.task_registry = TaskRegistry()
```

- [ ] **Step 7: Track the agent run**

In `testbench_ai_service/agents/routes.py`, find the `add_task(run_agent, ...)` call noted in Step 1. Wrap the coroutine rather than changing `run_agent` itself, so `tasks.py` stays free of console concerns. Add near the top of the file:

```python
from testbench_ai_service.webui.inflight import TaskRegistry
```

and define, next to the route that dispatches the task:

```python
async def _tracked_run_agent(registry: TaskRegistry, agent_key: str, **kwargs) -> None:
    """Run an agent while the console's in-flight registry counts it.

    A wrapper rather than a change to run_agent(): the console is an
    observer here, and tasks.py should not have to know it exists.
    """
    async with registry.track(agent_key):
        await run_agent(agent_key=agent_key, **kwargs)
```

Then change the dispatch to call `_tracked_run_agent`, passing `request.app.state.task_registry` as `registry` and keeping every other argument exactly as it was. Read the surrounding function first — the argument names must match `run_agent`'s signature (`agent_key`, `agent`, `context`, `conn`, `llm_factory`, `item_ids`).

- [ ] **Step 8: Add the count to the status payload**

In `testbench_ai_service/webui/models.py`, add a field to `StatusResponse`:

```python
    in_flight_tasks: int = 0
```

In `testbench_ai_service/webui/status.py`, change `build_status`'s signature and body:

```python
def build_status(config: AppConfig, started_at: datetime, in_flight_tasks: int = 0) -> StatusResponse:
```

and pass `in_flight_tasks=in_flight_tasks` into the `StatusResponse(...)` construction.

In `testbench_ai_service/webui/routes.py`, update `read_status`:

```python
@router.get("/status", response_model=StatusResponse)
async def read_status(
    request: Request,
    _: Session = Depends(current_session),
    config: AppConfig = Depends(get_app_config),
    registry: TaskRegistry = Depends(get_task_registry),
) -> StatusResponse:
    """Service facts, TestBench reachability, credential presence, agent counts,
    and how many agent runs are in flight."""
    return build_status(config, request.app.state.started_at, registry.count)
```

with `from testbench_ai_service.webui.inflight import TaskRegistry, get_task_registry` added to its imports.

- [ ] **Step 9: Test the wiring end to end**

Append to `tests/unit/webui/test_status.py`:

```python
def test_status_reports_zero_in_flight_tasks_on_a_quiet_service(client, login):
    login()

    body = client.get("/admin/api/status").json()

    assert body["in_flight_tasks"] == 0


def test_status_reports_a_tracked_task(app, client, login):
    login()
    registry = app.state.task_registry
    registry._labels.append("test_case_set_reviewer")
    try:
        body = client.get("/admin/api/status").json()
    finally:
        registry._labels.clear()

    assert body["in_flight_tasks"] == 1
```

- [ ] **Step 10: Run the whole suite**

```bash
pytest tests/unit/webui -v
pytest tests/unit tests/integration -q
```

Expected: PASS. If an existing test calls `build_status(config, started_at)` positionally, the new third parameter defaults to `0` and that call keeps working — that is why it has a default.

- [ ] **Step 11: Lint, type-check, commit**

```bash
ruff check . && ruff format --check . && mypy testbench_ai_service
git add testbench_ai_service/webui/inflight.py testbench_ai_service/webui/models.py testbench_ai_service/webui/status.py testbench_ai_service/webui/routes.py testbench_ai_service/main.py testbench_ai_service/agents/routes.py tests/unit/webui/test_inflight.py tests/unit/webui/test_status.py
git commit -m "Track in-flight agent runs for the console"
```

---

### Task 10: Hot reload

Spec 7. Write, then swap in process: rebuild `AppConfig` from the new file, swap `app.state.config`, close and re-initialise the LLM clients, re-apply logging, reload translations.

**Files:**
- Modify: `testbench_ai_service/webui/reload.py`
- Test: `tests/unit/webui/test_reload.py`

**Interfaces:**
- Consumes: `RESTART_FIELDS`, `restart_required` (Task 8); `LLMFactory`, `setup_logging`, `load_translations`
- Produces: `async def hot_reload(app: FastAPI, config: AppConfig) -> None`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/webui/test_reload.py`:

```python
from unittest.mock import AsyncMock, MagicMock

from testbench_ai_service.webui.reload import hot_reload


def fake_app(config: AppConfig):
    """A stand-in for the FastAPI app: reload only touches app.state."""
    app = MagicMock()
    app.state.config = config
    app.state.llm_factory = MagicMock()
    app.state.llm_factory.close_clients = AsyncMock()
    app.state.llm_factory.init_clients = MagicMock()
    return app


async def test_hot_reload_swaps_the_config_on_app_state():
    app = fake_app(make_config(language="de"))
    new = make_config(language="en")

    await hot_reload(app, new)

    assert app.state.config is new


async def test_hot_reload_closes_the_old_llm_clients_before_building_new_ones():
    app = fake_app(make_config())
    old_factory = app.state.llm_factory

    await hot_reload(app, make_config())

    old_factory.close_clients.assert_awaited_once()
    assert app.state.llm_factory is not old_factory
    app.state.llm_factory.init_clients.assert_called_once()


async def test_hot_reload_initialises_the_new_clients_from_the_new_llm_config():
    app = fake_app(make_config())
    new = make_config()
    new.llm_config.model = "gpt-4.1"

    await hot_reload(app, new)

    (configs,), _ = app.state.llm_factory.init_clients.call_args
    assert configs == [new.llm_config]


async def test_hot_reload_reapplies_logging_and_translations(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        "testbench_ai_service.webui.reload.setup_logging",
        lambda _config: calls.append("logging"),
    )
    monkeypatch.setattr(
        "testbench_ai_service.webui.reload.load_translations",
        lambda: calls.append("translations"),
    )
    app = fake_app(make_config())

    await hot_reload(app, make_config())

    assert calls == ["logging", "translations"]


async def test_a_failure_closing_the_old_clients_does_not_abort_the_reload():
    """The file is already written; refusing to swap would leave disk and
    memory disagreeing with nothing to fix it."""
    app = fake_app(make_config())
    app.state.llm_factory.close_clients = AsyncMock(side_effect=RuntimeError("already closed"))
    new = make_config(language="en")

    await hot_reload(app, new)

    assert app.state.config is new
    app.state.llm_factory.init_clients.assert_called_once()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest tests/unit/webui/test_reload.py -k hot_reload -v
```

Expected: FAIL — `ImportError: cannot import name 'hot_reload'`.

- [ ] **Step 3: Write the implementation**

Append to `testbench_ai_service/webui/reload.py`, and extend its imports:

```python
from fastapi import FastAPI

from testbench_ai_service.llm.factory import LLMFactory
from testbench_ai_service.log import logger, setup_logging
from testbench_ai_service.utils.i18n import load_translations
```

```python
async def hot_reload(app: FastAPI, config: AppConfig) -> None:
    """Make *config* the running configuration, in process.

    Ordered deliberately:

    1. logging first, so everything after it is logged the way the operator
       just asked for;
    2. translations, which are a module-level dict and cheap to re-read;
    3. the config swap, which every subsequent request sees through
       ``get_app_config``;
    4. the LLM clients last, because rebuilding them is the only step that
       touches the network and the only one that can be slow.

    Re-applying ``setup_logging`` is safe to repeat: the dict config names every
    logger the service cares about (``testbench_ai_service``, the four
    ``uvicorn`` loggers, ``py.warnings``), so ``disable_existing_loggers`` has
    nothing new to disable, and ``dictConfig`` flushes and closes the handlers
    it replaces.

    Failures closing the *old* clients are logged and swallowed. By the time
    this runs the new config is already on disk, so aborting would leave the
    file and the process disagreeing with no way to reconcile them -- and a
    client that cannot be closed is a leaked connection, not a corrupt state.

    Changes this cannot cover do not belong here at all; see
    :func:`restart_required`.
    """
    setup_logging(config.logging)
    load_translations()

    previous_factory = app.state.llm_factory
    app.state.config = config

    try:
        await previous_factory.close_clients()
    except Exception as e:
        logger.warning("Could not close the previous LLM clients during reload: %r", e)

    factory = LLMFactory()
    factory.init_clients([config.llm_config])
    app.state.llm_factory = factory

    logger.info("Configuration reloaded in process")
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
pytest tests/unit/webui/test_reload.py -v
```

Expected: PASS, all nineteen. `test_hot_reload_reapplies_logging_and_translations` asserts the order — if it fails on ordering, the implementation put the config swap first; move `setup_logging` and `load_translations` back to the top.

- [ ] **Step 5: Confirm the broad except passes lint**

```bash
ruff check testbench_ai_service/webui/reload.py
```

Expected: clean, or a `BLE001` to silence with `# noqa: BLE001` — the comment above it already explains why it is deliberate.

- [ ] **Step 6: Lint, type-check, commit**

```bash
ruff check . && ruff format --check . && mypy testbench_ai_service
git add testbench_ai_service/webui/reload.py tests/unit/webui/test_reload.py
git commit -m "Hot reload the service configuration in process"
```

---

### Task 11: `POST /config/preview`

The read-only half of the write path: merge, validate, render, diff — and touch nothing. Everything the apply dialog needs, and the source of the Raw screen's generated TOML.

**Files:**
- Modify: `testbench_ai_service/webui/models.py`, `testbench_ai_service/webui/routes.py`
- Create: `tests/unit/webui/test_config_routes.py`

**Interfaces:**
- Consumes: everything from Tasks 3–9
- Produces:
  - `ConfigEditsRequest` with `edits: dict[str, Any]`
  - `PreviewResponse` with `valid: bool`, `issues: list[ConfigIssue]`, `diffs: list[FileDiff]`, `restart_required: list[str]`, `in_flight_tasks: int`, `toml: str`
  - `POST /admin/api/config/preview`

- [ ] **Step 1: Add the request and response models**

Append to `testbench_ai_service/webui/models.py` (and add `from typing import Any` to its imports):

```python
class ConfigEditsRequest(BaseModel):
    """A sparse overlay of dotted config paths to new values.

    A ``None`` value removes the key so the model default takes over again.
    The browser posts only what the operator changed, never a whole config --
    see the module docstring of ``webui/edits.py`` for why.
    """

    edits: dict[str, Any] = Field(default_factory=dict)


class PreviewResponse(BaseModel):
    """What applying the current overlay would do, without doing it."""

    valid: bool
    issues: list[ConfigIssue]
    diffs: list[FileDiff]
    restart_required: list[str]
    in_flight_tasks: int
    # The rendered config.toml the apply would write. Also what the Raw screen
    # shows, which is why it is here rather than on a route of its own.
    toml: str
```

- [ ] **Step 2: Write the failing test**

Create `tests/unit/webui/test_config_routes.py`:

```python
from pathlib import Path

import pytest

from testbench_ai_service.webui.config_io import REDACTED_SENTINEL

COMMENTED = """\
[testbench-ai-service]
# Which TestBench we talk to.
tb_server_url = "https://localhost:9443/api/"
port = 8010
"""


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(COMMENTED, encoding="utf-8")
    return path


@pytest.fixture
def app_with_file(make_app, config_file: Path):
    app = make_app()
    app.state.config_path = config_file
    return app


@pytest.fixture
def file_client(app_with_file):
    from fastapi.testclient import TestClient

    with TestClient(app_with_file, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def admin(file_client, tb_connection):
    from unittest.mock import patch

    def _login(roles=None):
        if roles is not None:
            tb_connection.read_user_roles.return_value = roles
        with patch("testbench_ai_service.webui.auth.TBConnection", return_value=tb_connection):
            return file_client.post(
                "/admin/api/session", json={"username": "a.mueller", "password": "pw"}
            )

    return _login


def csrf(client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["tbai_admin_csrf"]}


def test_preview_of_no_edits_reports_no_diff(file_client, admin):
    admin()

    body = file_client.post(
        "/admin/api/config/preview", json={"edits": {}}, headers=csrf(file_client)
    ).json()

    assert body["valid"] is True
    assert body["issues"] == []
    assert body["diffs"] == []
    assert body["restart_required"] == []


def test_preview_returns_the_rendered_toml_even_with_no_edits(file_client, admin):
    admin()

    body = file_client.post(
        "/admin/api/config/preview", json={"edits": {}}, headers=csrf(file_client)
    ).json()

    assert body["toml"] == COMMENTED


def test_preview_of_a_scalar_edit_diffs_that_line_only(file_client, admin):
    admin()

    body = file_client.post(
        "/admin/api/config/preview",
        json={"edits": {"port": 9999}},
        headers=csrf(file_client),
    ).json()

    assert body["valid"] is True
    assert len(body["diffs"]) == 1
    assert body["diffs"][0]["added"] == 1
    assert body["diffs"][0]["removed"] == 1
    assert "+port = 9999" in body["diffs"][0]["diff"]
    assert "# Which TestBench we talk to." in body["toml"]


def test_preview_names_the_config_path_in_the_diff(file_client, admin, config_file):
    admin()

    body = file_client.post(
        "/admin/api/config/preview",
        json={"edits": {"port": 9999}},
        headers=csrf(file_client),
    ).json()

    assert body["diffs"][0]["path"] == str(config_file.resolve())


def test_preview_reports_a_restart_requiring_edit(file_client, admin):
    admin()

    body = file_client.post(
        "/admin/api/config/preview",
        json={"edits": {"port": 9999}},
        headers=csrf(file_client),
    ).json()

    assert body["restart_required"] == ["port"]


def test_preview_reports_a_hot_swappable_edit_as_needing_no_restart(file_client, admin):
    admin()

    body = file_client.post(
        "/admin/api/config/preview",
        json={"edits": {"language": "en"}},
        headers=csrf(file_client),
    ).json()

    assert body["restart_required"] == []


def test_preview_of_an_invalid_edit_reports_issues_and_no_diff(file_client, admin):
    admin()

    body = file_client.post(
        "/admin/api/config/preview",
        json={"edits": {"port": "not a number"}},
        headers=csrf(file_client),
    ).json()

    assert body["valid"] is False
    assert [issue["path"] for issue in body["issues"]] == ["port"]
    # No diff: there is nothing to approve, because nothing could be written.
    assert body["diffs"] == []


def test_preview_writes_nothing(file_client, admin, config_file):
    admin()
    before = config_file.read_text(encoding="utf-8")

    file_client.post(
        "/admin/api/config/preview",
        json={"edits": {"port": 9999}},
        headers=csrf(file_client),
    )

    assert config_file.read_text(encoding="utf-8") == before
    assert not config_file.with_suffix(".toml.bak").exists()


def test_preview_refuses_the_redaction_sentinel(file_client, admin):
    admin()

    response = file_client.post(
        "/admin/api/config/preview",
        json={"edits": {"llm_config.api_key": REDACTED_SENTINEL}},
        headers=csrf(file_client),
    )

    assert response.status_code == 400


def test_preview_refuses_a_non_admin(file_client, admin):
    admin(roles=["Test Manager"])

    response = file_client.post(
        "/admin/api/config/preview", json={"edits": {}}, headers=csrf(file_client)
    )

    assert response.status_code == 403


def test_preview_refuses_a_missing_csrf_header(file_client, admin):
    admin()

    response = file_client.post("/admin/api/config/preview", json={"edits": {}})

    assert response.status_code == 403


def test_preview_refuses_an_anonymous_caller(file_client):
    response = file_client.post("/admin/api/config/preview", json={"edits": {}})

    assert response.status_code == 401


def test_preview_reports_in_flight_tasks(file_client, admin, app_with_file):
    admin()
    app_with_file.state.task_registry._labels.append("test_case_set_reviewer")
    try:
        body = file_client.post(
            "/admin/api/config/preview", json={"edits": {}}, headers=csrf(file_client)
        ).json()
    finally:
        app_with_file.state.task_registry._labels.clear()

    assert body["in_flight_tasks"] == 1
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
pytest tests/unit/webui/test_config_routes.py -v
```

Expected: FAIL — every test 404s, because the route does not exist.

- [ ] **Step 4: Add a shared helper and the route**

In `testbench_ai_service/webui/routes.py`, extend the imports:

```python
from typing import Any

from testbench_ai_service.webui.auth import require_admin
from testbench_ai_service.webui.diff import file_diff
from testbench_ai_service.webui.document import apply_edits, load_document, render_document
from testbench_ai_service.webui.edits import merge_edits, validate_edit_paths
from testbench_ai_service.webui.inflight import TaskRegistry, get_task_registry
from testbench_ai_service.webui.models import (
    ConfigEditsRequest,
    FileDiff,
    PreviewResponse,
)
from testbench_ai_service.webui.reload import restart_required
from testbench_ai_service.webui.validate import validate_config_dict
```

(keep the existing imports; `read_config_file` also needs adding to the `config_io` import list.)

Then add, above the routes:

```python
def _plan_change(
    edits: dict[str, Any],
    config_path: Path,
    running: AppConfig,
) -> tuple[PreviewResponse, str]:
    """Work out what applying *edits* would do, without doing any of it.

    Returns the preview payload and the rendered TOML text, so ``apply`` can
    reuse exactly the text ``preview`` showed rather than re-deriving it and
    risking a different result.

    Everything is computed against *config_path* as it is on disk right now,
    which is what makes a second operator's diff show the first operator's
    changes instead of silently reverting them (spec 6.1).
    """
    validate_edit_paths(edits)

    document = load_document(config_path)
    current_text = render_document(document)

    merged = merge_edits(read_config_file(config_path), edits)
    candidate, issues = validate_config_dict(merged)

    if candidate is None:
        # Nothing to approve and nothing that could be written, so no diff and
        # no restart classification -- both would be claims about a config that
        # cannot exist.
        return (
            PreviewResponse(
                valid=False,
                issues=issues,
                diffs=[],
                restart_required=[],
                in_flight_tasks=0,
                toml=current_text,
            ),
            current_text,
        )

    apply_edits(document, edits)
    proposed_text = render_document(document)
    diff = file_diff(str(config_path.resolve()), current_text, proposed_text)

    return (
        PreviewResponse(
            valid=True,
            issues=[],
            diffs=[diff] if diff is not None else [],
            restart_required=restart_required(running, candidate),
            in_flight_tasks=0,
            toml=proposed_text,
        ),
        proposed_text,
    )
```

and the route itself:

```python
@router.post("/config/preview", response_model=PreviewResponse)
async def preview_config(
    body: ConfigEditsRequest,
    request: Request,
    config: AppConfig = Depends(get_app_config),
    registry: TaskRegistry = Depends(get_task_registry),
    _: Session = Depends(require_admin),
    __: None = Depends(require_csrf),
) -> PreviewResponse:
    """What applying the operator's edits would do -- diff, validity, restart need.

    Mutating-route guards despite reading nothing: it carries a body of
    operator edits and is only meaningful to someone who could apply them, so
    it is gated exactly like ``apply`` rather than becoming a way for a
    non-admin to explore the config surface.
    """
    preview, _text = _plan_change(body.edits, Path(request.app.state.config_path), config)
    preview.in_flight_tasks = registry.count
    return preview
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
pytest tests/unit/webui/test_config_routes.py -v
```

Expected: PASS, all thirteen. If `test_preview_refuses_an_anonymous_caller` returns 403 rather than 401, check the order of the dependencies — `require_admin` resolves `current_session`, which is what raises 401 for a missing cookie; a `require_csrf` that runs first would give 403 instead. FastAPI resolves in declaration order, so `require_admin` must be declared before `require_csrf`.

- [ ] **Step 6: Lint, type-check, commit**

```bash
ruff check . && ruff format --check . && mypy testbench_ai_service
git add testbench_ai_service/webui/models.py testbench_ai_service/webui/routes.py tests/unit/webui/test_config_routes.py
git commit -m "Add a config preview route to the console API"
```

---

### Task 12: `POST /config/apply`

Validate, write atomically, hot reload, report. The one route in phase 2 that changes the machine.

**Files:**
- Modify: `testbench_ai_service/webui/models.py`, `testbench_ai_service/webui/routes.py`
- Test: `tests/unit/webui/test_config_routes.py`

**Interfaces:**
- Consumes: `_plan_change` (Task 11), `write_atomic` (Task 5), `hot_reload` (Task 10)
- Produces:
  - `ApplyResponse` with `written: list[str]`, `backup: str | None`, `restart_required: list[str]`, `reloaded: bool`, `in_flight_tasks: int`
  - `POST /admin/api/config/apply`

- [ ] **Step 1: Add the response model**

Append to `testbench_ai_service/webui/models.py`:

```python
class ApplyResponse(BaseModel):
    """What an apply actually did."""

    written: list[str]
    backup: str | None
    restart_required: list[str]
    reloaded: bool
    in_flight_tasks: int
```

- [ ] **Step 2: Write the failing test**

Append to `tests/unit/webui/test_config_routes.py`:

```python
def test_apply_writes_the_change_and_keeps_the_comments(file_client, admin, config_file):
    admin()

    body = file_client.post(
        "/admin/api/config/apply",
        json={"edits": {"port": 9999}},
        headers=csrf(file_client),
    ).json()

    written = config_file.read_text(encoding="utf-8")
    assert "port = 9999" in written
    assert "# Which TestBench we talk to." in written
    assert body["written"] == [str(config_file.resolve())]


def test_apply_keeps_the_previous_contents_as_a_backup(file_client, admin, config_file):
    admin()

    body = file_client.post(
        "/admin/api/config/apply",
        json={"edits": {"port": 9999}},
        headers=csrf(file_client),
    ).json()

    backup = config_file.with_name("config.toml.bak")
    assert body["backup"] == str(backup)
    assert backup.read_text(encoding="utf-8") == COMMENTED


def test_apply_hot_reloads_a_swappable_change(file_client, admin, app_with_file):
    admin()

    body = file_client.post(
        "/admin/api/config/apply",
        json={"edits": {"language": "en"}},
        headers=csrf(file_client),
    ).json()

    assert body["reloaded"] is True
    assert body["restart_required"] == []
    assert app_with_file.state.config.language.value == "en"


def test_apply_writes_a_restart_requiring_change_but_does_not_swap_it(
    file_client, admin, app_with_file, config_file
):
    """The file is the source of truth; a port swap the process cannot honour
    must not be reported as live."""
    admin()

    body = file_client.post(
        "/admin/api/config/apply",
        json={"edits": {"port": 9999}},
        headers=csrf(file_client),
    ).json()

    assert body["restart_required"] == ["port"]
    assert "port = 9999" in config_file.read_text(encoding="utf-8")
    assert app_with_file.state.config.port == 8010


def test_apply_of_an_invalid_edit_writes_nothing(file_client, admin, config_file):
    admin()
    before = config_file.read_text(encoding="utf-8")

    response = file_client.post(
        "/admin/api/config/apply",
        json={"edits": {"port": "not a number"}},
        headers=csrf(file_client),
    )

    assert response.status_code == 422
    assert config_file.read_text(encoding="utf-8") == before
    assert not config_file.with_name("config.toml.bak").exists()


def test_apply_of_an_invalid_edit_returns_the_issues(file_client, admin):
    admin()

    body = file_client.post(
        "/admin/api/config/apply",
        json={"edits": {"port": "not a number"}},
        headers=csrf(file_client),
    ).json()

    assert [issue["path"] for issue in body["detail"]["issues"]] == ["port"]


def test_apply_with_no_edits_writes_nothing_and_reports_nothing_written(
    file_client, admin, config_file
):
    admin()

    body = file_client.post(
        "/admin/api/config/apply", json={"edits": {}}, headers=csrf(file_client)
    ).json()

    assert body["written"] == []
    assert body["backup"] is None
    assert not config_file.with_name("config.toml.bak").exists()


def test_apply_refuses_the_redaction_sentinel(file_client, admin, config_file):
    admin()
    before = config_file.read_text(encoding="utf-8")

    response = file_client.post(
        "/admin/api/config/apply",
        json={"edits": {"llm_config.api_key": REDACTED_SENTINEL}},
        headers=csrf(file_client),
    )

    assert response.status_code == 400
    assert config_file.read_text(encoding="utf-8") == before


def test_apply_refuses_a_non_admin(file_client, admin, config_file):
    admin(roles=["Test Manager"])
    before = config_file.read_text(encoding="utf-8")

    response = file_client.post(
        "/admin/api/config/apply",
        json={"edits": {"port": 9999}},
        headers=csrf(file_client),
    )

    assert response.status_code == 403
    assert config_file.read_text(encoding="utf-8") == before


def test_apply_refuses_a_missing_csrf_header(file_client, admin, config_file):
    admin()
    before = config_file.read_text(encoding="utf-8")

    response = file_client.post("/admin/api/config/apply", json={"edits": {"port": 9999}})

    assert response.status_code == 403
    assert config_file.read_text(encoding="utf-8") == before


def test_apply_removing_a_key_falls_back_to_the_default(file_client, admin, config_file):
    admin()

    file_client.post(
        "/admin/api/config/apply",
        json={"edits": {"port": None}},
        headers=csrf(file_client),
    )

    assert "port" not in config_file.read_text(encoding="utf-8")


def test_a_second_apply_sees_the_first_ones_change(file_client, admin, config_file):
    """The overlay merges into disk, so nothing silently reverts."""
    admin()

    file_client.post(
        "/admin/api/config/apply",
        json={"edits": {"language": "en"}},
        headers=csrf(file_client),
    )
    file_client.post(
        "/admin/api/config/apply",
        json={"edits": {"debug": True}},
        headers=csrf(file_client),
    )

    written = config_file.read_text(encoding="utf-8")
    assert 'language = "en"' in written
    assert "debug = true" in written
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
pytest tests/unit/webui/test_config_routes.py -k apply -v
```

Expected: FAIL — 404, the route does not exist.

- [ ] **Step 4: Write the route**

In `testbench_ai_service/webui/routes.py`, extend the imports with `ApplyResponse`, `write_atomic` and `hot_reload`:

```python
from testbench_ai_service.webui.atomic import write_atomic
from testbench_ai_service.webui.models import ApplyResponse
from testbench_ai_service.webui.reload import hot_reload, restart_required
```

and add the route:

```python
@router.post("/config/apply", response_model=ApplyResponse)
async def apply_config(
    body: ConfigEditsRequest,
    request: Request,
    config: AppConfig = Depends(get_app_config),
    registry: TaskRegistry = Depends(get_task_registry),
    _: Session = Depends(require_admin),
    __: None = Depends(require_csrf),
) -> ApplyResponse:
    """Validate the operator's edits, write them atomically, then reload.

    Refuses with 422 and the field-addressed issues if the merged config is one
    the service could not boot with -- nothing is written in that case, so a
    rejected apply can never leave a config file the service will not start
    from.

    A change the running process cannot honour (see
    :func:`~testbench_ai_service.webui.reload.restart_required`) is still
    written, but the in-process swap is skipped: the file is the source of
    truth, and reporting a new port as live when the socket is still the old
    one would be a lie. The response names what needs a restart; the console
    raises its banner. Nothing here ever restarts the service (spec 7).
    """
    config_path = Path(request.app.state.config_path)
    preview, proposed_text = _plan_change(body.edits, config_path, config)

    if not preview.valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "The configuration is not valid and was not written.",
                "issues": [issue.model_dump() for issue in preview.issues],
            },
        )

    if not preview.diffs:
        # Nothing to do. Writing anyway would churn the .bak and the mtime for
        # an operator who changed their mind back.
        return ApplyResponse(
            written=[],
            backup=None,
            restart_required=[],
            reloaded=False,
            in_flight_tasks=registry.count,
        )

    backup = write_atomic(config_path, proposed_text)

    needs_restart = preview.restart_required
    reloaded = False
    if not needs_restart:
        # Re-read rather than reuse the candidate _plan_change built: what the
        # process takes up must be what is now on disk, so a discrepancy
        # between the document path and the dict path shows up here as a
        # logged error instead of as a process quietly running something the
        # file does not say.
        reloaded_config, issues = validate_config_dict(read_config_file(config_path))
        if reloaded_config is not None:
            reloaded_config.loaded_from = config_path
            await hot_reload(request.app, reloaded_config)
            reloaded = True
        else:
            # Should be unreachable: the same dict validated moments ago. If it
            # happens, the file on disk is the one that is right and the
            # operator needs to know the process did not follow.
            logger.error("Wrote %s but could not reload it: %s", config_path, issues)

    return ApplyResponse(
        written=[str(config_path.resolve())],
        backup=str(backup) if backup is not None else None,
        restart_required=needs_restart,
        reloaded=reloaded,
        in_flight_tasks=registry.count,
    )
```

Add `HTTPException` to the `fastapi` import line and `from testbench_ai_service.log import logger` if either is missing.

- [ ] **Step 5: Run the test to verify it passes**

```bash
pytest tests/unit/webui/test_config_routes.py -v
```

Expected: PASS, all twenty-five.

- [ ] **Step 6: Confirm no route regressed**

```bash
pytest tests/unit tests/integration -q
```

Expected: PASS. Watch for `test_wiring.py` — it asserts the console's route list, and two new routes may need adding to its expectation.

- [ ] **Step 7: Lint, type-check, commit**

```bash
ruff check . && ruff format --check . && mypy testbench_ai_service
git add testbench_ai_service/webui/models.py testbench_ai_service/webui/routes.py tests/unit/webui/test_config_routes.py tests/unit/webui/test_wiring.py
git commit -m "Apply console config changes atomically and reload"
```

---

### Task 13: The draft overlay in the browser

Spec 6.1 / 10. The operator's uncommitted edits, keyed by the same dotted paths `FieldSpec.key` already uses, persisted to `localStorage` so a page reload does not lose work. This is the piece most worth unit-testing (spec 13), because everything visible in phases 2–4 reads from it.

**Files:**
- Create: `frontend/src/state/draft.tsx`
- Test: `frontend/src/state/draft.test.tsx`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `DraftProvider` — a React context provider
  - `useDraft(): DraftApi` where
    ```ts
    interface DraftApi {
      edits: Record<string, unknown>
      changeCount: number
      isChanged: (path: string) => boolean
      /** The edited value if there is one, otherwise `fallback`. */
      valueOf: <T>(path: string, fallback: T) => T | unknown
      setValue: (path: string, value: unknown) => void
      /** Record "remove this key", which is a change, not a discard. */
      unsetValue: (path: string) => void
      /** Drop the edit at `path`, reverting the field to its saved value. */
      revert: (path: string) => void
      discardAll: () => void
    }
    ```
  - `DRAFT_STORAGE_KEY = 'tbai_admin_draft'`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/state/draft.test.tsx`:

```tsx
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { DRAFT_STORAGE_KEY, DraftProvider, useDraft } from './draft'

function Probe() {
  const draft = useDraft()
  return (
    <div>
      <span data-testid="count">{draft.changeCount}</span>
      <span data-testid="port">{String(draft.valueOf('port', 8010))}</span>
      <span data-testid="changed">{String(draft.isChanged('port'))}</span>
      <span data-testid="edits">{JSON.stringify(draft.edits)}</span>
      <button onClick={() => draft.setValue('port', 9999)}>set</button>
      <button onClick={() => draft.setValue('port', 8010)}>set-same</button>
      <button onClick={() => draft.unsetValue('port')}>unset</button>
      <button onClick={() => draft.revert('port')}>revert</button>
      <button onClick={() => draft.discardAll()}>discard</button>
    </div>
  )
}

function renderProbe(saved: Record<string, unknown> = { port: 8010 }) {
  return render(
    <DraftProvider saved={saved}>
      <Probe />
    </DraftProvider>,
  )
}

beforeEach(() => {
  window.localStorage.clear()
})

describe('useDraft', () => {
  it('starts with no changes and shows the saved value', () => {
    renderProbe()

    expect(screen.getByTestId('count')).toHaveTextContent('0')
    expect(screen.getByTestId('port')).toHaveTextContent('8010')
    expect(screen.getByTestId('changed')).toHaveTextContent('false')
  })

  it('records an edit and counts it once', async () => {
    renderProbe()

    await userEvent.click(screen.getByText('set'))

    expect(screen.getByTestId('count')).toHaveTextContent('1')
    expect(screen.getByTestId('port')).toHaveTextContent('9999')
    expect(screen.getByTestId('changed')).toHaveTextContent('true')
  })

  it('drops an edit that sets the value back to what is saved', async () => {
    renderProbe()

    await userEvent.click(screen.getByText('set'))
    await userEvent.click(screen.getByText('set-same'))

    // Otherwise the operator is told they have an unapplied change that
    // would produce an empty diff.
    expect(screen.getByTestId('count')).toHaveTextContent('0')
  })

  it('records an unset as a null edit, which is a change', async () => {
    renderProbe()

    await userEvent.click(screen.getByText('unset'))

    expect(screen.getByTestId('count')).toHaveTextContent('1')
    expect(screen.getByTestId('edits')).toHaveTextContent('{"port":null}')
  })

  it('reverting a field forgets the edit rather than recording one', async () => {
    renderProbe()

    await userEvent.click(screen.getByText('set'))
    await userEvent.click(screen.getByText('revert'))

    expect(screen.getByTestId('count')).toHaveTextContent('0')
    expect(screen.getByTestId('edits')).toHaveTextContent('{}')
    expect(screen.getByTestId('port')).toHaveTextContent('8010')
  })

  it('discards every edit at once', async () => {
    renderProbe()

    await userEvent.click(screen.getByText('set'))
    await userEvent.click(screen.getByText('discard'))

    expect(screen.getByTestId('count')).toHaveTextContent('0')
    expect(screen.getByTestId('edits')).toHaveTextContent('{}')
  })

  it('persists edits to localStorage', async () => {
    renderProbe()

    await userEvent.click(screen.getByText('set'))

    expect(JSON.parse(window.localStorage.getItem(DRAFT_STORAGE_KEY) ?? '{}')).toEqual({
      port: 9999,
    })
  })

  it('restores edits from localStorage on mount', () => {
    window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify({ port: 9999 }))

    renderProbe()

    expect(screen.getByTestId('count')).toHaveTextContent('1')
    expect(screen.getByTestId('port')).toHaveTextContent('9999')
  })

  it('ignores unparseable localStorage rather than crashing the console', () => {
    window.localStorage.setItem(DRAFT_STORAGE_KEY, 'not json')

    renderProbe()

    expect(screen.getByTestId('count')).toHaveTextContent('0')
  })

  it('ignores a stored value that is not an object', () => {
    window.localStorage.setItem(DRAFT_STORAGE_KEY, '[1,2,3]')

    renderProbe()

    expect(screen.getByTestId('count')).toHaveTextContent('0')
  })

  it('clears the stored draft when everything is discarded', async () => {
    renderProbe()

    await userEvent.click(screen.getByText('set'))
    await userEvent.click(screen.getByText('discard'))

    expect(window.localStorage.getItem(DRAFT_STORAGE_KEY)).toBeNull()
  })

  it('drops an edit that a concurrent save has made redundant', () => {
    // The operator queued port = 9999; someone else applied the same value.
    window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify({ port: 9999 }))

    renderProbe({ port: 9999 })

    expect(screen.getByTestId('count')).toHaveTextContent('0')
  })

  it('compares structurally so a re-fetched list is not a phantom change', () => {
    window.localStorage.setItem(
      DRAFT_STORAGE_KEY,
      JSON.stringify({ trusted_proxies: ['10.0.0.1'] }),
    )

    render(
      <DraftProvider saved={{ trusted_proxies: ['10.0.0.1'] }}>
        <Probe />
      </DraftProvider>,
    )

    expect(screen.getByTestId('count')).toHaveTextContent('0')
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd frontend && npx vitest run src/state/draft.test.tsx
```

Expected: FAIL — cannot resolve `./draft`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/state/draft.tsx`:

```tsx
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { valueAt } from '../screens/fields'

export const DRAFT_STORAGE_KEY = 'tbai_admin_draft'

/**
 * The operator's uncommitted edits: dotted config path to new value.
 *
 * A `null` value means "remove this key", which is a change like any other —
 * the server reads it as "fall back to the model default". Absence of a key
 * means "no opinion", which is not a change at all. The distinction is the
 * whole reason `unsetValue` and `revert` are separate operations.
 */
export type Edits = Record<string, unknown>

export interface DraftApi {
  edits: Edits
  changeCount: number
  isChanged: (path: string) => boolean
  valueOf: (path: string, fallback: unknown) => unknown
  setValue: (path: string, value: unknown) => void
  unsetValue: (path: string) => void
  revert: (path: string) => void
  discardAll: () => void
}

const DraftContext = createContext<DraftApi | null>(null)

function readStored(): Edits {
  try {
    const raw = window.localStorage.getItem(DRAFT_STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    // An array is an object too, and a stored array would make every consumer
    // that iterates keys behave strangely rather than visibly break.
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    return parsed as Edits
  } catch {
    // A corrupt or unavailable localStorage must never take the console down:
    // an operator who cannot load the console cannot fix the config either.
    return {}
  }
}

function sameValue(left: unknown, right: unknown): boolean {
  // Structural, not referential: a re-fetched config hands back new array and
  // object identities for values that have not changed at all.
  return JSON.stringify(left) === JSON.stringify(right)
}

/**
 * Drop edits whose value already matches what is saved.
 *
 * Runs on every change and whenever `saved` arrives, which is what keeps a
 * concurrent save by another operator from leaving a phantom "1 unapplied
 * change" the diff would show as empty.
 */
function prune(edits: Edits, saved: Record<string, unknown>): Edits {
  const pruned: Edits = {}
  for (const [path, value] of Object.entries(edits)) {
    const savedValue = valueAt(saved, path)
    if (value === null) {
      // "Remove the key" is only a change if the key is actually there.
      if (savedValue !== undefined) pruned[path] = null
      continue
    }
    if (!sameValue(value, savedValue)) pruned[path] = value
  }
  return pruned
}

export function DraftProvider({
  saved,
  children,
}: {
  /** The configuration as saved on disk — what edits are measured against. */
  saved: Record<string, unknown>
  children: ReactNode
}) {
  const [edits, setEdits] = useState<Edits>(readStored)

  // `saved` arrives asynchronously and changes after every apply, so the
  // pruning has to be re-run rather than done once at mount.
  const effective = useMemo(() => prune(edits, saved), [edits, saved])

  useEffect(() => {
    try {
      if (Object.keys(effective).length === 0) {
        window.localStorage.removeItem(DRAFT_STORAGE_KEY)
      } else {
        window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(effective))
      }
    } catch {
      // Private-browsing quota errors are not worth a broken console.
    }
  }, [effective])

  const setValue = useCallback((path: string, value: unknown) => {
    setEdits((current) => ({ ...current, [path]: value }))
  }, [])

  const unsetValue = useCallback((path: string) => {
    setEdits((current) => ({ ...current, [path]: null }))
  }, [])

  const revert = useCallback((path: string) => {
    setEdits((current) => {
      const next = { ...current }
      delete next[path]
      return next
    })
  }, [])

  const discardAll = useCallback(() => setEdits({}), [])

  const api = useMemo<DraftApi>(
    () => ({
      edits: effective,
      changeCount: Object.keys(effective).length,
      isChanged: (path) => path in effective,
      valueOf: (path, fallback) => (path in effective ? effective[path] : fallback),
      setValue,
      unsetValue,
      revert,
      discardAll,
    }),
    [effective, setValue, unsetValue, revert, discardAll],
  )

  return <DraftContext.Provider value={api}>{children}</DraftContext.Provider>
}

export function useDraft(): DraftApi {
  const api = useContext(DraftContext)
  if (api === null) throw new Error('useDraft must be used inside a DraftProvider')
  return api
}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd frontend && npx vitest run src/state/draft.test.tsx
```

Expected: PASS, all thirteen.

- [ ] **Step 5: Type-check and commit**

```bash
cd frontend && npm run build && npm test
cd .. && git add frontend/src/state/draft.tsx frontend/src/state/draft.test.tsx
git commit -m "Add the console's draft edit overlay"
```

---

### Task 14: Preview and apply mutations

The typed client side of Tasks 11 and 12.

**Files:**
- Modify: `frontend/src/api/types.ts`
- Create: `frontend/src/api/mutations.ts`
- Test: `frontend/src/api/mutations.test.tsx`

**Interfaces:**
- Consumes: `apiFetch` from `./client`; `Edits` from `../state/draft`
- Produces:
  - types `ConfigIssue`, `FileDiff`, `PreviewResponse`, `ApplyResponse`
  - `usePreview()` — a TanStack `useMutation` taking `Edits`, returning `PreviewResponse`
  - `useApply()` — same, returning `ApplyResponse`, invalidating the `config` and `status` queries on success

- [ ] **Step 1: Add the types**

Append to `frontend/src/api/types.ts`:

```ts
export interface ConfigIssue {
  path: string
  message: string
  toml_section: string
}

export interface FileDiff {
  path: string
  diff: string
  added: number
  removed: number
}

export interface PreviewResponse {
  valid: boolean
  issues: ConfigIssue[]
  diffs: FileDiff[]
  restart_required: string[]
  in_flight_tasks: number
  toml: string
}

export interface ApplyResponse {
  written: string[]
  backup: string | null
  restart_required: string[]
  reloaded: boolean
  in_flight_tasks: number
}
```

Also add `in_flight_tasks: number` to the existing `StatusResponse` interface.

- [ ] **Step 2: Write the failing test**

Create `frontend/src/api/mutations.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useApply, usePreview } from './mutations'

const fetchMock = vi.fn()

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  document.cookie = 'tbai_admin_csrf=token-123'
  fetchMock.mockReset()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('usePreview', () => {
  it('posts the edits to the preview route', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        valid: true,
        issues: [],
        diffs: [],
        restart_required: [],
        in_flight_tasks: 0,
        toml: '',
      }),
    )
    const { result } = renderHook(() => usePreview(), { wrapper })

    result.current.mutate({ port: 9999 })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/admin/api/config/preview')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ edits: { port: 9999 } })
  })

  it('sends the CSRF header', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        valid: true,
        issues: [],
        diffs: [],
        restart_required: [],
        in_flight_tasks: 0,
        toml: '',
      }),
    )
    const { result } = renderHook(() => usePreview(), { wrapper })

    result.current.mutate({})
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const [, init] = fetchMock.mock.calls[0]
    expect(new Headers(init.headers).get('X-CSRF-Token')).toBe('token-123')
  })

  it('surfaces a validation response as data, not an error', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        valid: false,
        issues: [{ path: 'port', message: 'not an integer', toml_section: '[x]' }],
        diffs: [],
        restart_required: [],
        in_flight_tasks: 0,
        toml: '',
      }),
    )
    const { result } = renderHook(() => usePreview(), { wrapper })

    result.current.mutate({ port: 'nope' })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.valid).toBe(false)
    expect(result.current.data?.issues[0].path).toBe('port')
  })
})

describe('useApply', () => {
  it('posts the edits to the apply route', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        written: ['/tmp/config.toml'],
        backup: '/tmp/config.toml.bak',
        restart_required: [],
        reloaded: true,
        in_flight_tasks: 0,
      }),
    )
    const { result } = renderHook(() => useApply(), { wrapper })

    result.current.mutate({ language: 'en' })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/admin/api/config/apply')
    expect(JSON.parse(init.body)).toEqual({ edits: { language: 'en' } })
  })

  it('reports a 422 as an error carrying the server detail', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: { message: 'not valid', issues: [] } }, 422),
    )
    const { result } = renderHook(() => useApply(), { wrapper })

    result.current.mutate({ port: 'nope' })
    await waitFor(() => expect(result.current.isError).toBe(true))
  })
})
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
cd frontend && npx vitest run src/api/mutations.test.tsx
```

Expected: FAIL — cannot resolve `./mutations`.

- [ ] **Step 4: Write the implementation**

Create `frontend/src/api/mutations.ts`:

```ts
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { Edits } from '../state/draft'
import { apiFetch } from './client'
import type { ApplyResponse, PreviewResponse } from './types'

/**
 * What applying the current draft would do — diff, validity, restart need.
 *
 * A rejected draft comes back as `valid: false` with issues, not as an HTTP
 * error: the dialog renders the reasons, so this is a successful answer to the
 * question asked.
 */
export function usePreview() {
  return useMutation({
    mutationFn: (edits: Edits) =>
      apiFetch<PreviewResponse>('/config/preview', {
        method: 'POST',
        body: JSON.stringify({ edits }),
      }),
  })
}

/**
 * Write the draft and reload the service.
 *
 * On success the saved config and the status both changed, so both queries are
 * invalidated — the pending-change count is measured against the saved config,
 * and leaving it stale would keep every just-applied edit counted as pending.
 */
export function useApply() {
  const queries = useQueryClient()
  return useMutation({
    mutationFn: (edits: Edits) =>
      apiFetch<ApplyResponse>('/config/apply', {
        method: 'POST',
        body: JSON.stringify({ edits }),
      }),
    onSuccess: () => {
      void queries.invalidateQueries({ queryKey: ['config'] })
      void queries.invalidateQueries({ queryKey: ['status'] })
    },
  })
}
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
cd frontend && npx vitest run src/api/mutations.test.tsx
```

Expected: PASS, all five.

- [ ] **Step 6: Type-check and commit**

```bash
cd frontend && npm run build && npm test
cd .. && git add frontend/src/api/mutations.ts frontend/src/api/mutations.test.tsx frontend/src/api/types.ts
git commit -m "Add preview and apply mutations to the console client"
```

---

### Task 15: The editable field component

One control per `FieldSpec` type, bound to the draft. `ReadOnlyField` stays: a non-admin session still renders it, so the read-only console is unchanged rather than reimplemented as a disabled form.

**Files:**
- Create: `frontend/src/components/Field.tsx`
- Test: `frontend/src/components/Field.test.tsx`

**Interfaces:**
- Consumes: `FieldSpec` from `../screens/fields`; `useDraft` (Task 13)
- Produces: `Field({ spec, saved }: { spec: FieldSpec; saved: unknown })`

- [ ] **Step 1: Look at how ReadOnlyField renders, so the two match visually**

```bash
cat frontend/src/components/ReadOnlyField.tsx
```

Note the label/hint/value layout and reuse the same wrapper markup and styles. The editable field must sit in the same grid as its read-only twin, or the Service form will jump when an admin signs in.

- [ ] **Step 2: Write the failing test**

Create `frontend/src/components/Field.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { DraftProvider, useDraft } from '../state/draft'
import type { FieldSpec } from '../screens/fields'
import { Field } from './Field'

function Harness({ spec, saved }: { spec: FieldSpec; saved: Record<string, unknown> }) {
  return (
    <DraftProvider saved={saved}>
      <Field spec={spec} saved={saved[spec.key]} />
      <Edits />
    </DraftProvider>
  )
}

function Edits() {
  const draft = useDraft()
  return <span data-testid="edits">{JSON.stringify(draft.edits)}</span>
}

beforeEach(() => {
  window.localStorage.clear()
})

describe('Field', () => {
  it('renders a text field with the saved value', () => {
    const spec: FieldSpec = { key: 'host', type: 'text', hint: 'Bind address' }

    render(<Harness spec={spec} saved={{ host: '127.0.0.1' }} />)

    expect(screen.getByLabelText('host')).toHaveValue('127.0.0.1')
    expect(screen.getByText('Bind address')).toBeInTheDocument()
  })

  it('records a text edit against the field key', async () => {
    const spec: FieldSpec = { key: 'host', type: 'text', hint: 'Bind address' }
    render(<Harness spec={spec} saved={{ host: '127.0.0.1' }} />)

    await userEvent.clear(screen.getByLabelText('host'))
    await userEvent.type(screen.getByLabelText('host'), '0.0.0.0')

    expect(screen.getByTestId('edits')).toHaveTextContent('{"host":"0.0.0.0"}')
  })

  it('records an emptied optional text field as a removal', async () => {
    const spec: FieldSpec = { key: 'ssl_cert', type: 'text', hint: 'Certificate file' }
    render(<Harness spec={spec} saved={{ ssl_cert: '/etc/cert.pem' }} />)

    await userEvent.clear(screen.getByLabelText('ssl_cert'))

    // Not the empty string: '' is a value the model would reject, while
    // removing the key restores the default of "no certificate".
    expect(screen.getByTestId('edits')).toHaveTextContent('{"ssl_cert":null}')
  })

  it('records a number edit as a number, not a string', async () => {
    const spec: FieldSpec = { key: 'port', type: 'number', hint: 'Port to listen on' }
    render(<Harness spec={spec} saved={{ port: 8010 }} />)

    await userEvent.clear(screen.getByLabelText('port'))
    await userEvent.type(screen.getByLabelText('port'), '9999')

    expect(screen.getByTestId('edits')).toHaveTextContent('{"port":9999}')
  })

  it('leaves a half-typed number alone rather than sending NaN', async () => {
    const spec: FieldSpec = { key: 'port', type: 'number', hint: 'Port to listen on' }
    render(<Harness spec={spec} saved={{ port: 8010 }} />)

    await userEvent.clear(screen.getByLabelText('port'))

    expect(screen.getByTestId('edits')).toHaveTextContent('{"port":null}')
  })

  it('toggles a boolean', async () => {
    const spec: FieldSpec = { key: 'debug', type: 'bool', hint: 'Verbose logging' }
    render(<Harness spec={spec} saved={{ debug: false }} />)

    await userEvent.click(screen.getByRole('switch', { name: 'debug' }))

    expect(screen.getByTestId('edits')).toHaveTextContent('{"debug":true}')
  })

  it('reflects the boolean state to assistive technology', () => {
    const spec: FieldSpec = { key: 'debug', type: 'bool', hint: 'Verbose logging' }
    render(<Harness spec={spec} saved={{ debug: true }} />)

    expect(screen.getByRole('switch', { name: 'debug' })).toHaveAttribute('aria-checked', 'true')
  })

  it('renders a select with the spec options', async () => {
    const spec: FieldSpec = {
      key: 'language',
      type: 'select',
      options: ['de', 'en'],
      hint: 'Default language',
    }
    render(<Harness spec={spec} saved={{ language: 'de' }} />)

    await userEvent.selectOptions(screen.getByLabelText('language'), 'en')

    expect(screen.getByTestId('edits')).toHaveTextContent('{"language":"en"}')
  })

  it('edits a list as comma-separated text and stores an array', async () => {
    const spec: FieldSpec = { key: 'trusted_proxies', type: 'list', hint: 'Trusted proxies' }
    render(<Harness spec={spec} saved={{ trusted_proxies: null }} />)

    await userEvent.type(screen.getByLabelText('trusted_proxies'), '10.0.0.1, 10.0.0.2')

    expect(screen.getByTestId('edits')).toHaveTextContent(
      '{"trusted_proxies":["10.0.0.1","10.0.0.2"]}',
    )
  })

  it('records an emptied list as a removal', async () => {
    const spec: FieldSpec = { key: 'trusted_proxies', type: 'list', hint: 'Trusted proxies' }
    render(<Harness spec={spec} saved={{ trusted_proxies: ['10.0.0.1'] }} />)

    await userEvent.clear(screen.getByLabelText('trusted_proxies'))

    expect(screen.getByTestId('edits')).toHaveTextContent('{"trusted_proxies":null}')
  })

  it('marks a changed field and offers to revert it', async () => {
    const spec: FieldSpec = { key: 'host', type: 'text', hint: 'Bind address' }
    render(<Harness spec={spec} saved={{ host: '127.0.0.1' }} />)

    await userEvent.type(screen.getByLabelText('host'), 'x')
    await userEvent.click(screen.getByRole('button', { name: /revert/i }))

    expect(screen.getByTestId('edits')).toHaveTextContent('{}')
    expect(screen.getByLabelText('host')).toHaveValue('127.0.0.1')
  })

  it('offers no revert control on an unchanged field', () => {
    const spec: FieldSpec = { key: 'host', type: 'text', hint: 'Bind address' }
    render(<Harness spec={spec} saved={{ host: '127.0.0.1' }} />)

    expect(screen.queryByRole('button', { name: /revert/i })).not.toBeInTheDocument()
  })

  it('shows a validation issue against the field', () => {
    const spec: FieldSpec = { key: 'port', type: 'number', hint: 'Port to listen on' }
    render(
      <DraftProvider saved={{ port: 8010 }}>
        <Field spec={spec} saved={8010} issue="Input should be a valid integer" />
      </DraftProvider>,
    )

    expect(screen.getByLabelText('port')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByRole('alert')).toHaveTextContent('Input should be a valid integer')
  })
})
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
cd frontend && npx vitest run src/components/Field.test.tsx
```

Expected: FAIL — cannot resolve `./Field`.

- [ ] **Step 4: Write the implementation**

Create `frontend/src/components/Field.tsx`:

```tsx
import { useTranslations, type Lang } from '../i18n'
import type { FieldSpec } from '../screens/fields'
import { useDraft } from '../state/draft'

/** Turn the current draft value (or the saved one) into text for an input. */
function asText(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (Array.isArray(value)) return value.join(', ')
  return String(value)
}

export function Field({
  spec,
  saved,
  issue,
  lang = 'de',
}: {
  spec: FieldSpec
  /** The value as saved on disk — what an unedited field shows. */
  saved: unknown
  /** A server-side validation message addressed to this field, if any. */
  issue?: string
  lang?: Lang
}) {
  const t = useTranslations(lang)
  const draft = useDraft()
  const value = draft.valueOf(spec.key, saved)
  const changed = draft.isChanged(spec.key)
  const issueId = `${spec.key}-issue`

  /**
   * An empty input means "remove this key", never the empty string.
   *
   * Every optional field in AppConfig is `X | None` with a meaningful default;
   * writing `""` would either fail validation (`ssl_cert = ""` is not a file)
   * or persist a value the operator meant to clear.
   */
  const commit = (raw: string, parse: (text: string) => unknown) => {
    if (raw.trim() === '') {
      draft.unsetValue(spec.key)
      return
    }
    draft.setValue(spec.key, parse(raw))
  }

  const control = () => {
    switch (spec.type) {
      case 'bool':
        return (
          <button
            type="button"
            role="switch"
            id={spec.key}
            aria-checked={value === true}
            aria-labelledby={`${spec.key}-label`}
            onClick={() => draft.setValue(spec.key, value !== true)}
            style={{
              width: 36,
              height: 20,
              borderRadius: 10,
              border: '1px solid var(--color-divider)',
              background: value === true ? 'var(--color-accent)' : 'var(--color-surface)',
              position: 'relative',
              cursor: 'pointer',
              padding: 0,
            }}
          >
            <span
              style={{
                position: 'absolute',
                top: 2,
                left: value === true ? 18 : 2,
                width: 14,
                height: 14,
                borderRadius: 7,
                background: value === true ? '#fff' : 'var(--color-text)',
                transition: 'left .15s',
              }}
            />
          </button>
        )
      case 'select':
        return (
          <select
            className="input"
            id={spec.key}
            aria-invalid={issue ? true : undefined}
            aria-describedby={issue ? issueId : undefined}
            value={asText(value)}
            onChange={(event) => draft.setValue(spec.key, event.target.value)}
          >
            {(spec.options ?? []).map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        )
      case 'number':
        return (
          <input
            className="input"
            id={spec.key}
            type="number"
            aria-invalid={issue ? true : undefined}
            aria-describedby={issue ? issueId : undefined}
            value={asText(value)}
            onChange={(event) =>
              commit(event.target.value, (text) => {
                const parsed = Number(text)
                // A half-typed "1e" parses to NaN, which JSON.stringify turns
                // into null and the server would read as a removal. Keep the
                // raw text instead and let the server's validation say so.
                return Number.isNaN(parsed) ? text : parsed
              })
            }
          />
        )
      case 'list':
        return (
          <input
            className="input"
            id={spec.key}
            aria-invalid={issue ? true : undefined}
            aria-describedby={issue ? issueId : undefined}
            value={asText(value)}
            onChange={(event) =>
              commit(event.target.value, (text) =>
                text
                  .split(',')
                  .map((entry) => entry.trim())
                  .filter((entry) => entry !== ''),
              )
            }
          />
        )
      default:
        return (
          <input
            className="input"
            id={spec.key}
            aria-invalid={issue ? true : undefined}
            aria-describedby={issue ? issueId : undefined}
            value={asText(value)}
            onChange={(event) => commit(event.target.value, (text) => text)}
          />
        )
    }
  }

  return (
    // The grid, gap, padding and label styling deliberately match
    // ReadOnlyField exactly: the two render the same form for different
    // sessions, and a different metric here would make the Service screen
    // jump when an admin signs in.
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(180px, 260px) 1fr',
        gap: 16,
        padding: '10px 0',
        borderBottom: '1px solid var(--color-divider)',
        alignItems: 'start',
      }}
    >
      <div>
        <label
          id={`${spec.key}-label`}
          htmlFor={spec.key}
          // The last segment only, as ReadOnlyField shows it: the section is
          // already in the screen's subheading, so 'llm_config.model' would
          // read as 'llm_config.' twice. The id and htmlFor stay the full
          // dotted key, which is what makes them unique on a screen.
          style={{ fontSize: 13, fontFamily: 'ui-monospace, Menlo, monospace', display: 'block' }}
        >
          {spec.key.split('.').pop()}
        </label>
        <span className="text-muted" style={{ fontSize: 11 }}>
          {spec.hint}
        </span>
      </div>
      <div style={{ maxWidth: 480, display: 'flex', flexDirection: 'column', gap: 4 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {control()}
          {changed && (
            <button
              type="button"
              className="btn btn-ghost"
              style={{ fontSize: 11, padding: '0 6px', whiteSpace: 'nowrap' }}
              onClick={() => draft.revert(spec.key)}
            >
              {t.revert}
            </button>
          )}
        </div>
        {issue && (
          <span id={issueId} role="alert" style={{ fontSize: 11, color: '#a33a2b' }}>
            {issue}
          </span>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Add the `revert` translation key**

In `frontend/src/i18n/en.ts` add `revert: 'Revert',` and in `frontend/src/i18n/de.ts` add `revert: 'Zurücksetzen',`. Both dictionaries are `as const` objects with the same keys; `i18n.test.ts` already asserts they match, so a key added to one and not the other fails that test.

- [ ] **Step 6: Run the test to verify it passes**

```bash
cd frontend && npx vitest run src/components/Field.test.tsx src/i18n/i18n.test.ts
```

Expected: PASS, all fourteen plus the i18n parity test.

- [ ] **Step 7: Type-check and commit**

```bash
cd frontend && npm run build && npm test
cd .. && git add frontend/src/components/Field.tsx frontend/src/components/Field.test.tsx frontend/src/i18n/en.ts frontend/src/i18n/de.ts
git commit -m "Add an editable config field to the console"
```

---

### Task 16: The Service, LLM and Logging forms become editable

`ConfigSection` currently renders `ReadOnlyField` against `config.running`. Editing measures against `config.disk` instead — the draft is "what will be written", and `running` is fully defaulted, so measuring against it would count every default the file omits as an unapplied change the diff then shows as empty.

**Files:**
- Modify: `frontend/src/screens/ConfigSection.tsx`
- Modify: `frontend/src/screens/ConfigSection.test.tsx`

**Interfaces:**
- Consumes: `Field` (Task 15), `useDraft` (Task 13), `valueAt` and the `*_FIELDS` specs from `./fields`
- Produces: `ConfigSection({ section, lang, isAdmin, issues }: { section: Section; lang: Lang; isAdmin: boolean; issues?: ConfigIssue[] })`

- [ ] **Step 1: Read the existing test file to see what must keep passing**

```bash
cat frontend/src/screens/ConfigSection.test.tsx
```

The read-only assertions stay: a non-admin session must render exactly what it renders today. Only the admin path is new.

- [ ] **Step 2: Write the failing test**

Append to `frontend/src/screens/ConfigSection.test.tsx` (matching the query-client and mock-fetch setup the existing tests already use in that file):

```tsx
it('renders editable fields for an admin', async () => {
  renderSection({ section: 'service', isAdmin: true })

  expect(await screen.findByLabelText('host')).toBeEnabled()
})

it('renders read-only fields for a non-admin', async () => {
  renderSection({ section: 'service', isAdmin: false })

  await screen.findByText('tb_server_url')
  expect(screen.queryByLabelText('host')).not.toBeInTheDocument()
})

it('measures edits against the disk config, not the running one', async () => {
  // The disk file omits 'debug'; the running config defaults it to false.
  // Showing 'false' is right; counting it as a pending change is not.
  renderSection({
    section: 'service',
    isAdmin: true,
    disk: { host: '127.0.0.1' },
    running: { host: '127.0.0.1', debug: false, port: 8010 },
  })

  const debug = await screen.findByRole('switch', { name: 'debug' })
  expect(debug).toHaveAttribute('aria-checked', 'false')
  expect(screen.queryByRole('button', { name: /revert/i })).not.toBeInTheDocument()
})

it('shows a field-addressed validation issue on the right field', async () => {
  renderSection({
    section: 'service',
    isAdmin: true,
    issues: [{ path: 'port', message: 'Input should be a valid integer', toml_section: '[x]' }],
  })

  expect(await screen.findByLabelText('port')).toHaveAttribute('aria-invalid', 'true')
})

it('does not show an issue addressed to a different tab', async () => {
  renderSection({
    section: 'service',
    isAdmin: true,
    issues: [
      { path: 'llm_config.model', message: 'nope', toml_section: '[x]' },
    ],
  })

  await screen.findByLabelText('host')
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})
```

These tests need three imports the file does not have yet:

```tsx
import type { ConfigIssue } from '../api/types'
import { DraftProvider } from '../state/draft'
```

plus `window.localStorage.clear()` in the file's `beforeEach`, so a draft written by one test does not leak into the next.

Add a `renderSection` helper near the top of the file if the existing tests do not already have one, wrapping the component in a `QueryClientProvider` and a `DraftProvider`:

```tsx
function renderSection({
  section = 'service',
  isAdmin = false,
  disk = { host: '127.0.0.1', port: 8010, tb_server_url: 'https://tb:9443/api/' },
  running = { host: '127.0.0.1', port: 8010, tb_server_url: 'https://tb:9443/api/', debug: false },
  issues = [],
}: {
  section?: 'service' | 'llm' | 'logging'
  isAdmin?: boolean
  disk?: Record<string, unknown>
  running?: Record<string, unknown>
  issues?: ConfigIssue[]
} = {}) {
  fetchMock.mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ running, disk, config_path: '/tmp/config.toml' }),
  } as Response)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <DraftProvider saved={disk}>
        <ConfigSection section={section} lang="en" isAdmin={isAdmin} issues={issues} />
      </DraftProvider>
    </QueryClientProvider>,
  )
}
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
cd frontend && npx vitest run src/screens/ConfigSection.test.tsx
```

Expected: FAIL — `ConfigSection` takes no `isAdmin` or `issues` prop, so TypeScript rejects the render and the editable assertions find nothing.

- [ ] **Step 4: Make the component editable**

In `frontend/src/screens/ConfigSection.tsx`, change the imports and signature:

```tsx
import type { ConfigIssue } from '../api/types'
import { Field } from '../components/Field'
import { ReadOnlyField } from '../components/ReadOnlyField'
```

```tsx
export function ConfigSection({
  section,
  lang,
  isAdmin,
  issues = [],
}: {
  section: Section
  lang: Lang
  isAdmin: boolean
  /** Field-addressed validation failures from the last preview or apply. */
  issues?: ConfigIssue[]
}) {
```

Replace the field-rendering block at the bottom with:

```tsx
      <div>
        {fields.map((spec) => {
          const issue = issues.find((entry) => entry.path === spec.key)?.message
          // Non-admins keep the phase-1 read-only rendering unchanged rather
          // than getting a form full of disabled inputs.
          return isAdmin ? (
            <Field
              key={spec.key}
              spec={spec}
              // The draft is "what will be written", so it is measured against
              // the file, not against the fully-defaulted running config --
              // otherwise every default the file omits counts as a pending
              // change whose diff would come back empty.
              saved={valueAt(config.data.disk, spec.key) ?? valueAt(running, spec.key)}
              issue={issue}
              lang={lang}
            />
          ) : (
            <ReadOnlyField key={spec.key} spec={spec} value={valueAt(running, spec.key)} />
          )
        })}
      </div>
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
cd frontend && npx vitest run src/screens/ConfigSection.test.tsx
```

Expected: PASS — the five new tests plus every existing one in that file.

- [ ] **Step 6: Type-check and commit**

```bash
cd frontend && npm run build && npm test
cd .. && git add frontend/src/screens/ConfigSection.tsx frontend/src/screens/ConfigSection.test.tsx
git commit -m "Make the console config forms editable for admins"
```

---

### Task 17: The pending-changes banner and the diff dialog

The artboard's top strip: "**N** unapplied changes · view diff · discard · apply", and the modal it opens showing the real unified diff with the Apply button.

**Files:**
- Create: `frontend/src/components/PendingBanner.tsx`, `frontend/src/components/DiffDialog.tsx`
- Test: `frontend/src/components/PendingBanner.test.tsx`, `frontend/src/components/DiffDialog.test.tsx`

**Interfaces:**
- Consumes: `useDraft` (Task 13), `usePreview` / `useApply` (Task 14)
- Produces:
  - `PendingBanner({ lang }: { lang: Lang })`
  - `DiffDialog({ lang, onClose }: { lang: Lang; onClose: () => void })`

- [ ] **Step 1: Add the translation keys**

To `frontend/src/i18n/en.ts`:

```ts
  unapplied: 'unapplied changes',
  viewDiff: 'View diff',
  discard: 'Discard',
  apply: 'Apply',
  applying: 'Applying…',
  applied: 'Applied',
  noChanges: 'No changes to apply.',
  invalidDraft: 'These changes were not written:',
  restartNeeded: 'Some changes need a service restart to take effect.',
  restartWhich: 'Needs a restart:',
  inFlight: 'agent runs are still in flight.',
  writesTo: 'Writes to',
  backupKept: 'Previous contents kept as',
  close: 'Close',
```

To `frontend/src/i18n/de.ts`, the same keys:

```ts
  unapplied: 'nicht übernommene Änderungen',
  viewDiff: 'Diff anzeigen',
  discard: 'Verwerfen',
  apply: 'Übernehmen',
  applying: 'Wird übernommen…',
  applied: 'Übernommen',
  noChanges: 'Keine Änderungen zu übernehmen.',
  invalidDraft: 'Diese Änderungen wurden nicht geschrieben:',
  restartNeeded: 'Einige Änderungen werden erst nach einem Neustart wirksam.',
  restartWhich: 'Neustart erforderlich:',
  inFlight: 'Agent-Läufe sind noch aktiv.',
  writesTo: 'Schreibt nach',
  backupKept: 'Vorheriger Inhalt gesichert als',
  close: 'Schließen',
```

- [ ] **Step 2: Write the failing test for the banner**

Create `frontend/src/components/PendingBanner.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DraftProvider, useDraft } from '../state/draft'
import { PendingBanner } from './PendingBanner'

const fetchMock = vi.fn()

function Seed({ edits }: { edits: Record<string, unknown> }) {
  const draft = useDraft()
  return (
    <button
      onClick={() => {
        for (const [path, value] of Object.entries(edits)) draft.setValue(path, value)
      }}
    >
      seed
    </button>
  )
}

function renderBanner(saved: Record<string, unknown> = { port: 8010, host: '127.0.0.1' }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <DraftProvider saved={saved}>
        <Seed edits={{ port: 9999 }} />
        <PendingBanner lang="en" />
      </DraftProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  window.localStorage.clear()
  vi.stubGlobal('fetch', fetchMock)
  document.cookie = 'tbai_admin_csrf=token-123'
  fetchMock.mockReset()
})

describe('PendingBanner', () => {
  it('renders nothing when there are no changes', () => {
    renderBanner()

    expect(screen.queryByText(/unapplied changes/)).not.toBeInTheDocument()
  })

  it('counts the pending changes once there are some', async () => {
    renderBanner()

    await userEvent.click(screen.getByText('seed'))

    expect(screen.getByRole('status')).toHaveTextContent('1 unapplied changes')
  })

  it('lists the changed paths', async () => {
    renderBanner()

    await userEvent.click(screen.getByText('seed'))

    expect(screen.getByRole('status')).toHaveTextContent('port')
  })

  it('discards every change', async () => {
    renderBanner()

    await userEvent.click(screen.getByText('seed'))
    await userEvent.click(screen.getByRole('button', { name: 'Discard' }))

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('opens the diff dialog', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        valid: true,
        issues: [],
        diffs: [{ path: '/tmp/config.toml', diff: '-port = 8010\n+port = 9999\n', added: 1, removed: 1 }],
        restart_required: ['port'],
        in_flight_tasks: 0,
        toml: '',
      }),
    } as Response)
    renderBanner()

    await userEvent.click(screen.getByText('seed'))
    await userEvent.click(screen.getByRole('button', { name: 'View diff' }))

    expect(await screen.findByRole('dialog')).toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Write the failing test for the dialog**

Create `frontend/src/components/DiffDialog.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DRAFT_STORAGE_KEY, DraftProvider } from '../state/draft'
import { DiffDialog } from './DiffDialog'

const fetchMock = vi.fn()

function jsonResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}

const PREVIEW_OK = {
  valid: true,
  issues: [],
  diffs: [
    {
      path: '/tmp/config.toml',
      diff: '--- /tmp/config.toml\n+++ /tmp/config.toml\n-port = 8010\n+port = 9999\n',
      added: 1,
      removed: 1,
    },
  ],
  restart_required: ['port'],
  in_flight_tasks: 0,
  toml: '[testbench-ai-service]\nport = 9999\n',
}

function renderDialog(onClose = vi.fn()) {
  window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify({ port: 9999 }))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <DraftProvider saved={{ port: 8010 }}>
        <DiffDialog lang="en" onClose={onClose} />
      </DraftProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  window.localStorage.clear()
  vi.stubGlobal('fetch', fetchMock)
  document.cookie = 'tbai_admin_csrf=token-123'
  fetchMock.mockReset()
})

describe('DiffDialog', () => {
  it('previews on open and shows the diff', async () => {
    fetchMock.mockResolvedValue(jsonResponse(PREVIEW_OK))

    renderDialog()

    expect(await screen.findByText(/-port = 8010/)).toBeInTheDocument()
    expect(screen.getByText(/\+port = 9999/)).toBeInTheDocument()
  })

  it('names the file it would write', async () => {
    fetchMock.mockResolvedValue(jsonResponse(PREVIEW_OK))

    renderDialog()

    expect(await screen.findByText(/\/tmp\/config\.toml/)).toBeInTheDocument()
  })

  it('warns that the change needs a restart', async () => {
    fetchMock.mockResolvedValue(jsonResponse(PREVIEW_OK))

    renderDialog()

    expect(await screen.findByText(/Needs a restart:/)).toBeInTheDocument()
    expect(screen.getByText(/port/)).toBeInTheDocument()
  })

  it('applies and closes on success', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(PREVIEW_OK))
      .mockResolvedValueOnce(
        jsonResponse({
          written: ['/tmp/config.toml'],
          backup: '/tmp/config.toml.bak',
          restart_required: [],
          reloaded: true,
          in_flight_tasks: 0,
        }),
      )
    const onClose = vi.fn()
    renderDialog(onClose)

    await screen.findByText(/-port = 8010/)
    await userEvent.click(screen.getByRole('button', { name: 'Apply' }))

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(fetchMock.mock.calls[1][0]).toBe('/admin/api/config/apply')
  })

  it('clears the draft after a successful apply', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(PREVIEW_OK))
      .mockResolvedValueOnce(
        jsonResponse({
          written: ['/tmp/config.toml'],
          backup: null,
          restart_required: [],
          reloaded: true,
          in_flight_tasks: 0,
        }),
      )
    renderDialog()

    await screen.findByText(/-port = 8010/)
    await userEvent.click(screen.getByRole('button', { name: 'Apply' }))

    await waitFor(() =>
      expect(window.localStorage.getItem(DRAFT_STORAGE_KEY)).toBeNull(),
    )
  })

  it('shows the validation issues and offers no apply when the draft is invalid', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        valid: false,
        issues: [
          { path: 'port', message: 'Input should be a valid integer', toml_section: '[x]' },
        ],
        diffs: [],
        restart_required: [],
        in_flight_tasks: 0,
        toml: '',
      }),
    )

    renderDialog()

    expect(await screen.findByText(/Input should be a valid integer/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Apply' })).not.toBeInTheDocument()
  })

  it('warns about in-flight agent runs', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ...PREVIEW_OK, in_flight_tasks: 2 }))

    renderDialog()

    expect(await screen.findByText(/2 agent runs are still in flight/)).toBeInTheDocument()
  })

  it('closes without applying', async () => {
    fetchMock.mockResolvedValue(jsonResponse(PREVIEW_OK))
    const onClose = vi.fn()
    renderDialog(onClose)

    await screen.findByText(/-port = 8010/)
    await userEvent.click(screen.getByRole('button', { name: 'Close' }))

    expect(onClose).toHaveBeenCalled()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('reports a failed apply and keeps the dialog open', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(PREVIEW_OK))
      .mockResolvedValueOnce(jsonResponse({ detail: 'Cannot write /tmp/config.toml' }, 400))
    const onClose = vi.fn()
    renderDialog(onClose)

    await screen.findByText(/-port = 8010/)
    await userEvent.click(screen.getByRole('button', { name: 'Apply' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot write /tmp/config.toml')
    expect(onClose).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 4: Run both tests to verify they fail**

```bash
cd frontend && npx vitest run src/components/PendingBanner.test.tsx src/components/DiffDialog.test.tsx
```

Expected: FAIL — neither module resolves.

- [ ] **Step 5: Write the diff dialog**

Create `frontend/src/components/DiffDialog.tsx`:

```tsx
import { useEffect } from 'react'
import { useApply, usePreview } from '../api/mutations'
import { useTranslations, type Lang } from '../i18n'
import { useDraft } from '../state/draft'

/**
 * The gate between a draft and the filesystem.
 *
 * Previews on open rather than on every keystroke: the preview reads the file
 * off disk and constructs an AppConfig (which imports agent classes), so it is
 * not something to run per character.
 */
export function DiffDialog({ lang, onClose }: { lang: Lang; onClose: () => void }) {
  const t = useTranslations(lang)
  const draft = useDraft()
  const preview = usePreview()
  const apply = useApply()

  useEffect(() => {
    preview.mutate(draft.edits)
    // Deliberately on mount only: re-previewing as the draft changes underneath
    // an open dialog would show the operator a diff they did not ask to approve.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const data = preview.data

  const onApply = () => {
    apply.mutate(draft.edits, {
      onSuccess: () => {
        // The edits are on disk now, so the overlay has nothing left to say.
        draft.discardAll()
        onClose()
      },
    })
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t.viewDiff}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,.45)',
        display: 'grid',
        placeItems: 'center',
        padding: 24,
        zIndex: 20,
      }}
    >
      <div
        className="card"
        style={{
          background: 'var(--color-bg)',
          width: 'min(900px, 100%)',
          maxHeight: '85vh',
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
          padding: 20,
        }}
      >
        <h3 style={{ margin: 0 }}>{t.viewDiff}</h3>

        {preview.isPending && <div>…</div>}

        {preview.isError && (
          <div role="alert" style={{ color: '#a33a2b' }}>
            {(preview.error as Error).message}
          </div>
        )}

        {data && !data.valid && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ color: '#a33a2b' }}>{t.invalidDraft}</div>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
              {data.issues.map((issue) => (
                <li key={`${issue.path}-${issue.message}`}>
                  <code>{issue.path || issue.toml_section}</code> — {issue.message}
                </li>
              ))}
            </ul>
          </div>
        )}

        {data?.valid && data.diffs.length === 0 && <div>{t.noChanges}</div>}

        {data?.valid &&
          data.diffs.map((entry) => (
            <div key={entry.path} style={{ display: 'flex', flexDirection: 'column', gap: 4, minHeight: 0 }}>
              <div
                className="text-muted"
                style={{ fontSize: 12, fontFamily: 'ui-monospace, Menlo, monospace' }}
              >
                {t.writesTo} {entry.path} · +{entry.added} −{entry.removed}
              </div>
              <pre
                style={{
                  margin: 0,
                  padding: 12,
                  overflow: 'auto',
                  maxHeight: '45vh',
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-divider)',
                  fontSize: 12.5,
                  lineHeight: 1.5,
                  fontFamily: 'ui-monospace, Menlo, monospace',
                }}
              >
                {entry.diff}
              </pre>
            </div>
          ))}

        {data && data.restart_required.length > 0 && (
          <div style={{ fontSize: 13 }}>
            {t.restartWhich} <code>{data.restart_required.join(', ')}</code>
          </div>
        )}

        {data && data.in_flight_tasks > 0 && (
          <div style={{ fontSize: 13 }}>
            {data.in_flight_tasks} {t.inFlight}
          </div>
        )}

        {apply.isError && (
          <div role="alert" style={{ color: '#a33a2b' }}>
            {(apply.error as Error).message}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            {t.close}
          </button>
          {data?.valid && data.diffs.length > 0 && (
            <button
              type="button"
              className="btn btn-primary"
              onClick={onApply}
              disabled={apply.isPending}
            >
              {apply.isPending ? t.applying : t.apply}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 6: Write the banner**

Create `frontend/src/components/PendingBanner.tsx`:

```tsx
import { useState } from 'react'
import { useTranslations, type Lang } from '../i18n'
import { useDraft } from '../state/draft'
import { DiffDialog } from './DiffDialog'

/** The artboard's top strip: how many changes are queued, and what to do with them. */
export function PendingBanner({ lang }: { lang: Lang }) {
  const t = useTranslations(lang)
  const draft = useDraft()
  const [showDiff, setShowDiff] = useState(false)

  if (draft.changeCount === 0) return null

  return (
    <>
      <div
        role="status"
        style={{
          background: 'var(--color-accent-100)',
          borderBottom: '1px solid var(--color-accent-300)',
          padding: '7px 16px',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          fontSize: 13,
          color: 'var(--color-accent-900)',
        }}
      >
        <span
          style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--color-accent)' }}
        />
        <span
          style={{
            minWidth: 0,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          <b>{draft.changeCount}</b> {t.unapplied} ·{' '}
          <span style={{ fontFamily: 'ui-monospace, Menlo, monospace', fontSize: 12 }}>
            {Object.keys(draft.edits).join(', ')}
          </span>
        </span>
        <div style={{ flex: 1 }} />
        <button
          type="button"
          className="btn btn-secondary"
          style={{ padding: '4px 10px', fontSize: 13 }}
          onClick={() => setShowDiff(true)}
        >
          {t.viewDiff}
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          style={{ padding: '4px 10px', fontSize: 13 }}
          onClick={() => draft.discardAll()}
        >
          {t.discard}
        </button>
      </div>
      {showDiff && <DiffDialog lang={lang} onClose={() => setShowDiff(false)} />}
    </>
  )
}
```

- [ ] **Step 7: Run both tests to verify they pass**

```bash
cd frontend && npx vitest run src/components/PendingBanner.test.tsx src/components/DiffDialog.test.tsx src/i18n/i18n.test.ts
```

Expected: PASS — five banner tests, nine dialog tests, and the i18n parity test.

- [ ] **Step 8: Type-check and commit**

```bash
cd frontend && npm run build && npm test
cd .. && git add frontend/src/components/PendingBanner.tsx frontend/src/components/PendingBanner.test.tsx frontend/src/components/DiffDialog.tsx frontend/src/components/DiffDialog.test.tsx frontend/src/i18n/en.ts frontend/src/i18n/de.ts
git commit -m "Add the pending-changes banner and diff dialog"
```

---

### Task 18: The restart-required banner

Spec 7. `disk != running` after an apply that wrote a boot-fixed change. There is no button that restarts anything — the banner says what to restart and links the Windows service instructions.

**Files:**
- Create: `frontend/src/components/RestartBanner.tsx`
- Test: `frontend/src/components/RestartBanner.test.tsx`

**Interfaces:**
- Consumes: nothing beyond its props
- Produces: `RestartBanner({ lang, fields }: { lang: Lang; fields: string[] })`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/RestartBanner.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RestartBanner } from './RestartBanner'

describe('RestartBanner', () => {
  it('renders nothing when nothing needs a restart', () => {
    render(<RestartBanner lang="en" fields={[]} />)

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('says a restart is needed and names the fields', () => {
    render(<RestartBanner lang="en" fields={['host', 'port']} />)

    expect(screen.getByRole('status')).toHaveTextContent(
      'Some changes need a service restart to take effect.',
    )
    expect(screen.getByRole('status')).toHaveTextContent('host, port')
  })

  it('offers no button that claims to restart the service', () => {
    // Spec 7: re-execing only works under a supervisor and would kill a bare
    // terminal process outright.
    render(<RestartBanner lang="en" fields={['port']} />)

    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd frontend && npx vitest run src/components/RestartBanner.test.tsx
```

Expected: FAIL — cannot resolve `./RestartBanner`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/components/RestartBanner.tsx`:

```tsx
import { useTranslations, type Lang } from '../i18n'

/**
 * "Restart needed", and what for.
 *
 * Deliberately has no action: re-execing the process only works under a
 * supervisor (Windows service, systemd) and would kill a bare terminal process
 * outright, so the console tells the operator rather than doing it (spec 7).
 */
export function RestartBanner({ lang, fields }: { lang: Lang; fields: string[] }) {
  const t = useTranslations(lang)
  if (fields.length === 0) return null

  return (
    <div
      role="status"
      style={{
        background: 'var(--color-surface)',
        borderBottom: '1px solid var(--color-divider)',
        padding: '6px 16px',
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        fontSize: 13,
      }}
    >
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        aria-hidden="true"
      >
        <path d="M21 12a9 9 0 1 1-3-6.7" />
        <path d="M21 3v6h-6" />
      </svg>
      <span>
        {t.restartNeeded} {t.restartWhich}{' '}
        <code style={{ fontFamily: 'ui-monospace, Menlo, monospace' }}>{fields.join(', ')}</code>
      </span>
    </div>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd frontend && npx vitest run src/components/RestartBanner.test.tsx
```

Expected: PASS, all three.

- [ ] **Step 5: Type-check and commit**

```bash
cd frontend && npm run build && npm test
cd .. && git add frontend/src/components/RestartBanner.tsx frontend/src/components/RestartBanner.test.tsx
git commit -m "Add the console's restart-required banner"
```

---

### Task 19: The Raw `config.toml` screen

The artboard's Raw screen: the `config.toml` the current draft would produce, read-only, with copy-to-clipboard. It reads `PreviewResponse.toml`, so what it shows is literally the text an apply would write.

**Files:**
- Create: `frontend/src/screens/Raw.tsx`
- Test: `frontend/src/screens/Raw.test.tsx`

**Interfaces:**
- Consumes: `usePreview` (Task 14), `useDraft` (Task 13)
- Produces: `Raw({ lang }: { lang: Lang })`

- [ ] **Step 1: Add the translation keys**

To `frontend/src/i18n/en.ts`:

```ts
  rawSub: 'Generated from the current (unapplied) state · read-only',
  copy: 'Copy',
  copied: 'Copied',
```

To `frontend/src/i18n/de.ts`:

```ts
  rawSub: 'Aus dem aktuellen (nicht übernommenen) Stand erzeugt · nur lesbar',
  copy: 'Kopieren',
  copied: 'Kopiert',
```

- [ ] **Step 2: Write the failing test**

Create `frontend/src/screens/Raw.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DraftProvider } from '../state/draft'
import { Raw } from './Raw'

const fetchMock = vi.fn()
const TOML = '[testbench-ai-service]\nport = 9999\n'

function renderRaw() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <DraftProvider saved={{ port: 8010 }}>
        <Raw lang="en" />
      </DraftProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  window.localStorage.clear()
  vi.stubGlobal('fetch', fetchMock)
  document.cookie = 'tbai_admin_csrf=token-123'
  fetchMock.mockReset()
  fetchMock.mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      valid: true,
      issues: [],
      diffs: [],
      restart_required: [],
      in_flight_tasks: 0,
      toml: TOML,
    }),
  } as Response)
})

describe('Raw', () => {
  it('shows the generated config.toml', async () => {
    renderRaw()

    expect(await screen.findByText(/port = 9999/)).toBeInTheDocument()
  })

  it('says the view is read-only and generated', async () => {
    renderRaw()

    expect(
      await screen.findByText('Generated from the current (unapplied) state · read-only'),
    ).toBeInTheDocument()
  })

  it('offers no editable control', async () => {
    renderRaw()

    await screen.findByText(/port = 9999/)
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('copies the text to the clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } })
    renderRaw()

    await screen.findByText(/port = 9999/)
    await userEvent.click(screen.getByRole('button', { name: 'Copy' }))

    await waitFor(() => expect(writeText).toHaveBeenCalledWith(TOML))
    expect(await screen.findByRole('button', { name: 'Copied' })).toBeInTheDocument()
  })

  it('reports a preview failure rather than rendering an empty file', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: 'config.toml is not valid TOML' }),
    } as Response)

    renderRaw()

    expect(await screen.findByRole('alert')).toHaveTextContent('config.toml is not valid TOML')
  })
})
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
cd frontend && npx vitest run src/screens/Raw.test.tsx
```

Expected: FAIL — cannot resolve `./Raw`.

- [ ] **Step 4: Write the implementation**

Create `frontend/src/screens/Raw.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { usePreview } from '../api/mutations'
import { useTranslations, type Lang } from '../i18n'
import { useDraft } from '../state/draft'

/**
 * The `config.toml` the current draft would write.
 *
 * It comes from `POST /config/preview` rather than being rendered in the
 * browser: the artboard hand-rolled a `toToml`, and two serializers for one
 * file is two chances to disagree about what is actually on disk.
 */
export function Raw({ lang }: { lang: Lang }) {
  const t = useTranslations(lang)
  const draft = useDraft()
  const preview = usePreview()
  const [copied, setCopied] = useState(false)

  const edits = JSON.stringify(draft.edits)
  useEffect(() => {
    preview.mutate(draft.edits)
    // Keyed on the serialized edits: the object identity changes on every
    // render, and re-previewing per render would hammer the endpoint.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [edits])

  const onCopy = () => {
    void navigator.clipboard.writeText(preview.data?.toml ?? '').then(() => {
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div
      style={{
        padding: '28px 32px',
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
        maxWidth: 1000,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <h2 style={{ margin: 0, fontSize: 30 }}>config.toml</h2>
        <span className="text-muted" style={{ fontSize: 12 }}>
          {t.rawSub}
        </span>
        <div style={{ flex: 1 }} />
        {preview.data && (
          <button type="button" className="btn btn-secondary" onClick={onCopy}>
            {copied ? t.copied : t.copy}
          </button>
        )}
      </div>

      {preview.isError && (
        <div role="alert" style={{ color: '#a33a2b' }}>
          {(preview.error as Error).message}
        </div>
      )}

      {preview.data && (
        <pre
          style={{
            margin: 0,
            padding: '16px 20px',
            fontSize: 12.5,
            lineHeight: 1.55,
            background: 'var(--color-surface)',
            border: '1px solid var(--color-divider)',
            overflow: 'auto',
            fontFamily: 'ui-monospace, Menlo, monospace',
          }}
        >
          {preview.data.toml}
        </pre>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
cd frontend && npx vitest run src/screens/Raw.test.tsx src/i18n/i18n.test.ts
```

Expected: PASS, all five plus the i18n parity test.

- [ ] **Step 6: Type-check and commit**

```bash
cd frontend && npm run build && npm test
cd .. && git add frontend/src/screens/Raw.tsx frontend/src/screens/Raw.test.tsx frontend/src/i18n/en.ts frontend/src/i18n/de.ts
git commit -m "Add the generated config.toml screen to the console"
```

---

### Task 20: Wire it together in `App`

The provider, the two banners, the Raw route and its nav entry. This is the task that makes phase 2 visible.

**Files:**
- Modify: `frontend/src/App.tsx`, `frontend/src/components/NavRail.tsx`
- Modify: `frontend/src/App.test.tsx`, `frontend/src/components/NavRail.test.tsx`

**Interfaces:**
- Consumes: `DraftProvider` (13), `PendingBanner` (17), `RestartBanner` (18), `Raw` (19), `ConfigSection` (16), `useConfig` from `./api/queries`
- Produces: nothing new — this is integration

- [ ] **Step 1: Add the Raw nav entry**

In `frontend/src/components/NavRail.tsx`, append to `NAV_ITEMS`:

```tsx
  {
    key: 'raw',
    path: '/admin/raw',
    labelKey: 'raw',
    icon: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M9 13h6M9 17h6',
    adminOnly: true,
  },
```

`raw` is already a key in both i18n dictionaries (`'Raw config.toml'` / `'Rohe config.toml'`), so no translation work is needed.

- [ ] **Step 2: Write the failing nav test**

Append to `frontend/src/components/NavRail.test.tsx`:

```tsx
it('offers the raw config screen to an admin', () => {
  renderNav({ isAdmin: true })

  expect(screen.getByRole('link', { name: /Raw config\.toml/ })).toHaveAttribute(
    'href',
    '/admin/raw',
  )
})

it('marks the raw config screen restricted for a non-admin', () => {
  renderNav({ isAdmin: false })

  expect(screen.getByRole('link', { name: /Raw config\.toml/ })).toHaveAttribute(
    'aria-disabled',
    'true',
  )
})
```

Use whatever render helper the file already has; if it renders `<NavRail lang="en" isAdmin={...} />` inline inside a `MemoryRouter`, follow that pattern rather than introducing a helper.

- [ ] **Step 3: Write the failing App test**

Append to `frontend/src/App.test.tsx`, following the existing file's mocking of `useSession` and `fetch`:

```tsx
it('shows the pending-changes banner when the draft has edits', async () => {
  window.localStorage.setItem('tbai_admin_draft', JSON.stringify({ port: 9999 }))

  renderApp({ isAdmin: true })

  expect(await screen.findByRole('status')).toHaveTextContent('unapplied changes')
})

it('shows no pending-changes banner for a clean draft', async () => {
  renderApp({ isAdmin: true })

  await screen.findByRole('navigation')
  expect(screen.queryByText(/unapplied changes/)).not.toBeInTheDocument()
})

it('does not show the pending-changes banner to a non-admin', async () => {
  // A read-only session cannot apply anything, so a count of queued changes
  // would be an offer it cannot honour.
  window.localStorage.setItem('tbai_admin_draft', JSON.stringify({ port: 9999 }))

  renderApp({ isAdmin: false })

  await screen.findByRole('navigation')
  expect(screen.queryByText(/unapplied changes/)).not.toBeInTheDocument()
})

it('routes /admin/raw to the raw config screen', async () => {
  renderApp({ isAdmin: true, route: '/admin/raw' })

  expect(await screen.findByRole('heading', { name: 'config.toml' })).toBeInTheDocument()
})
```

`App.test.tsx` already has a `renderApp` that takes no arguments and hard-codes `initialEntries={['/admin/status']}`, and an `asSession` helper that mocks `useSession`. Widen `renderApp` and give it the session, keeping the existing `fetch` stub in `beforeEach`:

```tsx
const renderApp = ({
  isAdmin = false,
  route = '/admin/status',
}: { isAdmin?: boolean; route?: string } = {}) => {
  asSession({
    username: 'a.mueller',
    roles: isAdmin ? ['Administrator'] : ['Test Manager'],
    is_admin: isAdmin,
    tb_server_url: 'https://tb:9443/api/',
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}
```

The existing tests in that file call `asSession(...)` themselves and then `renderApp()`. Calling `asSession` twice is harmless — the second `mockReturnValue` wins — but check each existing test still asserts what it means to: one that mocked an admin session and now renders through `renderApp()` would get a non-admin. Pass `{ isAdmin: true }` where that is what the test was testing.

Add `window.localStorage.clear()` to the file's `beforeEach`, or the draft written by one test leaks into the next.

- [ ] **Step 4: Run both tests to verify they fail**

```bash
cd frontend && npx vitest run src/App.test.tsx src/components/NavRail.test.tsx
```

Expected: FAIL — no `/admin/raw` route, no banner, no Raw nav entry.

- [ ] **Step 5: Wire up `App.tsx`**

Add the imports:

```tsx
import { PendingBanner } from './components/PendingBanner'
import { RestartBanner } from './components/RestartBanner'
import { Raw } from './screens/Raw'
import { DraftProvider } from './state/draft'
import { useConfig } from './api/queries'
```

Inside the component, above the signed-in return, add:

```tsx
  const config = useConfig()
  const [restartFields, setRestartFields] = useState<string[]>([])
```

Then replace the signed-in JSX's outer wrapper so the provider spans everything, and insert the banners between `TopBar` and the read-only strip:

```tsx
  return (
    // The draft is measured against the config *on disk* -- the draft is "what
    // will be written", and the running snapshot is fully defaulted, so
    // measuring against it would count every default the file omits as a
    // pending change. `disk` can be absent while the query is in flight; an
    // empty object then means "nothing saved yet", which prunes no edits and
    // is corrected as soon as the query lands.
    <DraftProvider saved={config.data?.disk ?? {}}>
      <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
        <TopBar
          session={session}
          lang={lang}
          theme={theme}
          onToggleTheme={() => setTheme(theme === 'light' ? 'dark' : 'light')}
          onSetLang={setLang}
          onSignOut={() => void signOut()}
        />
        {session.is_admin && <PendingBanner lang={lang} />}
        <RestartBanner lang={lang} fields={restartFields} />
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
              <Route path="/admin/status" element={<Status lang={lang} />} />
              <Route
                path="/admin/service"
                element={
                  <ConfigSection section="service" lang={lang} isAdmin={session.is_admin} />
                }
              />
              <Route
                path="/admin/llm"
                element={<ConfigSection section="llm" lang={lang} isAdmin={session.is_admin} />}
              />
              <Route
                path="/admin/logging"
                element={
                  <ConfigSection section="logging" lang={lang} isAdmin={session.is_admin} />
                }
              />
              <Route path="/admin/raw" element={<Raw lang={lang} />} />
              <Route path="*" element={<Navigate to="/admin/status" replace />} />
            </Routes>
          </main>
        </div>
      </div>
    </DraftProvider>
  )
```

- [ ] **Step 6: Raise the restart banner after an apply**

The apply response carries `restart_required`, and the dialog is where it arrives. Rather than lifting that state through three components, keep it where the server put it: the banner reads the *status* query, which already refetches every 15 seconds and is invalidated by `useApply`.

Add to `testbench_ai_service/webui/models.py`, on `StatusResponse`:

```python
    restart_required: list[str] = []
```

In `testbench_ai_service/webui/status.py`, `build_status` gains the comparison. Add the parameter and pass it through:

```python
def build_status(
    config: AppConfig,
    started_at: datetime,
    in_flight_tasks: int = 0,
    restart_required: list[str] | None = None,
) -> StatusResponse:
```

and in `testbench_ai_service/webui/routes.py`, `read_status` computes it by comparing the running config against the file on disk:

```python
@router.get("/status", response_model=StatusResponse)
async def read_status(
    request: Request,
    _: Session = Depends(current_session),
    config: AppConfig = Depends(get_app_config),
    registry: TaskRegistry = Depends(get_task_registry),
) -> StatusResponse:
    """Service facts, TestBench reachability, credential presence, agent counts,
    in-flight runs, and whether the file on disk has changes the process has
    not taken up.

    The restart list is derived rather than remembered: an operator who edits
    config.toml by hand, or who reloads the console after an apply, must still
    see the banner, and process state would not survive either.
    """
    on_disk, issues = validate_config_dict(read_config_file(Path(request.app.state.config_path)))
    pending = restart_required(config, on_disk) if on_disk is not None else []
    return build_status(config, request.app.state.started_at, registry.count, pending)
```

Add `restart_required=restart_required or []` to the `StatusResponse(...)` construction in `status.py`, and add the matching field to `frontend/src/api/types.ts`'s `StatusResponse`:

```ts
  restart_required: string[]
```

Then in `App.tsx`, replace the `useState` with the status query:

```tsx
  const status = useStatus()
  const restartFields = status.data?.restart_required ?? []
```

importing `useStatus` alongside `useConfig` and dropping the now-unused `useState` import if nothing else in the file needs it.

- [ ] **Step 7: Test the derived restart list**

Append to `tests/unit/webui/test_config_routes.py`:

```python
def test_status_reports_no_restart_needed_when_disk_matches_the_process(file_client, admin):
    admin()

    body = file_client.get("/admin/api/status").json()

    assert body["restart_required"] == []


def test_status_reports_a_restart_after_a_boot_fixed_change_is_written(
    file_client, admin, config_file
):
    admin()

    file_client.post(
        "/admin/api/config/apply",
        json={"edits": {"port": 9999}},
        headers=csrf(file_client),
    )
    body = file_client.get("/admin/api/status").json()

    assert body["restart_required"] == ["port"]


def test_status_reports_a_restart_for_a_hand_edited_file(file_client, admin, config_file):
    """An operator editing config.toml by hand must see the banner too."""
    admin()
    config_file.write_text(
        COMMENTED.replace("port = 8010", "port = 7777"), encoding="utf-8"
    )

    body = file_client.get("/admin/api/status").json()

    assert body["restart_required"] == ["port"]


def test_status_reports_no_restart_after_a_hot_swappable_apply(file_client, admin):
    admin()

    file_client.post(
        "/admin/api/config/apply",
        json={"edits": {"language": "en"}},
        headers=csrf(file_client),
    )
    body = file_client.get("/admin/api/status").json()

    assert body["restart_required"] == []


def test_status_survives_an_invalid_file_on_disk(file_client, admin, config_file):
    """A hand-edit that broke the file must not 500 the status screen."""
    admin()
    config_file.write_text(
        '[testbench-ai-service]\nport = "not a number"\n', encoding="utf-8"
    )

    response = file_client.get("/admin/api/status")

    assert response.status_code == 200
    assert response.json()["restart_required"] == []
```

- [ ] **Step 8: Run everything**

```bash
cd frontend && npx vitest run
cd .. && pytest tests/unit tests/integration -q
```

Expected: PASS on both. The frontend suite will flag any test that still renders `<ConfigSection>` without `isAdmin` — add the prop.

- [ ] **Step 9: Lint, type-check, commit**

```bash
ruff check . && ruff format --check . && mypy testbench_ai_service
cd frontend && npm run build && cd ..
git add frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/components/NavRail.tsx frontend/src/components/NavRail.test.tsx frontend/src/api/types.ts testbench_ai_service/webui/models.py testbench_ai_service/webui/status.py testbench_ai_service/webui/routes.py tests/unit/webui/test_config_routes.py
git commit -m "Wire config editing into the console shell"
```

---

### Task 21: Documentation

`docs/web-console.md` currently carries a prominent "This release is **read-only**" notice and says the role distinction does not matter yet. Both become wrong the moment Task 20 lands.

**Files:**
- Modify: `docs/web-console.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: nothing
- Produces: documentation

- [ ] **Step 1: Replace the read-only notice**

In `docs/web-console.md`, replace the `:::info` block that begins "This release is **read-only**" with:

```markdown
The console can change the Service, LLM provider and Logging settings. Agents,
per-project overrides and prompts are still read-only from the browser and
arrive in a later release.

:::caution
Changing configuration from the console rewrites `config.toml` on the server.
The previous contents are always kept alongside as `config.toml.bak`, and your
comments and formatting are preserved.
:::
```

- [ ] **Step 2: Correct the roles table**

Replace the two role rows and the sentence after them with:

```markdown
| Role                             | What you get                                       |
| -------------------------------- | -------------------------------------------------- |
| Global `Administrator`           | Full console, including changing configuration     |
| Any other role                   | Read-only console                                  |

Editing is Administrator-only. A non-admin session sees the same screens with
the values displayed rather than as form fields, and every route that changes
something refuses a non-admin regardless of what the browser sends.
```

- [ ] **Step 3: Document the editing workflow**

Add a new section after **Signing in**:

```markdown
---

## Changing configuration

Edits are queued, reviewed, then written — nothing is saved as you type.

1. Change fields on the **Service**, **LLM provider** or **Logging** screen. A
   strip appears at the top of the console counting the queued changes.
2. **View diff** shows the exact unified diff that would be written, the file
   it would be written to, and whether the change needs a service restart.
3. **Apply** validates the result, writes `config.toml` atomically, and reloads
   the service in place. **Discard** throws the queued changes away.

Queued changes live in your browser, so they survive a page reload and are not
visible to anyone else. Two administrators editing at once do not clobber each
other silently: the diff is always computed against the file as it is on disk at
that moment, so the second one to apply sees the first one's changes in the
diff.

### What is written

The console edits `config.toml` in place through a comment-preserving TOML
document. Your comments, key order and formatting survive a save, and only the
keys you actually changed are touched — the console never expands the file with
every default.

Clearing a field removes its key rather than writing an empty value, so the
setting returns to its documented default.

The previous contents are kept as `config.toml.bak` next to the file. That is a
single undo step, not a history: each save overwrites it.

A configuration the service could not start with is refused before anything is
written, with the error marked against the offending field. A rejected apply
cannot leave a file the service will not boot from.

### Hot reload and restart

Most changes take effect immediately. The service re-applies logging, reloads
translations, swaps the configuration every request reads, and rebuilds its LLM
clients.

These cannot be swapped in a running process:

| Setting | Why |
| --- | --- |
| `host`, `port` | Handed to the web server when it binds its socket |
| `ssl_cert`, `ssl_key`, `ssl_ca_cert` | Same — TLS is configured at bind time |
| `trusted_proxies` | Fixed when the middleware stack is built |
| An agent's `endpoint_path` or `class_path` | Agent routes are registered once, at startup |

Those are written to `config.toml` and then flagged: the console shows a
"restart needed" strip naming the settings involved, and the service keeps
running with its old values until you restart it. The console will not restart
the service for you — that only works reliably under a supervisor. See
[Windows service installation](windows-service-installation.md), or stop and
start the process however you normally run it.

### Raw config.toml

The **Raw config.toml** screen shows the file the current queued changes would
produce, generated by the server rather than the browser, so it is the actual
text an apply would write. It is read-only; **Copy** puts it on the clipboard.
```

- [ ] **Step 4: Note the two new LLM options in the console docs**

The LLM screen now shows `timeout` and `max_retries` (Task 1). They are documented in `docs/configuration.md` by that task; nothing further is needed here — confirm the option table there has both rows:

```bash
grep -n "max_retries\|timeout" docs/configuration.md | head
```

- [ ] **Step 5: Add the changelog entry**

`CHANGELOG.md` follows Keep a Changelog. Under `## [Unreleased]`, first correct the phase-1 entry: it currently ends "Nothing can be edited from the browser yet — configuration editing is planned for a later release." Change the entry's opening from "A read-only web console" to "A web console", and replace that closing sentence with "Agents, per-project overrides and prompts are still read-only from the browser."

Then add these two entries under the same `### Added` heading:

```markdown
- Configuration editing in the web console, for administrators. Change Service, LLM provider and
  Logging settings, review the exact unified diff before anything is written, then apply: the
  service rewrites `config.toml` atomically through a comment-preserving TOML document — your
  comments, key order and formatting survive, and only the keys you changed are touched — keeps
  the previous contents as `config.toml.bak`, and reloads in place. A configuration the service
  could not start with is refused before anything is written, with the error marked against the
  offending field. Settings the running process cannot take up (`host`, `port`, the TLS paths,
  `trusted_proxies`, and an agent's `endpoint_path` or `class_path`) are written and then flagged
  in a "restart needed" banner. A new **Raw config.toml** screen shows the file the pending
  changes would produce. Editing requires the global `Administrator` role; every other session
  keeps the read-only console. Documented in `docs/web-console.md`.
- `[testbench-ai-service.llm_config]` gains `timeout` and `max_retries`. Both were already
  forwarded to the provider SDKs when present in the file; declaring them makes them validated,
  documented, and editable from the console.
```

- [ ] **Step 6: Check the docs build if the project builds them**

```bash
ls docs/ && grep -rn "docusaurus\|mkdocs" pyproject.toml package.json 2>/dev/null | head
```

If a docs build exists, run it; if not, verify the internal link target exists:

```bash
ls docs/windows-service-installation.md docs/configuration.md
```

- [ ] **Step 7: Commit**

```bash
git add docs/web-console.md CHANGELOG.md
git commit -m "Document config editing in the web console"
```

---

### Task 22: Verify the assembled console

Everything is written; this task proves it works together, in the binary as well as in the tests.

**Files:**
- Test: no new files — this is verification

**Interfaces:**
- Consumes: everything
- Produces: evidence

- [ ] **Step 1: Run the whole test suite**

```bash
pytest tests -q
cd frontend && npm test && cd ..
```

Expected: PASS, with no skips that were not skipped before. Record the counts.

- [ ] **Step 2: Lint and type-check everything**

```bash
ruff check .
ruff format --check .
mypy testbench_ai_service
cd frontend && npm run build && cd ..
```

Expected: all clean. `npm run build` runs `tsc -b` first, so a type error fails it.

- [ ] **Step 3: Confirm no mutating route is reachable without admin and CSRF**

```bash
grep -n "@router.post\|@router.put\|@router.delete\|@router.patch" -A 12 testbench_ai_service/webui/routes.py | grep -n "router\.\|require_admin\|require_csrf"
```

Expected: every `post`/`put`/`delete`/`patch` route except `POST /session` (which *is* the login) shows both `require_admin` and `require_csrf`. `DELETE /session` legitimately has `require_csrf` and `current_session` but not `require_admin` — signing out is not an admin action.

- [ ] **Step 4: Confirm no endpoint leaks a credential value**

```bash
pytest tests/unit/webui -q -k "redact or sentinel or api_key"
grep -rn "REDACTED_SENTINEL" testbench_ai_service/webui/
```

Expected: the redaction tests pass, and the sentinel appears in `config_io.py` (defining it) and `edits.py` (refusing it) only.

- [ ] **Step 5: Smoke-test a real service against a real file**

```bash
mkdir -p ../tbai-phase2-smoke && cd ../tbai-phase2-smoke
cp E:/Testbench-ecosystem/testbench-ai-service/config_example.toml config.toml
python -c "import pathlib; p=pathlib.Path('config.toml'); p.write_text('# operator note at the top\n' + p.read_text(encoding='utf-8'), encoding='utf-8')"
python -m testbench_ai_service run --config config.toml
```

Check the CLI's actual flags first (`python -m testbench_ai_service --help`) — `docs/cli.md` documents them. Then in a browser open <http://127.0.0.1:8010/admin>, sign in as a TestBench administrator, and confirm by hand:

1. the Service form's fields are editable;
2. changing `language` raises the pending-changes strip with a count of 1;
3. **View diff** shows a one-line diff naming your `config.toml`;
4. **Apply** succeeds and the strip disappears;
5. `config.toml` still has `# operator note at the top` as its first line, and `config.toml.bak` holds the previous contents;
6. changing `port` and applying shows the restart-needed strip, and the service is still answering on the *old* port;
7. the Raw screen shows the file including your comment;
8. signing in as a non-admin shows read-only fields, no pending strip, and no Raw entry in the nav.

Then clean up:

```bash
cd E:/Testbench-ecosystem/testbench-ai-service && rm -rf ../tbai-phase2-smoke
```

- [ ] **Step 6: Confirm the binary still builds with the console in it**

```bash
python build_binary.py
```

Expected: a `dist/` build that completes. `tomlkit` is pure Python and is picked up from the import graph; if PyInstaller reports it missing at runtime, add `"tomlkit"` to `hiddenimports` in `testbench-ai-service.spec` and rebuild.

- [ ] **Step 7: Review the whole branch diff before proposing a merge**

```bash
git log --oneline main..HEAD
git diff --stat main...HEAD
```

Then invoke `superpowers:requesting-code-review`. Do not merge without it: this phase writes to the operator's filesystem and gates on an authorization check, which are the two things a fresh reviewer is most likely to catch a hole in.

---

## Notes for the executor

**Task order matters.** Tasks 1–12 are backend and strictly sequential: 4 needs 2 and 3, 11 needs 3–9, 12 needs 11. Tasks 13–19 are frontend and mostly independent of each other, but all of them need 13 and 14. Task 20 needs everything. Do not start 20 until 12 and 19 are both green.

**The two properties worth re-checking by hand at the end**, because a test can be made to pass without them actually holding:

1. A `config.toml` with comments still has them after an apply. Task 2's tests assert this on synthetic content; Task 22 Step 5 asserts it on a real file.
2. A non-admin cannot write. The frontend renders read-only, but that is cosmetic — the enforcement is `require_admin` on the route, and Task 22 Step 3 is the check that no route was added without it.

**If a task's test does not fail at its "verify it fails" step**, stop. Either the behaviour already exists (in which case the task is redundant and the plan is wrong about the codebase) or the test is not asserting what it claims. Both are worth raising before writing implementation code.

## Spec coverage

Spec section 12's phase-2 list, mapped to tasks:

| Spec item | Task |
|---|---|
| Draft state | 13 |
| Editable forms with validation surfacing | 15, 16 |
| `POST /config/preview` diff dialog | 11, 17 |
| `POST /config/apply` with atomic write and hot reload | 5, 10, 12 |
| Restart-required banner | 8, 18, 20 |
| In-flight task registry | 9 |
| Raw `config.toml` view | 19 |
| `LLMConfig.timeout` / `max_retries` (spec 11.2) | 1 |

Spec 11.4 (`templates_dir` in the Service form) is already satisfied: phase 1 put it in
`SERVICE_TABS`, and Task 16 makes it editable along with the rest.

Two items from spec 13's test list do not apply to this phase and are deliberately absent:

- *"a multi-file apply with one invalid file writes nothing at all"* — phase 2 writes exactly one
  file. The all-or-nothing property still holds trivially (Task 12 validates before writing), and
  the multi-file case arrives with the prompt files in phase 4.
- *`effAgent()` inheritance and `cleanProject()` pruning* — both are phase-3 concerns; there is no
  agent or project editing here.
