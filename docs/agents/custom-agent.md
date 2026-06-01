---
sidebar_position: 5
title: Custom Agent
---

# Custom Agent

The TestBench AI Service is built to be extended. By implementing the `Agent` base class and registering your class in `config.toml`, you can add any AI-driven workflow without modifying the service source code. Custom agents follow the same lifecycle as the built-in ones. They get their own endpoint, participate in the precheck/run pipeline, and can use all configured LLM providers.

---

## How it works

A custom agent implements the same two-phase lifecycle described in the [Agents overview](index.md):

1. **Precheck**: Validate prerequisites and collect the item IDs to process. Return a `PrecheckResult` with `passed=True` and the list of item IDs, or `passed=False` to stop with `409 Conflict`.
2. **Run**: Receive the validated item IDs, retrieve full item data from TestBench, render the prompt, query the LLM, and write results back to TestBench.

The service handles endpoint registration, authentication, background execution, and LLM client creation. Your implementation focuses entirely on the domain logic.

---

## 1. Implement the agent class

Create a Python package anywhere that is importable by the service. The recommended layout mirrors the built-in agents:

```
my_agents/
└── risk_assessor/
    ├── __init__.py
    └── agent.py
```

### Skeleton

```python
# my_agents/risk_assessor/agent.py
import asyncio

from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.agents.base import Agent, AgentData
from testbench_ai_service.auth import AuthInfo
from testbench_ai_service.llm.base import LLMClient
from testbench_ai_service.models.agent import ExecutionContext, PrecheckResult
from testbench_ai_service.utils.agent import get_test_case_set_nodes
from testbench_ai_service.utils.prompt_utils import build_prompt


class RiskAssessorAgentData(AgentData, total=False):
    """Variables available as ``{{ agent.<key> }}`` in prompt templates."""

    step_sequence: str
    parameter_combinations: str | None


class RiskAssessor(Agent):

    async def precheck(
        self,
        context: ExecutionContext,
        conn: TBConnection,
        auth_info: AuthInfo,
    ) -> PrecheckResult:
        warnings = []
        nodes = get_test_case_set_nodes(conn, context)

        items = []
        for node in nodes:
            locked_by_other_user = (
                node.spec is not None
                and node.spec.locker is not None
                and node.spec.locker.key != context.user_key
            )
            if locked_by_other_user:
                warnings.append(f"Skipped '{node.base.uniqueID}': locked by another user.")
                continue
            items.append(node.base.uniqueID)

        if items:
            return PrecheckResult(passed=True, warnings=warnings, items=items)
        return PrecheckResult(passed=False, warnings=warnings)

    async def run(
        self,
        context: ExecutionContext,
        conn: TBConnection,
        llm_client: LLMClient,
        item_ids: list[str],
    ) -> None:
        tasks = [
            asyncio.create_task(
                self._process_item(uid, context, conn, llm_client)
            )
            for uid in item_ids
        ]
        await asyncio.gather(*tasks)

    async def _process_item(
        self,
        uid: str,
        context: ExecutionContext,
        conn: TBConnection,
        llm_client: LLMClient,
    ) -> None:
        # 1. Retrieve full item data from TestBench via conn.session
        # 2. Build agent data
        agent_data: RiskAssessorAgentData = {
            "step_sequence": ...,   # format the item into a plain-text string
            "parameter_combinations": None,
        }
        # 3. Build and send the prompt
        prompt = build_prompt(context.prompt_config, agent_data=agent_data)
        model = context.llm_config.model or prompt.model_name
        result = await llm_client.query_llm(model=model, messages=prompt.messages)
        # 4. Write result back to TestBench via conn.session
        ...
```

### Key interfaces

#### `precheck()`

| Return value | Effect |
|---|---|
| `PrecheckResult(passed=True, items=[...])` | Execution continues for the listed item IDs. |
| `PrecheckResult(passed=False, warnings=[...])` | Agent stops; the API responds with `409 Conflict`. |

Collect per-item warnings in `PrecheckResult.warnings`. They are surfaced in the `202 Accepted` response body so TestBench can display them to the user.

#### `run()`

Receives only the item IDs that passed precheck. Process items concurrently with `asyncio.gather`. This mirrors how all built-in agents work and keeps response times short.

#### `AgentData`

`AgentData` is a `TypedDict` that declares the variables your agent puts into the `{{ agent.* }}` namespace in prompt templates. Declare a key for each variable your prompt references.

## 2. Create a prompt file

Place the prompt YAML file under `prompts_dir/<language>/` (relative path matches what you set in `prompt.file`):

```
prompts/
└── en/
    └── risk_assessor/
        └── prompt.yaml
```

```yaml
name: "RiskAssessor"
summary: "Assess test case set risk level"
description: "Estimates the risk level for each test case set and logs the result."
default_model: "gpt-5.5"
default_variant: "default"
variants:
  - name: "default"
    messages:
      - role: "system"
        text: |
          You are a test engineer. Analyze the test case and respond with exactly one line:
          "Risk: <High|Medium|Low> — <one-sentence rationale>"
      - role: "user"
        text: |
          {{ agent.step_sequence }}
          {% if agent.parameter_combinations %}
          Parameters:
          {{ agent.parameter_combinations }}
          {% endif %}
```

See [Prompts](../prompts.md) for the full YAML schema, variable declarations, and multi-variant configuration.

## 3. Register in config.toml

Add an agent block to `config.toml` with a unique agent key and the fully-qualified `class_path` pointing to your `Agent` subclass:

```toml
# config.toml
[testbench-ai-service.agents.risk_assessor]
enabled = true
endpoint_path = "/risk-assessments"
class_path = "my_agents.risk_assessor.agent.RiskAssessor"

[testbench-ai-service.agents.risk_assessor.prompt]
file = "risk_assessor/prompt.yaml"
```

| Field | Description |
|---|---|
| `enabled` | Set to `false` to disable the agent without removing the config block. |
| `endpoint_path` | The URL path for the dedicated trigger endpoint. Must start with `/`. |
| `class_path` | Fully-qualified import path to the `Agent` subclass (`package.module.ClassName`). The module must be importable from the service's Python environment. |
| `prompt.file` | Path to the prompt YAML file, relative to `prompts_dir/<language>/`. |
| `prompt.variant` | Prompt variant to use (falls back to `default_variant` in the YAML). |
| `prompt.vars` | Key-value pairs for user-provided variables. |

:::note
The `name`, `summary`, and `description` defined in the prompt YAML file are shown in the OpenAPI UI and surfaced to TestBench as the agent name, summary, and description.
:::

Once registered, the agent is available on both the dedicated endpoint (`POST /risk-assessments`) and the generic endpoint (`POST /agents/risk_assessor/trigger`).

---

## Making your module importable

The `class_path` is resolved with a standard Python import at service startup. Make sure the module is importable from the environment in which the service runs:

- **Install into the same virtualenv:**

  ```bash
  pip install -e /path/to/my_agents
  ```

- **Add to `PYTHONPATH`** (useful during development):

  ```bash
  PYTHONPATH=/path/to/my_agents testbench-ai-service start
  ```

:::note
If the class cannot be imported at startup, the service will log an error and refuse to register the agent. Check the log output for the exact import error.
:::

---

## Reusing built-in utilities

The following utilities are available to custom agents. They are the same helpers used by all built-in agents.

### Service utilities

#### `testbench_ai_service.utils.agent`

| Function | Description |
|---|---|
| `get_test_case_set_nodes(conn, context)` | Returns all `TestCaseSetNode` items in scope, respecting `root_uid`, `filtering`, and cycle. Use this in `precheck()` to enumerate the items to process. |
| `has_required_permissions(token, required_permissions)` | Returns `True` if the JWT token grants all specified `PermissionWithCode` values. Use this in `precheck()` to enforce API token permissions for JWT-authenticated requests. |

#### `testbench_ai_service.utils.testbench`

| Function | Description |
|---|---|
| `get_test_case_set_catalog(conn, project_key, tov_key, cycle_key, root_uid, filtering)` | Downloads and parses the full JSON test report into a `TestCaseSet` catalog keyed by UID. Use this in `run()` to retrieve full test case data for each item. |
| `get_project_roles(conn, project_key)` | Returns the current user's project roles for the given project. Use this in `precheck()` to enforce role requirements. |
| `get_user_key(conn)` | Returns the key of the currently authenticated user. |
| `get_project_name(conn, project_key)` | Resolves a project key to its display name. |

#### `testbench_ai_service.utils.prompt_utils`

| Function | Description |
|---|---|
| `build_prompt(prompt_config, agent_data)` | Loads the prompt YAML, resolves the variant, renders all Jinja2 templates, and returns a `Prompt` ready for `llm_client.query_llm`. |
| `get_prompt_definition(prompt_path)` | Loads and validates a prompt YAML file, returning a `PromptDefinition` object. |

#### `testbench_ai_service.utils.testbench_helpers`

| Function | Description |
|---|---|
| `parameter_combinations_as_str(test_case_set)` | Formats the parameter combination table of a `TestCaseSet` as a Markdown table string. |

#### `testbench_ai_service.utils.html_utils`

| Function | Description |
|---|---|
| `extract_text_from_html_body(html)` | Extracts and returns visible text from the `<body>` of an HTML string. Useful for reading TestBench HTML fields as plain text. |
| `strip_html_body_tags(text)` | Removes `<html>`, `</html>`, `<body>`, and `</body>` wrapper tags from a string. Use this when you want to preserve the inner HTML structure but strip the outer tags. |

### Models and enumerations

```python
from testbench_ai_service.models.testbench import PermissionWithCode, ProjectRole
```

| Class | Description |
|---|---|
| `PermissionWithCode` | Enum of all TestBench API token permissions. Pass a set of these to `has_required_permissions()` to enforce JWT token scopes in `precheck()`. |
| `ProjectRole` | Enum of TestBench project roles. The built-in agents use `TestManager`, `Tester`, and `TestDesigner`. |

### External libraries

Two external libraries are bundled with the service and used by all built-in agents.

#### `testbench_cli_reporter` — TestBench connection

`testbench_cli_reporter.testbench.Connection` (imported as `TBConnection`) is an active, authenticated connection to the TestBench REST API. It is passed to both `precheck()` and `run()`.

Key attributes:

- `conn.session` — a `requests.Session` with authentication pre-configured. Use this for direct HTTP calls to the TestBench REST API.
- `conn.server_url` — the base URL of the TestBench REST API server.

```python
from testbench_cli_reporter.testbench import Connection as TBConnection

# Example: write a result back to TestBench
conn.session.patch(
    f"{conn.server_url}2/projects/{project_key}/specifications/{spec_key}",
    json={"description": generated_description},
)
```

For write-back patterns (PATCH specification, review comment, or execution result), refer to the built-in agent source files as reference implementations.

#### `testbench2robotframework` — test report models

The `testbench2robotframework` library provides the data models for the JSON test report downloaded from TestBench via `get_test_case_set_catalog`.

| Import | Description |
|---|---|
| `testbench2robotframework.json_reader.TestCaseSet` | Primary data model. Contains test case definitions, steps, parameters, and execution details. |
| `testbench2robotframework.json_reader.TestBenchJsonReader` | Parses a JSON report directory into a list of `TestCaseSet` objects. Used internally by `get_test_case_set_catalog`. |
| `testbench2robotframework.model.TestCaseDetails` | Details of a single test case within a set, including its steps and parameters. |
| `testbench2robotframework.model.KeywordCall` | Represents a single test step (keyword call). |

---

## Project-specific override

Like built-in agents, custom agents support per-project overrides:

```toml
# config.toml
[testbench-ai-service.projects."My Project".agents.risk_assessor]
enabled = false

[testbench-ai-service.projects."My Project".agents.risk_assessor.prompt]
variant = "concise"
```

See [Configuration precedence](../configuration.md#configuration-precedence) for the full override order.

---

## Complete example

The following is a self-contained agent that retrieves test case sets, sends each one to the LLM for a risk assessment, and logs the result. Extend `_process_item` to write the result back to TestBench via `conn.session`.

### `my_agents/risk_assessor/agent.py`

```python
import asyncio

from testbench2robotframework.json_reader import TestCaseSet
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.agents.base import Agent, AgentData
from testbench_ai_service.auth import AuthInfo
from testbench_ai_service.llm.base import LLMClient
from testbench_ai_service.log import logger
from testbench_ai_service.models.agent import ExecutionContext, PrecheckResult
from testbench_ai_service.utils.agent import get_test_case_set_nodes
from testbench_ai_service.utils.prompt_utils import build_prompt
from testbench_ai_service.utils.testbench import get_test_case_set_catalog
from testbench_ai_service.utils.testbench_helpers import parameter_combinations_as_str


class RiskAssessorAgentData(AgentData, total=False):
    step_sequence: str
    parameter_combinations: str | None


class RiskAssessor(Agent):

    async def precheck(
        self,
        context: ExecutionContext,
        conn: TBConnection,
        auth_info: AuthInfo,
    ) -> PrecheckResult:
        warnings = []
        nodes = get_test_case_set_nodes(conn, context)

        items = []
        for node in nodes:
            locked_by_other_user = (
                node.spec is not None
                and node.spec.locker is not None
                and node.spec.locker.key != context.user_key
            )
            if locked_by_other_user:
                warnings.append(f"Skipped '{node.base.uniqueID}': locked by another user.")
                continue
            items.append(node.base.uniqueID)

        if items:
            return PrecheckResult(passed=True, warnings=warnings, items=items)
        return PrecheckResult(passed=False, warnings=warnings)

    async def run(
        self,
        context: ExecutionContext,
        conn: TBConnection,
        llm_client: LLMClient,
        item_ids: list[str],
    ) -> None:
        catalog = get_test_case_set_catalog(
            conn=conn,
            project_key=context.project_key,
            tov_key=context.tov_key,
            cycle_key=context.cycle_key,
            root_uid=context.root_uid,
            filtering=context.filtering,
        )

        tasks = [
            asyncio.create_task(
                self._assess_test_case_set(tcs, context, conn, llm_client)
            )
            for tcs in catalog.values()
            if tcs.details.uniqueID in item_ids
        ]
        await asyncio.gather(*tasks)

    async def _assess_test_case_set(
        self,
        tcs: TestCaseSet,
        context: ExecutionContext,
        conn: TBConnection,
        llm_client: LLMClient,
    ) -> None:
        agent_data: RiskAssessorAgentData = {
            "step_sequence": "\n".join(
                f"{i + 1}. {step.name}"
                for i, step in enumerate(tcs.testCases[0].testSteps)
            ) if tcs.testCases else "",
            "parameter_combinations": parameter_combinations_as_str(tcs),
        }

        prompt = build_prompt(context.prompt_config, agent_data=agent_data)
        model = context.llm_config.model or prompt.model_name
        result = await llm_client.query_llm(model=model, messages=prompt.messages)

        logger.info(
            "Risk assessment for '%s': %s",
            tcs.details.uniqueID,
            result,
        )
        # Write result back to TestBench here, e.g.:
        # conn.session.patch(f"{conn.server_url}...", json={"reviewComment": result})
```

### `prompts/en/risk_assessor/prompt.yaml`

```yaml
name: "RiskAssessor"
summary: "Assess test case set risk level"
description: "Estimates the risk level for each test case set and logs the result."
default_model: "gpt-5.5"
default_variant: "default"
variants:
  - name: "default"
    messages:
      - role: "system"
        text: |
          You are a test engineer. Analyze the test case and respond with exactly one line:
          "Risk: <High|Medium|Low> — <one-sentence rationale>"
      - role: "user"
        text: |
          {{ agent.step_sequence }}
          {% if agent.parameter_combinations %}
          Parameters:
          {{ agent.parameter_combinations }}
          {% endif %}
  - name: "concise"
    model: "gpt-5.5-mini"
    messages:
      - role: "user"
        text: |
          Rate the risk of this test case as High, Medium, or Low.
          {{ agent.step_sequence }}
```

### `config.toml`

```toml
# config.toml
[testbench-ai-service.agents.risk_assessor]
enabled = true
endpoint_path = "/risk-assessments"
class_path = "my_agents.risk_assessor.agent.RiskAssessor"

[testbench-ai-service.agents.risk_assessor.prompt]
file = "risk_assessor/prompt.yaml"
```
