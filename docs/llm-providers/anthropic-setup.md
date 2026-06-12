---
sidebar_position: 2
title: Anthropic Setup
---

# Anthropic Setup

This guide walks you through connecting the TestBench AI Service to the Anthropic API (Claude models).

---

## Requirements

- An [Anthropic account](https://console.anthropic.com) with API access
- The TestBench AI Service installed and a `config.toml` present

---

## 1. Create an API key

1. Log in to the [Anthropic Console](https://console.anthropic.com).
2. Navigate to **API Keys** in the left sidebar.
3. Click **Create Key**, give it a name, and copy the key immediately. It is only shown once.

## 2. Set the API key

The service reads the Anthropic API key from the environment variable `ANTHROPIC_API_KEY`.

Create or update a `.env` file in the root of your installation directory:

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-...your_anthropic_api_key
```

:::tip
Never commit API keys to version control. Add `.env` to your `.gitignore`.
:::

## 3. Configure `config.toml`

Set the provider in the `[testbench-ai-service.llm_config]` section:

```toml
# config.toml
[testbench-ai-service.llm_config]
provider = "anthropic"
```

That is the only required setting for Anthropic. No endpoint URL or API version is needed.

## 4. Reference the model in a prompt variant

In your prompt YAML file, set `model` to any supported Claude model name:

```yaml
variants:
  - name: "Full Description"
    model: "claude-sonnet-4-6"
    messages:
      - role: "system"
        file: "system.jinja"
      - role: "user"
        file: "user.jinja"
```

### Supported chat models

Standard chat models use `temperature = 0` for deterministic outputs.

| Model | Notes |
|---|---|
| `claude-3-5-sonnet-20241022` | High-capability Claude 3.5 Sonnet |
| `claude-3-5-haiku-20241022` | Fast, lightweight Claude 3.5 |
| `claude-3-opus-20240229` | Most powerful Claude 3 model |
| `claude-3-sonnet-20240229` | Claude 3 Sonnet |
| `claude-3-haiku-20240307` | Compact Claude 3 model |

### Extended thinking models (budget)

These models support extended thinking with a configurable token budget. The `reasoning_effort` setting (`low`, `medium`, `high`) maps to a thinking token budget (2048 / 4096 / 8192 tokens).

| Model | Notes |
|---|---|
| `claude-haiku-4-5` | Claude Haiku 4.5 |
| `claude-haiku-4-5-20251001` | Claude Haiku 4.5 (dated version) |
| `claude-sonnet-4-5` | Claude Sonnet 4.5 |
| `claude-sonnet-4-5-20250929` | Claude Sonnet 4.5 (dated version) |
| `claude-opus-4-1` | Claude Opus 4.1 |
| `claude-opus-4-1-20250805` | Claude Opus 4.1 (dated version) |
| `claude-opus-4-5` | Claude Opus 4.5 |
| `claude-opus-4-5-20251101` | Claude Opus 4.5 (dated version) |

### Adaptive thinking models

These models use a streaming-based thinking approach with adaptive budgets. `reasoning_effort` defaults to `high`. Valid values are `low`, `medium`, `high`, `xhigh`, and `max`.

| Model | Notes |
|---|---|
| `claude-sonnet-4-6` | Claude Sonnet 4.6 |
| `claude-opus-4-6` | Claude Opus 4.6 |
| `claude-opus-4-7` | Claude Opus 4.7 |
| `claude-opus-4-8` | Claude Opus 4.8 |


:::note
Models not in either list are sent as-is with a fallback call and a warning in the logs.
:::

---

## Automatic provider routing

Even when `provider = "openai"` (or another provider) is set globally, any prompt variant whose `model` name starts with `claude-` is **automatically routed** to the Anthropic client. This means you can mix Claude and GPT models across different prompt variants without changing the global provider config.

The `ANTHROPIC_API_KEY` environment variable must be set whenever any Claude model is referenced.

---

## Minimal complete example

**`.env`**

```bash
ANTHROPIC_API_KEY=sk-ant-...your_anthropic_api_key
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
provider = "anthropic"
```

**`prompts/en/test_case_set_describer/prompt.yaml`** (excerpt)

```yaml
variants:
  - name: "Full Description"
    model: "claude-sonnet-4-6"
    messages:
      - role: "system"
        file: "system.jinja"
      - role: "user"
        file: "user.jinja"
```

---

## Project-specific API keys

You can set a separate API key per TestBench project using the pattern `{NORMALIZED_PROJECT_NAME}_ANTHROPIC_API_KEY`. The project name is normalized by uppercasing it and replacing all non-alphanumeric characters with underscores:

```bash
# .env
# For a project named "Car Configurator":
CAR_CONFIGURATOR_ANTHROPIC_API_KEY=sk-ant-project-specific-key
```

If a project-specific key is present the service creates a dedicated client for that project; otherwise the global `ANTHROPIC_API_KEY` is used.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `API key for provider 'anthropic' not found` | `ANTHROPIC_API_KEY` is not set | Set the variable in your `.env` file or system environment |
| `AuthenticationError` from Anthropic | Invalid or expired API key | Regenerate the key in the Anthropic Console and update `.env` |
| `Model not found` | Model name is incorrect or not available in your tier | Check the [Anthropic model list](https://docs.anthropic.com/en/docs/about-claude/models/all-models) and verify your account access |
| Empty response | Model returned no output | Check your prompt template for issues |
