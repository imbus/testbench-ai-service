# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.2.0][1.2.0] - 2026-08-20

### Added

- Microsoft Entra ID authentication for Azure OpenAI via a service principal, selected with `auth_method = "entra_id"` in `llm_config`. Credentials are read from `AZURE_TENANT_ID`, `AZURE_CLIENT_ID` and `AZURE_CLIENT_SECRET`, with per-project overrides using the `{PROJECT}_` prefix. A project that sets none of the three variables uses the global service principal; setting only some of them is rejected with `Entra ID authentication ... is incompletely configured`, which names the variables that are missing.
- `azure-identity` and `aiohttp` as runtime dependencies. Both are required for `auth_method = "entra_id"` and are bundled in the released binary; they are imported only when Entra ID authentication is actually configured, so API key installations are unaffected.

### Fixed

- Azure OpenAI client creation no longer overrides the provider resolved from the model name, so a `claude-*` model in a prompt variant correctly creates an Anthropic client even when `provider = "azure_openai"` is configured.

## [1.1.0][1.1.0] - 2026-07-30

### Added

- A minimum TestBench version check in the precheck of every built-in agent. All three agents require TestBench 4.1 or newer; against an older server the agent now stops immediately with `Your current TestBench version ... is not supported`, in German or English, instead of failing later with an unrelated error.
- The Defect Explainer rejects XML-based test object versions in its precheck with `The AI agent does not support XML-based test object versions`. A TOV whose exchange format is inherited is judged by the project default, so only projects that actually store JSON are accepted.

### Changed

- The Defect Explainer reads the comment format written by testbench2robotframework 2.x, which marks the relevant table cells with `data-tb-*` attributes. Comments written by tb2rf 1.1 and older are still recognized, so existing cycles keep working.
- `testbench-cli-reporter` and `testbench2robotframework` are now required as stable releases (3.x and 2.x) rather than the previous pre-release versions.

### Fixed

- Re-running the Defect Explainer on the same test case replaces the previous explanation instead of appending a second copy below it.
- Explanations containing `<` or `&` no longer break the layout of the execution comment they are written into.
- An execution comment that is empty is left untouched instead of being replaced by a lone result heading.
- Failure traces passed to the LLM keep table rows on one line and no longer contain non-breaking spaces, so the model sees the trace as readable plain text.

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
