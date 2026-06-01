---
sidebar_position: 0
title: LLM Providers
---

# LLM Providers

The TestBench AI Service supports multiple LLM providers out of the box and can be extended with a custom implementation.

---

## Supported providers

| Provider | `provider` value | Guide |
|---|---|---|
| OpenAI | `openai` | [OpenAI Setup](openai-setup.md) |
| Anthropic (Claude) | `anthropic` | [Anthropic Setup](anthropic-setup.md) |
| Azure OpenAI | `azure_openai` | [Azure OpenAI Setup](azure-openai-setup.md) |
| Custom | `custom` | [Custom Client](custom-client.md) |

---

## Choosing a provider

Set the active provider in `config.toml`:

```toml
# config.toml
[testbench-ai-service.llm_config]
provider = "openai"   # openai | anthropic | azure_openai | custom
```

### Automatic model routing

The service automatically routes each request to the correct provider based on the model name in the prompt variant — regardless of the global `provider` setting:

| Model name prefix | Routed to |
|---|---|
| `gpt-*` | OpenAI (or Azure OpenAI when configured) |
| `o*` | OpenAI (or Azure OpenAI when configured) |
| `claude-*` | Anthropic |
| anything else | uses `config.provider` |

This means you can mix models from different providers across prompt variants without changing the global config. Every provider whose models are referenced must have its API key set.

---

## API keys

API keys are read from environment variables. The recommended approach is a `.env` file in the installation directory:

```bash
# .env
OPENAI_API_KEY=sk-...
AZURE_OPENAI_API_KEY=...
ANTHROPIC_API_KEY=sk-ant-...
```

| Provider | Environment variable |
|---|---|
| `openai` | `OPENAI_API_KEY` |
| `azure_openai` | `AZURE_OPENAI_API_KEY` |
| `anthropic` | `ANTHROPIC_API_KEY` |
| `custom` | Not required |

Project-specific keys follow the pattern `{NORMALIZED_PROJECT_NAME}_{PROVIDER}_API_KEY`. See the individual provider guides for details.
