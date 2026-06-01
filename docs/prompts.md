---
sidebar_position: 6
title: Prompts
---
# Prompts

Prompts are the instructions sent to the LLM. The TestBench AI Service uses a structured YAML format with support for multiple prompt definitions, variants, and Jinja2 variable rendering.

---

## How prompts work

```
┌─────────────────────────────────────┐
│           Prompt YAML File          │
│  ┌────────────────────────────────┐ │
│  │        Prompt Definition       │ │
│  │  ┌──────────────────────────┐  │ │
│  │  │  Variant (by name)       │  │ │
│  │  │  - model: "gpt-4.1"      │  │ │
│  │  │  - messages:             │  │ │
│  │  │    - role: "user"        │  │ │
│  │  │      text: "..."         │  │ │
│  │  └──────────────────────────┘  │ │
│  │  ┌──────────────────────────┐  │ │
│  │  │  Another Variant         │  │ │
│  │  │  ...                     │  │ │
│  │  └──────────────────────────┘  │ │
│  └────────────────────────────────┘ │
└─────────────────────────────────────┘
```

1. The service loads the YAML file specified in the agent's `prompt.file` config.
2. It selects the **variant** matching `prompt.variant` (or the `default_variant` from the YAML).
3. Each message is rendered with Jinja2. Content is either an inline `text` string or loaded from an external `file`. Template variables are resolved from two namespaces: `{{ agent.<key> }}` for agent-generated data and `{{ vars.<key> }}` for user-provided values.
4. The resulting messages and the variant's `model` (or the definition's `default_model`) are sent to the LLM.

---

## File location

Prompt files are organized by language under the `prompts_dir` directory:

```
prompts/
├── en/
│   ├── test_case_set_reviewer/
│   │   ├── prompt.yaml
│   │   └── *.jinja           # external template files referenced by prompt.yaml
│   ├── test_case_set_describer/
│   │   ├── prompt.yaml
│   │   └── *.jinja
│   └── defect_explainer/
│       ├── prompt.yaml
│       └── *.jinja
└── de/
    ├── test_case_set_reviewer/
    ├── test_case_set_describer/
    └── defect_explainer/
```

The service resolves prompt files relative to `prompts_dir/<language>/`. So a config of:

```toml
# config.toml
[testbench-ai-service]
language = "en"
prompts_dir = "prompts"

[testbench-ai-service.agents.test_case_set_reviewer.prompt]
file = "test_case_set_reviewer/prompt.yaml"
```

will load `prompts/en/test_case_set_reviewer/prompt.yaml`.

---

## YAML schema

Each prompt YAML file contains a single prompt definition:

```yaml
name: "TestCaseSetReviewer"
summary: "Review test case sets"
description: "Analyzes test case sets against best practices and writes results to the review comment field."  # optional
default_model: "gpt-5.5"          # fallback model for variants that don't specify one
default_variant: "Full Review"
variants:
  - name: "Full Review"
    model: "gpt-5.5"               # optional — overrides default_model for this variant
    vars:
      glossary:                    # declare a user-provided variable
        name: "Glossary"
        description: "Optional glossary of project-specific terms."
        value_type: "text"
        required: false
    messages:
      - role: "system"
        text: |                   # inline Jinja2 template
          You are a test analyst.
      - role: "user"
        file: "review_user.jinja" # OR reference an external template file

  - name: "Quick Review"
    model: "gpt-5.5-mini"
    messages:
      - role: "user"
        text: |
          Review this test case:
          {{ agent.test_case_set }}
          {% if vars.glossary %}
          Use this glossary:
          {{ vars.glossary }}
          {% endif %}
```

:::note
Each message must have **either** `text` (inline template) **or** `file` (path to an external template file such as `.jinja`, `.j2`, or `.md`) — not both. External `file` paths are resolved relative to the directory of the prompt YAML file.
:::

### Schema reference

#### Prompt definition fields

| Field  | Type  | Description | Required |
| ------ | ----- | ----------- | -------- |
| `name` | String | Identifier for the prompt definition. Shown as the **agent name** in TestBench and the OpenAPI UI. | Yes |
| `summary` | String | Short label for the agent. Shown as the **agent summary** in TestBench and the OpenAPI UI. | No |
| `description` | String | Longer description of the agent. Shown as the **agent description** in TestBench and the OpenAPI UI. | No |
| `default_model` | String | Fallback LLM model for variants that don't declare their own. | Yes      |
| `default_variant` | String | Name of the default variant to use when none is specified.    | Yes      |
| `variants`        | List[Variant]   | At least one variant is required.                             | Yes      |

#### Variant fields

| Field           | Type   | Description                                                                                          | Required |
| --------------- | ------ | ---------------------------------------------------------------------------------------------------- | -------- |
| `name`        | String | Unique variant identifier.                                                                           | Yes      |
| `description` | String | Human-readable description.                                                                          | No       |
| `model`       | String | LLM model to use (e.g.,`"gpt-5.5"`, `"o3"`). Falls back to `default_model` if not set.         | No       |
| `vars`        | Object | Declared user-provided variables for this variant (see [Variable declarations](#variable-declarations)). | No       |
| `messages`    | List[Message]   | Ordered list of message blocks.                                                                      | Yes      |

#### Message fields

Exactly one of `text` or `file` must be provided per message.

| Field    | Type   | Description                                                                                                                                  | Default    |
| -------- | ------ | -------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| `role` | String | Message role: `"system"`, `"user"`, or `"assistant"`.                                                                                   | `"user"` |
| `text` | String | Inline Jinja2 template string.                                                                                                               | —         |
| `file` | String | Path to an external template file (`.jinja`, `.j2`, or `.md`). Relative paths are resolved from the directory of the prompt YAML file. | —         |

#### Variable declarations

The `vars` object on a variant declares the user-provided variables that the prompt expects. These are shown in the API and used for validation. Each key maps to a variable definition:

| Field             | Type    | Description                                                               | Required               |
| ----------------- | ------- | ------------------------------------------------------------------------- | ---------------------- |
| `name`          | String  | Human-readable label.                                                     | Yes                    |
| `description`   | String  | Explains the purpose of the variable.                                     | No                     |
| `value_type`    | String  | One of `"string"`, `"text"`, `"boolean"`, `"number"`, `"enum"`. | Yes                    |
| `choices`       | List    | Allowed values (required when `value_type` is `"enum"`).              | Conditional            |
| `default_value` | Any     | Default value if the variable is not supplied.                            | No                     |
| `required`      | Boolean | Whether the variable must be provided.                                    | No (default `false`) |

A JSON Schema for validation is available at `prompts/prompt.schema.json`.

---

## Jinja2 variables

Message templates (both inline `text` and external `file`) support [Jinja2](https://jinja.palletsprojects.com/) template syntax. Two separate variable namespaces are available at render time:

| Namespace       | Source                                                                    | Example                   |
| --------------- | ------------------------------------------------------------------------- | ------------------------- |
| `agent.<key>` | Data generated by the agent (e.g. test case data fetched from TestBench). | `{{ agent.test_case_set }}` |
| `vars.<key>`  | User-provided values from the prompt config or API request.               | `{{ vars.glossary }}`   |

See each agent's documentation for the full list of available `agent.*` variables. User-provided variables are declared in the variant's `vars` section.

**Example:**

Prompt message (inline `text`):

```yaml
- role: "user"
  text: |
    Review this test case:
    {{ agent.test_case_set }}
    {% if vars.glossary %}
    Use this glossary as reference:
    {{ vars.glossary }}
    {% endif %}
```

Or using an external template `file` (content of `review_user.jinja`):

```jinja
Review this test case:
{{ agent.test_case_set }}
{% if vars.glossary %}
Use this glossary as reference:
{{ vars.glossary }}
{% endif %}
```

Configuration (supplying user-provided variables):

```toml
# config.toml
[testbench-ai-service.agents.test_case_set_reviewer.prompt]
file = "test_case_set_reviewer/prompt.yaml"

[testbench-ai-service.agents.test_case_set_reviewer.prompt.vars]
glossary = "Domain: automotive\nABS = Anti-lock Braking System"
```

:::tip
Variables can also be supplied per-request via the `prompt_config.vars` field in the API body, which overrides config-level values.
:::

---

## Customizing prompts

### Using the `init` command

When you run `testbench-ai-service init`, the built-in prompt files are copied to a local `./prompts` directory. You can edit these files directly to customize prompts without modifying the package.

### Adding a new variant

Add a new entry to the `variants` list in the YAML file:

```yaml
name: "TestCaseSetReviewer"
summary: "Review test case sets"
default_model: "gpt-5.5"
default_variant: "Full Review"
variants:
  - name: "Full Review"
    model: "gpt-5.5"
    messages:
      - role: "system"
        text: |
          You are a test analyst.
      - role: "user"
        file: "full_review_user.jinja"  # external template file

  - name: "Quick Review"
    model: "gpt-5.5-mini"
    messages:
      - role: "user"
        text: |
          Review this test case: {{ agent.test_case_set }}
```

### Creating a new prompt file

1. Create a new YAML file in `prompts/<language>/` following the [schema](#yaml-schema).
2. Reference it in your config:

```toml
# config.toml
[testbench-ai-service.agents.test_case_set_reviewer.prompt]
file = "my_custom_reviews.yaml"
```

---

## Inspecting prompts via API

The service exposes a read-only endpoint to inspect the configured prompt and its variants:

```
GET /agents/{agent_key}/prompt?project_key=<project_key>
```

This returns the prompt definition including all variants and their variables, useful for debugging and integration.
