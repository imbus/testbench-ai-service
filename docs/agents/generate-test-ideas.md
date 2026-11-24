---
sidebar_position: 5
title: Test Idea Generator
---

# Test Idea Generator

AI-generated test ideas for requirements. The agent is triggered on a test theme. It loads the requirements assigned below that theme and looks at the tests that already exist there. It then writes a structured set of test ideas into the theme's description: test cases, grouped into subthemes where that helps. From TestBench 5.0, every idea also becomes a test case set below the theme.

**Endpoint:** configurable. The examples on this page use `POST /requirement-test-ideas`.

:::info
This agent is **not registered by default**. You have to add it to `config.toml` yourself. See [Configuration](#configuration).
:::

## Authorization

The triggering user must hold at least one of the following **project roles**:

| Role             | Description                     |
| ---------------- | ------------------------------- |
| `TestManager`  | Full project management access. |
| `TestDesigner` | Test design access.             |

When authenticating with a **JWT token**, the token must also grant all of the following API token permissions:

| Permission                   | Description                                                    |
| ---------------------------- | -------------------------------------------------------------- |
| `ReadOwnUserDetails`       | Read the authenticated user's details.                         |
| `ReadProjectDetails`       | Read project metadata.                                         |
| `ReadTestThemeTree`        | Read the test theme tree.                                      |
| `ReadTovRequirements`      | Read the requirements assigned in the test object version.     |
| `ReadTestThemeDetails`     | Read the test theme's specification.                           |
| `ReadTestCaseSetDetails`   | Read test case set details.                                    |
| `ModifySpecifications`     | Modify specifications (required to write back the test ideas). |
| `ModifySpecManagementInfo` | Modify specification management info (locker, reviewer).       |

Triggered on a test cycle, the agent reads the cycle's requirements instead, which needs `ReadCycleRequirements`. That one is not checked up front: without it, TestBench's own `403` is returned.

To create the test case sets (TestBench 5.0 and later), the token also needs `ModifyTestStructureElements`. It is not checked up front either, because tokens of older TestBench versions cannot carry it. Without it, the ideas are only written into the theme's description and the job shows a warning.

---

## How it works

1. The request must contain a `tov_key` and a `root_uid`, and the `root_uid` must name a **test theme**. If a `cycle_key` is given, the requirements are loaded from that cycle instead of the TOV. The active TestBench UI `filtering` is applied too.
2. Before accepting the request, the service loads the test structure below the theme and checks it:
   - The theme has a specification to write into.
   - The theme is not locked by another user.
   - No other user is entered as **responsible** for the theme's specification. A theme without a responsible person, or with the triggering user as responsible, is processed.
   - At least one requirement is assigned below the theme, and no more than `max_requirements` (if set).
3. The theme is marked as in progress: its description is replaced by a *"generation started"* marker (the previous description is kept below it), and the triggering user is set as locker and reviewer.
4. The service collects the context for the prompt:
   - **Requirement details.** If an `rm_service_url` is configured, each requirement's description, status, priority, owner and documents are fetched from the RM service. Every baseline of the requirement's repository in the TOV is tried, and the first one that knows the requirement wins. TestBench lists a TOV's baselines only on its legacy API, which a JWT cannot use, so with a JWT (or if that lookup fails) the service searches the RM service's own baselines instead: those of the projects in `rm_projects`, in that order, or of every RM project if it is unset. Within a project the `CURRENT` baseline is tried first. The match is on the requirement's ID and version, so a baseline other than the one the TOV references may answer. If the RM service is not configured, cannot be reached, or does not know a requirement, that requirement falls back to its TOV data (without a description). This never makes the run fail.
   - **Existing tests.** The theme's own attributes (path, priority, tags, user-defined fields, description, review comment), the subthemes below it, and every test case set below it with a short description and the requirements it is linked to.
5. All requirements of the theme go into **one** prompt, so the model treats them as a unit. The model answers with JSON, which is validated against a schema. If it is invalid, the model is asked once more to repair it.
6. The answer is normalised deterministically (see [Guardrails](#guardrails)).
7. **TestBench 5.0 and later** (unless `create_test_case_sets = false`): one test case set is created per idea, directly below the triggered theme, in the order of the ideas. See [Test case sets](#test-case-sets).
8. The ideas are rendered as plain text and written into the theme's description below the previous description. If test case sets were created in step 7, nothing is added to the theme: its description is set back to exactly what it was before the run. The theme's lock is restored: a theme the triggering user had locked stays locked for them, any other theme is unlocked.
9. If anything fails after step 3, the test case sets created so far are deleted again, the previous description is restored with a *"generation failed"* notice and the theme's lock is restored as in step 8.

:::note
If a check from step 1 or 2 fails, the endpoint answers `409 Conflict` and the reason is shown to the user; nothing is written to TestBench. Otherwise it answers `202 Accepted` and the rest runs in the background.
:::

### Guardrails

Whatever the model returns, the service enforces these rules before writing:

- `covered_requirements` keeps only the theme's own requirements, without duplicates.
- Ideas without a title, and ideas that repeat an earlier title, are dropped.
- Subthemes with the same name are merged. At most `max_ideas_per_theme` ideas are kept (if set).
- A subtheme with fewer than two ideas is dissolved, and its ideas move directly under the theme.
- A subtheme name that already exists below the theme gets a numeric suffix, e.g. `Discount thresholds (2)`.
- Subthemes are one level deep. Ideas directly under the theme come last.

### Output

If no test case sets were created (before TestBench 5.0, `create_test_case_sets = false`, or creation not permitted), the test ideas are appended to the theme's description as a block headed **AI Test Ideas - &lt;timestamp&gt;**, followed by an AI disclaimer. For example:

```text
Test ideas for:
REQ-12: Discount for large orders

1 Test theme: Discount thresholds

   1.1 Test case: No discount below the minimum order value
      Check that an order just below the minimum order value gets no discount ...
      Covers: REQ-12

   1.2 Test case: Discount applies exactly at the threshold
      ...

2 Test case: Discount is shown on the invoice
   ...
```

### Test case sets

From TestBench 5.0, the service also creates a test case set for every idea via `POST /api/2/projects/{projectKey}/tovs/{tovKey}/testCaseSets`:

- **Flat below the triggered theme.** TestBench's API cannot create test themes, so the subthemes the model proposes are not created. Because the theme's description then stays as it was, the proposed grouping is not kept.
- **Name:** the idea's title. Characters TestBench does not allow in names (`/ . , ' < ; > &`) are replaced by spaces, and the name is cut to 255 characters. If a sibling already has the name, TestBench adds a numeric suffix.
- **Description:** the idea's description and the requirements it covers, headed **AI Test Idea - &lt;timestamp&gt;**, with the AI disclaimer (template `test_case_set.jinja`). The requirements are only named in the text: the API cannot link requirements to a test case set.
- **All or nothing:** if creating a set or writing the theme's description fails, the sets created in this run are deleted again (`DELETE /api/2/projects/{projectKey}/testCaseSets/{testCaseSetKey}`). A set that cannot be deleted is logged and left in place.
- If TestBench answers the first creation with `403` (e.g. a token without `ModifyTestStructureElements`), no set is created, the ideas are written into the theme as text instead, and the job shows a warning.

On TestBench versions before 5.0, nothing changes: the ideas are only written into the theme's description.

When the agent runs again on the same theme, earlier test idea blocks are removed from the description before it goes into the prompt. This stops the model from reading its own earlier output as existing coverage.

---

## Configuration

### Registering the agent

```toml
# config.toml
[testbench-ai-service.agents.requirement]
enabled = true
endpoint_path = "/requirement-test-ideas"
class_path = "testbench_ai_service.agents.generate_test_ideas.agent.RequirementAgent"

[testbench-ai-service.agents.requirement.prompt]
file = "generate_test_ideas/prompt.yaml"

[testbench-ai-service.agents.requirement.args]
max_requirements = 20
max_ideas_per_theme = 30
# create_test_case_sets = false
# rm_service_url = "https://rm.example.com/api/"
# rm_username = "rm-user"
# rm_password = "rm-password"
# rm_projects = ["Dream Car", "Dream Car Legacy"]
```

The write-back templates (`started.jinja`, `template.jinja`, `failed.jinja`, `test_case_set.jinja`) are read from `templates/<language>/requirement/`, whatever agent key you choose.

### Agent arguments

The agent accepts the following options in its `args` table. They are validated when the service starts.

| Option                  | Type    | Default  | Description                                                                                                  |
| ----------------------- | ------- | -------- | ------------------------------------------------------------------------------------------------------------ |
| `max_requirements`    | Integer | no limit | Skip themes with more requirements than this. Must be greater than 0.                                        |
| `max_ideas_per_theme` | Integer | no limit | Keep at most this many test ideas per theme. Must be greater than 0.                                         |
| `create_test_case_sets` | Boolean | `true` | From TestBench 5.0, also create a test case set below the theme for every idea. Ignored before 5.0. |
| `rm_service_url`      | String  | unset    | Base URL of the RM service to fetch requirement details from. If unset, only the TOV requirement data is used. |
| `rm_username`         | String  | unset    | User name for HTTP basic auth against the RM service. Required if `rm_service_url` is set.                   |
| `rm_password`         | String  | unset    | Password for HTTP basic auth against the RM service. Required if `rm_service_url` is set.                    |
| `rm_projects`         | List of strings | all projects | RM projects searched, in this order, when TestBench cannot name the TOV's baselines (e.g. with a JWT). Must not be empty. Unset means every project the RM service lists. |

For every requirement, the RM service is called with `POST {rm_service_url}projects/{project}/baselines/{baseline}/extended-requirement`. The request body is `{"id": ..., "version": ...}`. When the RM service's baselines are searched, they are listed once per run with `GET {rm_service_url}projects` (skipped if `rm_projects` is set) and `GET {rm_service_url}projects/{project}/baselines`.

### Agent data

The following variables are generated by the agent and are accessible in prompt templates as `{{ agent.<key> }}`:

| Variable                 | Type            | Description                                                                                                                                                                                      |
| ------------------------ | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `agent.requirements`   | List of strings | One rendered block per requirement: identifier and title, attributes (version, status, priority, owner), full description, and the test case sets below the theme that are already linked to it. |
| `agent.existing_tests` | String          | The target theme: name, path, priority, tags, user-defined fields, current description (without earlier test ideas), review comment, and the subthemes and test case sets already below it.     |

### Project-specific override

The `args` of a project are merged over the global ones, key by key:

```toml
# config.toml
[testbench-ai-service.projects."My Project".agents.requirement.args]
max_ideas_per_theme = 10
rm_service_url = "https://rm-other.example.com/api/"
rm_username = "other-user"
rm_password = "other-password"
```

## Prompt variants

The built-in prompt file (`generate_test_ideas/prompt.yaml`) ships with the following variant:

| Variant                  | Model       | Description                                                                                                                                                                                     |
| ------------------------ | ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Test Ideas` (default) | `gpt-5.5` | Derives test ideas from the requirements and the existing tests, structured like a TestBench test structure. Test cases are grouped under subthemes where they share a functional aspect. Uses a system+user message structure and asks for a JSON answer. |

If you write your own variant, it must still answer with JSON in the `{"groups": [{"theme_name": ..., "ideas": [{"title", "description", "covered_requirements"}]}]}` format. See [Prompts](../prompts.md) for details on how to customize or create your own variants.
