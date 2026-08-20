# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- New `VERBOSE` log level, below `DEBUG`, which additionally logs request and response payloads —
  both those of the service's own API and those of every call made to the TestBench server. Set it
  per sink via `[testbench-ai-service.logging.console]` or `[testbench-ai-service.logging.file]`,
  or start the service with `--verbose`. `DEBUG` continues to report which requests were made, how
  they were answered and how long they took, without their contents. Payloads are only read and
  buffered when a sink asks for `VERBOSE`, so there is no cost while it is switched off.
- The bodies of requests sent to TestBench, and the bodies of the responses they return, are logged
  at `VERBOSE` level. Values of secret-looking keys (`password`, `token`, `api_key`,
  `authorization` and similar) are replaced with `***`, bodies longer than 2000 characters are
  truncated, and non-text payloads such as execution-result uploads and the JSON-report download
  are logged as a size placeholder only.
- `max_payload_length` under `[testbench-ai-service.logging]` (default `4000`, `0` disables
  truncation) to cap how much of the service's own API payloads is written to the log.

### Fixed

- Secrets in incoming request bodies, such as an `api_key` supplied in `llm_config`, are no longer
  written to the log in plaintext when payload logging is enabled. Response bodies are now redacted
  the same way; previously they were logged verbatim.

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
