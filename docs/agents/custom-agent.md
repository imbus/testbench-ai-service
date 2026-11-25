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
from testbench_ai_service.jobs.items import gather_items
from testbench_ai_service.llm.base import LLMClient
from testbench_ai_service.models.agent import ExecutionContext, PrecheckResult
from testbench_ai_service.models.testbench import PermissionWithCode, ProjectRole
from testbench_ai_service.utils.agent import check_min_testbench_version
from testbench_ai_service.utils.testbench import get_test_case_set_nodes


class RiskAssessorAgentData(AgentData, total=False):
    """Variables available as ``{{ agent.<key> }}`` in prompt templates."""

    step_sequence: str
    parameter_combinations: str | None


class RiskAssessor(Agent):
    # Required: the service checks the prompt's {{ agent.* }} variables against it.
    AGENT_DATA_CLASS = RiskAssessorAgentData
    # The JWT permission of every TestBench endpoint the agent calls (checked for
    # JWT callers only). Add the permission of each endpoint
    # run() calls, e.g. ModifySpecifications for a PATCH of a specification.
    REQUIRED_PERMISSIONS = frozenset(
        {
            PermissionWithCode.ReadOwnUserDetails,  # role check
            PermissionWithCode.ReadProjectDetails,  # execution context
            PermissionWithCode.ReadTestThemeTree,  # get_test_case_set_nodes
        }
    )
    # The project roles that may trigger the agent; None skips the role check.
    ALLOWED_ROLES = frozenset({ProjectRole.TestManager, ProjectRole.TestDesigner})

    async def precheck(
        self,
        context: ExecutionContext,
        conn: TBConnection,
    ) -> PrecheckResult:
        if unsupported_version := check_min_testbench_version(context, conn):
            return unsupported_version
        warnings = []
        # A blocking TestBench request: run it off the event loop.
        nodes = await asyncio.to_thread(get_test_case_set_nodes, conn, context)

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
        # A failed item becomes a warning on the job; only if all fail, the job fails.
        await gather_items(
            [(uid, self._process_item(uid, context, conn, llm_client)) for uid in item_ids],
            context.language,
        )

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
        # 3. Render the prompt variant, resolve the model and ask the LLM
        result = await self.get_ai_response(
            llm_client, context.llm_config, context.prompt_config, agent_data
        )
        # 4. Write result.result back to TestBench via conn.session
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

Receives only the item IDs that passed precheck. Process items concurrently, as all built-in agents do, to keep response times short. Use `gather_items` (see [Reporting to the job](#reporting-to-the-job)) rather than a plain `asyncio.gather`, so that one failing item does not fail the whole job.

If `run()` raises, the [job](index.md#jobs) of the run ends as `failed`. If it returns normally, the job ends as `succeeded`, unless the agent has called `fail()` (see below).

#### Reporting to the job

Every accepted trigger starts a [job](index.md#jobs), which the TestBench plugin and the web console poll. Inside `run()`, `current_job()` returns the handle of that job:

```python
from testbench_ai_service.jobs.handle import current_job

await current_job().progress(done, total, "Assessing test case sets")
```

| Method | Effect |
|---|---|
| `progress(done, total, text=None)` | Sets the progress shown in the plugin, for example `3` of `10` items. `text` describes the current step. |
| `warn(message)` | Adds a warning to the job. The job keeps its status. |
| `set_report(report_type, report)` | Stores the agent's result, a Pydantic model or a `dict`. `report_type` names its schema, see [Reports](index.md#reports). |
| `fail(message)` | Ends the job as `failed` with `message` as its error. It stays `failed` even if `run()` returns normally afterwards. |

All methods are coroutines. Write messages and texts in `context.language`; the plugin shows them as they are.

- **No job, no effect.** Outside a job, for example in a unit test, `current_job()` returns a handle whose methods do nothing. Your agent never has to check whether a job exists.
- **Errors are not raised.** If the job store cannot be written, the service logs the error and the call returns normally. A broken job never fails the run.
- **Reports must be plain JSON.** A report holding `NaN` or `Infinity`, or a value that is not JSON at all, is logged and dropped. Round or replace such floats before calling `set_report`.
- **Report types are a contract.** The plugin renders only the report types it knows. Call `set_report` only with a type agreed on with the plugin, otherwise do not call it; the job still shows status, progress and warnings. The web console and the job page in the browser show a report of any type, see [Reports without a view](index.md#reports-without-a-view).

**If one item fails, warn; if all fail, fail.** An agent that processes several items should keep the job `succeeded` when single items fail, and report each failure as a warning. Only when every item failed should the job end as `failed`. The built-in agents follow this rule through `gather_items`, which you can use as well:

```python
from testbench_ai_service.jobs.items import gather_items

await gather_items(
    [(tcs.details.key, self._process(tcs, context, conn)) for tcs in test_case_sets],
    context.language,
)
```

`gather_items` takes `(label, awaitable)` pairs and runs them concurrently. Each failed item adds a localized warning naming `label`, so use a name the user knows, such as the test case set's key; if all items failed, it calls `fail()`. It returns normally in both cases, so log the details of a failure inside the awaitable.

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

## Looking up templates: `context.agent_key`

`context.agent_key` is the key the agent is configured under. When your agent resolves write-back templates with `resolve_template_path(...)`, pass `agent_key=context.agent_key` instead of a hard-coded name. The agent then keeps working when it is registered under another key.

---

## Reusing built-in utilities

The following utilities are available to custom agents. They are the same helpers used by all built-in agents.

### Service utilities

#### `testbench_ai_service.utils.agent`

| Function | Description |
|---|---|
| `has_required_permissions(token, required_permissions)` | Returns `True` if the JWT token grants all specified `PermissionWithCode` values. Use this in `precheck()` to enforce API token permissions for JWT-authenticated requests. |
| `check_min_testbench_version(context, conn)` | Returns a failed `PrecheckResult` with a localized message if the connected TestBench server is older than `MIN_TESTBENCH_VERSION` (currently `4.1`), otherwise `None`. Call it at the start of `precheck()` — the built-in agents do the same. Custom agents that work with older servers may skip it or implement their own version check against `conn.server_version`. |

#### `testbench_ai_service.utils.testbench`

These functions make blocking HTTP requests to TestBench: call them with `asyncio.to_thread` inside `precheck()` and `run()`.

| Function | Description |
|---|---|
| `get_test_case_set_nodes(conn, context)` | Returns all `TestCaseSetNode` items in scope, respecting `root_uid`, `filtering`, and cycle. Use this in `precheck()` to enumerate the items to process. |
| `get_test_case_set_catalog(conn, project_key, tov_key, cycle_key, root_uid, filtering)` | Downloads and parses the full JSON test report into a `TestCaseSet` catalog keyed by UID. Use this in `run()` to retrieve full test case data for each item. |
| `get_project_roles(conn, project_key)` | Returns the current user's project roles for the given project. Use this in `precheck()` to enforce role requirements. |
| `get_user_key(conn)` | Returns the key of the currently authenticated user. |
| `get_project_name(conn, project_key)` | Resolves a project key to its display name. |

#### `testbench_ai_service.utils.prompt_utils`

| Function | Description |
|---|---|
| `get_prompt_definition(prompt_path)` | Loads and validates a prompt YAML file, returning a `PromptDefinition` object. |

To render a prompt and ask the LLM in one step, call `self.get_ai_response(llm_client, context.llm_config, context.prompt_config, agent_data)` from your agent: it renders the variant, resolves the model and returns an `AgentResult` whose `result` is the answer text.

#### `testbench_ai_service.utils.testbench_helpers`

| Function | Description |
|---|---|
| `parameter_combinations_as_str(test_case_set)` | Formats the parameter combination table of a `TestCaseSet` as a Markdown table string. |
| `test_case_set_as_str(test_case_set)` | Formats the test cases and their steps of a `TestCaseSet` as plain text, as the built-in agents put them into their prompts. |

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
from testbench_ai_service.jobs.items import gather_items
from testbench_ai_service.llm.base import LLMClient
from testbench_ai_service.log import logger
from testbench_ai_service.models.agent import ExecutionContext, PrecheckResult
from testbench_ai_service.models.testbench import PermissionWithCode, ProjectRole
from testbench_ai_service.utils.agent import check_min_testbench_version
from testbench_ai_service.utils.testbench import get_test_case_set_catalog, get_test_case_set_nodes
from testbench_ai_service.utils.testbench_helpers import (
    parameter_combinations_as_str,
    test_case_set_as_str,
)


class RiskAssessorAgentData(AgentData, total=False):
    step_sequence: str
    parameter_combinations: str | None


class RiskAssessor(Agent):
    # Required: the service checks the prompt's {{ agent.* }} variables against it.
    AGENT_DATA_CLASS = RiskAssessorAgentData
    # The JWT permission of every TestBench endpoint the agent calls (checked for
    # JWT callers only).
    REQUIRED_PERMISSIONS = frozenset(
        {
            PermissionWithCode.ReadOwnUserDetails,  # role check
            PermissionWithCode.ReadProjectDetails,  # execution context
            PermissionWithCode.ReadTestThemeTree,  # get_test_case_set_nodes
            PermissionWithCode.ReadTovReport,  # get_test_case_set_catalog, TOV scope
            PermissionWithCode.ReadCycleReport,  # get_test_case_set_catalog, cycle scope
            PermissionWithCode.ReadReportingJobDetails,
            PermissionWithCode.DownloadReportFile,
        }
    )
    # The project roles that may trigger the agent; None skips the role check.
    ALLOWED_ROLES = frozenset({ProjectRole.TestManager, ProjectRole.TestDesigner})

    async def precheck(
        self,
        context: ExecutionContext,
        conn: TBConnection,
    ) -> PrecheckResult:
        if unsupported_version := check_min_testbench_version(context, conn):
            return unsupported_version
        warnings = []
        # A blocking TestBench request: run it off the event loop.
        nodes = await asyncio.to_thread(get_test_case_set_nodes, conn, context)

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
        catalog = await asyncio.to_thread(
            get_test_case_set_catalog,
            conn=conn,
            project_key=context.project_key,
            tov_key=context.tov_key,
            cycle_key=context.cycle_key,
            root_uid=context.root_uid,
            filtering=context.filtering,
        )

        await gather_items(
            [
                (tcs.details.uniqueID, self._assess_test_case_set(tcs, context, llm_client))
                for tcs in catalog.values()
                if tcs.details.uniqueID in item_ids
            ],
            context.language,
        )

    async def _assess_test_case_set(
        self,
        tcs: TestCaseSet,
        context: ExecutionContext,
        llm_client: LLMClient,
    ) -> None:
        agent_data: RiskAssessorAgentData = {
            "step_sequence": test_case_set_as_str(tcs),
            "parameter_combinations": parameter_combinations_as_str(tcs),
        }

        result = await self.get_ai_response(
            llm_client, context.llm_config, context.prompt_config, agent_data
        )

        logger.info(
            "Risk assessment for '%s': %s",
            tcs.details.uniqueID,
            result.result,
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
