---
sidebar_position: 5
title: Prompts
---

# Prompts

Prompts are the instructions sent to the LLM. The TestBench AI Service uses a structured YAML format with support for multiple prompt definitions, variants, and Jinja2 placeholder rendering.

---

## How prompts work

```
┌─────────────────────────────────────┐
│        Prompt YAML File             │
│  ┌────────────────────────────────┐ │
│  │  Prompt Definition (by name)   │ │
│  │  ┌──────────────────────────┐  │ │
│  │  │  Variant (by name)       │  │ │
│  │  │  - model: "gpt-4.1"      │  │ │
│  │  │  - blocks:               │  │ │
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
2. It finds the **prompt definition** matching `prompt.name`.
3. It selects the **variant** matching `prompt.variant` (or the `default_variant`).
4. Each block's `text` is rendered with Jinja2, substituting placeholders with data from `placeholder_data` and automatically built context.
5. Blocks with the same `role` are merged into a single message.
6. The resulting messages and the variant's `model` are sent to the LLM.

---

## File location

Prompt files are organized by language under the `prompts_dir` directory:

```
prompts/
├── en/
│   ├── test_case_set_reviewer.yaml
│   ├── test_case_set_describer.yaml
│   └── defect_explainer.yaml
└── de/
    ├── test_case_set_reviewer.yaml
    ├── test_case_set_describer.yaml
    └── defect_explainer.yaml
```

The service resolves prompt files relative to `prompts_dir/<language>/`. So a config of:

```toml
# config.toml
[testbench-ai-service]
language = "en"
prompts_dir = "prompts"

[testbench-ai-service.agents.test_case_set_reviewer.prompt]
file = "test_case_set_reviewer.yaml"
```

will load `prompts/en/test_case_set_reviewer.yaml`.

---

## YAML schema

Each prompt YAML file is a list of prompt definitions:

```yaml
- name: "TestCaseSetReviewer"
  description: "Reviews test case sets from TestBench."
  default_variant: "interaction-based-tests-detailed-prompt"
  variants:
    - name: "interaction-based-tests-detailed-prompt"
      model: "gpt-4.1"
      blocks:
        - role: "user"
          text: |
            You are a test analyst. Review the following test case:
            {{ test_case }}
            Parameter combinations:
            {{ parameter_combinations }}

    - name: "simple-generic-prompt"
      model: "gpt-4.1-mini"
      blocks:
        - role: "user"
          text: |
            Review this test case set briefly:
            {{ test_case }}
```

### Schema reference

| Field | Type | Description | Required | 
|-------|------|-------------|----------|
| `name` | String | Unique identifier for the prompt definition. | Yes |
| `description` | String | Human-readable description. | Yes |
| `default_variant` | String | Name of the default variant to use when none is specified. | Yes |
| `variants` | List | At least one variant is required. | Yes |

#### Variant fields

| Field | Type | Description | Required |
|-------|------|-------------|----------|
| `name` | String | Unique variant identifier. | Yes |
| `model` | String | LLM model to use (e.g., `"gpt-4.1"`, `"o3"`). | Yes |
| `blocks` | List | Ordered list of content blocks. | Yes |

#### Block fields

| Field | Type | Description | Default |
|-------|------|-------------|---------|
| `role` | String | Message role: `"system"`, `"user"`, or `"assistant"`. | `"user"` |
| `text` | String | The prompt text. Supports Jinja2 template syntax. | — |

A JSON Schema for validation is available at `prompts/prompt.schema.json`.

---

## Jinja2 placeholders

Block text supports [Jinja2](https://jinja.palletsprojects.com/) template syntax. Placeholders are rendered at runtime with data from two sources:

1. **Automatically built data**: the agent service populates placeholders like `test_case_set`, `parameter_combinations`, `description`, etc.
2. **`placeholder_data`**: custom key-value pairs from the config or the API request.

Values from `placeholder_data` take precedence over automatically built data.

**Example:**

Prompt block:

```yaml
- role: "user"
  text: |
    Review this test case:
    {{ test_case }}
    {% if glossary %}
    Use this glossary as reference:
    {{ glossary }}
    {% endif %}
```

Configuration:

```toml
# config.toml
[testbench-ai-service.agents.test_case_set_reviewer.prompt]
file = "test_case_set_reviewer.yaml"
name = "TestCaseSetReviewer"

[testbench-ai-service.agents.test_case_set_reviewer.prompt.placeholder_data]
glossary = "Domain: automotive\nABS = Anti-lock Braking System"
```

---

## Customizing prompts

### Using the `init` command

When you run `testbench-ai-service init`, the built-in prompt files are copied to a local `./prompts` directory. You can edit these files directly to customize prompts without modifying the package.

### Adding a new variant

Add a new entry to the `variants` list in the YAML file:

```yaml
- name: "TestCaseSetReviewer"
  description: "Reviews test case sets."
  default_variant: "detailed-prompt"
  variants:
    - name: "detailed-prompt"
      model: "gpt-4.1"
      blocks:
        - role: "user"
          text: |
            # Detailed review instructions...

    - name: "quick-review"
      model: "gpt-4.1-mini"
      blocks:
        - role: "user"
          text: |
            # Quick review instructions...
```

### Creating a new prompt file

1. Create a new YAML file in `prompts/<language>/` following the [schema](#yaml-schema).
2. Reference it in your config:

```toml
# config.toml
[testbench-ai-service.agents.test_case_set_reviewer.prompt]
file = "my_custom_reviews.yaml"
name = "MyCustomReviews"
```

---

## Inspecting prompts via API

The service exposes a read-only endpoint to inspect the configured prompt and its variants:

```
GET /agents/{agent_key}/prompt?project=<project_name>
```

This returns the prompt definition including all variants and their placeholders, useful for debugging and integration.
