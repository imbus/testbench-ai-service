# Admin web UI — phase 3 decision log (agents and projects)

Spec: `docs/superpowers/specs/2026-09-08-admin-web-ui-design.md` (binding authority; amended
by its own §12.2 after this phase).
Predecessors: `2026-09-08-admin-web-ui-phase-1.md`, `2026-09-09-admin-web-ui-phase-2.md` and
its decision log.
Branch: `admin-web-ui`. Base at start: `839c98b`.

Phase 3 was designed and then implemented directly, step by step, rather than planned into
tasks and dispatched to subagents the way phase 2 was — so there is no task ledger here. This
is the decision record: what was decided, what implementation changed about those decisions,
and what was verified.

## 1. Scope

Make agents and projects editable from the console: which agents run, which prompt each one
uses, and which of those decisions a given TestBench project overrides. Same file, same draft,
same preview and apply as phase 2 — `config.toml` and nothing else.

Deliberately **not** in phase 3:

- **The prompt "fork"** (materialising a per-project prompt file from a global one). Master
  spec §2.1 folds it into phase 3; it moves to phase 4. A fork writes a *second* file that must
  land in the same transaction as the `config.toml` key pointing at it, and phase 2's
  `write_atomic` is single-file by construction.
- **Per-project `llm_config` editing.** A project that already carries an `llm_config` block
  renders read-only with "edit in `config.toml`".
- **Prompt file writes of any kind.** Phase 3 reads prompt YAML metadata; every write still
  goes through the single-file `config.toml` path.
- **Agent create and delete**, and editing `endpoint_path` / `class_path` (D6).

## 2. Findings that shaped the design

Verified against the running code, not read off the plan.

1. **`agents` replaces, it does not merge — and a partial block is rejected.**
   `AppConfig.agents` is a plain default with no merging validator and every `AgentConfig`
   field required. `agents = {"x": {"enabled": false}}` fails validation; spelling the block
   out in full silently deletes every agent the operator did not mention. The Agents screen's
   primary verb was unexpressible in `config.toml`.
2. **Project blocks are keyed by the raw TestBench project name**, which may contain a dot, a
   space or a quote — and the phase-2 edit paths were split on `.`.
3. **`vars` could not hold a number**, though `prompt.yaml` has always been able to declare
   `number` and `boolean` value types.
4. **Variant and variable metadata live in the prompt YAML**, not in config, so the console
   cannot render a variant select or a typed variable control without reading it.
5. **`validate_config` imports every `class_path`** — one more reason `class_path` is not an
   editable field (D6).
6. **The console has no live TestBench connection after login** (D3).
7. **Restart classification for agents already exists** from phase 2.
8. **"Inherit" is already expressible in the shipped overlay**: no edit and no saved value is
   inheritance, a value is an override, a queued `null` removes the key. Phase 3 needed no new
   overlay semantics.

## 3. Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Prompt fork moves to phase 4 | Keeps phase 3's apply path byte-identical to phase 2's: one file, one `.bak` |
| D2 | Edit paths use TOML-style quoted segments | Reads like the TOML it edits; every phase-2 path round-trips unquoted |
| D3 | Project list is fetched once at login, cached on the session | One outbound call per session; no repeated reuse of a token that may be a password |
| D4 | A failed projects fetch never fails the login, and `POST /projects/refresh` exists | Service, LLM and logging editing must not depend on an unrelated TestBench endpoint |
| D5 | The `agents` table merges onto the built-ins | Makes "disable one agent" expressible; fixes a service-level footgun, not just a console one |
| D6 | Global agents: `enabled` + `prompt.*` editable; `endpoint_path` / `class_path` read-only; no create or delete | A `class_path` typo stops the service booting, needs a restart anyway, and is imported at preview time. Defining an agent means shipping a Python class — a deploy, not a config change |
| D7 | A read-only prompt-metadata endpoint lands in phase 3 | Without it `variant` is typo-prone free text and `vars` cannot be typed. Uses `resolve_within`, which shipped in phase 1 and had no consumer until now |
| D8 | Per-project surface is `language` + agent overrides only | Follows the source design's Projects screen |
| D9 | One draft, one pending banner, one diff dialog, one apply | It is all one file. Two applies against one file means the second is baselined on a disk state the first just changed, and the operator approves a diff that no longer describes what gets written |

### 3.1 Correction to D5

D5 originally said to wire in `utils/config.py`'s existing `merge_model_dicts`. Implementation
showed it cannot do this job: it merges with `model_copy(update=...)`, which is both shallow
and unvalidated, so `{"prompt": {"variant": "x"}}` replaces the whole `PromptConfig` with a raw
dict — verified directly — and every later `agent.prompt.file` lookup raises `AttributeError`.
A local `_deep_merge` over raw dicts, applied *before* pydantic validates, reaches D5's
intended outcome with real validation and correctly nested partials, and lets pydantic
field-address every failure as `agents.<key>.<field>`. `merge_model_dicts` is left as it is,
still unused.

Two consequences of the merge, both recorded in `CHANGELOG.md`:

- An agent can no longer be **removed** by omitting it from a declared set — only disabled.
  That costs nothing observable: a disabled agent gets no router, so `enabled = false`
  withdraws the endpoint exactly as removal did.
- An operator who declared one *complete* agent in order to implicitly disable the rest gains
  those agents back. That usage is undocumented — `docs/configuration.md` documents declaring
  each agent fully and says nothing about replacement semantics — and the old behaviour is
  closer to a bug than a feature. Every documented usage behaves identically before and after.

## 4. What was built, and where it deviated

### 4.1 The path tokenizer

`testbench_ai_service/webui/paths.py` and `frontend/src/api/paths.ts` implement one grammar in
two languages, against one fixture: `tests/fixtures/path_vectors.json` (15 round-trip, 2
split-only, 22 invalid cases), read by both suites. Divergence between the two would otherwise
be silent, and the browser composes the paths the server tokenizes.

Call sites moved off `split('.')`: `edits.py` (`_check_path_prefix_collisions`,
`_validate_single_path`, `merge_edits`), `fields.ts::valueAt`, `Field.tsx`,
`ReadOnlyField.tsx`. `reload.py::_resolve_dotted_path` was left alone — it resolves fixed
literal field names against a pydantic model, not operator-supplied paths.

`_check_path_prefix_collisions` compares segment tuples rather than string prefixes, so two
spellings of one address collide correctly. That forced per-path validation to run *before* the
collision check, since the check tokenizes.

The grammar as implemented deviates from the design as first written; the design was corrected
in place with the reason.

### 4.2 Backend changes outside `webui/`

`PromptConfig.vars` and `ProjectPromptConfig.vars` widen to `str | bool | int | float` — `bool`
before `int` deliberately, since `bool` is a subclass of `int`. Pydantic's smart union is
pinned by test: `true` stays `bool`, `10` stays `int`, `"10"` stays `str`, `1.5` stays `float`.

`AppConfig.merge_agents_onto_defaults` plus `_deep_merge`, as corrected in §3.1.
`docs/configuration.md` gains the merge semantics, the one-line disable example, and a
"Required" column qualified to "required when declaring a new agent".

### 4.3 The API surface

- `Session` gains `projects`, `projects_fetched_at`, `projects_error`. `projects` is a
  per-session list: a shared mutable default would leak one operator's list into every session
  in the process, and there is a test for that.
- `webui/projects.py` — nothing in it raises. `fetch_projects` catches bare `Exception`
  deliberately: the vendored client sorts its own unvalidated JSON, so an unexpected payload
  raises `KeyError`/`TypeError` from *inside* the library and a curated tuple would not hold.
- `authenticate` returns a `LoginResult` (`token`, `roles`, `projects`) instead of a
  `(token, roles)` tuple. The fetch happens inside the existing `try`, before the `finally`
  closes the connection — asserted by call order in a test, not just by reading the code.
- `GET /projects` is session-gated and makes no outbound call. `POST /projects/refresh` is
  admin + CSRF and never 5xx: a failed refresh is a 200 with `source: "unavailable"`, and the
  previous list is kept rather than replaced with an empty one.
- `GET /prompts/{lang}/{agent}/meta` reuses `models.prompt.PromptVariableDefinition` verbatim,
  so `value_type` reaches the browser as the same literal the YAML schema declares. No message
  bodies.

Three deviations worth recording:

1. **`?file=` resolution mirrors the runtime, not the design's single path.** The design said
   `prompts_dir/<lang>/<file>`; `validators.resolve_prompt_file_path` actually searches
   `prompts_dir/<lang>/<file>` *then* `prompts_dir/<file>`. The endpoint does both, or the
   console would 404 on a shared prompt the service boots with happily. Containment is checked
   against `prompts_dir` for both candidates, and a traversing `{lang}` is still refused
   because the language directory goes through `resolve_within` first.
2. **A `.yaml`/`.yml` allowlist on the resolved path**, beyond what the design asked for.
   Containment alone would let `?file=` read any file under `prompts_dir`, which also holds the
   Jinja templates. Applied to the *resolved* path, so `p.yaml.` and `p.yaml:evil` are both
   refused. `?file=` also needs its own empty-string guard: `Path("")` is `Path(".")`, so once
   joined onto a base path `resolve_within`'s own empty check can no longer see it.
3. **`declared_prompt_file` prefers the on-disk value, falling back per field.** The forms show
   `GET /config`'s `disk`, so metadata must resolve from the same place. The fallback is per
   field, not wholesale, matching the agents merge: a config with no `[agents]` block, or one
   overriding only `prompt.variant`, still inherits the built-in's `prompt.file`. The on-disk
   table is unvalidated TOML, so every level of it is type-guarded.

One test had to move layers: `/admin/api/prompts/..%2f..%2fetc/x/meta` never reaches the
endpoint — phase 1's SPA fallback answers any unmatched `/admin/*` with `index.html`, so it is
a 200 that read nothing. The HTTP test uses `%2e%2e` (which does route, as `lang == ".."`) and
the deeper case is asserted directly on `resolve_prompt_file`.

### 4.4 The frontend

`api/agents.ts` carries the inherit/override model: `effectiveAgent` deep-merges a sparse
project override onto the global table, mirroring the server. Every level is type-guarded —
`disk` is unvalidated TOML, and a bad shape must cost a row, not a render.

`Field` gains an inherit mode over the phase-2 overlay semantics rather than new ones.
`screens/agentFields.ts` exposes `AGENT_FIELDS(scope, …)` as functions rather than constants,
because the path depends on scope. Both new screens are ungated and render through
`ReadOnlyField` for a non-admin, like Status: gating the nav link would hide information a
non-admin is allowed to see.

Four things worth recording, three of them bugs the tests caught:

1. **A pre-filled inherited text input cannot be typed over.** Clearing it calls `unsetValue`,
   which queues a removal, which is still inheritance, which puts the inherited value straight
   back — so the next keystroke appends to it. Fixed by splitting the control types: switches
   and selects *display* the inherited value (a switch has no placeholder, and toggling must
   move away from what is shown), while text, number, list and textarea render **empty with the
   inherited value as a placeholder**. An empty box is also the honest rendering of "no
   override here".
2. **`AgentDetail` crashed on its own first render.** `usePromptMeta` sat below the
   loading/error early returns, so the hook count changed between renders. Every hook now runs
   above the returns — the same hazard `App.tsx` documents at its own early returns.
3. **`Agents` and `Projects` crashed on a config payload without `running`/`disk`.** Both now
   default to `{}`: an operator who cannot load the console cannot fix the config either.
4. **The Agents tests passed on the first run of the implementation**, which is a weak red for
   17 behaviours. Verified by mutation instead: dropping config-only projects from the matrix
   union failed exactly 2 tests, and pointing the tri-state at the global path instead of the
   project path failed exactly 2 others. Both restored.

One test premise turned out to be wrong rather than the code: "global scope inherits from
nothing" is true of the agent *settings* but not of a prompt *variable*, which inherits from
the prompt YAML's own `default_value` even globally. The test was narrowed to the settings
block and a second one added for the prompt default.

## 5. Verification

| Suite | Base `839c98b` | Phase 3 |
|---|---|---|
| `tests/unit/webui` | 298 passed | **451 passed**, 0 failed |
| `tests/unit` | 816 passed, 54 failed, 3 errors | **988 passed**, 54 failed, 3 errors |
| frontend `vitest run` | 229 passed, 18 files (as recorded at phase-2 completion) | **401 passed**, 26 files |
| `tsc -b`, `npm run build` | — | clean |
| ruff check / ruff format / mypy | — | clean on every touched file |
| OpenAPI generation | — | all three new routes present; response schemas match the design's shapes field for field |

Both Python rows were measured on the same machine in the same session, the base column from
a `git worktree` at `839c98b`; the frontend base is the figure recorded when phase 2 finished,
not re-measured (the worktree has no `node_modules`). The 54 failures and 3 errors are byte-identical between the two
and all live under `tests/unit/agents/` and `tests/unit/utils/` — prompt-template and agent
fixtures this branch does not touch. Phase 3 adds 172 passing backend tests and 172 passing
frontend ones, and removes none.

One caveat on the `tests/unit/webui` row: it is green in both columns only because a TestBench
was listening on `localhost:9443` while it ran. See §6.

Pre-existing ruff findings in `testbench_ai_service/agents/defect_explainer/agent.py`
(4×F401, I001, W293) are untouched — not this branch's work.

## 6. Left open

- **Phase 4** owns the prompt editor, the fork (D1) and per-project `llm_config` editing (D8).
- **17 environment-dependent failures in `tests/unit/webui/test_config_routes.py`.**
  `validate_config_dict` → `AppConfig` → `validate_tb_server_url` makes a **real network call**
  to the configured `tb_server_url`. The tests patch `validate_tb_server_url` only around
  `create_app`, not around the preview/apply/status routes, so the suite passes or fails
  depending on whether something is listening on `localhost:9443`. Not phase 3's to fix, but it
  should not stay that way; worth doing before phase 4.
- Two phase-2 leftovers, untouched: the CRLF→LF rewrite on first save of a CRLF `config.toml`,
  and `main.py:107`'s relative `Path("config.toml")` fallback.
