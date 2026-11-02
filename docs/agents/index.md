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

:::warning
Execution-level agents, such as the Defect Explainer, do not support XML-based test-object versions (TOVs).
:::

---

## Built-in Agents

| Agent key                                                | Description                                                                                                                                |
| -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| [`test_case_set_reviewer`](test-case-set-reviewer.md)   | AI-powered quality reviews. Results are added to the review comment section of each test structure element specification.                  |
| [`test_case_set_describer`](test-case-set-describer.md) | Automatic generation of descriptive summaries. Results are assigned to the description field of each test structure element specification. |
| [`defect_explainer`](defect-explainer.md)               | AI-generated explanations for defects found during test execution. Results are added to the comment section of the execution overview.     |
| [`requirement`](generate-test-ideas.md) (opt-in)         | AI-generated test ideas for the requirements assigned below a test theme. Results are added to the description of the test theme. Not registered by default. |

Opt-in (not part of the default agents, enable it in the `config.toml`):

| Agent key                             | Description                                                                                                         |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| [`test_planner`](test-planner.md)     | Plans the most diverse test selection of a cycle via embeddings: sets the selected test cases to Planned and logs the result. |
| [`coverage_checker`](coverage-checker.md) | Checks whether the tests linked to a requirement prove all its aspects. Results are added to the review comment of every linked test case set. |
| [`link_finder`](link-finder.md) | Finds test case sets that test a requirement but are not linked to it. Every candidate gets a hint in its review comment; links are never set. |

---

## Custom Agents

In addition to the built-in agents, the service supports custom agents. A custom agent is a Python class that extends the `Agent` base class and is registered in `config.toml` via its `class_path`. It follows the same lifecycle and is exposed on the same generic endpoints as built-in agents.

See the [Custom Agent](custom-agent.md) guide for step-by-step instructions.

---

## Generic agent endpoints

In addition to the dedicated trigger endpoints, the service exposes a set of generic endpoints that work with any agent by key:

| Method   | Endpoint                        | Description                                                          |
| -------- | ------------------------------- | -------------------------------------------------------------------- |
| `GET`  | `/agents`                     | List all configured agents.                                          |
| `GET`  | `/agents/{agent_key}`         | Get details for a specific agent.                                    |
| `GET`  | `/agents/{agent_key}/prompt`  | Inspect the configured prompt and its variants.                      |
| `POST` | `/agents/{agent_key}/trigger` | Trigger any agent by key (same request body as dedicated endpoints). |

### Query parameters

The `GET` endpoints accept the following optional query parameters:

| Parameter       | Applies to           | Type                | Description                                                            |
| --------------- | -------------------- | ------------------- | ---------------------------------------------------------------------- |
| `keys`        | `GET /agents`      | String (repeatable) | Filter the list by one or more agent keys.                             |
| `project_key` | All`GET` endpoints | String              | Resolve the agent's effective configuration for the given project key. |
| `language`    | All`GET` endpoints | String              | Override language for prompt resolution (`en` or `de`).            |
| `enabled`     | `GET /agents`      | Boolean             | Filter by enabled status.                                              |

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

| Field             | Type   | Description                                                                                                                                                                                                               | Required |
| ----------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| `project_key`   | String | TestBench project key.                                                                                                                                                                                                    | Yes      |
| `tov_key`       | String | Test-object-version key.                                                                                                                                                                                                  | Yes      |
| `cycle_key`     | String | Test cycle key (required for defect explanations).                                                                                                                                                                        | No       |
| `root_uid`      | String | Unique ID of the element in TestBench on which the agent was triggered. Limits processing to the subtree rooted at this element.                                                                                          | No       |
| `root_key`      | String | Key of the element in TestBench on which the agent was triggered. Alternative to`root_uid` for subtree scoping.                                                                                                         | No       |
| `element_type`  | String | Type of the element the agent was triggered on (e.g.`"TESTCASESET"`, `"TESTTHEME"`, `"ROOT"`). Provided by the TestBench plugin as part of the execution context.                                                   | No       |
| `tree_type`     | String | Tree the element belongs to in TestBench (e.g.`"TESTTHEMES"`, `"TESTELEMENTS"`, `"REQUIREMENTS"`). Provided by the TestBench plugin as part of the execution context.                                               | No       |
| `filtering`     | Object | Active UI filter state from TestBench at the time of triggering:`appliedFilters` (list of named filters), `excludedTestThemes` (UIDs of collapsed/excluded themes), and `labelFilter` (active label filter string). | No       |
| `language`      | String | Override language (`"en"` or `"de"`).                                                                                                                                                                                 | No       |
| `prompt_config` | Object | Override prompt configuration for this request.                                                                                                                                                                           | No       |
| `llm_config`    | Object | Override LLM configuration for this request.                                                                                                                                                                              | No       |

### Response

On success, `202 Accepted`:

```json
{
  "status": "accepted",
  "job_id": "7f3a9c1e5b2d4e8f9a0b1c2d3e4f5a6b",
  "warnings": ["Optional list of per-item warnings from the precheck"]
}
```

`job_id` identifies this run. Use it with [`GET /jobs/{job_id}`](#jobs) to follow the run and to fetch its report. It is also the `run_id` in the service log.

### Error responses

| Status  | Meaning                                                                                     |
| ------- | ------------------------------------------------------------------------------------------- |
| `401` | Missing or invalid authorization token.                                                     |
| `403` | Insufficient permissions or project role. See each agent's page for the exact requirements. |
| `404` | Agent not found, project not found, or agent is disabled for the project.                   |
| `409` | Precheck failed. No items passed validation.                                                |
| `422` | Invalid request body. The request failed schema validation.                                 |
| `502` | The service could not reach the TestBench REST API server.                                  |

---

## Jobs

Every accepted trigger starts a **job**. The `202` response carries its `job_id`; the TestBench plugin polls the job to show progress and, once it is done, the agent's report.

```
GET /jobs/{job_id}
```

The request needs the same `Authorization` header as the agent endpoints. Example response for a running job:

```json
{
  "job_id": "7f3a9c1e5b2d4e8f9a0b1c2d3e4f5a6b",
  "agent_key": "coverage_checker",
  "project_key": "PRJ-1",
  "project_name": "Dream Car",
  "root_key": "REQ-12",
  "item_ids": [],
  "status": "running",
  "progress": {"done": 3, "total": 7, "text": "Interpreting test case sets"},
  "error": null,
  "warnings": [],
  "report_type": null,
  "report": null,
  "created_at": "2026-10-22T09:14:03Z",
  "updated_at": "2026-10-22T09:14:21Z",
  "finished_at": null
}
```

| Field                              | Description                                                                                                  |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `status`                           | `running`, `succeeded` or `failed`. These are the only values.                                               |
| `progress`                         | `done` of `total` steps plus an optional `text`; `null` while the agent reports none.                        |
| `error`                            | Why the job `failed`, in the language of the run. `null` otherwise.                                          |
| `warnings`                         | Per-item warnings from the precheck.                                                                         |
| `report_type`, `report`            | Set once the agent has stored a report, otherwise `null`. See [Reports](#reports).                           |
| `created_at`, `updated_at`, `finished_at` | Timestamps. `finished_at` is `null` while the job runs.                                               |

Poll every 2 to 3 seconds until `status` is `succeeded` or `failed`.

| Status | Meaning                                                                                                |
| ------ | ------------------------------------------------------------------------------------------------------ |
| `404`  | No such job, or it belongs to another user. Both look the same, and administrators are no exception.     |
| `401`  | Missing or invalid authorization token.                                                                |
| `503`  | The job store could not be read. Try again later.                                                      |

### Reports

`report_type` names the schema of `report`; the service stores the report as JSON and returns it unchanged. It renders nothing, the plugin does.

| `report_type`      | `report`                                                                                                  |
| ------------------ | --------------------------------------------------------------------------------------------------------- |
| `coverage_checker` | The [Coverage Checker](coverage-checker.md#report)'s `CoverageResult`.                                    |
| `link_finder`      | The [Link Finder](link-finder.md#report)'s `LinkFinderResult`; not yet agreed on with the plugin.          |

:::caution
The report schemas are a contract with the plugin. A change to one, for example to `CoverageResult`, is a breaking change.
:::

Agents without a report type still have a job with status and progress, but `report_type` and `report` stay `null`.

### Retention

Jobs are kept in the same SQLite file as the [token usage](../configuration.md#service-settings) (`usage_file`). At startup, jobs older than `[testbench-ai-service.jobs] retention_days` (default 90) are deleted, and jobs still `running` become `failed` with the error "Aborted by a service restart", since a restart ends their runs. The error is written in the service's default `language`, so a German service writes "Durch Neustart des Service abgebrochen". See [Configuration](../configuration.md#jobs).

---

## Authorization

All agent endpoints require an **`Authorization` header** containing either a JWT token or a session token. The token is validated by calling the TestBench REST API.

Allowed project roles and required API token permissions differ per agent. See each agent's page for details:

- [Test Case Set Reviewer](test-case-set-reviewer.md#authorization)
- [Test Case Set Describer](test-case-set-describer.md#authorization)
- [Defect Explainer](defect-explainer.md#authorization)
- [Test Idea Generator](generate-test-ideas.md#authorization)
- [Test Planner](test-planner.md#authorization)
- [Link Finder](link-finder.md#authorization)
- [Coverage Checker](coverage-checker.md#authorization)

The permissions an OpenAI API key needs per agent are listed in [OpenAI Setup](../llm-providers/openai-setup.md#restrict-the-keys-permissions).

For custom agents, implement your own permission and role checks inside `precheck()`. See [Custom Agent: 1. Implement the agent class](custom-agent.md#1-implement-the-agent-class) for details.

:::note
The API token permission check applies only to JWT tokens. Session tokens bypass it but still require the correct project role.
:::

---

## Configuring Agents

Each agent can be enabled/disabled, assigned a different prompt, or overridden per project in `config.toml`. See the [Configuration](../configuration.md#agent-settings) page for details.
