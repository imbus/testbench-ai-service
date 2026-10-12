# Admin Web UI Phase 4d — Per-Project LLM Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a project's `llm_config` editable from the console with inherit / override / remove semantics, and stop the service refusing to boot when a provider credential is missing.

**Architecture:** Almost entirely frontend. The console's edit path is already generic — `webui/edits.py` has no allowlist and `validate_config_dict` addresses pydantic errors through `join_path` — so `projects."<name>".llm_config.<field>` already validates, previews, writes and hot-reloads with no backend change. The LLM screen gains a scope tab strip extracted from `AgentDetail`, and each field is rendered with `Field`'s existing `inheritedFrom` prop. One backend task guards the unguarded `init_clients` call at boot.

**Tech Stack:** Python 3.10+ / FastAPI / pydantic v2 / pytest on the backend. React 18 + TypeScript + Vite + TanStack Query + react-router + vitest + @testing-library/react on the frontend.

**Spec:** `docs/superpowers/specs/2026-09-18-admin-web-ui-phase-4d-design.md` (binding authority — read it before Task 1; the parent spec is `docs/superpowers/specs/2026-09-08-admin-web-ui-design.md`)

## Global Constraints

Every task's requirements implicitly include this section.

- **Branch:** `admin-web-ui`. Do not branch off or merge to `main`.
- **Python floor is 3.10** (`pyproject.toml:12`). No `asyncio.timeout`, no `match` on anything exotic, no 3.11+ stdlib.
- **Line length is 100 columns, enforced by `ruff format`, not `ruff check`** — `E501` is disabled in `pyproject.toml`. Run `python -m ruff format` on every Python file you touch, then `python -m ruff check`.
- **Every commit message ends with this trailer, on its own last line:**
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`
  It is a trailer, not part of the subject line. Phase 4b shipped three commits with it glued onto the subject; do not repeat that.
- **i18n parity is enforced by a test.** `frontend/src/i18n/i18n.test.ts` asserts `Object.keys(de).sort()` equals `Object.keys(en).sort()` and that no value is the empty string. Every key added to `en.ts` must be added to `de.ts` in the same task.
- **German is the default language.** The console's default `lang` is `'de'`.
- **Config paths are built with `joinPath`, never string concatenation.** A project may be named `Release 2.0`; `'projects.' + name` tokenizes into the wrong table. Phase 4c shipped this bug as a Critical finding.
- **In-app navigation uses react-router `<Link>`, never `<a href>`.** A plain anchor is a full page load: it bypasses `useBlocker`, fires the browser's native leave-site dialog, and loses the operator's queued draft edits.
- **Frontend gates:** `npx tsc -b` clean and `npx vitest run` green, from `frontend/`. Run `npm run build` once, in the final task.
- **Type-only React imports are direct:** `import type { ComponentProps } from 'react'`. The `React.*` namespace is unavailable under this project's `react-jsx` transform without an explicit React import.
- **There are 54 failing tests + 3 errors in `tests/unit` that pre-date this work** (in `agents/`, `test_cli.py`, `utils/test_agent.py`, `test_tasks.py`). They fail identically on `main` — measured 2026-09-18: `main` is 55 failed + 3 errors, `admin-web-ui` is 54 failed + 3 errors. Do not fix them, and do not report them as regressions. Verify your own work with the targeted commands each task names.

---

## File Structure

**Created:**

| File | Responsibility |
|---|---|
| `frontend/src/components/ScopeTabs.tsx` | The Global / per-project tab strip and its add-project select. Extracted from `AgentDetail`, shared by it and the LLM screen. |
| `frontend/src/components/ScopeTabs.test.tsx` | Tests for the above. |

**Modified:**

| File | Change |
|---|---|
| `testbench_ai_service/main.py` | `init_services` stops letting a missing provider credential abort boot. |
| `tests/unit/test_main.py` | Tests for the above. |
| `tests/unit/utils/test_config.py` | Pins the sparse-override inheritance the whole screen rests on (design §7.1). |
| `frontend/src/screens/AgentDetail.tsx` | Uses `ScopeTabs` instead of its private `ScopeTab` + inline select. |
| `frontend/src/api/agents.ts` | Gains `projectLlmPath`, `scopedLlmPath`, `llmOverridingProjects`. |
| `frontend/src/api/agents.test.ts` | Tests for the above, including a dotted project name. |
| `frontend/src/screens/fields.ts` | `LLM_FIELDS` becomes `llmFields(scope)`; scoped keys and `allowEmpty` in project scope. |
| `frontend/src/screens/fields.test.ts` | Tests for the above. |
| `frontend/src/screens/ConfigSection.tsx` | Scope strip, scoped editing, inherited values, per-project credential notice. |
| `frontend/src/screens/ConfigSection.test.tsx` | Tests for the above; gains a `MemoryRouter` wrapper. |
| `frontend/src/screens/Projects.tsx` | The `llm_config` panel's label becomes a `<Link>` into the LLM screen. |
| `frontend/src/screens/Projects.test.tsx` | Tests for the above. |
| `frontend/src/i18n/en.ts`, `frontend/src/i18n/de.ts` | New keys, added in the task that first renders them. |
| `docs/configuration.md`, `CHANGELOG.md` | Operator-facing documentation. |

**Deliberately not modified:** any file under `testbench_ai_service/webui/`, `testbench_ai_service/models/`, or `testbench_ai_service/llm/`. Design §3.3 establishes that the edit, validation and write path already handles these paths. If you find yourself needing a backend change beyond Task 1, stop and report it — it means a design assumption was wrong.

---

### Task 1: Boot survives a missing provider credential

Implements design §5.1 and §3.1.

**Files:**
- Modify: `testbench_ai_service/main.py:29-35` (`init_services`)
- Test: `tests/unit/test_main.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: nothing later tasks import. `init_services(app: FastAPI) -> None` keeps its signature; only its failure behaviour changes.

- [ ] **Step 1: Read the precedent before writing anything**

Open `testbench_ai_service/webui/reload.py:173-186`. It wraps the same `init_clients` call in `try/except Exception`, sets a failure flag, and logs a warning. Your change makes boot agree with it. Do not invent a different message shape.

- [ ] **Step 2: Write the failing tests**

Add to `tests/unit/test_main.py`, inside `class TestCreateApp` (the file already defines `_make_app_config()` at module level and the class already has `_create_app_with_mock_config`):

```python
    def test_boot_survives_a_missing_provider_credential(self):
        """A missing API key must not stop the service starting.

        The console exists partly to repair a misconfigured provider, so the
        one configuration that cannot start is the one the operator most needs
        to fix. Asserts the app is built, not that a log line was emitted.
        """
        config = _make_app_config()
        with (
            patch("testbench_ai_service.main.load_translations"),
            patch("testbench_ai_service.main.LLMFactory") as mock_factory_cls,
        ):
            mock_factory = MagicMock()
            mock_factory.init_clients.side_effect = ValueError(
                "API key for provider 'openai' not found in environment variables."
            )
            mock_factory.close_clients = AsyncMock()
            mock_factory_cls.return_value = mock_factory

            app = create_app(config)

        assert isinstance(app, FastAPI)
        # The factory is still on the app: clients are created on demand by
        # get_client, so the next agent request is where a genuinely missing
        # credential surfaces -- which is where it is actionable.
        assert app.state.llm_factory is mock_factory
        mock_factory.init_clients.assert_called_once()

    def test_boot_failure_is_logged_as_a_warning(self):
        """The operator gets told, on the one channel available at boot."""
        config = _make_app_config()
        with (
            patch("testbench_ai_service.main.load_translations"),
            patch("testbench_ai_service.main.LLMFactory") as mock_factory_cls,
            patch("testbench_ai_service.main.logger") as mock_logger,
        ):
            mock_factory = MagicMock()
            mock_factory.init_clients.side_effect = ValueError("no key")
            mock_factory.close_clients = AsyncMock()
            mock_factory_cls.return_value = mock_factory

            create_app(config)

        assert mock_logger.warning.called

    def test_keyboard_interrupt_during_boot_still_propagates(self):
        """BaseException is not swallowed: Ctrl-C must still stop the process."""
        config = _make_app_config()
        with (
            patch("testbench_ai_service.main.load_translations"),
            patch("testbench_ai_service.main.LLMFactory") as mock_factory_cls,
        ):
            mock_factory = MagicMock()
            mock_factory.init_clients.side_effect = KeyboardInterrupt()
            mock_factory.close_clients = AsyncMock()
            mock_factory_cls.return_value = mock_factory

            with pytest.raises(KeyboardInterrupt):
                create_app(config)
```

Add `import pytest` to the file's imports if it is not already there.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_main.py -v -k "boot or keyboard"`
Expected: `test_boot_survives_a_missing_provider_credential` and `test_boot_failure_is_logged_as_a_warning` FAIL with `ValueError: API key for provider 'openai' not found...` escaping `create_app`. `test_keyboard_interrupt_during_boot_still_propagates` PASSES already (nothing catches it yet) — that is correct, it is a regression guard for Step 4.

- [ ] **Step 4: Write the implementation**

Replace `init_services` in `testbench_ai_service/main.py`:

```python
def init_services(app: FastAPI):
    """Initialization of app singleton services"""

    # Initialize a singleton instance of LLMFactory and add it to the application state
    app.state.llm_factory = LLMFactory()
    try:
        app.state.llm_factory.init_clients([app.state.config.llm_config])
    except Exception as e:
        # Pre-initialising the clients is an optimisation, not a precondition:
        # LLMFactory.get_client creates them on demand. Letting a missing
        # credential abort startup makes the one configuration the console
        # exists to repair the one the operator cannot start the console to
        # repair. reload.py:173-186 already treats the same call this way
        # after a config apply; this makes boot agree with reload.
        #
        # Exception, not BaseException: a KeyboardInterrupt during startup
        # must still stop the process rather than being logged and ignored.
        logger.warning(
            "Could not pre-initialise the LLM clients at startup: %r. The clients will be "
            "created on demand; a missing provider credential will surface on the next agent "
            "request.",
            e,
        )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_main.py -v`
Expected: PASS, all three new tests plus every pre-existing test in the file.

- [ ] **Step 6: Verify it end to end, not just in a mock**

Run, from the repo root, with no provider key in the environment:

```bash
env -u OPENAI_API_KEY -u ANTHROPIC_API_KEY python -c "
from unittest.mock import patch
from testbench_ai_service.config import AppConfig
from testbench_ai_service.main import create_app
with (
    patch('testbench_ai_service.config.validate_tb_server_url'),
    patch('testbench_ai_service.config.AppConfig.validate_prompt_paths', return_value=None),
    patch('testbench_ai_service.config.AppConfig.validate_prompts_dir_exists', return_value=None),
):
    config = AppConfig()
app = create_app(config)
print('booted:', app.title)
"
```
Expected: prints `booted: TestBench AI Service` with a warning logged above it. Before the fix this raises `ValueError`. Record the actual output in your task report — the mocked test proves the guard, this proves the guard is on the real path.

- [ ] **Step 7: Lint and commit**

```bash
python -m ruff format testbench_ai_service/main.py tests/unit/test_main.py
python -m ruff check testbench_ai_service/main.py tests/unit/test_main.py
git add testbench_ai_service/main.py tests/unit/test_main.py
git commit -m "Let the service boot without a provider credential

Pre-initialising the LLM clients is an optimisation, not a precondition:
get_client creates them on demand. Aborting startup on a missing key made
the one configuration the console exists to repair also the one the operator
could not start the console to repair. reload.py already treats the same call
this way after an apply; boot now agrees with it.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Pin the sparse-override inheritance the screen rests on

Implements design §7.1 and §3.2. No production code changes — this is the regression guard for the semantics every later task assumes.

**Files:**
- Test: `tests/unit/utils/test_config.py`

**Interfaces:**
- Consumes: `get_llm_config(config, project_name=None, request_config=None)` from `testbench_ai_service.utils.config`.
- Produces: nothing.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/utils/test_config.py`. Check the file's existing import block first and add only what is missing:

```python
class TestProjectLlmConfigInheritance:
    """The property the console's per-project LLM form is built on.

    A project block is *sparse*: it states only what it overrides, and every
    other field must come from the global table. LLMConfig has its own
    defaults (provider=openai, auth_method=api_key), so if the merge ever
    stopped using exclude_unset those defaults would silently overwrite the
    operator's global provider -- and the project form would start writing
    them into config.toml as if the operator had chosen them.
    """

    def _config(self):
        return AppConfig(
            **{
                "llm_config": {
                    "provider": "anthropic",
                    "model": "claude-opus-5",
                    "max_retries": 7,
                },
                "projects": {"Release 2.0": {"llm_config": {"timeout": 12.5}}},
            }
        )

    def test_unstated_fields_are_inherited_from_the_global_table(self):
        merged = get_llm_config(self._config(), project_name="Release 2.0")

        assert merged.provider == LLMProvider.ANTHROPIC
        assert merged.model == "claude-opus-5"
        assert merged.max_retries == 7

    def test_the_stated_field_wins(self):
        merged = get_llm_config(self._config(), project_name="Release 2.0")

        assert merged.timeout == 12.5

    def test_the_project_block_dumps_only_what_it_states(self):
        """The mechanism itself, pinned separately from its effect.

        If this dump ever grows a second key, the assertions above start
        passing for the wrong reason.
        """
        project = self._config().projects["Release 2.0"].llm_config

        assert project.model_dump(exclude_unset=True) == {"timeout": 12.5}

    def test_a_project_without_an_llm_block_gets_the_global_table(self):
        config = AppConfig(
            **{
                "llm_config": {"provider": "anthropic", "model": "claude-opus-5"},
                "projects": {"Release 2.0": {"language": "en"}},
            }
        )

        merged = get_llm_config(config, project_name="Release 2.0")

        assert merged.provider == LLMProvider.ANTHROPIC
        assert merged.model == "claude-opus-5"
```

The imports this needs: `AppConfig` from `testbench_ai_service.config`, `get_llm_config` from `testbench_ai_service.utils.config`, and `LLMProvider` from `testbench_ai_service.models.config`. If `AppConfig()` construction in this file is guarded by the `validate_tb_server_url` / `validate_prompt_paths` patches used in `tests/unit/test_main.py`, follow whatever pattern the surrounding tests in this file already use rather than introducing a new one.

- [ ] **Step 2: Run the tests**

Run: `python -m pytest tests/unit/utils/test_config.py -v -k ProjectLlmConfigInheritance`
Expected: PASS, all four. These describe behaviour that already works — they are a guard, not a red-green cycle. If any fails, **stop and report**: a design finding measured on 2026-09-18 is wrong, and Tasks 5-6 rest on it.

- [ ] **Step 3: Mutation-verify the guard**

A test that cannot fail is not a guard. Temporarily change `utils/config.py:398-400` from
`update=project_config.llm_config.model_dump(exclude_unset=True)` to
`update=project_config.llm_config.model_dump()` and re-run.
Expected: `test_unstated_fields_are_inherited_from_the_global_table` FAILS (provider becomes `openai`). **Revert the change** and confirm the suite is green again. Record both outcomes in your report.

- [ ] **Step 4: Lint and commit**

```bash
python -m ruff format tests/unit/utils/test_config.py
python -m ruff check tests/unit/utils/test_config.py
git add tests/unit/utils/test_config.py
git commit -m "Pin per-project LLM config inheritance

The console's per-project LLM form reads 'no key in the project block' as
'inherits from global'. That is only true while the merge uses
exclude_unset, so pin it: a project stating only timeout must keep the
global provider, model and max_retries.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Extract `ScopeTabs` from `AgentDetail`

Implements design D4. A pure refactor: `AgentDetail`'s existing tests must stay green without being edited.

**Files:**
- Create: `frontend/src/components/ScopeTabs.tsx`
- Create: `frontend/src/components/ScopeTabs.test.tsx`
- Modify: `frontend/src/screens/AgentDetail.tsx` (remove the private `ScopeTab` at lines 390-421 and the inline tab strip at lines ~180-217)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces, and Task 6 relies on exactly this:

```ts
export function ScopeTabs(props: {
  projects: string[]          // project tabs to show, in order
  selected: string | null     // null = the Global tab
  addable: string[]           // offered by the add-project select
  onSelect: (project: string | null) => void
  globalLabel: string         // already-translated
  addLabel: string            // already-translated
}): JSX.Element
```

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/ScopeTabs.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ScopeTabs } from './ScopeTabs'

function renderTabs(overrides: Partial<Parameters<typeof ScopeTabs>[0]> = {}) {
  const onSelect = vi.fn()
  render(
    <ScopeTabs
      projects={['Alpha', 'Release 2.0']}
      selected={null}
      addable={['Beta']}
      onSelect={onSelect}
      globalLabel="Global"
      addLabel="add project"
      {...overrides}
    />,
  )
  return { onSelect }
}

test('the global tab is selected when no project is', () => {
  renderTabs()
  expect(screen.getByRole('tab', { name: 'Global' })).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByRole('tab', { name: 'Alpha' })).toHaveAttribute('aria-selected', 'false')
})

test('a project tab is selected when it is the current scope', () => {
  renderTabs({ selected: 'Release 2.0' })
  expect(screen.getByRole('tab', { name: 'Release 2.0' })).toHaveAttribute(
    'aria-selected',
    'true',
  )
  expect(screen.getByRole('tab', { name: 'Global' })).toHaveAttribute('aria-selected', 'false')
})

test('choosing the global tab reports null, not a name', async () => {
  const { onSelect } = renderTabs({ selected: 'Alpha' })
  await userEvent.click(screen.getByRole('tab', { name: 'Global' }))
  expect(onSelect).toHaveBeenCalledWith(null)
})

test('choosing a project tab reports its name', async () => {
  const { onSelect } = renderTabs()
  await userEvent.click(screen.getByRole('tab', { name: 'Alpha' }))
  expect(onSelect).toHaveBeenCalledWith('Alpha')
})

test('the add select offers only projects without a tab', () => {
  renderTabs()
  const select = screen.getByRole('combobox', { name: 'add project' })
  expect(select).toHaveTextContent('Beta')
  expect(select).not.toHaveTextContent('Alpha')
})

test('picking from the add select selects that project', async () => {
  const { onSelect } = renderTabs()
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'add project' }), 'Beta')
  expect(onSelect).toHaveBeenCalledWith('Beta')
})

test('the add select is absent when every known project already has a tab', () => {
  renderTabs({ addable: [] })
  expect(screen.queryByRole('combobox', { name: 'add project' })).not.toBeInTheDocument()
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/ScopeTabs.test.tsx`
Expected: FAIL — `Failed to resolve import "./ScopeTabs"`.

- [ ] **Step 3: Write the component**

Create `frontend/src/components/ScopeTabs.tsx`. The tab markup is moved verbatim from `AgentDetail.tsx:390-421` and the select from `AgentDetail.tsx:199-216`; keep the styling identical so the refactor is invisible on screen:

```tsx
/**
 * The Global / per-project scope switcher.
 *
 * Shared by the Agents screen and the LLM screen so there is one answer to
 * "edit this globally or per project" rather than two that drift apart.
 *
 * Choosing a scope is navigation, never an edit: this component reports the
 * choice and holds no draft state. Writing an empty override table on
 * selection would put a change in the operator's diff they never asked for.
 */
export function ScopeTabs({
  projects,
  selected,
  addable,
  onSelect,
  globalLabel,
  addLabel,
}: {
  /** Project tabs to show, in order. */
  projects: string[]
  /** The current scope; `null` is the Global tab. */
  selected: string | null
  /** Projects offered by the add select — those without a tab. */
  addable: string[]
  onSelect: (project: string | null) => void
  /** Already translated by the caller: this component holds no dictionary. */
  globalLabel: string
  addLabel: string
}) {
  return (
    <div
      role="tablist"
      style={{ display: 'flex', gap: 18, alignItems: 'center', flexWrap: 'wrap' }}
    >
      <ScopeTab label={globalLabel} selected={selected === null} onSelect={() => onSelect(null)} />
      {projects.map((name) => (
        <ScopeTab
          key={name}
          label={name}
          selected={selected === name}
          onSelect={() => onSelect(name)}
        />
      ))}
      {addable.length > 0 && (
        <select
          className="input"
          aria-label={addLabel}
          value=""
          style={{ fontSize: 13, width: 'auto' }}
          onChange={(event) => {
            if (event.target.value) onSelect(event.target.value)
          }}
        >
          <option value="">+ {addLabel}</option>
          {addable.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      )}
    </div>
  )
}

function ScopeTab({
  label,
  selected,
  onSelect,
}: {
  label: string
  selected: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      role="tab"
      className="tb-chip"
      aria-selected={selected}
      onClick={onSelect}
      style={{
        // A chip, as the artboard draws the scope switcher -- but still a tab,
        // because that is what selecting a scope is.
        border: '1px solid var(--color-divider)',
        padding: '4px 12px',
        font: 'inherit',
        fontSize: 13,
        background: selected ? 'var(--color-accent)' : 'transparent',
        color: selected ? 'var(--color-bg)' : 'inherit',
        cursor: 'pointer',
      }}
    >
      {label}
    </button>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/components/ScopeTabs.test.tsx`
Expected: PASS (7 tests).

- [ ] **Step 5: Use it in `AgentDetail`**

In `frontend/src/screens/AgentDetail.tsx`:
1. Add `import { ScopeTabs } from '../components/ScopeTabs'`.
2. Replace the whole `<div role="tablist">…</div>` block (the one containing the `ScopeTab` list and the `addable` select) with:

```tsx
      <ScopeTabs
        projects={tabs}
        selected={project}
        addable={addable}
        onSelect={setProject}
        globalLabel={t.globalScope}
        addLabel={t.addProjectOverride}
      />
```

3. Delete the now-unused private `function ScopeTab({...})` at the bottom of the file.

Leave `tabs`, `addable`, `overriders` and every other computation exactly as they are — they are the component's inputs now, not its internals.

- [ ] **Step 6: Run the tests that pin the refactor**

Run: `cd frontend && npx vitest run src/screens/AgentDetail.test.tsx src/components/ScopeTabs.test.tsx`
Expected: PASS. **Do not edit `AgentDetail.test.tsx`.** Those 29 tests are what proves this refactor changed nothing; if one fails, the extraction is wrong, not the test.

- [ ] **Step 7: Typecheck, run the whole frontend suite, commit**

```bash
cd frontend && npx tsc -b && npx vitest run
```
Expected: `tsc` clean; the full suite green.

```bash
git add frontend/src/components/ScopeTabs.tsx frontend/src/components/ScopeTabs.test.tsx frontend/src/screens/AgentDetail.tsx
git commit -m "Extract the scope tab strip from AgentDetail

The LLM screen needs the same Global/per-project switcher. A second copy is
how phase 4b's cross-task drift happened, so share one component instead.
Pure refactor: AgentDetail's own tests are unchanged and still green.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Scoped LLM path helpers

Implements design §5.3 and §5.2's tab source. Pure functions, no rendering.

**Files:**
- Modify: `frontend/src/api/agents.ts` (append; it already holds `projectPath`, `scopedAgentPath`, `overridingProjects`)
- Test: `frontend/src/api/agents.test.ts`

**Interfaces:**
- Consumes: `joinPath` from `./paths`, and the existing `Scope` type and `table()` helper already in `agents.ts`.
- Produces, used by Tasks 5 and 6:

```ts
export function projectLlmPath(project: string, setting?: string): string
export function scopedLlmPath(scope: Scope, setting?: string): string
export function llmOverridingProjects(config: Record<string, unknown>): string[]
```

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/api/agents.test.ts`. Add the three new names to the existing import from `./agents`:

```ts
describe('scopedLlmPath', () => {
  test('global scope addresses the top-level llm_config table', () => {
    expect(scopedLlmPath({ kind: 'global' }, 'provider')).toBe('llm_config.provider')
  })

  test('project scope addresses the project’s own llm_config table', () => {
    expect(scopedLlmPath({ kind: 'project', project: 'Alpha' }, 'provider')).toBe(
      'projects.Alpha.llm_config.provider',
    )
  })

  test('a dotted project name is quoted, not concatenated', () => {
    // Phase 4c shipped this exact bug as a Critical finding: string
    // concatenation makes 'Release 2.0' tokenize as two segments, addressing
    // a table that does not exist -- silently.
    expect(scopedLlmPath({ kind: 'project', project: 'Release 2.0' }, 'provider')).toBe(
      'projects."Release 2.0".llm_config.provider',
    )
  })

  test('the quoted path tokenizes back to the four segments it means', () => {
    expect(splitPath(scopedLlmPath({ kind: 'project', project: 'Release 2.0' }, 'provider'))).toEqual(
      ['projects', 'Release 2.0', 'llm_config', 'provider'],
    )
  })

  test('without a setting it addresses the table itself', () => {
    expect(scopedLlmPath({ kind: 'project', project: 'Alpha' })).toBe('projects.Alpha.llm_config')
    expect(scopedLlmPath({ kind: 'global' })).toBe('llm_config')
  })
})

describe('llmOverridingProjects', () => {
  test('lists the projects declaring an llm_config table, in config order', () => {
    const config = {
      projects: {
        Alpha: { llm_config: { model: 'gpt-5' } },
        Beta: { language: 'en' },
        'Release 2.0': { llm_config: {} },
      },
    }
    expect(llmOverridingProjects(config)).toEqual(['Alpha', 'Release 2.0'])
  })

  test('an empty llm_config table still counts', () => {
    // It is a block the operator wrote. Hiding it would make the tab strip
    // disagree with the file.
    expect(llmOverridingProjects({ projects: { Alpha: { llm_config: {} } } })).toEqual(['Alpha'])
  })

  test('a null llm_config does not count', () => {
    // `running` is a pydantic dump, so an unset optional is present as an
    // explicit null. That is "no opinion", not an override.
    expect(llmOverridingProjects({ projects: { Alpha: { llm_config: null } } })).toEqual([])
  })

  test('no projects table is not an error', () => {
    expect(llmOverridingProjects({})).toEqual([])
  })
})
```

Add `splitPath` to the file's import from `./paths` if it is not already imported.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/api/agents.test.ts`
Expected: FAIL — `scopedLlmPath is not a function` / `llmOverridingProjects is not a function`.

- [ ] **Step 3: Write the implementation**

Append to `frontend/src/api/agents.ts`:

```ts
/** Address a setting on a project's own `[projects.<name>.llm_config]` table. */
export function projectLlmPath(project: string, setting?: string): string {
  const tail = setting ? setting.split('.') : []
  return joinPath(['projects', project, 'llm_config', ...tail])
}

/** Address an LLM setting for whichever scope is in play. */
export function scopedLlmPath(scope: Scope, setting?: string): string {
  const tail = setting ? setting.split('.') : []
  return scope.kind === 'global'
    ? joinPath(['llm_config', ...tail])
    : projectLlmPath(scope.project, setting)
}

/**
 * The names of the projects that override `llm_config`, in config order.
 *
 * An empty table counts, for the same reason it does in `overridingProjects`:
 * `[projects.Alpha.llm_config]` with nothing under it is still a block the
 * operator wrote, and hiding it would make the scope strip disagree with the
 * file.
 */
export function llmOverridingProjects(config: Record<string, unknown>): string[] {
  const projects = table(config.projects)
  if (!projects) return []
  return Object.keys(projects).filter((name) => table(table(projects[name])?.llm_config) !== undefined)
}
```

`table()` already returns `undefined` for `null`, so the null case needs no extra branch.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/api/agents.test.ts`
Expected: PASS, including the 22 pre-existing tests in the file.

- [ ] **Step 5: Typecheck and commit**

```bash
cd frontend && npx tsc -b
git add frontend/src/api/agents.ts frontend/src/api/agents.test.ts
git commit -m "Add scoped llm_config path helpers

Built with joinPath, never concatenation: a project named 'Release 2.0'
otherwise tokenizes into a table that does not exist, which is the bug
phase 4c shipped as a Critical finding.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Scope-aware LLM field specs

Implements design §5.3 and §3.6.

**Files:**
- Modify: `frontend/src/screens/fields.ts:102-128` (the `LLM_FIELDS` constant)
- Test: `frontend/src/screens/fields.test.ts`

**Interfaces:**
- Consumes: `scopedLlmPath` and `Scope` from Task 4 (`../api/agents`).
- Produces, used by Task 6:

```ts
export function llmFields(scope: Scope): FieldSpec[]
export const LLM_FIELDS: FieldSpec[]   // === llmFields({ kind: 'global' })
```

Each returned spec carries `setting` (`'provider'`, `'model'`, …), which Task 6 uses to read the global value for the inherited note without having to parse it back out of `key`.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/screens/fields.test.ts`:

```ts
describe('llmFields', () => {
  test('global scope keeps the existing top-level keys', () => {
    const keys = llmFields({ kind: 'global' }).map((field) => field.key)
    expect(keys).toEqual([
      'llm_config.provider',
      'llm_config.model',
      'llm_config.auth_method',
      'llm_config.azure_endpoint',
      'llm_config.api_version',
      'llm_config.class_path',
      'llm_config.timeout',
      'llm_config.max_retries',
    ])
  })

  test('LLM_FIELDS stays the global list, so existing callers are unchanged', () => {
    expect(LLM_FIELDS).toEqual(llmFields({ kind: 'global' }))
  })

  test('project scope addresses the project table', () => {
    const keys = llmFields({ kind: 'project', project: 'Alpha' }).map((field) => field.key)
    expect(keys[0]).toBe('projects.Alpha.llm_config.provider')
    expect(keys[7]).toBe('projects.Alpha.llm_config.max_retries')
  })

  test('a dotted project name is quoted', () => {
    const keys = llmFields({ kind: 'project', project: 'Release 2.0' }).map((field) => field.key)
    expect(keys[0]).toBe('projects."Release 2.0".llm_config.provider')
  })

  test('selects gain a way back to inheriting in project scope', () => {
    // Without allowEmpty a select can only move between its options, so an
    // override could be set and never taken back off.
    const provider = llmFields({ kind: 'project', project: 'Alpha' }).find(
      (field) => field.setting === 'provider',
    )
    expect(provider?.type).toBe('select')
    expect(provider?.allowEmpty).toBe(true)
  })

  test('selects have no blank option globally', () => {
    // The service always has a provider; offering "none" there would be a
    // setting that cannot boot.
    const provider = llmFields({ kind: 'global' }).find((field) => field.setting === 'provider')
    expect(provider?.allowEmpty).toBeUndefined()
  })

  test('every field carries the setting it edits', () => {
    for (const field of llmFields({ kind: 'project', project: 'Alpha' })) {
      expect(field.setting, `no setting on ${field.key}`).toBeTruthy()
      expect(field.key.endsWith(field.setting as string)).toBe(true)
    }
  })

  test('options and hints survive the scoping', () => {
    const provider = llmFields({ kind: 'project', project: 'Alpha' }).find(
      (field) => field.setting === 'provider',
    )
    expect(provider?.options).toEqual(['openai', 'azure_openai', 'anthropic', 'custom'])
    expect(provider?.hint).toBeTruthy()
  })
})
```

Add `llmFields` and `LLM_FIELDS` to the file's import from `./fields`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/screens/fields.test.ts`
Expected: FAIL — `llmFields is not a function`.

- [ ] **Step 3: Write the implementation**

In `frontend/src/screens/fields.ts`, add the import at the top:

```ts
import { scopedLlmPath } from '../api/agents'
import type { Scope } from '../api/agents'
```

Then replace the whole `export const LLM_FIELDS: FieldSpec[] = [ … ]` block with:

```ts
/** The `llm_config` settings, independent of the scope that holds them. */
const LLM_SETTINGS: Omit<FieldSpec, 'key'>[] = [
  {
    setting: 'provider',
    type: 'select',
    options: ['openai', 'azure_openai', 'anthropic', 'custom'],
    hint: 'gpt-*/o-series route to OpenAI, claude-* to Anthropic, regardless of this setting',
  },
  {
    setting: 'model',
    type: 'text',
    hint: "Global override. When empty, each prompt variant's model is used.",
  },
  { setting: 'auth_method', type: 'text', hint: 'Azure only: api_key or entra_id' },
  { setting: 'azure_endpoint', type: 'text', hint: 'Required for Azure' },
  { setting: 'api_version', type: 'text', hint: 'Required for Azure' },
  { setting: 'class_path', type: 'text', hint: 'Custom LLMClient subclass' },
  {
    setting: 'timeout',
    type: 'number',
    hint: "Seconds to wait for an LLM response. Empty uses the provider SDK's default.",
  },
  {
    setting: 'max_retries',
    type: 'number',
    hint: "Retries after a failed LLM request. Empty uses the provider SDK's default.",
  },
]

/**
 * The LLM fields, addressed at one scope.
 *
 * In project scope every control must be removable, so selects gain the blank
 * option that is the only thing wired to `draft.unsetValue`. Globally they
 * must not: the service always has a provider, and offering "none" there is a
 * setting that cannot boot.
 */
export function llmFields(scope: Scope): FieldSpec[] {
  const project = scope.kind === 'project'
  return LLM_SETTINGS.map((spec) => ({
    ...spec,
    key: scopedLlmPath(scope, spec.setting),
    ...(project && spec.type === 'select' ? { allowEmpty: true } : {}),
  }))
}

export const LLM_FIELDS: FieldSpec[] = llmFields({ kind: 'global' })
```

`FieldSpec.setting` already exists on the interface (`fields.ts:33`), declared for the agent screens; this reuses it rather than adding a parallel field.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/screens/fields.test.ts src/screens/ConfigSection.test.tsx`
Expected: PASS. `ConfigSection` still imports `LLM_FIELDS` and must be unaffected at this point.

- [ ] **Step 5: Typecheck and commit**

```bash
cd frontend && npx tsc -b && npx vitest run
git add frontend/src/screens/fields.ts frontend/src/screens/fields.test.ts
git commit -m "Make the LLM field specs scope-aware

One list of settings, addressed at either the global table or a project's.
Selects gain a blank option in project scope: it is the only control wired
to unsetValue, so without it an override could be set and never removed.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: The LLM screen edits a project's config

The increment's centre. Implements design §5.2, §5.3, §5.4 and D2, D3, D5.

**Files:**
- Modify: `frontend/src/screens/ConfigSection.tsx`
- Modify: `frontend/src/i18n/en.ts`, `frontend/src/i18n/de.ts`
- Test: `frontend/src/screens/ConfigSection.test.tsx`

**Interfaces:**
- Consumes: `ScopeTabs` (Task 3), `scopedLlmPath` / `llmOverridingProjects` (Task 4), `llmFields` (Task 5), plus the existing `useProjects`, `useModels`, `configuredProjects`, `valueAt` and `Field`.
- Produces: nothing later tasks import. Task 7 links to `/admin/llm?project=<name>`, which this task makes meaningful.

**The rule that this task exists to get right.** In project scope, `saved` comes from `disk` **only** — never from `running`. Measured on 2026-09-18: a project declaring only `timeout = 12.5` dumps into `running` as

```json
{ "provider": "openai", "auth_method": "api_key", "model": null, "timeout": 12.5, … }
```

because a pydantic dump fills every default. Reading `saved` from `running` would therefore show `provider` as overridden to `openai` on a project that actually inherits `anthropic` — wrong on screen, and one keystroke away from writing that default into the operator's file. Global scope keeps the existing `disk ?? running` fallback, which is correct there.

- [ ] **Step 1: Add the translation keys**

In `frontend/src/i18n/en.ts`:

```ts
  llmScopeHint: 'Empty fields inherit from the global configuration.',
  projectKeyPresent: 'This project has its own key; its runs use it.',
  projectKeyAbsent: 'No project key; runs fall back to the global credential.',
  credentialsHeading: 'Credentials',
```

In `frontend/src/i18n/de.ts`, at the same position:

```ts
  llmScopeHint: 'Leere Felder werden aus der globalen Konfiguration übernommen.',
  projectKeyPresent: 'Dieses Projekt hat einen eigenen Schlüssel; seine Läufe verwenden ihn.',
  projectKeyAbsent: 'Kein Projektschlüssel; Läufe verwenden die globale Zugangsdaten.',
  credentialsHeading: 'Zugangsdaten',
```

`globalScope` and `addProjectOverride` already exist — `AgentDetail` uses them. Do not add duplicates.

- [ ] **Step 2: Write the failing tests**

In `frontend/src/screens/ConfigSection.test.tsx`, first wrap the render helper in a router — `useSearchParams` throws outside one. Add to the imports:

```tsx
import { MemoryRouter } from 'react-router-dom'
import { de } from '../i18n/de'
import { DRAFT_STORAGE_KEY } from '../state/draft'
```

`DRAFT_STORAGE_KEY` is `'tbai_admin_draft'`, exported from `state/draft.tsx:13` — import the constant rather than repeating the literal, so a future rename cannot leave these tests asserting against a key nothing writes.

and give `renderSection` an `initialEntries` option, wrapping the existing tree:

```tsx
  return render(
    <MemoryRouter initialEntries={[initialEntries]}>
      <QueryClientProvider client={client}>
        <DraftProvider saved={disk}>
          <ConfigSection section={section} lang="de" isAdmin={isAdmin} issues={issues} />
        </DraftProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
```

with `initialEntries = '/admin/llm'` added to the destructured options and its type `string`. Every existing test keeps passing unchanged.

Then append:

```tsx
const PROJECT_CONFIG = {
  running: {
    ...CONFIG.running,
    llm_config: { provider: 'anthropic', model: 'claude-opus-5', timeout: null },
    projects: {
      Alpha: {
        language: null,
        // As the backend really dumps it: every default filled in.
        llm_config: {
          provider: 'openai',
          auth_method: 'api_key',
          model: null,
          timeout: 12.5,
          max_retries: null,
          extra_models: {},
        },
        agents: null,
      },
    },
  },
  disk: {
    llm_config: { provider: 'anthropic', model: 'claude-opus-5' },
    projects: { Alpha: { llm_config: { timeout: 12.5 } } },
  },
  config_path: '/tmp/config.toml',
}

function renderLlm(options: { initialEntries?: string; isAdmin?: boolean } = {}) {
  return renderSection({
    section: 'llm',
    isAdmin: options.isAdmin ?? true,
    running: PROJECT_CONFIG.running,
    disk: PROJECT_CONFIG.disk,
    initialEntries: options.initialEntries ?? '/admin/llm',
  })
}

test('the LLM screen offers a tab per project that overrides llm_config', async () => {
  renderLlm()
  expect(await screen.findByRole('tab', { name: 'Alpha' })).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: /global/i })).toHaveAttribute('aria-selected', 'true')
})

test('a project in the URL is the selected scope', async () => {
  renderLlm({ initialEntries: '/admin/llm?project=Alpha' })
  expect(await screen.findByRole('tab', { name: 'Alpha' })).toHaveAttribute(
    'aria-selected',
    'true',
  )
})

test('an unstated field shows the inherited global value, not a filled default', async () => {
  // The whole point. `running` reports provider="openai" for Alpha because a
  // pydantic dump fills defaults; the operator must see the anthropic they
  // actually inherit.
  renderLlm({ initialEntries: '/admin/llm?project=Alpha' })
  await screen.findByRole('tab', { name: 'Alpha' })
  expect(screen.getByText(/anthropic/)).toBeInTheDocument()
})

test('a stated field shows the project value', async () => {
  renderLlm({ initialEntries: '/admin/llm?project=Alpha' })
  await screen.findByRole('tab', { name: 'Alpha' })
  expect(screen.getByDisplayValue('12.5')).toBeInTheDocument()
})

test('editing in project scope writes the project path, not the global one', async () => {
  renderLlm({ initialEntries: '/admin/llm?project=Alpha' })
  await screen.findByRole('tab', { name: 'Alpha' })

  const model = screen.getByLabelText(/model/i)
  await userEvent.type(model, 'gpt-5')

  await waitFor(() =>
    expect(
      JSON.parse(window.localStorage.getItem(DRAFT_STORAGE_KEY) ?? '{}'),
    ).toHaveProperty(['projects.Alpha.llm_config.model']),
  )
})

test('selecting a project scope queues no edit', async () => {
  // Choosing a scope is navigation, never an edit: an empty override table
  // would appear in the diff the operator never asked for.
  renderLlm()
  await userEvent.click(await screen.findByRole('tab', { name: 'Alpha' }))
  await screen.findByText(/anthropic/)
  expect(JSON.parse(window.localStorage.getItem(DRAFT_STORAGE_KEY) ?? '{}')).toEqual({})
})

test('the model table is global-only', async () => {
  // ModelTable renders no testid; its <h3>{t.models}</h3> heading is what
  // identifies it, and this suite renders in German.
  renderLlm()
  expect(await screen.findByRole('heading', { name: de.models })).toBeInTheDocument()

  await userEvent.click(screen.getByRole('tab', { name: 'Alpha' }))
  await waitFor(() =>
    expect(screen.queryByRole('heading', { name: de.models })).not.toBeInTheDocument(),
  )
})

test('a validation issue on a project field lands on that field', async () => {
  renderSection({
    section: 'llm',
    isAdmin: true,
    running: PROJECT_CONFIG.running,
    disk: PROJECT_CONFIG.disk,
    initialEntries: '/admin/llm?project=Alpha',
    issues: [
      {
        path: 'projects.Alpha.llm_config.provider',
        message: 'not a valid provider',
        toml_section: '[testbench-ai-service.projects.Alpha.llm_config]',
      },
    ],
  })
  expect(await screen.findByText('not a valid provider')).toBeInTheDocument()
})
```

Do not add a `data-testid` to `ModelTable` — it is outside this task's files, and its `<h3>{t.models}</h3>` heading already identifies it.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/screens/ConfigSection.test.tsx`
Expected: FAIL — no tabs are rendered.

- [ ] **Step 4: Write the implementation**

In `frontend/src/screens/ConfigSection.tsx`:

1. Extend the imports:

```tsx
import { useSearchParams } from 'react-router-dom'
import { configuredProjects, llmOverridingProjects } from '../api/agents'
import { useConfig, useModels, useProjects } from '../api/queries'
import { ScopeTabs } from '../components/ScopeTabs'
import { LLM_FIELDS, LOGGING_FIELDS, SERVICE_TABS, llmFields, valueAt, type FieldSpec } from './fields'
```

2. Inside the component, above the early returns (every hook must be called on every render — the same hook-order rule `AgentDetail` documents):

```tsx
  const [params, setParams] = useSearchParams()
  const projects = useProjects()
  // Only the LLM screen has scopes; on Service and Logging the parameter is
  // ignored rather than being allowed to put those screens in a state they
  // cannot render.
  const project = section === 'llm' ? params.get('project') : null
  const scope: Scope = project === null ? { kind: 'global' } : { kind: 'project', project }
  const catalogue = useModels(project ?? undefined)
```

with `import type { Scope } from '../api/agents'` added.

3. Replace the `fields` selection for the LLM section:

```tsx
  } else {
    fields = section === 'llm' ? llmFields(scope) : LOGGING_FIELDS
  }
```

`LLM_FIELDS` may now be unused in this file — remove it from the import if so, rather than leaving a dead name.

4. Render the strip directly under the heading, for the LLM section only:

```tsx
      {section === 'llm' && (
        <>
          <ScopeTabs
            projects={tabs}
            selected={project}
            addable={addable}
            onSelect={(next) => {
              // Navigation, not an edit. Replacing the whole parameter set is
              // deliberate: this screen owns no other search parameter, and a
              // stale one left behind would outlive the scope it described.
              setParams(next === null ? {} : { project: next })
            }}
            globalLabel={t.globalScope}
            addLabel={t.addProjectOverride}
          />
          {project !== null && (
            <div className="text-muted" style={{ fontSize: 12 }}>
              {t.llmScopeHint}
            </div>
          )}
        </>
      )}
```

computed just above the `return`, after the early returns:

```tsx
  // From `disk`, not `running`: `running` reports an llm_config table for a
  // project only when it has one, but reading the file is what "this project
  // overrides the LLM config" means, and it is the same source the fields are
  // measured against.
  const llmTabs = llmOverridingProjects(config.data.disk)
  const tabs = [...new Set(project !== null ? [...llmTabs, project] : llmTabs)]
  const known = [
    ...(projects.data?.projects ?? []).map((entry) => entry.name),
    ...configuredProjects(running),
  ]
  const addable = [...new Set(known)].filter((name) => !tabs.includes(name))
```

5. Change how `saved` is read, and add the inherited note. Replace the `isAdmin ? <Field …/>` branch's props:

```tsx
            <Field
              key={spec.key}
              spec={spec}
              // In project scope the value comes from `disk` ONLY. `running`
              // is a pydantic dump, so a project stating just `timeout` still
              // carries provider="openai" and auth_method="api_key" -- the
              // model's defaults, not the operator's choices. Falling back to
              // it would show every field as overridden, and would offer the
              // operator a default to accidentally write into their file.
              // Measured 2026-09-18; see the plan's Task 6.
              saved={
                scope.kind === 'project'
                  ? valueAt(config.data.disk, spec.key)
                  : (valueAt(config.data.disk, spec.key) ?? valueAt(running, spec.key))
              }
              inheritedFrom={
                scope.kind === 'project'
                  ? { value: valueAt(running, `llm_config.${spec.setting}`), label: t.globalScope }
                  : undefined
              }
              issue={issue}
              lang={lang}
            />
```

The inherited value reads from `running`'s **global** `llm_config`, which is correct: globally, a dump filled with defaults is exactly what applies.

6. Gate the model table on global scope:

```tsx
      {section === 'llm' && scope.kind === 'global' && (
        <ModelTable … />
      )}
```

7. Add the credential notice, after the fields, in project scope:

```tsx
      {section === 'llm' && scope.kind === 'project' && catalogue.data && (
        <div style={{ maxWidth: 860 }}>
          <h3 style={{ fontSize: 16, marginBottom: 8 }}>{t.credentialsHeading}</h3>
          {catalogue.data.providers.map((entry) => (
            <div key={entry.provider} className="text-muted" style={{ fontSize: 12 }}>
              <strong>{entry.provider}</strong> —{' '}
              {entry.key_present ? t.projectKeyPresent : t.projectKeyAbsent}
            </div>
          ))}
        </div>
      )}
```

Presence only. No endpoint returns a credential value and no code here may print one.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/screens/ConfigSection.test.tsx`
Expected: PASS, new tests and all pre-existing ones.

- [ ] **Step 6: Mutation-verify the one that matters**

Temporarily change the `saved` expression to the old `valueAt(disk, key) ?? valueAt(running, key)` in both scopes and re-run.
Expected: `an unstated field shows the inherited global value, not a filled default` FAILS. **Revert.** If it still passes, the test is not pinning the property it names — fix the test before moving on, and say so in your report.

- [ ] **Step 7: Typecheck, full suite, commit**

```bash
cd frontend && npx tsc -b && npx vitest run
git add frontend/src/screens/ConfigSection.tsx frontend/src/screens/ConfigSection.test.tsx frontend/src/i18n/en.ts frontend/src/i18n/de.ts
git commit -m "Edit a project's llm_config from the LLM screen

Scope tabs like the Agents screen, with the scope in the URL so the Projects
screen can link to one. In project scope the saved value is read from disk
only: the running dump fills LLMConfig's defaults into a sparse project
block, so falling back to it would report provider=openai on a project that
inherits anthropic.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: The Projects screen links to the editor, plus docs

Implements design §5.5, and finishes the increment.

**Files:**
- Modify: `frontend/src/screens/Projects.tsx:396-425`
- Modify: `frontend/src/i18n/en.ts`, `frontend/src/i18n/de.ts`
- Modify: `docs/configuration.md`, `CHANGELOG.md`
- Test: `frontend/src/screens/Projects.test.tsx`

**Interfaces:**
- Consumes: the `?project=` contract from Task 6.
- Produces: nothing.

- [ ] **Step 1: Add the translation key**

`en.ts`: `editLlmConfig: 'Edit LLM configuration',`
`de.ts`: `editLlmConfig: 'LLM-Konfiguration bearbeiten',`

Leave `editInConfigToml` in place — check with `grep -rn "editInConfigToml" frontend/src` first; if this was its only use, delete it from both dictionaries in this task so the parity test does not guard a dead key.

- [ ] **Step 2: Write the failing test**

Append to `frontend/src/screens/Projects.test.tsx`, following the file's existing render helper:

```tsx
test('the llm_config panel links into the LLM screen for that project', async () => {
  // Fixture: a project that overrides llm_config.
  renderProjects({
    running: {
      ...RUNNING,
      projects: { 'Release 2.0': { llm_config: { model: 'gpt-5' }, language: null, agents: null } },
    },
  })

  const link = await screen.findByRole('link', { name: /LLM/i })
  // encodeURIComponent, so a project name with a space or a slash survives.
  expect(link).toHaveAttribute('href', '/admin/llm?project=Release%202.0')
})

test('the panel still shows what the project overrides', async () => {
  renderProjects({
    running: {
      ...RUNNING,
      projects: { Alpha: { llm_config: { model: 'gpt-5' }, language: null, agents: null } },
    },
  })
  expect(await screen.findByTestId('project-llm-config')).toHaveTextContent('gpt-5')
})
```

Match `renderProjects` and `RUNNING` to whatever the file actually calls them; read it first rather than assuming.

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/screens/Projects.test.tsx`
Expected: FAIL — no link role in the panel.

- [ ] **Step 4: Write the implementation**

In `Projects.tsx`, add `import { Link } from 'react-router-dom'` if absent, and replace the panel's label line:

```tsx
          <div style={{ marginBottom: 4 }}>
            <strong>llm_config</strong> ·{' '}
            <Link to={`/admin/llm?project=${encodeURIComponent(name)}`}>{t.editLlmConfig}</Link>
            <div className="text-muted" style={{ fontSize: 11 }}>{t.removedWithProject}</div>
          </div>
```

`<Link>`, never `<a href>`: a full page load bypasses the unsaved-changes guard and drops the operator's queued edits.

Also update the comment above the panel — it currently says "D8 keeps the per-project surface to language and agents", which this increment makes false:

```tsx
      {/* The project's llm_config, summarised. Phase 4d made it editable on
          the LLM screen; this stays as the at-a-glance view of what the
          project overrides, and links there. */}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/screens/Projects.test.tsx`
Expected: PASS, including the file's 27 pre-existing tests.

- [ ] **Step 6: Update the operator documentation**

In `docs/configuration.md`, find the section describing `[projects.<name>]` overrides and add:

```markdown
### Per-project LLM configuration

A project may override any `llm_config` setting. The override is *sparse*:
state only what differs, and every other setting is inherited from the global
`[testbench-ai-service.llm_config]` table.

```toml
[testbench-ai-service.projects."Release 2.0".llm_config]
model = "gpt-5"
timeout = 30
```

Edit this from the console on the **LLM** screen, which has a tab per project.
An empty field inherits; clearing a field removes the override.

Two things behave differently from the rest of the table:

- **`extra_models` is not merged.** A project that declares any `extra_models`
  entry replaces the global catalogue for that project rather than adding to
  it. The console therefore edits `extra_models` globally only.
- **A project API key is separate from the project's config.** The key is read
  from `<PROJECT_NAME>_<PROVIDER>_API_KEY` in the environment; when it is not
  set, runs for that project fall back to the global credential even though
  the project's own LLM settings still apply.
```

In `CHANGELOG.md`, under `Unreleased`, add:

```markdown
- The LLM screen now edits a project's `llm_config` as well as the global one,
  with a tab per project. Empty fields inherit from the global configuration.
- The service no longer refuses to start when a provider API key is missing.
  The LLM clients are created on demand, so a missing credential surfaces on
  the first agent request instead of at startup — which means the console can
  be used to fix the provider configuration that is wrong.
```

Then read the surrounding `Unreleased` section and remove any line these two now contradict — phase 4a hit exactly this, with a stale "prompt files are read-only from the browser" claim left 40 lines above its own contradiction.

- [ ] **Step 7: Full verification**

```bash
cd frontend && npx tsc -b && npx vitest run && npm run build
cd .. && python -m pytest tests/unit/webui tests/unit/llm tests/unit/test_main.py tests/unit/utils/test_config.py -q
python -m ruff check testbench_ai_service tests && python -m ruff format --check testbench_ai_service tests
```

Expected: `tsc` clean, frontend green, `npm run build` succeeds, backend selection green, ruff clean. Record the counts.

Then confirm the branch baseline is unmoved:

```bash
python -m pytest tests/unit -q --tb=no | tail -3
```
Expected: **54 failed, 3 errors**, and a passed count higher than 1314 by the number of backend tests this increment added. A different failure count means you broke something — compare the failing test *ids*, not the totals, before concluding anything.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/screens/Projects.tsx frontend/src/screens/Projects.test.tsx frontend/src/i18n/en.ts frontend/src/i18n/de.ts docs/configuration.md CHANGELOG.md
git commit -m "Link the Projects screen to the LLM editor, and document 4d

The per-project llm_config panel stops saying 'edit in config.toml' and
links into its tab on the LLM screen. Uses react-router Link, not an
anchor: a full page load would drop queued draft edits.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Manual verification before the increment is called done

The unit suites stub `fetch`; none of them proves the console and the real API agree on the wire. Phase 1 caught its worst defect this way and phase 4c's two Criticals were both invisible to two agreeing test suites. Do this once, at the end:

1. Start the service against a scratch `config.toml` that declares a global `[llm_config]` and a project with a dotted name (`[testbench-ai-service.projects."Release 2.0".llm_config]`). **Do not export a provider API key** — Task 1 means it should now start anyway. Record that it does.
2. Sign in as an admin, open **LLM**, and confirm: the Global tab shows the global values; a `Release 2.0` tab exists; selecting it shows empty fields with the global values as placeholders.
3. Set `timeout` on the project tab, open the diff, and confirm the preview shows a change to `[testbench-ai-service.projects."Release 2.0".llm_config]` — **quoted**, and not a new top-level table.
4. Apply, then read the file on disk and confirm the TOML is what the diff promised.
5. Clear the field, apply again, and confirm the key is gone and the project inherits once more.
6. Reload the browser on `/admin/llm?project=Release%202.0` and confirm the tab is still selected (this is what D2 buys).

Record the outcome of each step. If step 3 shows an unquoted path, stop — that is phase 4c's C2 finding reappearing, and it means a path was built by concatenation somewhere.

---

## Plan self-review

Run against the design before dispatching Task 1.

**Spec coverage:** §5.1 → Task 1. §3.2/§7.1 → Task 2. D4 → Task 3. §5.3's path rule and §5.2's tab source → Task 4. §3.6 and §5.3's field list → Task 5. §5.2, §5.3, §5.4, D2, D3, D5 → Task 6. §5.5 → Task 7. §7.2's dotted-name test → Task 4 Step 1 (two tests) and the manual step 3. §7.3 → Task 1 Step 2. §8's known gaps are documented, not implemented, which is what §8 means. No uncovered requirement.

**Placeholders:** none. Every code step carries the code. Two steps deliberately say "read the file first and match its existing helper names" (Task 2's `AppConfig` construction and Task 7's `renderProjects`/`RUNNING`) rather than inventing names this plan has not verified — that is a check, not a TBD, and each names exactly what to look for. Everything else was verified against the running code: `DRAFT_STORAGE_KEY`, `useModels`' optional `project` parameter, `ModelTable`'s heading, `Field`'s `inheritedFrom` shape and `FieldSpec.setting` were each read before being written into a step.

**Type consistency:** `Scope` is the existing type from `api/agents.ts` throughout — Tasks 4, 5 and 6 all import it from there, none redefines it. `scopedLlmPath(scope, setting?)` is produced in Task 4 and consumed in Task 5 with that exact signature. `llmFields(scope)` is produced in Task 5 and consumed in Task 6. `ScopeTabs`' six props are declared in Task 3 and passed in Tasks 3 and 6 with the same names. `FieldSpec.setting` is the pre-existing optional field, populated in Task 5 and read in Task 6.

**Known risk this plan accepts:** Task 6 is larger than the others. It is not split because its parts are not independently reviewable — the tab strip without the scoped fields renders a screen that lies, and the scoped fields without the strip are unreachable. Its `saved`-from-`disk` rule is the single most likely thing to be got wrong, which is why it has its own mutation-verification step.
