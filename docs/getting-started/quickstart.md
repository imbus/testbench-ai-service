---
sidebar_position: 2
title: Quickstart
---

# Quickstart

## 1. Set your LLM API key

OpenAI is the default provider. Create a `.env` file at the root of your installation directory and set the key for the provider you want to use:

```bash
# OpenAI (default)
OPENAI_API_KEY=your_openai_api_key

# Azure OpenAI
# AZURE_OPENAI_API_KEY=your_azure_openai_api_key

# Anthropic
# ANTHROPIC_API_KEY=your_anthropic_api_key
```

The server automatically loads environment variables from this file.

## 2. Create a configuration

```bash
testbench-ai-service init
```

This creates a default `config.toml` and copies the built-in prompt YAML files to a `./prompts` directory. For most setups, the only setting you need to verify is `tb_server_url`:

```toml
# config.toml
[testbench-ai-service]
tb_server_url = "https://localhost:9443/api/"
```

Make sure `tb_server_url` points to your TestBench REST API Server.

If you want to use Azure OpenAI, configure the provider in `config.toml`:

```toml
# config.toml
[testbench-ai-service.llm_config]
provider = "azure_openai"
azure_endpoint = "https://your-resource.openai.azure.com"
api_version = "2025-04-01-preview"
```

:::tip
To copy prompts to a different location, use:
```bash
testbench-ai-service init --prompts-dir ./path/to/prompts
```
:::

## 3. Start the service

```bash
testbench-ai-service start
```

## 4. Open Swagger UI

Visit [http://127.0.0.1:8010/docs](http://127.0.0.1:8010/docs) to explore the API interactively.

**That's it!** Your service is ready to accept requests from TestBench.

---

## API documentation endpoints

Once the service is running, these endpoints are available without authentication:

| Endpoint | Description |
|----------|-------------|
| `/docs` | Interactive Swagger UI. |
| `/redoc` | ReDoc API documentation. |
| `/openapi.json` | OpenAPI specification (JSON). |

## Next steps

- Customize the service → [Configuration](../configuration.md)
- Learn about Agents → [Agents overview](../agents/index.md)
- Customize prompts → [Prompts](../prompts.md)
- Connect TestBench → [TestBench Integration](../testbench-integration.md)
- Explore all CLI options → [CLI Commands](../cli.md)
