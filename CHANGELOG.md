# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- The console can restart the service. When a change needs a restart, an administrator clicks
  **Restart now** in the "restart needed" strip. The restart runs inside the service process
  (graceful shutdown, configuration and agent packages read again, new server), so it works in a
  terminal, from the executable and as a Windows service alike. A new agent package version is
  swapped in, console sessions survive, and a configuration that cannot start falls back to the
  previous one. `POST /admin/api/restart`; documented in `docs/web-console.md`.
- Four opt-in agents, each documented under `docs/agents/`:
  - **Test Idea Generator** (`requirement`): writes test ideas for the requirements below a test
    theme into the theme's description. From TestBench 5.0 it also creates one test case set per
    idea, all or nothing; `create_test_case_sets = false` switches that off, and a token without
    `ModifyTestStructureElements` falls back to the description with a job warning.
  - **Test Planner** (`test_planner`): plans the most diverse test selection of a cycle via
    embeddings and sets the selected test cases to Planned.
  - **Coverage Checker** (`coverage_checker`): checks whether the test case sets linked to a
    requirement prove all its aspects and writes the result into their review comments.
  - **Link Finder** (`link_finder`): suggests unlinked test case sets that test a requirement,
    with a hint in each candidate's review comment. Links are never set.
- Multi-step prompt variants. A variant may carry `steps` -- one message list per named step --
  instead of `messages`, for agents that ask the model several times. `prompt.schema.json`
  accepts them, and the console's prompt editor edits and renders each step's messages; steps
  cannot be added, removed or renamed there. Documented in `docs/prompts.md`.
- A job can be opened in the browser. `POST /jobs/{job_id}/view-ticket` hands the job's owner a
  one-time ticket for `/jobs/{job_id}/view`, a standalone page that shows the job and refreshes
  while it runs; the JWT never reaches the browser. Each job now also keeps the `root_uid` of the
  element it was triggered on. Documented in `docs/agents/index.md`.
- The console's Jobs screen filters by status with chips, shows each job's duration and a status
  pill, names the item by its unique ID, and opens every job on its own page
  (`/admin/jobs/<job id>`) with a real link. Documented in `docs/web-console.md`.
- The service root `/` redirects to the web console, or to the Swagger UI when the console is
  disabled.
- A failed console sign-in names the likely cause (wrong credentials, TestBench unreachable,
  invalid `tb_server_url`, service down) with a hint; the raw message stays under **Details**.
  The console remembers the picked language across reloads.

- A model per agent. `[testbench-ai-service.llm_config.agent_models]` maps agent keys to models
  and takes precedence over `model`; a project's `llm_config.agent_models` overrides it agent by
  agent. The web console's Agents screen picks the global model in the model column, which now
  shows the model the agent actually runs on. A project's model is picked in the agent's expanded
  row and on the agent's detail screen for the selected project. Documented in
  `docs/configuration.md`.

- Agent jobs. Every agent trigger now returns a `job_id` in its `202` response, and
  `GET /jobs/{job_id}` reports the run's status (`running`, `succeeded`, `failed`), progress,
  warnings, error and report, for the user who triggered it only. Other users' and unknown jobs
  answer `404`. The coverage checker stores its full `CoverageResult` as the report and fails the
  job with the reason when it stops early. Jobs are kept in the `usage_file` SQLite file;
  `[testbench-ai-service.jobs] retention_days` (default 90) deletes older ones at startup, where
  jobs still running are marked failed. A new **Jobs** screen in the web console shows your own
  jobs and reports. Documented in `docs/agents/index.md`.

- Token usage per model on the web console's Status screen. Every LLM call -- agent runs and
  prompt test runs alike -- adds its input and output tokens to a running total per provider and
  model, kept in a SQLite file that survives restarts. Only the totals are stored, never the
  individual calls. The file is `usage.sqlite` next to `config.toml` unless `usage_file` says
  otherwise; delete it to start counting from zero. A prompt test run in the editor also shows its
  own token count next to the latency.
- A web console at `/admin`, served by the service itself and bundled in the release
  binary. Sign in with TestBench credentials against the server configured as `tb_server_url`;
  the console then shows service status, a tail of the log file, and the effective Service, LLM
  and Logging configuration.
- `[testbench-ai-service.admin_ui]` with `enabled` (default `true`) and `require_loopback`
  (default `false`). Set `enabled = false` to switch the console off entirely: `/admin` and the
  console API then return `404` and the agent endpoints are unaffected. Documented in
  `docs/web-console.md`.
- Configuration editing in the web console, for administrators. Change Service, LLM provider and
  Logging settings, review the exact unified diff before anything is written, then apply: the
  service rewrites `config.toml` atomically through a comment-preserving TOML document — your
  comments, key order and formatting survive, and only the keys you changed are touched — keeps
  the previous contents as `config.toml.bak`, and reloads in place. A configuration the service
  could not start with is refused before anything is written, with the error marked against the
  offending field. Settings the running process cannot take up (`host`, `port`, the TLS paths,
  `trusted_proxies`, `admin_ui.enabled`, and an agent's `endpoint_path` or `class_path`) are written and then flagged
  in a "restart needed" banner. A new **Raw config.toml** screen shows the file the pending
  changes would produce. Editing requires the global `Administrator` role; every other session
  keeps the read-only console. Documented in `docs/web-console.md`.
- Agent and per-project editing in the web console, for administrators. A new **Agents** screen
  lists every agent with a switch, its endpoint and which projects override it, plus a matrix
  view of agents against projects. Each agent has its own screen with a scope switcher — global,
  or any project that overrides it — for its `enabled` flag, prompt file, prompt variant and
  prompt variables. The variant list and each variable's control (number, checkbox, list of
  allowed values, text area) come from the prompt YAML's own declarations, so a variant name can
  no longer be a silent typo and a variable can no longer be an untyped string. A variable set in
  `config.toml` that the selected variant does not declare is shown and flagged rather than
  hidden. `endpoint_path` and `class_path` are displayed read-only: defining an agent means
  shipping a Python class, and a typo in either stops the service booting.
- A new **Projects** screen, one card per project over the union of the projects TestBench
  reports and the projects `config.toml` mentions — a project in the configuration but not in
  TestBench is flagged. Each card carries the project's `language` override, a three-state
  toggle per agent (inherited · off · on, so an override can always be taken back off) and
  "Remove all overrides". A per-project `llm_config` block is summarised on the card, which
  links to its tab on the LLM screen. The project list is read from TestBench once per session
  and cached, with its age shown and a **Refresh**
  action; if TestBench cannot be reached the console says so and lets the project name be typed
  by hand. Documented in `docs/web-console.md`.
- `[testbench-ai-service.llm_config]` gains `timeout` and `max_retries`. Both were already
  forwarded to the provider SDKs when present in the file; declaring them makes them validated,
  documented, and editable from the console.
- Prompt variables may now hold numbers and booleans, not only strings. `vars` under both
  `[testbench-ai-service.agents.<key>.prompt]` and a project's prompt override accepts
  `str`, `bool`, `int` and `float`, matching the `number` and `boolean` value types that
  `prompt.yaml` has always been able to declare. Writing `max_findings = 10` previously failed
  validation at startup with "Input should be a valid string".
- Prompt editing in the web console, for administrators. A new **Prompts** screen lists every
  `<language>/<agent>/prompt.yaml` the service knows about, including any that fail to parse —
  shown with the error rather than hidden, so a broken prompt is never silently missing from the
  tree, though it must still be repaired on disk before it can be opened. Selecting a prompt that
  parses opens a document editor for its name, default model, default variant, and each variant's
  own model, variable declarations and Jinja messages. A **Lint** button checks every message of
  the selected variant at once and is available to any signed-in session; **Render** evaluates the
  messages against typed variables and the agent's own context and is Administrator-only, since it
  executes the template text — always inside a sandboxed Jinja environment. Renaming or removing a
  variant that an agent or project still points at by name is refused, naming the global agents
  table or the project holding the reference, so it can be repointed in `config.toml` before the
  rename is retried. Saving writes `prompt.yaml` and any template file a message references, each
  with the previous contents kept as `<file>.bak`. Documented in `docs/web-console.md`.
- The prompt editor can now move a message's text between `prompt.yaml` and its own `.jinja`
  file, in both directions. Switching a message to a file proposes a name in the convention the
  shipped prompts already use (`<variant>_<role>.jinja`), deduplicated against the files the
  prompt already references, and the name is editable. Creation is confined to a plain file name
  in the prompt's own directory — no subdirectory, no `../`, no absolute path — while pointing a
  message at an existing template elsewhere under `prompts_dir` is unchanged. A name that already
  exists on disk and that this prompt does not already reference is refused rather than
  overwritten, so a save can never clobber a template belonging to another prompt; the one
  exception is a file whose content is already exactly what the message holds, where pointing at
  it is allowed and nothing is written.
- A template file that no prompt references any more is now deleted when you save, with its
  previous contents kept as `<file>.bak` — the same single undo step `config.toml.bak` is, not a
  history. Deletion requires all three of: the prompt referenced the file on disk before the
  save (re-read by the server, so the browser cannot nominate a file for deletion), the saved
  document no longer references it, and no other `prompt.yaml` anywhere under `prompts_dir`
  references it — so a template shared by two prompts survives. **If any `prompt.yaml` under
  `prompts_dir` fails to parse, the save still writes but deletes nothing at all**, and the
  response names the file that blocked it: a prompt that cannot be parsed cannot be asked which
  templates it uses, and reading it as using none would delete files still in service. Deletion
  happens only as a consequence of saving the prompt that used to reference the file; orphans
  left by a hand edit, or by a save from an earlier release, are not swept up.
- **Save** now asks the server what a save would do before it does it, and the confirm dialog
  shows the files that would be created, updated and deleted as three groups, plus the reason
  when deletions were skipped. The plan is computed by the same code the save runs, against the
  files as they are on disk, so the dialog and the save cannot disagree — and a save the server
  would refuse is now refused inside that dialog, with the reason, instead of after it closes.
- Forking a prompt for one project, from an agent's screen in that project's scope, for
  administrators. **Give this project its own prompt** copies the prompt the project loads into a
  sibling directory `prompts_dir/<language>/<agent>__<project-slug>/` — the `prompt.yaml` plus a
  byte-for-byte copy of every template it references, with the YAML's `file:` references
  rewritten to the copies — then writes
  `projects.<project>.agents.<agent>.prompt.file = "<language>/<agent>__<project-slug>/prompt.yaml"`
  to `config.toml`, keeping the previous contents as `config.toml.bak`, validates the result
  before writing it, and reloads in place; a `prompt.file` change never needs a restart. The fork
  appears in the Prompts tree and is editable immediately. The proposed directory name is shown
  and its last segment is editable; an existing directory is refused by name rather than silently
  given another. A fork that would produce a configuration the service cannot load writes nothing
  outside the new directory, and that directory is removed. It costs: the forked `prompt.yaml` is
  re-serialized because every `file:` reference has to be rewritten, so **comments in it are not
  preserved** (the copied `.jinja` templates are unaffected); the fork is refused while the
  browser holds unapplied configuration changes, since it writes `config.toml` itself; and a fork
  is never undone automatically — clearing the project's prompt file override is an ordinary
  configuration change and leaves the forked files on disk. Documented in
  `docs/web-console.md`.
- The LLM screen now edits a project's `llm_config` as well as the global one,
  with a tab per project. Empty fields inherit from the global configuration.
- The service no longer refuses to start when a provider API key is missing.
  The LLM clients are created on demand, so a missing credential surfaces on
  the first agent request instead of at startup — which means the console can
  be used to fix the provider configuration that is wrong.
- Agent packages. An administrator can upload a Python wheel with custom agents in the web
  console, register its agents (key, endpoint path) and restart the service, without touching
  the server's Python environment. The wheel is checked in a separate process, so no package
  code runs in the service before the restart; a broken or missing package never stops the
  service from starting, its agents just answer `503`. Versions can be updated, activated and
  deleted. Off by default: set `agent_packages.allow_upload = true` (`dir`, `max_upload_mb`,
  not editable in the console) and use custom `prompts_dir`/`templates_dir`. Registered package
  code runs with the service's rights, so enable it only for trusted administrators. Documented
  in `docs/agents/agent-packages.md`, with a runnable example in `examples/agent_package/`.
  - `ExecutionContext.agent_key` carries the key an agent is configured under. Custom agents
    should resolve their write-back templates with `agent_key=context.agent_key`, so they keep
    working when registered under another key.

### Changed

- **Python 3.11 or newer is required.** Python 3.10 is no longer supported.

- **Saving a prompt from the console rewrites the whole `prompt.yaml` and does not preserve
  hand-written comments.** The prompt editor writes YAML with `PyYAML` rather than a
  comment-preserving library — unlike the configuration editor's `config.toml` writer. Key
  order and German text survive, multi-line message text comes back as a literal block scalar,
  and the `# yaml-language-server: $schema=` header is re-emitted, but any comment an operator
  added by hand is gone after the first save from the console. Keep notes for a prompt
  somewhere other than the file itself, or accept that the console will remove them.

- The console's remaining screens now follow the Claude Design artboard the agents and
  projects screens were rebuilt against. The sign-in screen carries the TestBench lockup on
  the artboard's blueprint grid, with language and theme controls that work before sign-in;
  the top bar carries the same lockup, the address the service answers on, and the signed-in
  operator with their role; the nav rail is grouped by rules, badges Projects with the number
  of overrides in force, and names the files the console writes; the Status log reads as the
  artboard's four-column register; and the settings screens take the artboard's header,
  tab strip and measure. The pending-changes strip gains the artboard's **Apply** button,
  which opens the same diff dialog the existing one does -- nothing is written without the
  operator approving the exact text first.

- A partial `[testbench-ai-service.agents.<key>]` block now overrides only the settings it
  names, instead of replacing the whole agent table. Writing just `enabled = false` for a
  built-in agent is now valid and leaves the other agents alone; nested blocks merge too, so
  `[testbench-ai-service.agents.<key>.prompt] variant = "..."` keeps the agent's `prompt.file`.
  An agent key that is not built in must still be declared in full -- there is nothing for it
  to inherit from.

  **This changes behaviour for one undocumented usage.** Previously, declaring a single agent
  in full silently dropped every agent you did not mention, which was the only way to express
  "run just this one". Those configurations now get the other built-in agents back. To turn an
  agent off, set `enabled = false` on it -- a disabled agent registers no endpoint, so the
  effect is the same as its removal. An empty `[testbench-ai-service.agents]` block, or none
  at all, likewise leaves all three built-ins enabled.

  Two consequences for a custom `prompts_dir` that does not hold the built-in prompt files.
  A built-in agent you never configured is now skipped at startup with a warning instead of
  refusing to boot over a prompt file you never wrote; and a **disabled** agent is no longer
  checked at all -- neither its prompt file nor its `class_path` has to resolve. Both keep a
  configuration that started before this release starting after it.

- The coverage checker's precheck no longer loads the JSON report of the whole TOV, so the
  trigger answers quickly. It only checks that the requirement exists in a JSON-based TOV; the
  run searches the linked test case sets. A requirement without a linked test case is no longer
  refused with `409`: the job succeeds with a report whose `no_linked_tests` is `true`, and the
  console's Jobs screen says so. Nothing is written to TestBench in that case.

- The test planner's precheck no longer loads the JSON report of the cycle, so the trigger
  answers quickly. It only checks the TestBench version, the TOV format and the prompt
  parameters; the run collects the test cases. Fewer than two test cases that are not executed
  yet are no longer refused with `409`: the job fails with that reason. The warnings about
  missing requirement links or planned durations are job warnings now instead of being part of
  the `202` response.

- The built-in model lists follow the current OpenAI, Azure OpenAI and Anthropic offerings.
  New: `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-6-astra`, `gpt-6-sol`, `gpt-6-luna`,
  `gpt-6.1-sol`, `gpt-6.1-terra` as reasoning models and `claude-opus-5-5`, `claude-sonnet-5-5`,
  `claude-haiku-5-5`, `claude-fable-5` as adaptive thinking models. Removed, because neither
  OpenAI nor Azure serves them any more: `gpt-3.5-turbo*`, `gpt-4`, `gpt-4-turbo*`, the
  `gpt-4o*-search-preview` models and the o-series (`o1*`, `o3*`, `o4-mini*`); also
  `claude-opus-4-1*`. These names now take the fallback request unless `model_routing` maps them.

- In the console's agent and LLM screens, a project without an override is reached through a
  **+** tab after the last scope tab instead of the "Add a project override" select. It opens a
  searchable project list; picking a project still only opens it, nothing is written until a
  field is changed and applied.

- The agent model in the console's Agents list and agent screen is shown as a value instead of
  a select: an inherited model is dashed and names its source (global entry, project or LLM
  default, prompt), an own value is bold. Clicking it opens a searchable list per provider that
  marks providers without an API key and offers **Inherit** first.

### Fixed

- Write-back templates and prompt message templates are now rendered in a sandboxed Jinja
  environment at run time, as the console's preview already was. Before, an edited template
  could reach Python internals and run code in the service process.
- A `port` of 0, a negative one or one above 65535 is now rejected when the configuration is
  validated -- also in the console's preview -- instead of failing when the server binds.

- A run whose `llm_config.model` names a model of another provider than the prompt's model now
  reaches that provider's client. The client was chosen by the prompt's model.

- A project that overrides both `language` and its agent's `prompt.file` now starts. At boot,
  `validate_prompt_paths` checked such a file against the **global** language while
  `get_prompt_config` resolves it against the **project's** language at request time, so where
  the two differed the service refused to start over a file that is, by its own runtime rules,
  the wrong one. The boot check now uses the project's own language when it declares one. This
  affects hand-written configurations independently of the console.
- `GET /admin/api/config` previously did not redact credential keys written with hyphens or
  dots (`api-key`, `x-api-key`, `api.key`), so such a value could be shown in plaintext by
  the console's configuration screen. Now all credential-named keys, regardless of separator
  style, are redacted uniformly.

## [1.3.0][1.3.0] - 2026-10-27

Release for **TestBench 4.2**. The minimum TestBench version for the built-in agents stays at
4.1.

### Changed

- Dependency raised to `testbench2robotframework>=2.1.0,<3.0.0`, the release that ships with
  TestBench 4.2.
- Documentation states that the service is tested against TestBench 4.2, describes the
  responsible-person precheck and the lock handling of the Test Case Set Reviewer and Describer,
  and lists the JSON-TOV check and the accepted `Fail` verdict of the Defect Explainer.

## [1.2.2][1.2.2] - 2026-10-09

### Added

- The Test Case Set Reviewer and Describer skip a test case set when another user is entered as
  responsible for its specification, with a localized precheck warning naming that user.

### Fixed

- A specification that was already locked before the run stays locked after the Test Case Set
  Reviewer or Describer finishes instead of being unlocked.

## [1.2.1][1.2.1] - 2026-08-25

### Added

- `tb_connect_timeout`, `tb_read_timeout` and `tb_max_retries` in `app_config` to tune outbound
  TestBench requests. They default to 10 s, 120 s and 3 retries; documented in
  `docs/configuration.md`.

### Fixed

- Outbound TestBench requests are now bounded and retried. The adapter that
  `testbench-cli-reporter` mounts has no timeout of its own and overwrites any per-request
  timeout, so a stalled request blocked the connection heartbeat — observed at 600 s — and a
  keep-alive connection dropped by the peer aborted the whole agent run with a
  `ConnectionError`. The service now mounts an adapter that applies a default
  `(connect, read)` timeout only when the caller supplied none and retries connection and read
  failures. Retries are limited to idempotent methods, so a `PATCH` on a specification is never
  replayed and a review comment cannot be appended twice.
- Token validation during authentication is bounded as well, so an unreachable or stalled
  TestBench server fails the request instead of hanging it.
- A TestBench server that accepts the connection and then stalls now returns `502 Bad Gateway`
  instead of `500 Internal Server Error`. With the request timeouts in place such a server
  raises `requests.exceptions.Timeout`, which is not a `ConnectionError` and therefore escaped
  the handlers that translate unreachable-server failures into a `502`.
- Test case sets are no longer skipped when the project uses a unique-ID prefix other than
  `iTB`. Node filtering now matches the `-TC-<number>` suffix instead of the full
  `iTB-TC-<number>` pattern.

## [1.2.0][1.2.0] - 2026-08-20

### Added

- Microsoft Entra ID authentication for Azure OpenAI via a service principal, selected with `auth_method = "entra_id"` in `llm_config`. Credentials are read from `AZURE_TENANT_ID`, `AZURE_CLIENT_ID` and `AZURE_CLIENT_SECRET`, with per-project overrides using the `{PROJECT}_` prefix. A project that sets none of the three variables uses the global service principal; setting only some of them is rejected with `Entra ID authentication ... is incompletely configured`, which names the variables that are missing.
- `azure-identity` and `aiohttp` as runtime dependencies. Both are required for `auth_method = "entra_id"` and are bundled in the released binary; they are imported only when Entra ID authentication is actually configured, so API key installations are unaffected.

### Fixed

- Azure OpenAI client creation no longer overrides the provider resolved from the model name, so a `claude-*` model in a prompt variant correctly creates an Anthropic client even when `provider = "azure_openai"` is configured.

## [1.1.0][1.1.0] - 2026-07-30

### Added

- Minimum TestBench version check: all built-in agents now verify the connected server during
  precheck and fail with `409 Conflict` and a localized message if it is older than
  **TestBench 4.1**.
- `check_min_testbench_version(context, conn)` helper, available to custom agents. Custom agents
  that support older servers can skip it or check `conn.server_version` themselves.
- The Defect Explainer now rejects **XML-based test object versions**. Only JSON-based TOVs are
  supported — either set directly on the TOV or inherited from the project's default exchange
  format.
- TestBench API support for reading project and TOV metadata: `get_project_details()`,
  `get_tov_details()` and `is_json_based_tov()`, backed by the new `ProjectDetails`, `TOVDetails`
  and `ProjectContext` models and the `ProjectStatus`, `ProjectExchangeFormat` and
  `TOVExchangeFormat` enums.
- English and German messages for both new precheck failures.
- Dependabot configuration to keep GitHub Actions up to date.

### Changed

- The Defect Explainer reads failure messages and inserts explanations using the `data-tb-*`
  anchors of the current **testbench2robotframework 2.x** comment format. Comments written by
  tb2rf 1.1 and older are still handled by a legacy fallback.
- Re-running the Defect Explainer on the same test case now replaces the previous explanation
  instead of appending another one — including when only its heading remained in the stored
  comment.
- LLM output is HTML-escaped before it is written into an execution comment, so explanations
  containing `<` or `&` no longer corrupt the comment markup.
- Dependencies now require final releases instead of pre-releases:
  `testbench-cli-reporter>=3.0.0,<4.0.0` and `testbench2robotframework>=2.0.0,<3.0.0`.
- Documentation states the TestBench version requirements per agent and the TOV format
  restriction of the Defect Explainer.

### Fixed

- An empty execution comment is no longer replaced by a bare AI disclaimer heading.
- Execution traces passed to the LLM keep table cells on one line and no longer contain
  non-breaking spaces from tb2rf's comment indentation.
- Test cases without an explanation are skipped instead of producing an empty annotation.

## [1.0.1][1.0.1] - 2026-06-29

### Fixed

- Use the current version of a test case set instead of the checked-in version.
- Do not automatically switch to a checked-in version just because one exists.

## [1.0.0][1.0.0] - 2026-06-12

### Added

- Initial public release as open source project
- Three AI agents: test case set reviewer, test case set describer, and defect explainer
- Pluggable LLM provider architecture with built-in support for OpenAI, Azure OpenAI, and Anthropic
- YAML-based prompt templates with Jinja2 support for full customization
- Per-project overrides for language and LLM configuration
- German and English locale support
- REST API with built-in Swagger UI at `/docs`
- SSL/TLS support with optional mutual TLS (mTLS)
- Trusted reverse proxy configuration
- CLI commands: `init` (scaffold config) and `start` (run the service)

[1.0.0]: https://github.com/imbus/testbench-ai-service/releases/tag/v1.0.0
[1.0.1]: https://github.com/imbus/testbench-ai-service/releases/tag/v1.0.1
[1.1.0]: https://github.com/imbus/testbench-ai-service/releases/tag/v1.1.0
[1.2.0]: https://github.com/imbus/testbench-ai-service/releases/tag/v1.2.0
[1.2.1]: https://github.com/imbus/testbench-ai-service/releases/tag/v1.2.1
[1.2.2]: https://github.com/imbus/testbench-ai-service/releases/tag/v1.2.2
[1.3.0]: https://github.com/imbus/testbench-ai-service/releases/tag/v1.3.0
