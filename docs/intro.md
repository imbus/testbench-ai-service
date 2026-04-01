---
sidebar_position: 1
title: Introduction
---

# Introduction

[**TestBench AI Service**](https://github.com/imbus/testbench-ai-service) is a proxy server for [imbus TestBench](https://www.imbus.de/en/testbench) that integrates external AI / LLM providers to support multiple AI-driven use cases during test design and test execution.

## What It Does

TestBench manages test cases, test structures, and defect data. The AI Service sits between TestBench and a language model (e.g., OpenAI) and translates domain-specific test artifacts into structured LLM prompts. Results are written back into TestBench automatically.

At its core the service:

- Exposes a stable HTTP API that TestBench calls to trigger AI-driven use cases.
- Authenticates every request against the TestBench REST API using session tokens.
- Loads configurable prompt templates (YAML) and renders them with project data.
- Sends the rendered prompts to the configured LLM provider and writes the results back to TestBench.

## Key Features

- **Multiple use cases** — test case set reviews, test case set description generation, and defect explanations, each configurable independently.
- **Pluggable LLM providers** — ships with OpenAI support; bring your own provider by implementing a custom `LLMClient`.
- **Configurable prompts** — YAML-based prompt definitions with variants, Jinja2 placeholders, and per-project overrides.
- **Per-project configuration** — language, LLM provider, prompt variant, and enabled use cases can all be overridden per TestBench project.
- **Session-token authentication** — every API call is validated against the TestBench server; no separate credential management required.
- **SSL/TLS & reverse proxy support** — optional HTTPS with client certificate verification and trusted-proxy configuration.
- **Localization** — built-in English and German translations for AI-generated output.
- **Async processing** — use cases run as background tasks so the API responds immediately.

## Architecture

```
┌──────────────────────────────────────┐
│             TestBench                │
└───────────────────┬──────────────────┘
                    │  HTTP (Session Token)
┌───────────────────▼──────────────────┐
│       TestBench AI Service           │
│              (FastAPI)               │
│  ┌──────────────────────────────┐    │
│  │          Use Cases           │    │
│  ├──────────┬─────────┬─────────┤    │
│  │Test Case │Test Case│ Defect  │    │
│  │  Set     │  Set    │Expla-   │    │
│  │ Reviews  │ Descr.  │nations  │    │
│  └──────────┴────┬────┴─────────┘    │
└──────────────────┼───────────────────┘
                   │  LLM requests only
┌──────────────────▼───────────────────┐
│            LLM Provider              │
├───────────────────┬──────────────────┤
│      OpenAI       │     Custom       │
└──────────┬────────┴────────┬─────────┘
           │                 │
     OpenAI API        Your LLM API
```

The service is built on [FastAPI](https://fastapi.tiangolo.com/) and [Uvicorn](https://www.uvicorn.org/), providing high-performance async request handling.

## Built-in Use Cases

| Use Case | Endpoint | Description |
|----------|----------|-------------|
| [**Test Case Set Reviews**](use-cases/test-case-set-reviews.md) | `/test-case-set-reviews` | AI-powered quality reviews of test case sets. |
| [**Test Case Set Descriptions**](use-cases/test-case-set-descriptions.md) | `/test-case-set-descriptions` | Automatic generation of descriptive summaries for test case sets. |
| [**Defect Explanations**](use-cases/defect-explanations.md) | `/defect-explanations` | AI-generated explanations for defects found during test execution. |

## Where to Go Next

- **New here?** Start with the [Installation](getting-started/installation.md) and [Quickstart](getting-started/quickstart.md) guides.
- **Configuring the service?** See the [Configuration](configuration.md) page.
- **Learning about use cases?** Check the [Use Cases overview](use-cases/index.md).
- **Customizing prompts?** See the [Prompts](prompts.md) guide.
- **Connecting TestBench?** See [TestBench Integration](testbench-integration.md).
- **CLI reference?** See the [CLI Commands](cli.md) page.
