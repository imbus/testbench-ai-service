# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

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
