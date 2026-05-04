---
sidebar_position: 1
title: Agents
---

# Agents

A **agent** is a self-contained AI-driven workflow that the service exposes as an HTTP endpoint. Each agent follows the same lifecycle:

1. **Trigger**: TestBench sends a POST request with project, test-object-version, and (optionally) cycle information.
2. **Precheck**: The service validates prerequisites (e.g., that test structure elements are not locked by another user) and collects the items to process.
3. **Background execution**: The API responds with `202 Accepted` immediately. In the background, prompt templates are rendered with test data, sent to the configured LLM, and the results are written back to TestBench.

---

## Built-in Agents

| agent | Endpoint | Description |
|----------|----------|-------------|
| [**Test Case Set Reviewer**](test-case-set-reviewer.md) | `/test-case-set-reviews` | AI-powered quality reviews. Results are added to the review comment section of each test structure element specification. |
| [**Test Case Set Describer**](test-case-set-describer.md) | `/test-case-set-descriptions` | Automatic generation of descriptive summaries. Results are assigned to the description field of each test structure element specification. |
| [**Defect Explainer**](defect-explainer.md) | `/defect-explanations` | AI-generated explanations for defects found during test execution. Results are added to the comment section of the execution overview. |

---

## Common request format

All agent endpoints accept the same request body:

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

| Field | Type | Description | Required |
|-------|------|----------|-------------|
| `project_key` | String | TestBench project key. | Yes |
| `tov_key` | String | Test-object-version key. | Yes |
| `cycle_key` | String | Test cycle key (required for defect explanations). | No |
| `root_uid` | String | Root UID to limit scope to a subtree. | No |
| `language` | String | Override language (`"en"` or `"de"`). | No |
| `prompt_config` | Object | Override prompt configuration for this request. | No |
| `llm_config` | Object | Override LLM configuration for this request. | No |

### Response

On success, `202 Accepted`:

```json
{
  "status": "accepted",
  "warnings": ["Optional list of per-item warnings from the precheck"]
}
```

### Error responses

| Status | Meaning |
|--------|---------|
| `401` | Missing or invalid session token. |
| `403` | Insufficient permissions (requires Administrator, TestManager, or TestDesigner role). |
| `404` | Project not found, or agent is disabled for the project. |
| `409` | Precheck failed. No items passed validation. |

---

## Authorization

All agent endpoints require a valid **TestBench session token** passed as the `Authorization` header. The token is validated by calling the TestBench REST API. The user must have at least one of the following roles:

- Administrator
- TestManager
- TestDesigner

---

## Configuring Agents

Each agent can be enabled/disabled, assigned a different prompt, or overridden per project in `config.toml`. See the [Configuration](../configuration.md#use-case-settings) page for details.
