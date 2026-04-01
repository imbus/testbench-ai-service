# TestBench AI Service

A service supporting multiple AI-driven use cases for [imbus TestBench](https://www.imbus.de/en/testbench).

## Features

- **Multiple use cases** — test case set reviews, description generation, and defect explanations
- **Pluggable LLM providers** — ships with OpenAI support; bring your own provider
- **Configurable prompts** — YAML-based prompt templates with variants and Jinja2 placeholders
- **Per-project configuration** — language, LLM provider, and prompt settings can be overridden per project
- **Swagger UI** — built-in interactive API documentation at `/docs`
- **SSL/TLS & reverse proxy support** — optional HTTPS with mTLS and trusted-proxy configuration

## Requirements

- Python 3.10+

## Quick Start

```bash
pip install testbench-ai-service
```

Create a `.env` file with your OpenAI API key:

```bash
OPENAI_API_KEY=your_openai_api_key
```

Initialize configuration and start the service:

```bash
testbench-ai-service init
testbench-ai-service start
```

The service runs at `http://127.0.0.1:8010` by default. Open `/docs` for the interactive Swagger UI.

## Documentation

Full documentation is available in the [`docs/`](docs/) folder:

- [Introduction](docs/intro.md)
- [Installation](docs/getting-started/installation.md)
- [Quickstart](docs/getting-started/quickstart.md)
- [Configuration](docs/configuration.md)
- [Use Cases](docs/use-cases/index.md)
- [Prompts](docs/prompts.md)
- [TestBench Integration](docs/testbench-integration.md)
- [CLI Commands](docs/cli.md)

## Development

```bash
git clone https://github.com/imbus/testbench-ai-service.git
cd testbench-ai-service
python -m venv .venv && .venv\Scripts\activate
pip install -e .[dev]
```

### Testing

```bash
# Unit tests
python -m unittest discover -v tests\unit\

# Integration tests (requires a running TestBench server)
python -m unittest discover -v tests\integration\

# Prompt engineering tests
python -m unittest discover -v tests\prompt_engineering\<use_case>
```

## License

This project is licensed under the Apache 2.0 License. See the [LICENSE](LICENSE) file for details.