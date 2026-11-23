# Prompts (`prompt.yaml`) and the TestBench plugin

An agent's `prompt.yaml` is two things at once:

1. **The prompt**: the messages sent to the LLM, per variant, as Jinja templates.
2. **The agent's user interface in TestBench**: the TestBench client's AI plugin reads it
   (through the service API) to show the agent's name and description, the variants to choose
   from, and a form field for every variable in `vars`. What the user enters there comes back
   in the trigger request.

Get the YAML right for both.

## How the plugin uses it

```
TestBench client                         AI Service
────────────────                         ──────────
right-click element → Export → AI plugin
  GET /agents?project_key=…  ─────────▶  name, summary, description per agent  (prompt.yaml top level)
  GET /agents/{key}/prompt?project_key=… ▶ default_variant, variants[]: name, description,
                                          model, vars{ key: {name, description, value_type,
                                          choices, default_value, required} }
  plugin dialog:
    agent name / description
    "Variant" selector (variant name + description; preselected: default_variant)
    "Prompt Variables": one input per var of the selected variant
      label = vars.<key>.name, help = description, input type from value_type,
      enum → choices, prefilled with default_value, required → must be filled to Start
  Start ─ POST <endpoint_path> ────────▶  { …context…, "language": …,
                                            "prompt_config": {"variant": "<chosen>",
                                                              "vars": {"<key>": "<value>"}} }
                                          → precheck → 202 / 409 shown in the dialog
```

- The endpoints resolve **project overrides and language** (`project_key`, `language` query
  parameters), so the plugin shows the prompt file that will actually run. A project can switch
  to another YAML or default variant without a code change.
- `summary` and `description` are also used as the OpenAPI summary/description of the agent's
  dedicated endpoint.
- Only the variant `name` travels back in the trigger. Renaming a variant breaks every
  `config.toml` / project override that references the old name (`Variant '…' not found`).
- Every language has its own YAML (`prompts/<lang>/<agent>/prompt.yaml`). Variant names,
  labels and descriptions are what the user sees, so translate them. Keep the variable **keys**
  identical across languages, because templates and configs use the keys.

## File layout

```
prompts/
├── prompt.schema.json                   JSON schema (first line of each YAML references it)
├── en/<agent_key>/prompt.yaml           definition + variants
├── en/<agent_key>/<variant>_system.jinja   message templates referenced by `file:`
├── en/<agent_key>/<variant>_user.jinja
└── de/<agent_key>/…                     same structure, German texts
```

Shipped defaults live in `testbench_ai_service/prompts/`. `testbench-ai-service init --prompts-dir <dir>`
copies them there (without `--prompts-dir` nothing is copied) (in this repo's dev config: `./prompts`). The service reads only
`prompts_dir`. Start each YAML with
`# yaml-language-server: $schema=../../prompt.schema.json` for editor validation.

## Structure (`models/prompt.py`, `prompts/prompt.schema.json`)

```yaml
# yaml-language-server: $schema=../../prompt.schema.json
name: "Test Case Set Reviewer"          # REQUIRED  agent name shown in the plugin
summary: "Review test case sets"        #           one-liner shown in the plugin / OpenAPI
description: >                          #           what the agent does and WHERE it writes the result
  Reviews the selected test case sets. The results are added to the review comment field.
default_model: "gpt-5.5"                # REQUIRED  model for variants without `model`
default_variant: "Full Review"          # REQUIRED  must match a variant name; preselected in the plugin
variants:                               # REQUIRED  at least one
  - name: "Full Review"                 # REQUIRED  shown in the variant selector; sent back as prompt_config.variant
    description: "Comprehensive review …"   #       help text for the variant
    model: "gpt-5.5"                    #           overrides default_model (also selects the LLM provider)
    vars:                               #           form fields for this variant (key → definition)
      glossary:                         # key: used as {{ vars.glossary }} and in prompt_config.vars
        name: "Glossary"                # REQUIRED  field label
        description: "Optional glossary …"  #       field help text
        value_type: "text"              # REQUIRED  string | text | boolean | number | enum
        required: false                 #           true = plugin requires a value before Start
        default_value: ""               #           prefill in the form (NOT applied by the service)
      depth:
        name: "Review depth"
        value_type: "enum"
        choices: ["short", "detailed"]  # REQUIRED for enum, forbidden otherwise
    messages:                           # REQUIRED  in order; each has `text` XOR `file`
      - role: "system"                  # system | user | assistant (default user)
        file: "full_review_system.jinja"   # relative to this YAML's directory
      - role: "user"
        text: |
          {{ agent.test_case_set }}
          {% if vars.glossary %}Glossary:
          {{ vars.glossary }}{% endif %}
```

Unknown keys are rejected by the schema (`additionalProperties: false`), but the schema is
only checked at **startup**, for the configured language's default prompt. At runtime
(`GET /agents`, trigger) the YAML is loaded with Pydantic only, which silently drops unknown
keys: a typo like `requried: true` in the other language's YAML just disappears. A YAML that
fails Pydantic validation breaks `GET /agents` and therefore the plugin's list for every agent
on that server. Validate **both** languages after every edit with
`validators.validate_prompt_file` (schema + model) or the YAML language server;
`get_prompt_definition(path)` does not check the schema.

The `value_type` enum lives in two places, `models/prompt.py` (`Literal`) and
`prompt.schema.json`. Change both together, otherwise a YAML passes one and fails the other.

### Two variable namespaces

|                    | `agent.*`                                                               | `vars.*`                                                   |
| ------------------ | ------------------------------------------------------------------------- | ------------------------------------------------------------ |
| Source             | the agent code (`AgentData` dict built in `run()`)                    | the user, via the plugin form (or `config.toml` / request) |
| Declared in        | `AGENT_DATA_CLASS` (TypedDict keys)                                     | `variants[].vars` in the YAML                              |
| Shown in plugin    | no                                                                        | yes, one field each                                          |
| Checked at trigger | every `agent.<key>` used must exist in `AGENT_DATA_CLASS` → else 422 | see "required" below                                         |
| Typical content    | test case set text, parameters, existing description                      | glossary, style options, switches                            |

`vars` values come from three places: `config.toml` (`agents.<key>.prompt.vars`), the project
override, then the trigger request. They are **not merged per key**: each level that sets
`vars` replaces the whole dict. Since the plugin always sends the form's `vars`, config presets
effectively only apply to triggers without `vars` (scripts, Swagger). Request `vars` must be
strings (`dict[str, str]`); a JSON `true` or `3` is rejected with 422.

### Value types

All `vars` values reach the template as **strings** (`PromptConfig.vars: dict[str, str]`),
whatever the `value_type`:

| `value_type` | Plugin input (intended) | In the template                                                                                                                    |
| -------------- | ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `string`     | single-line text        | `{{ vars.x }}`                                                                                                                   |
| `text`       | multi-line text         | `{{ vars.x }}`                                                                                                                   |
| `number`     | number field            | a string: `{{ vars.x \| int }}` / `\| float` before comparing                                                                    |
| `boolean`    | checkbox                | `"true"`/`"false"`: compare explicitly, `{% if vars.x == "true" %}`. A bare `{% if vars.x %}` is also true for `"false"` |
| `enum`       | dropdown of `choices` | one of the choices: `{% if vars.depth == "detailed" %}`                                                                          |

An unset var is undefined and renders as empty. Guard optional vars with `{% if vars.x %}`.
`default_value` is only the form prefill: the service does not apply it, so write templates
that work when the var is missing.

### `required`

`required: true` is how the plugin knows a field must be filled before **Start**. It is
essential for variables the prompt cannot work without (e.g. a target language or a mandatory
glossary). Mark exactly those, and keep optional inputs `required: false` with a template
guard.

On the service side, `routes.validate_template_and_agent_vars` checks that every required var
is used in the variant's templates. **Known bug (as of 2026-10):** its variable extractor
(`prompt_utils.template_variables` → `_build_ast_path`) collects only paths rooted at `agent`.
Because of that, a variant with any `required: true` var is rejected with
`422 Missing required variables`, even when the template uses the var (and the "unauthorized
vars" check never fires). Fix the extractor to also collect `vars.*` before shipping required
variables, and add a test that triggers a variant with a required var.

## Design rules for prompts

- One variant per user-visible mode ("Full Review", "Quick Review"). Each variant has its own
  `vars`, so repeat shared vars (same key) in every variant that uses them.
- `description` says what the agent changes in TestBench (which field, appended or replaced).
  The plugin shows it before the user starts the agent.
- Put long instructions in `*_system.jinja` files, and the item data (`agent.*`) in the user
  message.
- If the agent parses the answer (JSON, fixed lines), define the format in the system message
  and keep it identical in every language and variant.
- The model in `variants[].model` / `default_model` also selects the LLM provider
  (`gpt-*`/`o*` → OpenAI/Azure, `claude-*` → Anthropic; see `service-internals.md`).
- Inspect what the plugin will get:
  `GET /agents/{key}/prompt?project_key=<key>&language=de` (Swagger at `/docs`).
