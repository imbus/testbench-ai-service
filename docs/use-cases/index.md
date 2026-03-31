---
sidebar_position: 1
title: Use Cases
---

# Use Cases

A **use case** is a self-contained AI-driven workflow that the service exposes as an HTTP endpoint. Each use case follows the same lifecycle:

1. **Trigger** — TestBench sends a POST request with project, test-object-version, and (optionally) cycle information.
2. **Precheck** — The service validates prerequisites (e.g., that test structure elements are not locked by another user) and collects the items to process.
3. **Background execution** — The API responds with `202 Accepted` immediately. In the background, prompt templates are rendered with test data, sent to the configured LLM, and the results are written back to TestBench.

---

## Built-in Use Cases

| Use Case | Endpoint | Description |
|----------|----------|-------------|
| [**Test Case Set Reviews**](test-case-set-reviews.md) | `/test-case-set-reviews` | AI-powered quality reviews. Results are added to the review comment section of each test structure element specification. |
| [**Test Case Set Descriptions**](test-case-set-descriptions.md) | `/test-case-set-descriptions` | Automatic generation of descriptive summaries. Results are assigned to the description field of each test structure element specification. |
| [**Defect Explanations**](defect-explanations.md) | `/defect-explanations` | AI-generated explanations for defects found during test execution. Results are added to the comment section of the execution overview. |

---

## Common Request Format

All use case endpoints accept the same request body:

```json
{
  "project_key": "PRJ-123",
  "tov_key": "TOV-456",
  "cycle_key": "CYC-789",
  "root_uid": "UID-000",
  "language": "en",
  "prompt_config": {
    "file": "custom_prompt.yaml",
    "name": "PromptName",
    "variant": "variant-name",
    "placeholder_data": {
      "glossary": "path/to/glossary.txt"
    }
  },
  "llm_config": {
    "provider": "openai",
    "model": "gpt-4.1"
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `project_key` | String | Yes | TestBench project key |
| `tov_key` | String | Yes | Test-object-version key |
| `cycle_key` | String | No | Test cycle key (required for defect explanations) |
| `root_uid` | String | No | Root UID to limit scope to a subtree |
| `language` | String | No | Override language (`"en"` or `"de"`) |
| `prompt_config` | Object | No | Override prompt configuration for this request |
| `llm_config` | Object | No | Override LLM configuration for this request |

### Response

On success, `202 Accepted`:

```json
{
  "status": "accepted",
  "warnings": ["Optional list of per-item warnings from the precheck"]
}
```

### Error Responses

| Status | Meaning |
|--------|---------|
| `401` | Missing or invalid session token |
| `403` | Insufficient permissions (requires Administrator, TestManager, or TestDesigner role) |
| `404` | Project not found, or use case is disabled for the project |
| `409` | Precheck failed — no items passed validation |

---

## Authorization

All use case endpoints require a valid **TestBench session token** passed as the `Authorization` header. The token is validated by calling the TestBench REST API. The user must have at least one of the following roles:

- Administrator
- TestManager
- TestDesigner

---

## Configuring Use Cases

Each use case can be enabled/disabled, assigned a different prompt, or overridden per project in `config.toml`. See the [Configuration](../configuration.md#use-case-settings) page for details.
