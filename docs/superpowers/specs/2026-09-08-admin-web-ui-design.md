# Admin Web UI (Service Console) — Design

**Date:** 2026-09-08
**Status:** Approved for implementation planning
**Branch:** `admin-web-ui`
**Source design:** Claude Design project `Testbench AI Service Configuration`,
artboard `TestBench AI Service Console.dc.html`

## 1. Purpose

Give operators a browser console for the TestBench AI Service so that configuring
the service no longer requires hand-editing `config.toml` and the prompt YAML tree
on the server's filesystem.

The console covers the whole configuration surface the service already has —
service settings, TestBench connection, TLS, reverse proxy, LLM provider, logging,
agents, per-project overrides, and prompts — plus read-only operational insight
(service health, TestBench reachability, which API keys are present, recent log
lines).

Everything is served by the existing FastAPI app and ships inside the existing
PyInstaller binary. No second deployment artifact.

## 2. The source design

The Claude Design artboard is not a static mockup. It is a working React
prototype (`renderVals()` over an `sc-if`/`sc-for` template) with a complete state
model, and it functions as the functional spec for this work. It simulates the
backend entirely in the browser: `localStorage` persistence, a hand-rolled
`toToml`/`toYaml`, a regex Jinja linter, mocked project and test-case-set lists,
and a `setTimeout` test run.

Its screens:

| Screen | Contents |
|---|---|
| Status | Service / TestBench / API-key cards, agent + override summary, recent log |
| Service | Tabs: General, TestBench connection, HTTPS/TLS, Reverse proxy |
| LLM provider | Provider, model override, Azure fields, custom class path |
| Logging | Console and file sinks |
| Agents | List view (expandable per-project rows) and Matrix view (agents x projects) |
| Agent detail | Scope switcher (global / project), inherit-vs-override fields, variants, variables |
| Projects | Per-project cards: language override, per-agent toggles |
| Prompts | CodeMirror Jinja editor, variant/message tree, variables, rendered preview, test run |
| Raw | Generated `config.toml`, copy to clipboard |

Its central concept — and the spine of this feature — is a three-way config state:

- `cfg` — the draft the user is editing
- `disk` — what is written to `config.toml` and the prompt files
- `running` — what the live service actually loaded

`cfg != disk` drives "N unapplied changes → view diff → apply · write files".
`disk != running` drives "restart needed". This design keeps that model.

The prototype's config shape maps almost 1:1 onto the real `AppConfig`. Every
field under its `service` section already exists as a top-level `AppConfig` field,
and its prompt structure matches `PromptDefinition` / `PromptVariant` /
`MessageTemplate` exactly, including inline `text` versus external `file`.

## 3. Decisions

| Decision | Choice |
|---|---|
| Stack | React + Vite + TypeScript, built to static assets served by FastAPI |
| First increment | Vertical slice: login + Status + read-only config |
| Session | Opaque session id in an httpOnly cookie, plus a double-submit CSRF header |
| Apply semantics | Write files, then hot reload in process; no self-restart |

### 3.1 Deliberate deviations from the prototype

1. **Writes are Administrator-only.** The prototype gives a non-admin "test
   manager" role write access to agents and prompts, locking only Service, LLM and
   Logging. Editing a prompt rewrites what is sent to an LLM on behalf of every
   user of that agent, which is as consequential as editing `llm_config`. Non-admins
   get a read-only console. The nav lock affordance stays; it simply covers more.
2. **The login server field is read-only.** The prototype lets the user type a
   TestBench URL. The service is configured against exactly one `tb_server_url`;
   the field is prefilled from config and not editable.
3. **No self-restart button.** See section 7.
4. **`deployment_mapping` is dropped from the UI.** See section 11.
5. **The role selector on the login screen disappears.** It is labelled "(demo)" in
   the prototype; roles come from TestBench.

## 4. Architecture

### 4.1 Layout

```
frontend/                          # Vite + React + TS
  package.json  vite.config.ts  tsconfig.json
  src/
    main.tsx  App.tsx
    screens/     # Status, Service, Llm, Logging, Agents, AgentDetail, Projects, Prompts, Raw, Login
    components/  # Field, Switch, Seg, Card, Dialog, DiffView, NavRail, TopBar
    state/       # useConfigDraft, useSession, queries
    styles/      # industry.css (design system), brand.css (TestBench tokens), fonts/
    i18n/        # de.ts, en.ts (ported from the prototype's I18N)
testbench_ai_service/
  static/admin/                    # Vite build output (build artifact, gitignored)
  admin/                           # new backend package
    __init__.py
    routes.py                      # APIRouter mounted at /admin/api
    session.py                     # login, session store, CSRF, dependencies
    config_io.py                   # read / serialize / diff / atomic write of config.toml
    prompts_io.py                  # read / write / lint / render prompt YAML + jinja files
    status.py                      # service, TestBench, env-key, log-tail probes
    reload.py                      # hot reload + restart-required classification
    tasks.py                       # in-flight agent task registry
    models.py                      # request/response pydantic models
```

`frontend/` currently contains nothing but an orphaned `node_modules` from an
abandoned scaffold, and `.gitignore` has no `node_modules` entry. Both are fixed as
the first step.

### 4.2 Serving

`create_app()` gains a call that, when the console is enabled:

1. includes the `/admin/api` router;
2. mounts `StaticFiles(directory=<pkg>/static/admin)` at `/admin`;
3. registers an SPA fallback so any unmatched `/admin/*` path returns `index.html`,
   which is what makes React Router deep links survive a page reload.

Vite is configured with `base: '/admin/'` and `outDir` pointing at
`testbench_ai_service/static/admin`.

The existing `router` in `routes.py` and the agent routers are untouched. `GET /`
keeps redirecting to `/docs`.

### 4.3 Packaging

`testbench-ai-service.spec` already collects package data via
`pkg_datas = collect_data_files("testbench_ai_service")`. Because the build output
lands inside the package directory, the console is swept into the binary with no
`.spec` change.

`build_binary.py` gains a frontend build step (`npm ci && npm run build`) that runs
before PyInstaller and fails with an explicit message if Node is unavailable, so a
binary can never be built with a stale or missing console.

### 4.4 Enablement

```toml
[testbench-ai-service.admin_ui]
enabled = true
```

Default `true`, because `host` defaults to `127.0.0.1` and the console is therefore
local-only out of the box. When the console is enabled *and* the bind address is not
loopback, startup logs a warning naming the risk. Setting `enabled = false` removes
both the router and the static mount.

## 5. Authentication and authorization

### 5.1 Login

`POST /admin/api/session` accepts `{username, password}` and opens a
`TBConnection` against the configured `tb_server_url`. The
`testbench-cli-reporter` library already provides everything needed:

- `Connection(...)` logs in and exposes `session_token`
- `read_user_roles(session)` calls `GET {server}1/user/{login}/roles`
- `GlobalHumanRole.Administrator` in those roles means admin

No new TestBench API work is required.

### 5.2 Session store

The cookie carries an **opaque session id**, never the TestBench token. A
process-local store maps

```
sid -> { tb_session_token, username, roles, is_admin, created_at, last_seen }
```

with a 60-minute idle timeout and an 8-hour absolute cap, whichever expires first.
A leaked cookie therefore cannot be replayed against TestBench directly, and logout
revokes server-side. Both durations are constants in `session.py`, not config —
there is no requirement yet to make them tunable.

Because the store is in-process, restarting the service logs everyone out. That is
acceptable and, given section 7 keeps restarts rare, unsurprising.

Cookie attributes: `httpOnly`, `SameSite=Strict`, `Path=/admin`, and `Secure`
whenever `ssl_cert`/`ssl_key` are configured.

### 5.3 CSRF

Double-submit: login also sets a readable `tbai_admin_csrf` cookie which the SPA
echoes in an `X-CSRF-Token` header on every mutating request. The server compares
the two and rejects a mismatch. `SameSite=Strict` is the primary defence; this is
the belt to its braces.

### 5.4 Authorization

A `require_admin` dependency guards every mutating route. Read routes require only a
valid session. The frontend mirrors this by rendering non-admin sessions read-only,
but the server is the enforcement point.

## 6. Config lifecycle

### 6.1 Where the draft lives

In the browser, persisted to `localStorage`, exactly as the prototype does. The
server holds no draft, which avoids inventing multi-user draft locking for what is
a single-operator tool.

The consequence — two admins editing simultaneously can clobber each other — is
mitigated by `POST /config/preview` diffing against *current* disk contents at apply
time, so the second writer sees the first writer's changes in the diff rather than
silently overwriting them.

### 6.2 Serialization

Serialization is server-side, replacing the prototype's hand-rolled `toToml`.

- **`config.toml` round-trips through `tomlkit`** (new dependency). The existing
  `tomli_w` cannot preserve comments, and `config.toml` is a hand-edited,
  heavily-commented file; losing an operator's comments on first save would be a
  serious regression. `tomlkit` edits the existing document in place.
- **Prompt YAML is emitted canonically with PyYAML** (already a dependency). The
  console owns those files completely — it is the editor for them — so a canonical
  re-emit is in the spirit of the design rather than a loss.

### 6.3 Validation

Before anything is written, the draft is validated by constructing
`AppConfig(**draft)` — the same model the service boots with. Prompt files are
validated by constructing `PromptDefinition`. The console therefore cannot write a
configuration that would prevent the service from starting.

Validation errors come back as field-addressed messages so the UI can mark the
offending input.

### 6.4 Writing

Every write is atomic: serialize to a temp file in the target directory, `os.replace`
into place. A `.bak` copy of the previous contents is kept alongside. A multi-file
apply (config plus several prompt files) validates every file first and only then
begins writing, so a validation failure cannot leave a half-applied state.

## 7. Hot reload and restart-required

`POST /config/apply` writes the files and then, under a lock:

1. rebuilds `AppConfig` from the new files;
2. swaps `app.state.config`;
3. closes and re-initialises the `LLMFactory` clients;
4. reloads translations.

It responds with the list of written paths and a `restart_required` flag.

`restart_required` is `true` only for changes a live swap genuinely cannot cover:

- any agent's `endpoint_path` or `class_path` — agent routers are registered once at
  startup by `init_routers()`;
- `host`, `port`, `ssl_cert`, `ssl_key`, `ssl_ca_cert`, `trusted_proxies` — these are
  uvicorn/middleware-level and fixed at boot.

Those raise the design's "restart needed" banner. There is no self-restart button:
re-execing only works under a supervisor (Windows service, systemd) and would kill a
bare terminal process outright. The banner tells the operator what to restart; the
Windows service instructions already in `docs/windows-service-installation.md` are
linked from it.

### 7.1 In-flight agent tasks

The prototype offers "wait for running tasks to finish, then restart". Agent
executions currently run as untracked FastAPI `BackgroundTasks`, so there is nothing
to wait on. `admin/tasks.py` adds a small in-process registry — incremented when an
agent task starts, decremented when it finishes — so apply can report how many are
in flight and optionally wait, bounded, before reloading.

## 8. Backend API surface

All routes are under `/admin/api`. Mutating routes require admin and a valid CSRF
header.

| Method | Path | Purpose |
|---|---|---|
| POST | `/session` | Log in with TestBench credentials; set cookies |
| GET | `/session` | Current user, roles, admin flag (survives page reload) |
| DELETE | `/session` | Log out; revoke server-side |
| GET | `/status` | Service info, TestBench reachability, env-key presence, counts |
| GET | `/logs` | Tail of the configured log file |
| GET | `/config` | On-disk config as JSON, plus the running snapshot |
| POST | `/config/preview` | Per-file unified diff of draft against current disk |
| POST | `/config/apply` | Validate, write atomically, hot reload |
| GET | `/projects` | Real TestBench project list via `get_all_projects()` |
| GET | `/prompts` | Tree of languages, agents, variants, message files |
| GET | `/prompts/{lang}/{agent}` | Parsed prompt YAML plus referenced file contents |
| PUT | `/prompts/{lang}/{agent}` | Validate and write prompt YAML and its files |
| POST | `/prompts/lint` | Real Jinja2 parse; syntax errors with line numbers |
| POST | `/prompts/render` | Render messages against a sample context |
| GET | `/models` | Model catalogue and which provider API keys are present |

`GET /status` reports API-key **presence only**, never values. No endpoint returns
an environment variable's contents.

`GET /models` needs a source the backend does not currently have. It returns a
curated static catalogue defined in `admin/models.py`, grouped by provider and
annotated with whether that provider's API key is present in the environment — the
same shape the prototype's `MODELS` constant has. It is deliberately *not* fetched
from the provider APIs: the service may have no outbound access at console load
time, and a stale hardcoded list degrades better than a hanging request. The model
picker keeps the prototype's free-text entry, so a model missing from the catalogue
is always reachable.

## 9. Prompt editing

`GET /prompts/{lang}/{agent}` returns the parsed `prompt.yaml` together with the
contents of every `file:`-referenced template, which is what lets the editor treat a
variant's messages uniformly whether inline or external.

The prototype's regex linter is replaced by a real `jinja2.Environment().parse()`,
reporting genuine `TemplateSyntaxError` line numbers. Likewise `POST /prompts/render`
uses the real Jinja2 environment with the same sample-context shape the prototype
builds, so the preview matches what the agent would actually send.

Switching a message between inline `text` and an external `file` (which the prototype
supports) creates or absorbs the template file as part of the same atomic write.

## 10. Frontend architecture

- **Routing:** React Router, upgrading the prototype's `ui.route` string to real URLs
  so screens are linkable and the back button works.
- **Server state:** TanStack Query for reads.
- **Draft state:** a single `useConfigDraft` reducer persisted to `localStorage`. The
  prototype's `effAgent()` inheritance resolution and `cleanProject()` override
  pruning port over nearly verbatim as pure functions; they are the part most worth
  unit-testing.
- **Design system:** `_ds/.../styles.css` copies in as `styles/industry.css`, and the
  artboard's `[data-brand=testbench]` block (green `#128a5e`, orange `#f28c00`) as
  `styles/brand.css`. `data-theme` / `data-brand` / `data-corners` are set on the root
  element, honouring `prefers-color-scheme` with an explicit toggle.
- **Fonts:** Barlow and Barlow Condensed are **self-hosted as woff2**. The design
  system's Google Fonts `@import` is removed — an on-prem service cannot assume
  internet access.
- **Editor:** CodeMirror 5 from npm, not cdnjs, for the same reason. CM5 keeps the
  prototype's editor glue (`showHint`, `addLineClass`) intact; CM6 would be a rewrite
  and is deliberately not attempted now.
- **i18n:** the prototype's `I18N` de/en dictionary transfers directly. The console
  language follows the operator's choice, independent of the service's `language`
  setting, which governs agent output.
- **Generic over agents:** `AppConfig.agents` is a dict and a fourth prompt set
  (`requirement`) already exists on disk without a `DEFAULT_AGENTS` entry. The UI
  iterates the dict; it never hardcodes the prototype's three agent keys.

## 11. Backend changes outside the admin package

Small, but they block phases 2 to 4:

1. **`PromptConfig.vars` widening.** Declared `dict[str, str]`, but the design stores
   typed variable values (`max_findings = 10`) and `PromptVariableDefinition`
   already supports `number` and `boolean` value types. Widen to
   `dict[str, str | int | float | bool]`.
2. **`LLMConfig.timeout` and `LLMConfig.max_retries`.** Present in the design, absent
   from the model. `extra="allow"` means they would be written and silently ignored
   today. Add the fields and wire them into the LLM clients.
3. **`deployment_mapping` is dropped from the UI.** The design offers Azure
   deployment aliasing that the backend has no notion of. Rather than ship a control
   that does nothing, it is removed; if Azure users need it, it becomes its own piece
   of work with backend support.
4. **`templates_dir` is added to the Service form.** It exists in `AppConfig` and the
   design omits it.

## 12. Increments

**Phase 1 — vertical slice.** Frontend scaffold, `frontend/node_modules` cleanup and
gitignore, Vite build wiring, `build_binary.py` step, `/admin` mount with SPA
fallback, `admin_ui.enabled` config, login with session store and CSRF, `GET /status`,
Status screen, and read-only Service / LLM / Logging forms from `GET /config`.
Deployable, and incapable of changing anything.

**Phase 2 — config editing.** Draft state, editable forms with validation surfacing,
`POST /config/preview` diff dialog, `POST /config/apply` with atomic write and hot
reload, restart-required banner, in-flight task registry, raw `config.toml` view.
Includes the `LLMConfig.timeout` / `max_retries` additions from section 11, since the
LLM form becomes editable here.

**Phase 3 — agents and projects.** Agents list and matrix views, agent detail with
scope switching and inherit-vs-override semantics, Projects screen, real project list.
Includes the `PromptConfig.vars` widening.

**Phase 4 — prompt editor.** CodeMirror integration, variant and message tree,
variable declaration and values, real lint and render endpoints, inline-vs-file
switching.

**Phase 5 — optional.** Agent test run against a live LLM.

## 13. Testing

Test-driven, using the existing pytest setup.

Backend:

- `tomlkit` round-trip preserves comments and formatting on an untouched section
- atomic write leaves no partial file; `.bak` holds the previous contents
- an invalid draft is rejected with field-addressed errors and nothing is written
- a multi-file apply with one invalid file writes nothing at all
- diff output matches expectations for add / change / remove
- hot reload swaps `app.state.config` and re-inits LLM clients
- `restart_required` is set for `endpoint_path`, `class_path`, `host`, `port`, TLS and
  proxy changes, and not otherwise
- login rejects bad credentials; sessions expire on idle and absolute caps; logout
  revokes; CSRF mismatch is rejected
- every mutating route refuses a non-admin session
- no endpoint leaks an environment variable value

Frontend, with Vitest and React Testing Library, concentrated on the logic rather
than the markup:

- `effAgent()` inheritance: global value, project override, override equal to global
- `cleanProject()` prunes empty override structures
- draft-versus-disk change detection drives the pending-changes count

Playwright is available for smoke-testing the assembled console.

## 14. Security considerations

- The console writes executable-adjacent configuration (`class_path` imports a Python
  class) and rewrites LLM prompts. Both are Administrator-only, and `class_path`
  already goes through `validate_class_path`.
- The TestBench token never reaches the browser; the cookie holds an opaque id.
- API-key presence is reported, never values.
- The console defaults to a loopback bind and warns when enabled on a public one.
- All frontend assets are local; no CDN or webfont fetch at runtime, which also means
  no third-party origin can inject script into an admin session.
- Prompt and config content rendered in the UI is inserted as text, never as HTML.

## 15. Out of scope

- Self-restarting the service process.
- Multi-user draft locking or collaborative editing.
- Editing `.env` or managing API-key values.
- Creating or deleting agents (`class_path` implies a Python class that must exist);
  the console configures the agents that are registered.
- Azure `deployment_mapping`.
- Persisting console sessions across a service restart.
- Any change to the existing agent trigger API.

## 16. Open items to verify against a live TestBench

1. `read_user_roles()` calls `GET {server}1/user/{login}/roles`. Confirm the response
   shape against the deployed TestBench version and that a plain project user gets a
   non-admin role list rather than an error.
2. `get_all_projects()` response shape for the Projects screen, and whether it is
   filtered by the calling user's visibility.
3. Whether logging in via `TBConnection` with username and password is acceptable to
   operators who use Azure Entra ID against TestBench, or whether the console needs to
   accept a pasted session token as an alternative.
4. Confirm no reverse-proxy deployment strips the `X-CSRF-Token` header.
