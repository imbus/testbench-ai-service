---
sidebar_position: 5
title: Prompts
---

# Prompts

Prompts are the instructions sent to the LLM. The TestBench AI Service uses a structured YAML format with support for multiple prompt definitions, variants, and Jinja2 placeholder rendering.

---

## How Prompts Work

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

1. The service loads the YAML file specified in the use case's `prompt.file` config.
2. It finds the **prompt definition** matching `prompt.name`.
3. It selects the **variant** matching `prompt.variant` (or the `default_variant`).
4. Each block's `text` is rendered with Jinja2, substituting placeholders with data from `placeholder_data` and automatically built context.
5. Blocks with the same `role` are merged into a single message.
6. The resulting messages and the variant's `model` are sent to the LLM.

---

## File Location

Prompt files are organized by language under the `prompts_dir` directory:

```
prompts/
├── en/
│   ├── test_case_set_reviews.yaml
│   ├── test_case_set_descriptions.yaml
│   └── defect_explanations.yaml
└── de/
    ├── test_case_set_reviews.yaml
    ├── test_case_set_descriptions.yaml
    └── defect_explanations.yaml
```

The service resolves prompt files relative to `prompts_dir/<language>/`. So a config of:

```toml
[testbench-ai-service]
language = "en"
prompts_dir = "prompts"

[testbench-ai-service.usecases.test_case_set_reviews.prompt]
file = "test_case_set_reviews.yaml"
```

will load `prompts/en/test_case_set_reviews.yaml`.

---

## YAML Schema

Each prompt YAML file is a list of prompt definitions:

```yaml
- name: "TestCaseSetReviews"
  description: "Reviews test case sets from TestBench."
  default_variant: "interaction-based-tests-detailed-prompt"
  variants:
    - name: "interaction-based-tests-detailed-prompt"
      model: "gpt-4.1"
      blocks:
        - role: "user"
          text: |
            You are a test analyst. Review the following test case:
            {{ test_case_set }}

        - role: "user"
          text: |
            Parameter combinations:
            {{ parameter_combinations }}

    - name: "simple-generic-prompt"
      model: "gpt-4.1-mini"
      blocks:
        - role: "user"
          text: |
            Review this test case set briefly:
            {{ test_case_set }}
```

### Schema Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | String | Yes | Unique identifier for the prompt definition |
| `description` | String | Yes | Human-readable description |
| `default_variant` | String | Yes | Name of the default variant to use when none is specified |
| `variants` | List | Yes | At least one variant is required |

#### Variant Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | String | Yes | Unique variant identifier |
| `model` | String | Yes | LLM model to use (e.g., `"gpt-4.1"`, `"o3"`) |
| `blocks` | List | Yes | Ordered list of content blocks |

#### Block Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `role` | String | `"user"` | Message role: `"system"`, `"user"`, or `"assistant"` |
| `text` | String | — | The prompt text. Supports Jinja2 template syntax. |

A JSON Schema for validation is available at `prompts/prompt.schema.json`.

---

## Jinja2 Placeholders

Block text supports [Jinja2](https://jinja.palletsprojects.com/) template syntax. Placeholders are rendered at runtime with data from two sources:

1. **Automatically built data** — the use case service populates placeholders like `test_case_set`, `parameter_combinations`, `description`, etc.
2. **`placeholder_data`** — custom key-value pairs from the config or the API request.

Values from `placeholder_data` take precedence over automatically built data.

### Example

Prompt block:

```yaml
- role: "user"
  text: |
    Review this test case:
    {{ test_case_set }}

    {% if glossary %}
    Use this glossary as reference:
    {{ glossary }}
    {% endif %}
```

Config:

```toml
[testbench-ai-service.usecases.test_case_set_reviews.prompt]
file = "test_case_set_reviews.yaml"
name = "TestCaseSetReviews"

[testbench-ai-service.usecases.test_case_set_reviews.prompt.placeholder_data]
glossary = "Domain: automotive\nABS = Anti-lock Braking System"
```

---

## Customizing Prompts

### Using the `init` Command

When you run `testbench-ai-service init`, the built-in prompt files are copied to a local `./prompts` directory. You can edit these files directly to customize prompts without modifying the package.

### Adding a New Variant

Add a new entry to the `variants` list in the YAML file:

```yaml
- name: "TestCaseSetReviews"
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

Then reference the variant in your config:

```toml
[testbench-ai-service.usecases.test_case_set_reviews.prompt]
variant = "quick-review"
```

### Creating a New Prompt File

1. Create a new YAML file in `prompts/<language>/` following the schema above.
2. Reference it in your config:

```toml
[testbench-ai-service.usecases.test_case_set_reviews.prompt]
file = "my_custom_reviews.yaml"
name = "MyCustomReviews"
```

---

## Inspecting Prompts via API

The service exposes a read-only endpoint to inspect the configured prompt and its variants:

```
GET /usecases/{usecase_key}/prompt?project=<project_name>
```

This returns the prompt definition including all variants and their placeholders, useful for debugging and integration.
