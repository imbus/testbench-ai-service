---
sidebar_position: 1
title: Introduction
---

# Introduction

[**TestBench AI Service**](https://github.com/imbus/testbench-ai-service) is an asynchronous REST API service for [imbus TestBench](https://www.testbench.com) that integrates external AI / LLM providers to support multiple AI-driven Agents during test design and test execution.

## What it does

TestBench manages test cases, test structures, and defect data. The AI Service sits between TestBench and a language model (e.g., OpenAI) and translates domain-specific test artifacts into structured LLM prompts. Results are written back into TestBench automatically.

At its core the service:

- Exposes a REST API that TestBench calls to trigger AI-driven Agents.
- Authenticates every request against the TestBench REST API using JWT tokens.
- Loads configurable prompt templates (YAML) and renders them with project data.
- Sends the rendered prompts to the configured LLM provider and writes the results back to TestBench.

## Features

- **Multiple Agents**: test case set reviews, test case set description generation, and defect explanations, each configurable independently.
- **Custom Agents**: extend the service with your own AI workflows by implementing the `Agent` base class — no service source code changes required.
- **Pluggable LLM providers**: ships with OpenAI, Azure OpenAI, and Anthropic support; bring your own provider by implementing a custom `LLMClient`.
- **Automatic provider routing**: model names starting with `gpt-*` and o-series models (`o1`, `o3`, `o4-mini`, …) are automatically routed to OpenAI, `claude-*` to Anthropic — without changing the global config.
- **Configurable prompts**: YAML-based prompt definitions with variants, Jinja2 variables, and per-project overrides.
- **Per-project configuration**: language, LLM provider, prompt variant, and enabled Agents can all be overridden per TestBench project.
- **JWT authentication**: every API call is validated against the TestBench server using a JWT token; no separate credential management required.
- **SSL/TLS & reverse proxy support**: optional HTTPS with client certificate verification and trusted-proxy configuration.
- **Localization**: built-in English and German translations for AI-generated output.
- **Async processing**: Agents run as background tasks so the API responds immediately.

## Architecture

Built on [FastAPI](https://fastapi.tiangolo.com/) and [Uvicorn](https://uvicorn.dev/), the service exposes a REST API that TestBench calls to trigger Agents. For each request, it validates the JWT token, retrieves relevant data from TestBench, renders a [Jinja2](https://jinja.palletsprojects.com/) prompt template, and forwards it to the configured LLM. The response is written back to TestBench as an async background task.

```
┌──────────────────────────────────────┐
│              TestBench               │
└─────────────────┬──▲─────────────────┘
    Trigger agent │  │ agent results
┌─────────────────▼──┴─────────────────┐
│         TestBench AI Service         │
│               (FastAPI)              │
│  ┌────────────────────────────────┐  │
│  │             Agents             │  │
│  ├────────────────────────────────┤  │
│  │ • Test Case Set Reviewer       │  │
│  │ • Test Case Set Describer      │  │
│  │ • Defect Explainer             │  │
│  └──────────┬──────────▲──────────┘  │
└─────────────┼──────────┼─────────────┘
 LLM requests │          │ LLM responses
┌─────────────▼──────────┴─────────────┐
│             LLM Provider             │
├──────────────────────────────────────┤
│    • OpenAI / Azure OpenAI           │
│    • Anthropic                       │
│    • Custom                          │
└──────────────────────────────────────┘
```

## Built-in Agents

| Agent | Dedicated endpoint | Description |
|----------|----------|-------------|
| [**Test Case Set Reviewer**](agents/test-case-set-reviewer.md) | `POST /test-case-set-reviews` | AI-powered quality reviews of test case sets. |
| [**Test Case Set Describer**](agents/test-case-set-describer.md) | `POST /test-case-set-descriptions` | Automatic generation of descriptive summaries for test case sets. |
| [**Defect Explainer**](agents/defect-explainer.md) | `POST /defect-explanations` | AI-generated explanations for defects found during test execution. |

## Where to go next

- **New here?** Start with the [Installation](getting-started/installation.md) and [Quickstart](getting-started/quickstart.md) guides.
- **Configuring the service?** See the [Configuration](configuration.md) page.
- **Learning about Agents?** Check the [Agents overview](agents/index.md).
- **Building a custom Agent?** See the [Custom Agent](agents/custom-agent.md) guide.
- **Customizing prompts?** See the [Prompts](prompts.md) guide.
- **Connecting TestBench?** See [TestBench Integration](testbench-integration.md).
- **CLI reference?** See the [CLI Commands](cli.md) page.
