---
sidebar_position: 4.7
title: Link Finder
---
# Link Finder

Finds test case sets that test a requirement but are **not linked** to it. Tests are often written before or beside the requirements, moved, or written from other themes; the link is then missing although the test exists. The link finder reads every unlinked set of the test object version against the requirement and suggests candidates, ranked by confidence, with the evidence from their test steps. It is the counterpart of the [Coverage Checker](coverage-checker.md), which checks the sets that are already linked.

**Endpoint:** `POST /link-candidates` (configurable, see [Configuration](#configuration))

:::warning
The agent is **opt-in**: it is not part of the default agents and only runs when it is added to the `config.toml`. TestBench must offer the plugin on **requirements**. It requires a **JSON-based** test object version (TOV). Links are never set: every candidate is a hint for a person to decide on.
:::

## Authorization

The triggering user must hold the **project role** `TestManager` or `TestDesigner`.

For JWT tokens the following API token permissions are required: `ReadOwnUserDetails`, `ReadProjectDetails`, `ReadTovRequirements`, `ReadTovReport`, `ReadReportingJobDetails`, `DownloadReportFile`, `ReadTestThemeTree`, `ReadTestCaseSetDetails`, `ModifySpecifications`.

## How it works

1. **Precheck** (answers `409` with a reason otherwise): the trigger names a requirement of a TOV, the TOV is JSON-based, and at least one test case set is not linked to the requirement, neither as a whole nor through one of its test cases. A requirement without any links is the main use case. TestBench only lists the requirements of a TOV that are assigned to a test, so a requirement without any links is looked up in the RM service instead: by the ID from the trigger, in the TOV's baselines (or, with a JWT, in the baselines of `rm_projects`), in its latest version. Without an RM service, or if it does not know the requirement, the precheck refuses.
2. **Aspects**: the model splits the requirement into testable aspects, exactly as in the coverage checker (each aspect must quote the requirement text; at most `max_aspects`).
3. **Prefilter** (recall): the model screens all unlinked sets in batches of `prefilter_batch_size` (one model call per batch, so this is where a large TOV costs tokens; a requirement with more unlinked sets than `max_sets_searched` is refused, and the precheck tells the user how many sets are searched), seeing only key, path, title and the start of the description. It is told to include a set when in doubt. At most `max_candidates` sets pass, the most relevant first.
4. **Interpretation** (precision): for each candidate the model reads all test cases (keyword calls with arguments, `[check]` calls marked) against the aspects and names `full` or `partial` evidence, as in the coverage checker.
5. **Confidence** (code, not model):

   | Confidence | Rule |
   | --- | --- |
   | `high` | at least one `full` evidence, and the set touches at least `high_confidence_ratio` of the aspects |
   | `medium` | at least one `full` evidence, fewer aspects |
   | `low` | only `partial` evidence |
   | dropped | no evidence |

   Without a requirement description every level drops by one and `low` candidates are dropped. Without an RM service the precheck says so; if a configured RM service delivers no description (not reachable, the requirement unknown there, or its description empty), the job gets a warning. The requirement description is looked up as in the [Coverage Checker](coverage-checker.md), including the search of `rm_projects` when the trigger uses a JWT.
6. **Write-back**: every candidate from `min_confidence_for_comment` up gets a block **AI Link Candidate &lt;requirement&gt;** on top of its review comment: confidence, the strongest evidence, the aspects it touches, for `medium` the aspects it does not prove, and the other requirements the set is already linked to (often a hint at overlapping requirements). A rerun replaces the block, and removes it from sets that are no longer candidates, for example because they have been linked in the meantime. Blocks of other requirements, of the coverage checker and of the reviewer agent stay. Sets locked by another user are skipped. By default every candidate gets a block, `low` ones included; raise `min_confidence_for_comment` to comment only the likelier ones. The full result is stored as the job's [report](#report) and written to the service log.

The JSON report of the TOV already holds every set's test steps, so the two stages save model tokens, not TestBench calls.

## Report

The trigger's `202` response carries a `job_id`. [`GET /jobs/{job_id}`](index.md#jobs) shows the progress (aspects, prefilter, candidates, review comments) and, when the run ends, the full result as `report` with `report_type` `link_finder`. A run that finds no candidate still has a report, with an empty `candidates` list. The report is the `LinkFinderResult` as JSON:

| Field               | Description                                                                                                    |
| ------------------- | -------------------------------------------------------------------------------------------------------------- |
| `requirement_key`   | The requirement searched for.                                                                                  |
| `aspects`           | Aspect ID to its statement.                                                                                    |
| `candidates`        | Ranked: `set_key`, `set_unique_id`, `set_title`, `path`, `spec_status`, `confidence`, `covered_aspect_ids`, `evidence`, `already_linked_to`. |
| `sets_screened`     | Unlinked sets the prefilter looked at.                                                                         |
| `sets_detailed`     | Sets whose test steps were read.                                                                               |
| `empty_sets`        | Candidates without test cases, which prove nothing.                                                            |
| `failed_sets`       | Candidates whose interpretation failed.                                                                        |
| `skipped_comments`  | Candidates whose review comment was not written (locked by someone else, or the write failed).                 |
| `reduced_mode`      | The requirement description was unknown; the aspects rest on the title alone.                                  |
| `incomplete`        | A prefilter batch or a candidate could not be evaluated.                                                       |
| `set_paths`         | Set key to its path in the test structure, for the sets read in detail.                                        |

:::note
The `link_finder` report type is not yet agreed on with the TestBench plugin; the web console shows it.
:::

## Variables

| Variable | Values | Default |
| --- | --- | --- |
| `write_review_comments` | `true`, `false` — `false` writes only the log. Overrides the config argument when the client sends it | `true` |
| `min_confidence_for_comment` | `high`, `medium`, `low` — candidates below only appear in the log. Overrides the config argument when the client sends it | `low` |

## Configuration

```toml
[testbench-ai-service.agents.link_finder]
enabled = true
endpoint_path = "/link-candidates"
class_path = "testbench_ai_service.agents.link_finder.agent.LinkFinder"

[testbench-ai-service.agents.link_finder.prompt]
file = "link_finder/prompt.yaml"

[testbench-ai-service.agents.link_finder.args]
# rm_service_url = "https://rm.example.com/api/"   # unset: aspects from the requirement title only
# rm_username = "rm-user"
# rm_password = "rm-password"
# rm_projects = ["Dream Car"]                   # searched with a JWT; unset: every RM project
max_aspects = 12
max_sets_searched = 1000
prefilter_batch_size = 40
max_candidates = 15
high_confidence_ratio = 0.5
min_confidence_for_comment = "low"
write_review_comments = true
max_parallel_sets = 4
max_test_cases_per_call = 20
```

The prompt uses one variant with three **steps** (`aspects`, `prefilter`, `interpretation`). The `aspects` and `interpretation` templates ship as copies of the coverage checker's, so both agents read requirements and tests the same way; an installation may change them separately. The web console shows the steps read-only; edit their template files directly.

The prefilter's recall decides the agent's quality: a set it drops is never read. Before relying on the agent, take a few requirements whose correct links are known, unlink them in a copy of the TOV, run the agent and check which of the known sets the log lists; tune `prefilter_batch_size` and `max_candidates` accordingly.
