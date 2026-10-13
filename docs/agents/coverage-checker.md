---
sidebar_position: 4.6
title: Coverage Checker
---
# Coverage Checker

Checks whether the test case sets linked to a requirement prove **all** of its aspects. In TestBench a requirement counts as covered as soon as a set is linked to it; the coverage checker reads the test steps and says which aspects are actually tested, which only weakly, and which not at all.

**Endpoint:** `POST /coverage` (configurable, see [Configuration](#configuration))

:::warning
The agent is **opt-in**: it is not part of the default agents and only runs when it is added to the `config.toml`. TestBench must offer the plugin on **requirements**. It requires a **JSON-based** test object version (TOV). Links and test elements are never changed.
:::

## Authorization

The triggering user must hold the **project role** `TestManager` or `TestDesigner`.

For JWT tokens the following API token permissions are required: `ReadOwnUserDetails`, `ReadProjectDetails`, `ReadTovRequirements`, `ReadTovReport`, `ReadReportingJobDetails`, `DownloadReportFile`, `ReadTestThemeTree`, `ReadTestCaseSetDetails`, `ModifySpecifications`.

## How it works

1. **Precheck** (answers `409` with a reason otherwise): the trigger names a requirement of a TOV, the TOV is JSON-based, and at least one test case is linked to the requirement. A set linked as a whole contributes all its test cases, otherwise only the test cases linked one by one.
2. **Aspects**: the model splits the requirement's title and description into testable aspects (`happy_path`, `negative`, `boundary`, `non_functional`). Each aspect must quote the requirement text; aspects that do not are dropped, as are duplicates. At most `max_aspects` are kept.
3. **Interpretation**: for each linked set the model reads the test cases (keyword calls with arguments, `[check]` calls marked) against the aspects and names `full` or `partial` evidence. Large sets are read in batches of `max_test_cases_per_call`.
4. **Matrix** (code, not model): an aspect is `covered` by `full` evidence from a set whose specification status counts; `weak` if there is only `partial` evidence or the proving set is not released yet; `missing` otherwise.
5. **Gaps**: one more model call explains each weak or missing aspect and sketches a test that would close it.
6. **Write-back**: every linked set gets a block **AI Coverage &lt;requirement&gt;** on top of its review comment. A rerun replaces only this block; blocks of other requirements and of the reviewer agent stay. Each open aspect lists the reason for the gap and a sketch of the missing test. Sets locked by another user are skipped. Two runs for different requirements at the same time on the same set can lose one block; a rerun restores it. The full result is written to the service log.

Without an RM service the requirement description is unknown; the aspects then rest on the title alone and the blocks say so.

## Variables

| Variable | Values | Default |
| --- | --- | --- |
| `write_review_comments` | `true`, `false` — `false` writes only the log. Overrides the `write_review_comments` config argument when the client sends it | `true` |
| `coverage_view` | `release`: only sets in review or released count; `work`: unfinished sets count too | `release` |

## Configuration

```toml
[testbench-ai-service.agents.coverage_checker]
enabled = true
endpoint_path = "/coverage"
class_path = "testbench_ai_service.agents.coverage_checker.agent.CoverageChecker"

[testbench-ai-service.agents.coverage_checker.prompt]
file = "coverage_checker/prompt.yaml"

[testbench-ai-service.agents.coverage_checker.args]
# rm_service_url = "https://rm.example.com/api/"   # unset: aspects from the requirement title only
# rm_username = "rm-user"
# rm_password = "rm-password"
max_aspects = 12
counting_spec_status = ["InReview", "Released"]
work_spec_status = ["Planned", "InProgress", "InReview", "Released"]
write_review_comments = true
max_parallel_sets = 4
max_test_cases_per_call = 20
```

The prompt uses one variant with three **steps** (`aspects`, `interpretation`, `gaps`). The web console shows the steps read-only; edit their template files directly.
