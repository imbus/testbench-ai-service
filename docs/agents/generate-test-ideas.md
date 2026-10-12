---
sidebar_position: 5
title: Test Idea Generator
---

# Test Idea Generator

AI-generated test ideas for requirements. The agent is triggered on a test theme. It loads the requirements assigned below that theme and looks at the tests that already exist there. It then writes a structured set of test ideas into the theme's description: test cases, grouped into subthemes where that helps.

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
| `ReadTestCaseSetDetails`   | Read test case set details.                                    |
| `ModifySpecifications`     | Modify specifications (required to write back the test ideas). |
| `ModifySpecManagementInfo` | Modify specification management info (locker, reviewer).       |

---

## How it works

1. The request must contain a `tov_key` and a `root_uid`, and the `root_uid` must name a **test theme**. If a `cycle_key` is given, the requirements are loaded from that cycle instead of the TOV. The active TestBench UI `filtering` is applied too.
2. The service loads the test structure below the theme and checks it:
   - The theme has a specification to write into.
   - The theme is not locked by another user.
   - At least one requirement is assigned below the theme, and no more than `max_requirements` (if set).
3. The theme is marked as in progress: its description is replaced by a *"generation started"* marker (the previous description is kept below it), and the triggering user is set as locker and reviewer.
4. The service collects the context for the prompt:
   - **Requirement details.** If an `rm_service_url` is configured, each requirement's description, status, priority, owner and documents are fetched from the RM service. Every baseline of the requirement's repository in the TOV is tried, and the first one that knows the requirement wins. If the RM service is not configured, cannot be reached, or does not know a requirement, that requirement falls back to its TOV data (without a description). This never makes the run fail.
   - **Existing tests.** The theme's own attributes (path, priority, tags, user-defined fields, description, review comment), the subthemes below it, and every test case set below it with a short description and the requirements it is linked to.
5. All requirements of the theme go into **one** prompt, so the model treats them as a unit. The model answers with JSON, which is validated against a schema. If it is invalid, the model is asked once more to repair it.
6. The answer is normalised deterministically (see [Guardrails](#guardrails)), rendered as plain text, and written into the theme's description below the previous description. The theme is unlocked.
7. If anything fails after step 3, the previous description is restored with a *"generation failed"* notice and the theme is unlocked.

:::note
The precheck of this agent currently accepts every request, so the endpoint always answers `202 Accepted`. All checks from step 1 and 2 happen in the background. If one fails, nothing is written to TestBench and the reason is only logged. Check the service log if no test ideas appear.
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

The test ideas are appended to the theme's description as a block headed **AI Test Ideas - &lt;timestamp&gt;**, followed by an AI disclaimer. For example:

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

When the agent runs again on the same theme, earlier test idea blocks are removed from the description before it goes into the prompt. This stops the model from reading its own earlier output as existing coverage.

---

## Configuration

### Registering the agent

```toml
# config.toml
[testbench-ai-service.agents.requirement]
enabled = true
endpoint_path = "/requirement-test-ideas"
class_path = "testbench_ai_service.agents.generate_test_idears.agent.RequirementAgent"

[testbench-ai-service.agents.requirement.prompt]
file = "generate_test_idears/prompt.yaml"

[testbench-ai-service.agents.requirement.args]
max_requirements = 20
max_ideas_per_theme = 30
# rm_service_url = "https://rm.example.com/api/"
# rm_username = "rm-user"
# rm_password = "rm-password"
```

The write-back templates (`started.jinja`, `template.jinja`, `failed.jinja`) are read from `templates/<language>/requirement/`, whatever agent key you choose.

### Agent arguments

The agent accepts the following options in its `args` table. They are validated when the service starts.

| Option                  | Type    | Default  | Description                                                                                                  |
| ----------------------- | ------- | -------- | ------------------------------------------------------------------------------------------------------------ |
| `max_requirements`    | Integer | no limit | Skip themes with more requirements than this. Must be greater than 0.                                        |
| `max_ideas_per_theme` | Integer | no limit | Keep at most this many test ideas per theme. Must be greater than 0.                                         |
| `rm_service_url`      | String  | unset    | Base URL of the RM service to fetch requirement details from. If unset, only the TOV requirement data is used. |
| `rm_username`         | String  | unset    | User name for HTTP basic auth against the RM service. Required if `rm_service_url` is set.                   |
| `rm_password`         | String  | unset    | Password for HTTP basic auth against the RM service. Required if `rm_service_url` is set.                    |

For every requirement, the RM service is called with `POST {rm_service_url}projects/{project}/baselines/{baseline}/extended-requirement`. The request body is `{"id": ..., "version": ...}`.

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

The built-in prompt file (`generate_test_idears/prompt.yaml`) ships with the following variant:

| Variant                  | Model       | Description                                                                                                                                                                                     |
| ------------------------ | ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Test Ideas` (default) | `gpt-5.5` | Derives test ideas from the requirements and the existing tests, structured like a TestBench test structure. Test cases are grouped under subthemes where they share a functional aspect. Uses a system+user message structure and asks for a JSON answer. |

If you write your own variant, it must still answer with JSON in the `{"groups": [{"theme_name": ..., "ideas": [{"title", "description", "covered_requirements"}]}]}` format. See [Prompts](../prompts.md) for details on how to customize or create your own variants.
