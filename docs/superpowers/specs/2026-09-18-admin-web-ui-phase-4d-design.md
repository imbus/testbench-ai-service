# Admin Web UI — Phase 4d: per-project LLM configuration

**Status:** design, 2026-09-18. Binding authority for
`docs/superpowers/plans/2026-09-18-admin-web-ui-phase-4d.md`.

**Parent spec:** `docs/superpowers/specs/2026-09-08-admin-web-ui-design.md`
(§12 Increments names this phase; §12.2 and §12.3 carry the amendments from
phases 3, 4a and 4b).

This design lives under `docs/` rather than in the gitignored
`.superpowers/sdd/` workspace, deliberately. Phase 4c's ledger recorded the
problem it fixes: 4c's `design.md` was gitignored and therefore absent from git
history, while the plan committed under `docs/` named it as the binding
authority — a committed document pointing at a spec that does not exist in the
repository. The working notes stay in the SDD workspace; the spec is committed.

---

## 1. Purpose

A project can already override `language` and any agent's settings from the
console. Its `llm_config` is the one override that still requires hand-editing
`config.toml` — the Projects screen renders it as a read-only JSON blob
labelled "edit in config.toml" (`Projects.tsx:399-422`). This increment makes
it editable, with the same inherit / override / remove semantics every other
per-project control already uses.

It also removes the reason an operator may not be able to reach the console at
all (§5.1).

## 2. Scope

**In:**

- Boot survives a missing or invalid LLM provider credential (§5.1).
- The LLM screen gains a scope tab strip: Global, one tab per project that
  overrides `llm_config`, and a select to add a project (§5.2).
- In project scope, the eight `LLMConfig` fields are editable as sparse
  overrides with an inherited-value affordance (§5.3).
- The screen reports which credential a project's runs would use (§5.4).
- The Projects screen's read-only `llm_config` panel becomes a link into the
  right tab (§5.5).

**Out, and why:**

- **`extra_models` stays global-only.** `get_llm_config` merges with
  `model_copy(update=project.llm_config.model_dump(exclude_unset=True))`, so a
  project that declares *any* `extra_models` entry replaces the global table
  wholesale rather than merging into it — the same trap `prompt.vars` has, and
  the one `AgentDetail`'s `varsReplaced` notice exists to explain. Exposing
  that needs a scope-aware `ModelTable` plus its own warning, and it is not
  what makes per-project LLM config useful. The table stays on the Global tab
  only, and the project tabs do not render it.
- **No change to the merge semantics themselves.** Making `extra_models` merge
  per key would change what four production agents resolve at runtime, from a
  console increment. Out of scope; recorded in §8.
- **No credential editing.** Unchanged from the parent spec's §15: the console
  reports key presence and never reads, writes or displays a key value.
- **No per-project `admin_ui`, `logging` or service settings.** `ProjectConfig`
  has exactly three fields (`language`, `llm_config`, `agents`); the other two
  are already editable.

## 3. Findings that shape the design

Verified against the running code on 2026-09-18, by execution, not by reading
the plan.

### 3.1 The boot failure is one unguarded call, and the fix already exists

`main.py:122` calls `init_services(app)`, which calls
`app.state.llm_factory.init_clients([app.state.config.llm_config])`
(`main.py:34`) with no guard. `init_clients` calls `get_client` for each
config, and `_get_api_key` (`llm/factory.py:146`) raises `ValueError` when the
provider's environment variable is unset. The service therefore cannot start
without a provider credential, including when the operator's goal is to start
the console and fix the provider setting that is wrong.

`reload.py:173-186` already does the right thing for the same call after a
config apply: it wraps `init_clients` in `try/except`, logs a warning, and
records that "the clients will be created on demand; a missing provider
credential will surface on the next agent request." The behaviour is therefore
already accepted by this codebase — it is merely not applied at boot. §5.1 is
the smallest change that makes the two paths agree.

### 3.2 Sparse project overrides inherit per field — measured

The whole screen rests on this, so it was executed rather than assumed. With a
global `[llm_config]` of `provider = "anthropic"`, `model = "claude-opus-5"`,
`max_retries = 7` and a project block declaring only `timeout = 12.5`:

```
provider    : LLMProvider.ANTHROPIC
model       : claude-opus-5
max_retries : 7
timeout     : 12.5
project block model_dump(exclude_unset=True) == {'timeout': 12.5}
```

`LLMConfig`'s own defaults (`provider = openai`, `auth_method = api_key`) do
**not** leak over the global values, because `exclude_unset=True` omits every
field the project did not state. This is what makes "inherit" representable at
all, and §7 requires a test pinning it.

### 3.3 The write path is already generic

`webui/edits.py` has no allowlist of editable paths — it takes a sparse map of
dotted paths, enforces the redaction sentinel, prefix collisions, `MAX_EDITS =
500` and `MAX_PATH_SEGMENTS = 8`, and merges into a freshly read disk config.
`projects."<name>".llm_config.<field>` is four segments. Validation is equally
generic: `validate_config_dict` constructs `AppConfig` and turns each pydantic
error location into a path through `join_path` (`validate.py:67-78`), so an
issue on a project's LLM field comes back addressed exactly as the form
addresses it, including quoting for a project name containing a dot.

**No backend change is needed for the editing itself.** This increment is
frontend work plus §5.1.

### 3.4 `Field` already has the override affordance

`Field`'s `inheritedFrom?: { value: unknown; label: string }` prop
(`Field.tsx:47`) was built in phase 3 for exactly this: it renders text-like
controls empty with the inherited value as a placeholder, shows the inherited
value in selects and switches, and treats a queued `null` as "go back to
inheriting". No new overlay semantics are required.

### 3.5 `GET /models?project=` already exists

Phase 4c shipped `build_catalogue(config, project)` and the route's `project`
query parameter (`routes.py:729-734`), plus the `useModels(project)` hook. The
per-project credential notice in §5.4 is a consumer of work already done, not
new backend surface.

### 3.6 A select has no way back to inheriting without `allowEmpty`

`Field`'s `select` renders a blank option only when `spec.allowEmpty` is set,
and that blank option is the only control that calls `draft.unsetValue`.
`LLM_FIELDS` sets it on nothing, which is correct globally — the service always
has a provider — and wrong in project scope, where every field must be
removable. Hence §5.3's scope-dependent field specs.

## 4. Decisions

- **D1 — Scope tabs on the LLM screen, not a form on the Projects card.** The
  console already has one answer to "edit this thing globally or per project":
  `AgentDetail`'s scope tab strip. A second, differently-shaped answer on the
  Projects screen would mean two mental models for one concept. Chosen by the
  user on 2026-09-18 over the alternative.
- **D2 — The selected scope lives in the URL, not component state.**
  `AgentDetail` keeps it in `useState`, which is why it cannot be linked to.
  The Projects screen has to link into a specific project's LLM tab (§5.5), and
  phase 4b's I3 finding was precisely a route that could not be refreshed or
  bookmarked. A `?project=<name>` search parameter is deep-linkable, needs no
  new route inside the SPA mount, and survives a reload.
- **D3 — Choosing a scope is navigation, never an edit.** Carried verbatim from
  `AgentDetail`'s contract: selecting a project must not queue an empty
  `[projects."X".llm_config]` table. A change appears in the diff only when the
  operator sets a field.
- **D4 — `ScopeTabs` is extracted from `AgentDetail`, not duplicated.** The tab
  strip, the "add project" select and the known-projects union (cached
  TestBench list ∪ projects named in config) are non-trivial and already
  reviewed. A second copy would be the kind of drift phase 4b's M5-a finding
  caught. The extraction is a pure refactor pinned by `AgentDetail`'s existing
  tests.
- **D5 — The project tabs are driven by the config, not by TestBench.** A tab
  exists for every project with an `llm_config` block on disk; every other
  known project is reachable through the add-project select. This mirrors
  `overridingProjects` for agents, and it means an unreachable TestBench never
  removes a tab for an override that exists.

## 5. Behaviour

### 5.1 Boot survives a missing provider credential

`init_services` wraps the `init_clients` call in `try/except Exception`, logs a
warning naming the failure, and continues. The clients are created on demand by
`get_client`, so a genuinely missing credential still fails the first agent
request — which is where it is actionable — rather than the process start.

The warning text states the consequence, matching `reload.py`'s precedent:
clients will be created on demand and a missing credential surfaces on the next
agent request.

`BaseException` is **not** caught: `KeyboardInterrupt` during startup must still
stop the process. `SystemExit` is not caught either — unlike
`validate_config_dict`, this call does not reach into `utils/config.py`'s
`sys.exit()` paths.

### 5.2 The scope strip

Above the fields, on the LLM screen only:

```
LLM provider                    [testbench-ai-service.llm_config] · /path/config.toml
┌────────────────────────────────────────────────────────────┐
│ Global │ Alpha │ Release 2.0 │            + project ▾      │
└────────────────────────────────────────────────────────────┘
```

- **Global** is always present and selected by default.
- One tab per project whose *disk* config declares an `llm_config` table, in
  config order.
- The currently selected project always has a tab, even before it declares
  anything — otherwise selecting it from the add-project select would deselect
  it immediately.
- The add-project select offers every known project (the session's cached
  TestBench list ∪ the projects named in config) that has no tab yet.
- Selecting a scope sets `?project=<name>`; selecting Global removes it.

### 5.3 Editing in project scope

The same eight fields as global scope — `provider`, `model`, `auth_method`,
`azure_endpoint`, `api_version`, `class_path`, `timeout`, `max_retries` —
addressed at `projects."<name>".llm_config.<field>`, built with `joinPath` and
never by string concatenation (phase 4c's C2 finding: a project named
`Release 2.0` tokenizes into the wrong table otherwise).

Each field is rendered with `inheritedFrom = { value: <the global value>,
label: "global" }`, which gives the three states the draft already has:

| Operator sees | Draft state | `config.toml` |
|---|---|---|
| Empty box, global value as placeholder | no edit, nothing on disk | no key |
| A value | `setValue` | `key = value` |
| Cleared box | `unsetValue` → queued `null` | key deleted |

Every select gains `allowEmpty` in project scope (§3.6), so `provider` and
`auth_method` can be taken back off.

The `extra_models` table renders on the Global tab only (§2).

`issueMatchesField` already matches an issue path against a field key by exact
equality or a `key + '.'` prefix; because the scoped keys are full paths, a
validation issue on `projects."Alpha".llm_config.provider` lands on the right
control with no change to that function.

### 5.4 Which credential this project would use

Under the fields in project scope, one read-only line per configured provider,
sourced from `GET /models?project=<name>` — already available through
`useModels(project)`:

- key present → the project's own key is set, and its runs use it;
- key absent → runs fall back to the global credential.

Presence only, never a value (parent spec §14). This closes the gap 4c's
`credential_scope` field describes from the other side: the test-run result
reports which credential *was* used, and this reports which one *would* be.

### 5.5 The Projects screen stops lying

`Projects.tsx`'s per-project `llm_config` panel currently renders
`JSON.stringify(llmConfig, null, 2)` under the label "llm_config · edit in
config.toml". The JSON summary stays — it is a useful at-a-glance view of what
the project overrides — and the label becomes a react-router `<Link>` to
`/admin/llm?project=<name>`.

`<Link>`, never `<a href>`: phase 4c's Task 11 ruling established that a plain
anchor is a full page load, which bypasses `useBlocker`, fires the browser's
native leave-site dialog and loses queued draft edits.

## 6. What this does not change

- No new or changed backend route, model or validation rule.
- No change to `get_llm_config`'s merge, to `LLMConfig`, or to `ProjectConfig`.
- No change to how the draft, preview, diff or apply path works: a scoped LLM
  edit is an ordinary path edit and travels the phase-2 machinery unmodified.

## 7. Testing

Beyond each task's own tests, three properties are required:

1. **Inheritance is real, not assumed.** A backend test pinning §3.2: a project
   declaring only `timeout` inherits the global `provider`, `model` and
   `max_retries`, and its `model_dump(exclude_unset=True)` contains only
   `timeout`. If this ever regresses, every field on the project tab silently
   starts writing `LLMConfig`'s defaults into the operator's file.
2. **A dotted project name round-trips.** `Release 2.0` must produce
   `projects."Release 2.0".llm_config.provider` and tokenize back to four
   segments. Phase 4c shipped exactly this bug by building paths with string
   concatenation, and §7 of its design had required the test that was dropped.
3. **Boot survives.** A test that `create_app` succeeds with a config whose
   provider has no credential in the environment, asserting the app is built
   rather than asserting a log line.

## 8. Out of scope and known gaps

- **`LLMConfig` sets `model_config = ConfigDict(extra="allow")`, so a
  misspelled key is silently accepted.** Measured:
  `LLMConfig(provdier="openai").model_dump(exclude_unset=True)` returns
  `{'provdier': 'openai'}` with no error, and that key reaches the merged
  config and does nothing. The form itself can never produce one — it writes
  only the eight known paths — so this increment does not make the situation
  worse, and tightening it to `extra="forbid"` would reject configurations that
  boot today. Recorded for whoever next owns config validation.
- **A project's `extra_models` replaces rather than merges** (§2). Unchanged
  and now documented in the operator docs.
- **`credential_scope` describes the credential, not the config** (4c §9,
  unchanged): a project with an `llm_config` override but no project key
  reports `global` scope with the project's settings. §5.4 shows both halves,
  which is the closest this increment gets to closing it.
- **Azure Entra ID projects.** `get_llm_config` re-checks the
  `auth_method = entra_id` / `provider = azure_openai` pairing after the merge
  and raises `ValueError` when a project breaks it. That surfaces as a
  validation issue at preview time, addressed to the project's `auth_method`
  field, which is the correct place — but the message is the runtime's, not the
  console's, and reads accordingly.
- The six live-TestBench items in the parent spec's §16 remain open; nothing
  here closes any of them.
