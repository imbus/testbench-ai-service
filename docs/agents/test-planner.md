---
sidebar_position: 4.5
title: Test Planner
---
# Test Planner

Plans a test selection for a test cycle: the test cases that differ most in content, so a small selection covers as much functionality as possible and near-identical tests are not planned twice.

**Endpoint:** `POST /test-planner` (configurable, see [Configuration](#configuration))

:::warning
The selected test cases are set to **Planned** in the cycle (see [Result](#result)); the full result is written to the **service log**.
The agent is **opt-in**: it is not part of the default agents and only runs when it is added to the `config.toml`.
It requires **TestBench 4.1 or newer** and a **JSON-based** test object version (TOV).
:::

## Authorization

The triggering user must hold the **project role** `TestManager`.

For JWT tokens the following API token permissions are required: `ReadOwnUserDetails`, `ReadProjectDetails`, `ReadTovReport`, `ReadCycleReport`, `ReadReportingJobDetails`, `DownloadReportFile`, `ReadTestThemeTree`, `ReadTestCaseSetDetails`, `ImportExecutionResults`.

## How it works

1. Every test case of the cycle (below `root_uid`, if given) is turned into a text; test cases of the TOV that have no execution in the cycle are ignored, since they cannot be planned. The text consists of the test case set name, description, test sequence and the parameter values of the test case. The text is embedded; embeddings are cached in `cache_dir` by content hash.
2. The selection starts at the test case with the largest mean distance to all others and then repeatedly takes the test case that is farthest from everything selected so far (farthest point sampling). Equal data gives the same ranking.
3. The prompt variant decides where the selection ends.
4. The selected test cases are set to `Planned` through one JSON execution results import (`protocol.json` plus the details of each affected test case set). Their blocked state and verdict are kept.

Rules that apply in every variant:

- Test cases carrying the `mandatory_tag` are always selected.
- Test cases that are already executed (`Performed`, `Running`) are never selected, but similar test cases count as covered by them.
- A test case with distance 0 to a selected one is never selected; it is an indistinguishable duplicate.

## Variants

| Variant (en / de)                              | Ends …                                                        | Variables                          |
| ---------------------------------------------- | ------------------------------------------------------------- | ---------------------------------- |
| Automatic / Automatisch (default)              | at the knee of the curve, where each further test adds little | `knee_percent`, `existing`         |
| Count / Anzahl                                 | after `count` test cases (default 40)                         | `count`, `existing`                |
| Time budget / Zeitbudget                       | before the planned durations exceed `budget_minutes` (240)    | `budget_minutes`, `existing`       |
| Requirement coverage / Requirement-Abdeckung   | when `coverage_percent` % of the requirements are covered     | `coverage_percent`, `existing`     |

`existing = keep` (default) keeps already planned test cases and adds to them; `replan` selects without them.

`knee_percent` (default 100) moves the end of the automatic selection relative to the knee: 150 selects one and a half times as many test cases as the knee, 50 half as many. Mandatory and already planned test cases are not counted and always stay selected; the selection takes at least one further test case and never reaches the first duplicate. `cutoff_hints.knee` still shows the unscaled knee.

Example request:

```json
{
  "project_key": "12",
  "tov_key": "34",
  "cycle_key": "56",
  "root_uid": "itb-TT-42",
  "prompt_config": { "variant": "Count", "vars": { "count": "30" } }
}
```

## Configuration

```toml
[testbench-ai-service.agents.test_planner]
enabled = true
endpoint_path = "/test-planner"
class_path = "testbench_ai_service.agents.test_planner.agent.TestPlannerAgent"

[testbench-ai-service.agents.test_planner.prompt]
file = "test_planner/prompt.yaml"

[testbench-ai-service.agents.test_planner.args]
mandatory_tag = "mandatory"      # test cases with this tag are always selected
cluster_threshold = 0.05         # distance below which test cases count as redundant

[testbench-ai-service.agents.test_planner.args.embedding]
provider = "openai"              # openai | azure_openai | local
model = "text-embedding-3-small"
cache_dir = "data/embedding_cache"
batch_size = 256
```

All `args` keys are optional. Unknown keys are rejected at startup. Projects can override single keys in `[testbench-ai-service.projects."<project>".agents.test_planner.args]`.

Embedding providers:

- **openai** uses `OPENAI_API_KEY`, or the project key `<PROJECT>_OPENAI_API_KEY`. A restricted key needs the permission **Model capabilities: Request** (`POST /v1/embeddings`), see [OpenAI Setup](../llm-providers/openai-setup.md#restrict-the-keys-permissions).
- **azure_openai** takes `azure_endpoint`, `api_version` and `auth_method` (API key or Entra ID) from the `llm_config`; `model` is the name of the embedding deployment.
- **local** computes embeddings inside the service with [fastembed](https://github.com/qdrant/fastembed), e.g. `model = "BAAI/bge-small-en-v1.5"`. Install the extra with `pip install testbench-ai-service[local-embeddings]`. The model is downloaded on first use; for offline use, place it in the fastembed cache beforehand. The planner then makes no LLM or embedding API calls at all and needs no API key. The prebuilt binary (`build_binary.py`) does not include fastembed: there, use `openai` or `azure_openai`, or run the service from a Python installation with the extra.

## Result

Selected test cases that are `NotPlanned`, `Skipped` or `Canceled` are set to `Planned`. Test cases that are already `Planned` or `Assigned` stay as they are, and test cases that are not selected are never changed, not even with `existing = replan`. The import runs as a TestBench background job; its outcome shows in TestBench, not in the service log.

The log contains a line `Test planner looked at A test cases, B of them in the cycle, C of them not executed yet`, a line `Test planner skipped K selected test cases | already planned=…, executed=…, …` when some selected test cases could not be changed, a line `Test planner set N of M selected test cases to planned` and a line `Test planner selection | project=… | cycle=… | mode=… | selected=…/…` followed by JSON:

```json
{
  "selected": 30, "total": 606, "planned_minutes": 238.0, "mode": "count",
  "cutoff_hints": { "knee": 40, "full_requirement_coverage": 31, "distance_zero_from": 480 },
  "selection": [
    { "rank": 1, "unique_id": "itb-TC-42-PC-1", "key": "4711", "path": "/Regression/…",
      "min_distance": 1.0, "reason": "farthest" }
  ],
  "redundancy_clusters": [ { "tests": ["itb-TC-7-PC-1", "itb-TC-9-PC-1"], "sets": ["Delete test case set"] } ],
  "warnings": []
}
```

- `reason` is `mandatory`, `existing` (already planned, `existing = keep`) or `farthest`.
- `cutoff_hints` give the rank of the knee, of full requirement coverage and of the first duplicate, whatever variant was used.
- `redundancy_clusters` list test cases closer than `cluster_threshold`: candidates for cleaning up the suite.
