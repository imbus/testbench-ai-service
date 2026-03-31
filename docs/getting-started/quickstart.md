---
sidebar_position: 2
title: Quickstart
---

# Quickstart

## 1. Set the OpenAI API Key

Since OpenAI is the default language model provider, you need to set your API key. Create a `.env` file at the root of your project:

```bash
OPENAI_API_KEY=your_openai_api_key
```

The server automatically loads environment variables from this file.

## 2. Create a Configuration

```bash
testbench-ai-service init
```

This creates a default `config.toml` and copies the built-in prompt YAML files to a `./prompts` directory. For most setups, the only setting you need to verify is `tb_server_url`:

```toml
[testbench-ai-service]
tb_server_url = "https://localhost:9443/api/"
```

Make sure `tb_server_url` points to your TestBench REST API Server.

:::tip
To copy prompts to a different location, use:
```bash
testbench-ai-service init --prompts-dir ./path/to/prompts
```
:::

## 3. Start the Service

```bash
testbench-ai-service start
```

## 4. Open Swagger UI

Visit [http://127.0.0.1:8010/docs](http://127.0.0.1:8010/docs) to explore the API interactively.

**That's it!** Your service is ready to accept requests from TestBench.

---

## API Documentation Endpoints

Once the service is running, these endpoints are available without authentication:

| Endpoint | Description |
|----------|-------------|
| `/docs` | Interactive Swagger UI |
| `/redoc` | ReDoc API documentation |
| `/openapi.json` | OpenAPI specification (JSON) |

## Next Steps

- Customize the service → [Configuration](../configuration.md)
- Learn about use cases → [Use Cases overview](../use-cases/index.md)
- Customize prompts → [Prompts](../prompts.md)
- Connect TestBench → [TestBench Integration](../testbench-integration.md)
- Explore all CLI options → [CLI Commands](../cli.md)
