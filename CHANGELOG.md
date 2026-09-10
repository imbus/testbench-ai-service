# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- A web console at `/admin`, served by the service itself and bundled in the release
  binary. Sign in with TestBench credentials against the server configured as `tb_server_url`;
  the console then shows service status, a tail of the log file, and the effective Service, LLM
  and Logging configuration. Prompt files themselves are still read-only from the browser.
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
  "Remove all overrides". A per-project `llm_config` block is shown read-only. The project list
  is read from TestBench once per session and cached, with its age shown and a **Refresh**
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

### Changed

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

### Fixed

- `GET /admin/api/config` previously did not redact credential keys written with hyphens or
  dots (`api-key`, `x-api-key`, `api.key`), so such a value could be shown in plaintext by
  the console's configuration screen. Now all credential-named keys, regardless of separator
  style, are redacted uniformly.

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
