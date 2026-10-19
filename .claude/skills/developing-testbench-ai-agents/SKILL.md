---
name: developing-testbench-ai-agents
description: Use when creating, changing, reviewing or debugging an agent of the TestBench AI Service - built-in agents in testbench_ai_service/agents, custom agents registered via class_path, their prompt.yaml (variants, vars, required fields the TestBench client plugin renders as a form), write-back templates or precheck - or when agent code needs TestBench concepts (TOV, cycle, test case set, specification, lock, UID vs key), TestBench REST endpoints and JWT permissions, the TestBench JSON report (cycle_structure.json, test case set/test case files) or protocol.json for importing execution results, or has to write rich-text HTML (description, review comment, execution comment) back into TestBench.
---
# Developing TestBench AI Service agents

## Overview

**TestBench** (imbus) is a test management tool: projects contain test object versions (TOVs)
with a tree of test themes and test case sets (specification) and test cycles (execution).
The **TestBench AI Service** is a FastAPI service that TestBench calls to run an **agent**: an
agent reads TestBench data over the TestBench REST API, renders a Jinja prompt, asks an LLM, and
writes the answer back into a TestBench rich-text field.

Background you will need, load on demand:

| Need                                                                                  | Read                                                                                  |
| ------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| TestBench terms: TOV, cycle, UID vs key, spec vs execution, locks, roles, permissions | `references/testbench-domain.md`                                                    |
| Which endpoint to call, its URL, JWT permission, allowed roles                        | `references/testbench-rest-api.md` (index). Schemas: `references/openapi.yml` is ~7000 lines, so **grep** it for the schema or `operationId` (`grep -n "SpecificationDetailsForUpdate:" …`), never read it whole |
| JSON report files (structure, test case set, test case), `protocol.json`, execution import | `references/testbench-json-report.md`, real example in `references/examples/` |
| Auth (JWT scope vs body), config precedence, LLM client/model selection, prompt rendering, HTTP retries, testing | `references/service-internals.md` |
| Any HTML that ends up in TestBench                                                    | **REQUIRED SUB-SKILL:** `testbench-rich-text-html`                            |
| `prompt.yaml`: structure, variants, `vars` (plugin form fields), `required`, how the TestBench plugin renders it | `references/prompts-and-plugin.md` (schema: `testbench_ai_service/prompts/prompt.schema.json`) |

Source of truth is the code. `docs/agents/custom-agent.md` is partly stale (as of 2026-10):
`precheck()` has **no** `auth_info` parameter, `build_prompt` lives in
`utils/build_prompt_utils.py`, `get_test_case_set_nodes` lives in `utils/testbench.py`,
`AGENT_DATA_CLASS` is mandatory, and its skeleton lacks `REQUIRED_PERMISSIONS`/`ALLOWED_ROLES`.

## Lifecycle

Users start agents from the **AI plugin in the TestBench client** (right-click → Export).
The plugin builds its dialog from the agent's `prompt.yaml` (served by `GET /agents` and
`GET /agents/{key}/prompt`) and sends the user's choice as `prompt_config.variant`/`vars`. The
YAML is the agent's UI; see `references/prompts-and-plugin.md`.

```
TestBench ──POST /<endpoint_path> or /agents/{key}/trigger (JWT, TriggerAgentRequest)──▶ router
router (agents/routes.py, generic for all agents):
  build ExecutionContext → agent enabled for project? (404) → JWT has REQUIRED_PERMISSIONS? (403)
  → user has one of ALLOWED_ROLES in project? (403) → prompt vars match AGENT_DATA_CLASS? (422)
  → agent.precheck(context, conn)  ── passed=False ──▶ 409 with warnings
  → schedule tasks.run_agent → respond 202 {"status": "accepted", "warnings": [...]}
background: llm_client = factory(...) → agent.run(context, conn, llm_client, item_ids)
  → per item: read data → mark "started" (lock) → get_ai_response → write result (unlock)
              on error: restore previous content + "failed" note (unlock), re-raise
```

- Exceptions in `run()` are only logged; the user sees nothing unless the agent writes the
  "failed" state into TestBench. That is why every write-back has a failure path.
- Not every bad request gets a clean 4xx: an unknown `prompt_config.variant` (`ValueError`), an
  unknown key on `/agents/{key}/trigger` (`KeyError`) and any non-HTTP exception in `precheck()`
  give **500**. A TestBench `HTTPError` raised in precheck is passed through with TestBench's
  status code; `Timeout`/`ConnectionError` become 502. Report expected precheck failures as
  `PrecheckResult(passed=False, warnings=[...])` (→ 409), not as exceptions.

## Agent contract (`agents/base.py`)

```python
class MyAgentData(AgentData, total=False):    # keys = {{ agent.<key> }} in prompts
    test_case_set: str

class MyAgent(Agent):
    AGENT_DATA_CLASS = MyAgentData               # required; validated against the prompt
    REQUIRED_PERMISSIONS = frozenset({...})       # JWT permission of EVERY endpoint used
    ALLOWED_ROLES = frozenset({ProjectRole.TestManager, ...})  # None = no role check

    async def precheck(self, context: ExecutionContext, conn: TBConnection) -> PrecheckResult:
        # fast, read-only: version check, required keys, scope, skip locked items
        # return PrecheckResult(passed=bool(items), items=[uid, ...], warnings=[...])

    async def run(self, context, conn, llm_client: LLMClient, item_ids: list[str]) -> None:
        # asyncio.gather one task per item; use self.get_ai_response(...)
```

- `precheck()` runs inside the HTTP request: no LLM calls, no writes. Start with
  `if r := check_min_testbench_version(context, conn): return r`. Return item **UIDs**; put
  per-item skip reasons (translated) in `warnings`.
- `REQUIRED_PERMISSIONS` always includes `ReadProjectDetails` (context build) and
  `ReadOwnUserDetails` (role check via `users/self/projectRoles`), plus the permission of every
  endpoint the agent's own code and helpers call (see `references/testbench-rest-api.md`). It
  is only checked for **JWT** callers; session-token callers skip it.
- `ALLOWED_ROLES` is matched against the user's **project** roles only (always checked, also
  for session tokens). The type allows `GlobalHumanRole`, but a global role there never matches.
- `run()`: wrap blocking `requests`/helper calls in `asyncio.to_thread`, but `await` the
  helpers that are already `async def` (`patch_test_structure_element_spec`, the `patch_*`
  write-backs); the full sync/async list is in `references/testbench-rest-api.md`. One task per
  item, each with its own failure path. The built-in agents use plain `asyncio.gather(*tasks)`
  (enough, because each item handles its own failure); `return_exceptions=True` additionally
  lets you log every item's error instead of only the first. Large scopes mean one LLM call per
  item: consider an `asyncio.Semaphore` for provider limits.
- `conn.session` raises `HTTPError` on every 4xx/5xx (response hook), including `409` on PATCH.
- Re-running an agent prepends a new result above the previous content each time; decide
  (and document) whether that is wanted.
- `await self.get_ai_response(llm_client, context.llm_config, context.prompt_config, agent_data)`
  renders the prompt variant, resolves the model and returns an `AgentResult` (text in
  `.result`); use it instead of calling `build_prompt`.
- All user-visible strings go through `get_translation(key, context.language, **kw)` with keys
  in both `locales/en.json` and `locales/de.json`.

## Files for a new built-in agent `<key>`

| File                                                                                                 | Content                                                                          |
| ---------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| `testbench_ai_service/agents/<key>/agent.py`                                                       | `AgentData` subclass + `Agent` subclass                                      |
| `testbench_ai_service/agents/<key>/utils.py`                                                       | write-back functions (`patch_*_started/result/previous`)                       |
| `testbench_ai_service/prompts/{en,de}/<key>/prompt.yaml` + `*.jinja`                             | prompt definition; `name`/`summary`/`description` are what TestBench shows |
| `testbench_ai_service/templates/{en,de}/<key>/started.jinja`, `template.jinja`, `failed.jinja` | HTML written to TestBench                                                        |
| `testbench_ai_service/locales/{en,de}.json`                                                        | precheck and result messages                                                     |
| `testbench_ai_service/config.py`                                                                   | default `AgentConfig(enabled, endpoint_path, class_path, prompt)`              |
| `config_example.toml`                                                                              | the same agent section (what installations copy); must still parse             |
| `docs/agents/<kebab-key>.md` (e.g. `test-case-set-reviewer.md`)                                    | agent page incl. required permissions, roles, `agent.*` variables              |
| `tests/unit/agents/<key>/`, `tests/integration/test_<key>.py`, `tests/prompt_engineering/`     | tests                                                                            |

## Registering the agent

The config **key** (`<key>` below, snake_case) is the agent's identity everywhere: URL
`/agents/<key>/trigger`, prompt dir `prompts/<lang>/<key>/`, template dir
`templates/<lang>/<key>/` (via `AGENT_KEY`), config sections. Keep all of them identical.

**Built-in agent**: add a default in `testbench_ai_service/config.py` …

```python
DEFAULT_AGENTS: dict[str, AgentConfig] = {
    # … existing agents …
    "test_case_set_translator": AgentConfig(
        enabled=True,
        endpoint_path="/test-case-set-translations",   # dedicated POST route, plural noun, kebab-case
        class_path="testbench_ai_service.agents.test_case_set_translator.agent.TestCaseSetTranslator",
        prompt=PromptConfig(
            file=Path("test_case_set_translator/prompt.yaml"),  # relative to prompts_dir/<lang>/
        ),
    ),
}
```

… and the same constant in `agents/<key>/utils.py`, used for every `resolve_template_path` call:

```python
AGENT_KEY = "test_case_set_translator"
```

… **and** the section in `config_example.toml` and in every `config.toml` you run with. A
`[testbench-ai-service.agents.*]` table in `config.toml` **replaces**
`DEFAULT_AGENTS` as a whole, and `testbench-ai-service init` writes all defaults into the file,
so a new default never shows up in an existing installation by itself. A global agent table
must be complete (`enabled`, `endpoint_path`, `class_path`, `prompt`); only project overrides
can change a single field:

```toml
[testbench-ai-service.agents.test_case_set_translator]
enabled = true
endpoint_path = "/test-case-set-translations"
class_path = "testbench_ai_service.agents.test_case_set_translator.agent.TestCaseSetTranslator"

[testbench-ai-service.agents.test_case_set_translator.prompt]
file = "test_case_set_translator/prompt.yaml"
# variant = "Full Translation"            # optional: overrides default_variant of the YAML
# [testbench-ai-service.agents.test_case_set_translator.prompt.vars]
# target_language = "German"              # optional preset; dropped entirely as soon as the
#                                         # request sends ANY vars (dict replaced, not merged)
```

The repo-root `config.toml`, `prompts/` and `templates/` are **gitignored** local copies: the
developer's dev `config.toml` points `prompts_dir`/`templates_dir` at them. They are missing in a
fresh clone or worktree, and nothing written there gets committed. So put every file under
`testbench_ai_service/` and the section into `config.py` + `config_example.toml`; if the local
copies exist, copy the new prompt/template dirs and the section there too, or the locally
running service won't find them. A comment in TOML ends at the line break, so check the example
still parses: `python -c "import tomllib; tomllib.load(open('config_example.toml','rb'))"`.

**Custom (external) agent**: same `Agent` subclass in any importable package (installed in the
service's environment, e.g. `pip install -e ./my_tb_agents`); no change to `config.py`:

```python
# my_tb_agents/release_notes/agent.py  - one Agent subclass per module (startup
# validation reads AGENT_DATA_CLASS from the classes in this module)
from testbench_ai_service.agents.base import Agent
from testbench_ai_service.models.agent import AgentData

class ReleaseNotesAgentData(AgentData, total=False):
    test_case_set: str

class ReleaseNotesAgent(Agent):
    AGENT_DATA_CLASS = ReleaseNotesAgentData
    ...
```

```toml
# Keep the built-in agents' sections in this file, otherwise they disappear (see above).
[testbench-ai-service.agents.release_notes]
enabled = true
endpoint_path = "/release-notes"
class_path = "my_tb_agents.release_notes.agent.ReleaseNotesAgent"

[testbench-ai-service.agents.release_notes.prompt]
file = "release_notes/prompt.yaml"   # -> <prompts_dir>/en/release_notes/prompt.yaml and …/de/…
```

Place its prompts in `<prompts_dir>/{en,de}/release_notes/` and its write-back templates in
`<templates_dir>/{en,de}/release_notes/` (or pass absolute template paths). Both directories
default to the installed package's `prompts/`/`templates/`, so set `prompts_dir` and
`templates_dir` in `config.toml` (`testbench-ai-service init --prompts-dir … --templates-dir …`
copies the defaults there). `get_translation` only reads the service's own `locales/*.json`
and returns the bare key for unknown keys; a custom agent brings its own texts per
`context.language`.

**Per project** (keyed by project **name**), switch an agent off or change its prompt:

```toml
[testbench-ai-service.projects."Demo Project".agents.release_notes]
enabled = false

[testbench-ai-service.projects."Demo Project".agents.test_case_set_translator.prompt]
file = "test_case_set_translator/prompt_demo.yaml"
variant = "Quick Translation"
```

What happens at startup: `AppConfig` imports every `class_path` (import error → service does
not start), resolves `prompt.file` under `prompts_dir/<language>/` (missing → does not start),
validates that YAML against `prompt.schema.json` and checks its `agent.*` variables against
`AGENT_DATA_CLASS` (mismatch → does not start). This applies to **disabled agents too**, and only
to the configured language's default prompt: project overrides, the other language and a
request `prompt_config.file` are checked at trigger time (422) or not at all. An agent with
`enabled = false` gets no dedicated `endpoint_path` route, and `/agents/<key>/trigger` answers
`404` (also when disabled only for the project). Verify with `GET /agents` and
`GET /agents/<key>/prompt`.

## Writing back to TestBench

Specification fields (description, review comment): `PATCH 2/projects/{projectKey}/specifications/{specKey}`
via `await utils.testbench.patch_test_structure_element_spec(...)` with a `SpecificationDetailsForUpdate`.
Execution comments and results: zip with `protocol.json` + the changed report files, uploaded and
imported into the cycle (see `references/testbench-json-report.md` and `agents/defect_explainer/utils.py`).

Copy the three-state pattern of `agents/test_case_set_reviewer/utils.py`:

| State                                 | Template           | `locker`                              | Content                                |
| ------------------------------------- | ------------------ | ------------------------------------- | -------------------------------------- |
| started                               | `started.jinja`  | `OptionalUser(optional=user_key)`   | "AI … started" + previous content     |
| result                                | `template.jinja` | `OptionalUser(optional=None)`       | result + disclaimer + previous content |
| failed (in `except`, then re-raise) | `failed.jinja`   | `OptionalUser(optional=None)`       | "AI … failed" + previous content      |

`locker`/`reviewer` are `OptionalUser` wrappers and the PATCH is sent with `exclude_unset`: a bare
`OptionalUser()` serialises to `{}` and does **not** release the lock.

Service-specific rules for the HTML (the general rules, safe CSS vocabulary and verified
patterns are in `testbench-rich-text-html`; follow it, don't invent markup):

- Render `render_template(resolve_template_path("template.jinja", templates_dir=context.templates_dir, language=context.language, agent_key=AGENT_KEY), values)`.
  `language` must be a `LanguageOption` (`context.language` is one); a plain `"en"` raises
  `AttributeError`. The result must be a full `<html><body>…</body></html>`.
- Jinja templates here are **not autoescaped**. LLM output is untrusted text: pass it through
  `utils.html_utils.escape_html()` (escapes and turns `\n` into `<br/>`). Never insert raw LLM
  HTML.
- Need formatting (badges, tables, lists)? Ask the LLM for structured data (JSON or fixed
  lines), parse it, escape each value, and build the markup in the Jinja template, with labels
  from the `en`/`de` template. Don't copy `defect_explainer` here: it predates this rule and
  builds its HTML in Python and has no `templates/` dir.
- Keep previous content: read it first (`get_test_case_set_details(...).spec.description` /
  `.reviewComment`), strip the wrapper with `strip_html_body_tags`, insert it only if
  `has_visible_text`. `strip_html_body_tags` only removes the exact lowercase `<html><body>`
  tags; `<body style=…>`, `<head>` or `<HTML>` stay in. For prompt input use
  `extract_text_from_html_body`.
- `RichTextInfo(html=..., images=[])` - `images` is required.
- Lint every template output in tests:
  `python .claude/skills/testbench-rich-text-html/scripts/check_tb_html.py out.html`.

## Verifying the change

Run the tests closest to your change first: `tests/unit/agents/<key>/`, plus
`tests/unit/test_config.py`, `tests/unit/agents/test_routes.py` (trigger flow 404/403/422/409/202)
and `tests/unit/test_routes.py` (`/agents` GET routes), and the `tests/unit/utils/` tests of any
shared helper you touched. Run `tests/unit` and `tests/integration` as **separate** pytest calls:
`tests/unit/test_tasks.py` leaves patches active that make every integration test error in a
combined run.

The full suite has failures that already exist on `main`. Don't investigate them one by one, and
don't re-run the whole suite repeatedly to prove they are not yours: run it once on your change,
then compare the failing test **IDs** with one run of the unchanged commit, e.g.
`pytest tests/unit -q -p no:cacheprovider | grep -E "^(FAILED|ERROR)" | cut -d' ' -f2 | sort > after.txt`, the same
on a clean checkout into `before.txt`, then `diff before.txt after.txt`. Only new IDs are yours.

## Known bugs in the current code (as of 2026-10; re-check, then drop the line once fixed)

| Bug | Effect / workaround |
|---|---|
| `prompt_utils.template_variables` collects only `agent.*` paths | a variant with any `required: true` var always fails the trigger with `422 Missing required variables`. `required` is essential for the plugin form: fix the extractor, don't drop `required` (`references/prompts-and-plugin.md`) |
| `build_messages` falls back to `msg_template.text` on a render error | for `file:` messages (all built-in prompts) the message silently becomes **empty**; only logged. A missing variable renders as empty without any error |
| `merge_prompt_configs` replaces `vars` as a whole | config/project `vars` presets are lost as soon as the request sends any `vars` |
| `tests/unit/test_tasks.py` leaks patches | run unit and integration tests separately |

## Common mistakes

| Area | Mistake | Fix |
|---|---|---|
| API | URL built as `f"{conn.server_url}/api/2/..."` | `conn.server_url` already ends with `/api/`: `f"{conn.server_url}2/..."` |
| API | Using a UID where the API wants a key | UIDs identify items; URLs need `projectKey`, `specificationKey`, `testCaseSetKey` |
| Permissions | List only covers the write endpoint | add permissions of every helper used (structure, report job, download, details, patch) |
| Permissions | Setting `locker`/`reviewer` with only `ModifySpecifications` | built-in agents also require `ModifySpecManagementInfo` |
| Permissions | Global role in `ALLOWED_ROLES` | only project roles are matched |
| Async | Blocking `conn.session.*` call inside `async def` | `await asyncio.to_thread(...)` |
| Async | `asyncio.to_thread(patch_test_structure_element_spec, ...)` | it is already `async def`: `await` it (sync/async list in `references/testbench-rest-api.md`) |
| Write-back | No failure path, or one that only unlocks | `try/except` around LLM + write: write `failed.jinja` with the previous content, unlock, re-raise |
| Write-back | `locker=OptionalUser()` to release | `OptionalUser(optional=None)` |
| Write-back | Writing to specs locked by another user | skip them in precheck with a warning |
| Write-back | HTML fragment without `<html><body>` | full document; `add_html_body_tags` if needed |
| Registration | New prompt/template not found when running locally | copy the new dirs into the gitignored repo-root `prompts/`/`templates/` the dev `config.toml` points at |
| Registration | Edited `config_example.toml` breaks parsing | multi-line comment without `#` on every line; check with `tomllib` |
| Registration | Only an English prompt/template/locale | every agent needs `en` and `de`: default `language` is `de`, startup only checks the configured language, and `GET /agents?language=<other>` loads every agent's `prompt.yaml`, so one missing file breaks the plugin's whole agent list |
| Prompts | `{{ agent.x }}` not in `AGENT_DATA_CLASS` | declare it: the service won't start (default prompt) or the trigger fails with 422 (other prompts). Nested `{{ agent.x.y }}` also fails validation: pass a flat key |
| Prompts | `llm_config.model` from another provider than the variant's `model` | the client is chosen from the variant's model; keep both in one family |
| Prompts | Relying on `default_value` for prompt `vars` | it only prefills the plugin form; guard with `{% if vars.x %}` |
| Prompts | `{% if vars.flag %}` on a boolean var | values are strings; compare `== "true"` |
| Context | Expecting `project_key`/`cycle_key` from the request body | with a JWT they come from the token `scope`; the body keys are ignored |
| Execution | `protocol.json` with UIDs or keys typed by hand | copy `testCaseSetKey`, `executionKey`, `testCaseExecutionKey` from the report; UIDs only in `uniqueID` |
| Execution | Comment-only import changes the verdict | copy the current `status`/`execStatus`/`verdict` into `result` |
| Execution | Execution-level agent on XML TOV | check `is_json_based_tov` in precheck |
