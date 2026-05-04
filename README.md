# TestBench AI Service

[![PyPI version](https://img.shields.io/pypi/v/testbench-ai-service.svg)](https://pypi.org/project/testbench-ai-service/)
[![Python versions](https://img.shields.io/pypi/pyversions/testbench-ai-service.svg)](https://pypi.org/project/testbench-ai-service/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://github.com/imbus/testbench-ai-service/blob/main/LICENSE)

A proxy service that integrates external LLM providers with [imbus TestBench](https://www.testbench.com) to automate AI-driven Agents during test design and execution.

## Features

- **Multiple Agents:** test case set reviews, description generation, and defect explanations
- **Pluggable LLM providers:** ships with OpenAI and Azure OpenAI support; implement a custom `LLMClient` to bring your own
- **Configurable prompts:** YAML-based templates with Jinja2 placeholders and per-project overrides
- **Session-token auth:** every request is validated against the TestBench REST API; no separate credential management
- **Async processing:** Agents run as background tasks so the API responds immediately
- **Swagger UI:** interactive API docs at `/docs`
- **SSL/TLS & reverse proxy support:** optional HTTPS with mTLS and trusted-proxy headers

## Installation

**With pip** (Python 3.10–3.14 required):

```bash
pip install testbench-ai-service
```

**Standalone executable** (no Python required): download the pre-built binary from the [GitHub releases page](https://github.com/imbus/testbench-ai-service/releases).

## Quick Start

**1. Set your LLM API key**

```bash
# .env
# For OpenAI
OPENAI_API_KEY=your_openai_api_key

# For Azure OpenAI
AZURE_OPENAI_API_KEY=your_azure_openai_api_key
```

**2. Initialize configuration**

```bash
testbench-ai-service init
```

Open `config.toml` and point `tb_server_url` at your TestBench REST API:

```toml
[testbench-ai-service]
tb_server_url = "https://localhost:9443/api/"

[testbench-ai-service.llm_config]
# openai (default) or azure_openai
provider = "openai"
```

**3. Start the service**

```bash
testbench-ai-service start
```

The service runs at `http://127.0.0.1:8010` by default. Open `/docs` for the interactive Swagger UI.

## Documentation

Full documentation is available in the [docs/](https://github.com/imbus/testbench-ai-service/tree/main/docs) folder of the repository:

- [Introduction](https://github.com/imbus/testbench-ai-service/blob/main/docs/intro.md)
- [Installation](https://github.com/imbus/testbench-ai-service/blob/main/docs/getting-started/installation.md)
- [Quickstart](https://github.com/imbus/testbench-ai-service/blob/main/docs/getting-started/quickstart.md)
- [Configuration](https://github.com/imbus/testbench-ai-service/blob/main/docs/configuration.md)
- [Agents](https://github.com/imbus/testbench-ai-service/blob/main/docs/agents/index.md)
- [Prompts](https://github.com/imbus/testbench-ai-service/blob/main/docs/prompts.md)
- [TestBench Integration](https://github.com/imbus/testbench-ai-service/blob/main/docs/testbench-integration.md)
- [CLI Reference](https://github.com/imbus/testbench-ai-service/blob/main/docs/cli.md)

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](https://github.com/imbus/testbench-ai-service/blob/main/CONTRIBUTING.md) for setup instructions and guidelines.

## Changelog

See [CHANGELOG.md](https://github.com/imbus/testbench-ai-service/blob/main/CHANGELOG.md) for release history.

## License

Apache 2.0. See [LICENSE](https://github.com/imbus/testbench-ai-service/blob/main/LICENSE) for details.