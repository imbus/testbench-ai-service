---
sidebar_position: 1
title: Agents
---

# Agents

An **agent** is a self-contained AI-driven workflow that the service exposes as an HTTP endpoint. Each agent follows the same lifecycle:

1. **Trigger**: TestBench sends a POST request with project, test-object-version, and (optionally) cycle information.
2. **Precheck**: The service validates requirements (e.g., that test structure elements are not locked by another user) and collects the items to process.
3. **Background execution**: The API responds with `202 Accepted` immediately. In the background, prompt templates are rendered with test data, sent to the configured LLM, and the results are written back to TestBench.

---

## Built-in Agents

| Agent key | Description |
|-----------|-------------|
| [`test_case_set_reviewer`](test-case-set-reviewer.md) | AI-powered quality reviews. Results are added to the review comment section of each test structure element specification. |
| [`test_case_set_describer`](test-case-set-describer.md) | Automatic generation of descriptive summaries. Results are assigned to the description field of each test structure element specification. |
| [`defect_explainer`](defect-explainer.md) | AI-generated explanations for defects found during test execution. Results are added to the comment section of the execution overview. |

---

## Custom Agents

In addition to the built-in agents, the service supports custom agents. A custom agent is a Python class that extends the `Agent` base class and is registered in `config.toml` via its `class_path`. It follows the same lifecycle and is exposed on the same generic endpoints as built-in agents.

See the [Custom Agent](custom-agent.md) guide for step-by-step instructions.

---

## Generic agent endpoints

In addition to the dedicated trigger endpoints, the service exposes a set of generic endpoints that work with any agent by key:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/agents` | List all configured agents. |
| `GET` | `/agents/{agent_key}` | Get details for a specific agent. |
| `GET` | `/agents/{agent_key}/prompt` | Inspect the configured prompt and its variants. |
| `POST` | `/agents/{agent_key}/trigger` | Trigger any agent by key (same request body as dedicated endpoints). |

### Query parameters

The `GET` endpoints accept the following optional query parameters:

| Parameter | Applies to | Type | Description |
|-----------|------------|------|-------------|
| `keys` | `GET /agents` | String (repeatable) | Filter the list by one or more agent keys. |
| `project_key` | All `GET` endpoints | String | Resolve the agent's effective configuration for the given project key. |
| `language` | All `GET` endpoints | String | Override language for prompt resolution (`en` or `de`). |
| `enabled` | `GET /agents` | Boolean | Filter by enabled status. |

For example, to trigger the Test Case Set Reviewer via the generic endpoint:

```
POST /agents/test_case_set_reviewer/trigger
```

---

## Common request format

All agent trigger endpoints accept the same request body:

```json
{
  "project_key": "PRJ-123",
  "tov_key": "TOV-456",
  "cycle_key": "CYC-789",
  "root_uid": "UID-000",
  "root_key": "ROOT-001",
  "element_type": "TESTCASESET",
  "tree_type": "TESTTHEMES",
  "language": "en",
  "prompt_config": {
    "file": "custom_prompt/prompt.yaml",
    "variant": "variant-name",
    "vars": {
      "glossary": "Domain: automotive\nABS = Anti-lock Braking System"
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
| `root_uid` | String | Unique ID of the element in TestBench on which the agent was triggered. Limits processing to the subtree rooted at this element. | No |
| `root_key` | String | Key of the element in TestBench on which the agent was triggered. Alternative to `root_uid` for subtree scoping. | No |
| `element_type` | String | Type of the element the agent was triggered on (e.g. `"TESTCASESET"`, `"TESTTHEME"`, `"ROOT"`). Provided by the TestBench plugin as part of the execution context. | No |
| `tree_type` | String | Tree the element belongs to in TestBench (e.g. `"TESTTHEMES"`, `"TESTELEMENTS"`, `"REQUIREMENTS"`). Provided by the TestBench plugin as part of the execution context. | No |
| `filtering` | Object | Active UI filter state from TestBench at the time of triggering: `appliedFilters` (list of named filters), `excludedTestThemes` (UIDs of collapsed/excluded themes), and `labelFilter` (active label filter string). | No |
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
| `401` | Missing or invalid authorization token. |
| `403` | Insufficient permissions or project role. See each agent's page for the exact requirements. |
| `404` | Agent not found, project not found, or agent is disabled for the project. |
| `409` | Precheck failed. No items passed validation. |
| `422` | Invalid request body. The request failed schema validation. |
| `502` | The service could not reach the TestBench REST API server. |

---

## Authorization

All agent endpoints require an **`Authorization` header** containing either a JWT token or a session token. The token is validated by calling the TestBench REST API.

Allowed project roles and required API token permissions differ per agent. See each agent's page for details:

- [Test Case Set Reviewer](test-case-set-reviewer.md#authorization)
- [Test Case Set Describer](test-case-set-describer.md#authorization)
- [Defect Explainer](defect-explainer.md#authorization)

For custom agents, implement your own permission and role checks inside `precheck()`. See [Custom Agent: 1. Implement the agent class](custom-agent.md#1-implement-the-agent-class) for details.

:::note
The API token permission check applies only to JWT tokens. Session tokens bypass it but still require the correct project role.
:::

---

## Configuring Agents

Each agent can be enabled/disabled, assigned a different prompt, or overridden per project in `config.toml`. See the [Configuration](../configuration.md#agent-settings) page for details.
