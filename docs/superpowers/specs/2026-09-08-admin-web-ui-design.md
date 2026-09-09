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

### 2.1 The abandoned August attempt

The working tree contains an earlier, uncommitted attempt at this feature:
`testbench_ai_service/webui/` and `tests/unit/webui/` exist as empty directories
whose `__pycache__` still holds compiled bytecode for `routes.py`, `config_io.py`,
`prompt_io.py`, `project_prompts.py`, `apply.py`, `security.py`, `static.py`,
`tree.py`, `models.py` and `errors.py`, dated 2026-08-17. The sources were deleted
and never committed.

It is worth recording what that attempt had settled on, because it converges with
this design and corroborates several choices:

- the same `/admin/api` route prefix;
- `static.py` with `_SpaStaticFiles` / `mount_spa` — the same SPA-fallback approach
  as section 4.2;
- `apply.py` with `apply_config` / `restart_required` — the same apply model as
  section 7;
- `config_io.py` with a `_document` helper and both `write_config_raw` and
  `write_config_structured` — i.e. it also reached for a comment-preserving TOML
  document, confirming the `tomlkit` choice in section 6.2.

Two things it did differently, both of which change this design:

1. **Its security model was `require_loopback`**, not authentication — the console
   was simply refused from a non-loopback client, with no login at all. The source
   design has a login screen, so authentication as specified in section 5 stands;
   but loopback enforcement is cheap defence-in-depth and is kept as an optional
   `admin_ui.require_loopback` setting (default `false`, since operators do reach
   the console from another machine).
2. **It had a `resolve_within` path-containment helper.** This design originally
   omitted that, which was a genuine gap; see section 9.1.

It also had a prompt "fork" concept (`create_fork`, `delete_fork`,
`_write_prompt_override`) for materialising a per-project prompt file from a global
one. That is a real workflow — the source design's per-project `prompt.file`
override implies it — and it is folded into phase 3 rather than invented afresh.

Because those directories already exist and carry the name the earlier attempt
chose, the new backend package is `testbench_ai_service/webui/`, not `admin/`. The
route prefix stays `/admin/api`.

The bytecode is not decompiled into the new implementation; it is evidence about
intent, not a source of code. If the attempt was abandoned for a reason not visible
in the bytecode, that reason should be raised before implementation starts.

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
  webui/                           # new backend package (name inherited, see 2.1)
    __init__.py
    routes.py                      # APIRouter mounted at /admin/api
    session.py                     # login, session store, CSRF, dependencies
    security.py                    # resolve_within path containment, loopback check
    config_io.py                   # read / serialize / diff / atomic write of config.toml
    prompts_io.py                  # read / write / lint / render prompt YAML + jinja files
    status.py                      # service, TestBench, env-key, log-tail probes
    reload.py                      # hot reload + restart-required classification
    tasks.py                       # in-flight agent task registry
    catalogue.py                   # static model catalogue for GET /models
    models.py                      # request/response pydantic models
    static.py                      # mount_spa + SPA-fallback StaticFiles subclass
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
require_loopback = false
```

`enabled` defaults to `true`, because `host` defaults to `127.0.0.1` and the console
is therefore local-only out of the box. When the console is enabled *and* the bind
address is not loopback, startup logs a warning naming the risk. Setting
`enabled = false` removes both the router and the static mount.

`require_loopback` defaults to `false` — operators do legitimately reach the console
from another machine — but when set, every `/admin` request from a non-loopback
client is refused. This is the August attempt's entire security model (section 2.1)
kept as an optional extra layer on top of authentication, for hosts where the console
should never be reachable off-box.

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
| GET | `/meta` | **Unauthenticated.** The configured `tb_server_url`, so the login screen can show which TestBench it signs into |
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

`GET /meta` is the only unauthenticated route, and it exists because the login screen
has to name the TestBench server it is about to authenticate against (section 3.1.2)
before any session exists. It returns the `tb_server_url` and nothing else. That is a
deliberate, bounded disclosure: it tells an unauthenticated caller which TestBench
this service talks to. The service already publishes its version and full route list
at `/docs` and `/openapi.json` without authentication, so this does not widen the
exposure meaningfully — but it is the one route that must be reviewed against a
deployment where the console is reachable from an untrusted network, and it is a
reason to consider `admin_ui.require_loopback` there.

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

### 9.1 Path containment

Every filesystem path the console derives from request data — the `{lang}` and
`{agent}` path segments, a prompt's `file:` reference, an agent's `prompt.file`
config value, a renamed template file — is resolved and then checked to be inside
the configured `prompts_dir` before it is read or written. `webui/security.py`
provides the single helper both read and write paths go through:

```
resolve_within(base: Path, candidate: str | Path) -> Path
```

It resolves `base / candidate` (and `candidate` alone when absolute), then rejects
anything not under the resolved `base`, raising a 400. Symlinks are resolved before
the check, so a symlink inside `prompts_dir` pointing outside it is refused too.

Without this, `GET /prompts/../../../../etc/passwd` or a `file: "../../secrets.env"`
reference turns the console into an arbitrary file read, and the write endpoints into
an arbitrary file write. This is the single most security-sensitive piece of the
feature and it is why `security.py` exists as its own module with its own tests.

The same helper guards `templates_dir` if template editing is ever added.

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
fallback, `admin_ui.enabled` / `require_loopback` config, `resolve_within` and the
loopback check in `security.py`, login with session store and CSRF, `GET /status`,
Status screen, and read-only Service / LLM / Logging forms from `GET /config`.
Deployable, and incapable of changing anything.

`security.py` lands in phase 1 even though the paths it guards arrive in phase 4, so
that no prompt endpoint can ever be written without the helper already existing.

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
switching. Includes the live test run below, which is no longer deferred.

**Phase 5 — folded into phase 4 (2026-09-09).** The agent test run against a live
LLM was originally optional. It ships with the prompt editor instead: a prompt the
operator cannot try against the configured model is a prompt they have to deploy to
evaluate, which defeats the point of editing it in the console. It gets its own
endpoint (`POST /prompts/test`), is Administrator-only like every other mutating
route, and is the one console action that spends money — so it is never triggered
implicitly, only by the editor's explicit "Test run" button.

### 12.1 Increment decision, 2026-09-09

Phase 2 is being implemented as its own reviewable increment before phases 3 and 4,
rather than folded into an agents-and-prompts push. Agents are configured *in*
`config.toml`, so agent editing cannot exist without the phase-2 write path
(draft, validate, diff, atomic write, hot reload); building the two together would
mean a single unreviewable change that can corrupt an operator's config file. The
deviations in section 3.1 are re-confirmed as approved and unchanged.

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
- `resolve_within` rejects `..` traversal, absolute paths outside the base, and a
  symlink inside the base that points outside it — for both read and write paths

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
- Every request-derived filesystem path is contained to `prompts_dir` by
  `resolve_within` (section 9.1). Without it the prompt endpoints would be an
  arbitrary file read and write.
- `admin_ui.require_loopback` can additionally refuse the console to any
  non-loopback client, for deployments where the operator always works on the host.
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

1. `read_user_roles()` is TestBench-version dependent: on TestBench 4 it reads
   `GET {server}2/login/session` and returns `globalRoles`; on TestBench 3 it goes
   via `1/checkLogin` and `1/users` to `1/user/{login}/roles`, and returns
   `["Project User"]` when `1/users` answers 403. Confirm against the deployed
   version that an admin's list actually contains the string `Administrator`, since
   the TB3 path can yield `"Project User"` with a space while
   `GlobalHumanRole.ProjectUser` is spelled without one — the admin check must not
   depend on that spelling.
2. `get_all_projects()` response shape for the Projects screen, and whether it is
   filtered by the calling user's visibility.
3. Whether logging in via `TBConnection` with username and password is acceptable to
   operators who use Azure Entra ID against TestBench, or whether the console needs to
   accept a pasted session token as an alternative.
4. Confirm no reverse-proxy deployment strips the `X-CSRF-Token` header.
5. `TBConnection.__init__` requires `server_url` to match
   `(https?)://host:port/api/` exactly and takes `verify` as a required positional
   argument. A configured `tb_server_url` without an explicit port would raise
   `ValueError` at login rather than returning 401, so login must surface that as a
   configuration error rather than bad credentials.
6. Whether the August attempt was abandoned for a reason not recoverable from its
   bytecode (see section 2.1).
