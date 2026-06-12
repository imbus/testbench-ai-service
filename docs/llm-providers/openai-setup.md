---
sidebar_position: 1
title: OpenAI Setup
---

# OpenAI Setup

This guide walks you through connecting the TestBench AI Service to the OpenAI API.

---

## Requirements

- An [OpenAI account](https://platform.openai.com) with API access
- The TestBench AI Service installed and a `config.toml` present

---

## 1. Create an API key

1. Log in to the [OpenAI Platform](https://platform.openai.com).
2. Navigate to **API keys** in the left sidebar.
3. Click **Create new secret key**, give it a name, and copy the key immediately. It is only shown once.

## 2. Set the API key

The service reads the OpenAI API key from the environment variable `OPENAI_API_KEY`.

Create or update a `.env` file in the root of your installation directory:

```bash
# .env
OPENAI_API_KEY=sk-...your_openai_api_key
```

:::tip
Never commit API keys to version control. Add `.env` to your `.gitignore`.
:::

## 3. Configure `config.toml`

Set the provider in the `[testbench-ai-service.llm_config]` section:

```toml
# config.toml
[testbench-ai-service.llm_config]
provider = "openai"
```

That is the only required setting for OpenAI. No endpoint URL or API version is needed.

## 4. Reference the model in a prompt variant

In your prompt YAML file, set `model` to any supported OpenAI model name:

```yaml
variants:
  - name: "Full Description"
    model: "gpt-5.5"
    messages:
      - role: "system"
        file: "system.jinja"
      - role: "user"
        file: "user.jinja"
```

### Supported chat models

| Model | Notes |
|---|---|
| `gpt-4o` | Flagship multimodal model |
| `gpt-4o-mini` | Fast, cost-efficient |
| `gpt-4o-search-preview` | gpt-4o with integrated web search |
| `gpt-4o-mini-search-preview` | gpt-4o-mini with integrated web search |
| `gpt-4.1` | 1 M context window |
| `gpt-4.1-mini` | 1 M context, cost-efficient |
| `gpt-4.1-nano` | Fastest and cheapest GPT-4.1 variant |
| `gpt-4-turbo` | GPT-4 Turbo (legacy) |
| `gpt-4` | GPT-4 (legacy) |
| `gpt-3.5-turbo` | GPT-3.5 Turbo (legacy) |
| `gpt-3.5-turbo-16k` | GPT-3.5 Turbo with 16k context (legacy) |
| `gpt-3.5-turbo-instruct` | GPT-3.5 Turbo Instruct (legacy) |

### Supported reasoning models

Reasoning models use `reasoning_effort` (`low`, `medium`, `high`) instead of temperature. The default is `medium`.

**GPT-5 family**

| Model | Notes |
|---|---|
| `gpt-5` | GPT-5 |
| `gpt-5-mini` | Compact GPT-5 variant |
| `gpt-5-nano` | Lightweight GPT-5 variant |
| `gpt-5-codex` | Code-focused GPT-5 variant |
| `gpt-5-pro` | High-capability GPT-5 variant |
| `gpt-5.1` | GPT-5.1 |
| `gpt-5.1-codex` | Code-focused GPT-5.1 variant |
| `gpt-5.1-codex-max` | Extended code-focused GPT-5.1 variant |
| `gpt-5.1-codex-mini` | Compact code-focused GPT-5.1 variant |
| `gpt-5.2` | GPT-5.2 |
| `gpt-5.2-codex` | Code-focused GPT-5.2 variant |
| `gpt-5.2-pro` | High-capability GPT-5.2 variant |
| `gpt-5.3-codex` | Code-focused GPT-5.3 variant |
| `gpt-5.4` | GPT-5.4 |
| `gpt-5.4-mini` | Compact GPT-5.4 variant |
| `gpt-5.4-nano` | Lightweight GPT-5.4 variant |
| `gpt-5.4-pro` | High-capability GPT-5.4 variant |
| `gpt-5.5` | GPT-5.5 |
| `gpt-5.5-pro` | High-capability GPT-5.5 variant |

**o-series**

| Model | Notes |
|---|---|
| `o1` | First-generation reasoning model |
| `o1-pro` | High-capability o1 variant |
| `o3` | Powerful reasoning |
| `o3-mini` | Lightweight o3 |
| `o4-mini` | Compact o4 reasoning model |


:::note
Models not in either list are sent as-is with a fallback call and a warning in the logs.
:::

---

## Minimal complete example

**`.env`**

```bash
OPENAI_API_KEY=sk-...your_openai_api_key
```

**`config.toml`**

```toml
# config.toml
[testbench-ai-service]
tb_server_url = "https://localhost:9443/api/"
host = "127.0.0.1"
port = 8010
language = "en"

[testbench-ai-service.llm_config]
provider = "openai"
```

**`prompts/en/test_case_set_describer/prompt.yaml`** (excerpt)

```yaml
variants:
  - name: "Full Description"
    model: "gpt-5.5"
    messages:
      - role: "system"
        file: "system.jinja"
      - role: "user"
        file: "full_description_user.jinja"
```

---

## Project-specific API keys

You can set a separate API key per TestBench project using the pattern `{NORMALIZED_PROJECT_NAME}_OPENAI_API_KEY`. The project name is normalized by uppercasing it and replacing all non-alphanumeric characters with underscores:

```bash
# .env
# For a project named "Car Configurator":
CAR_CONFIGURATOR_OPENAI_API_KEY=sk-project-specific-key
```

If a project-specific key is present the service creates a dedicated client for that project; otherwise the global `OPENAI_API_KEY` is used.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `API key for provider 'openai' not found` | `OPENAI_API_KEY` is not set | Set the variable in your `.env` file or system environment |
| `AuthenticationError` from OpenAI | Invalid or expired API key | Regenerate the key in the OpenAI Platform and update `.env` |
| `Model not found` | Model name is incorrect or not yet available in your tier | Check the [OpenAI model list](https://platform.openai.com/docs/models) and verify your account access |
| Empty response | Model returned no output | Check your prompt template for issues; increase `max_tokens` if needed |
