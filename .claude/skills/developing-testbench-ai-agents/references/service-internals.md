# Service internals an agent depends on

What the framework does around `precheck()`/`run()`. Read this when an agent behaves
differently than its code suggests: wrong project, wrong model, missing variable, a
retry that doesn't happen.

## Authentication and where the keys come from

`auth.validate_auth_token` reads the `Authorization` header and validates it against TestBench.

| | JWT (normal case, sent by TestBench) | Session token (Swagger, scripts) |
|---|---|---|
| `project_key`, `tov_key`, `cycle_key` | taken from the token's `scope` claim (`proj`, `tov`, `ccl`); **the request body's keys are ignored** | taken from the request body |
| `REQUIRED_PERMISSIONS` check | yes (`perms` claim) | skipped |
| `ALLOWED_ROLES` check | yes | yes |
| `user_key` | `auth_info.user_key` (fetched once during validation) | same |

Consequences: when testing with a JWT, the body cannot redirect the agent to another project
or cycle. A token without `ccl` gives `context.cycle_key = None` even if the body has one. A
missing or malformed `scope` returns `401`. Everything after the route uses
`ExecutionContext`, never the raw request.

## Configuration precedence

`utils/agent.build_execution_context` resolves each setting as **request > project > global**:

| Setting | Request field | Project override (`config.toml`) | Global |
|---|---|---|---|
| language | `language` | `[testbench-ai-service.projects."<name>"] language` | `language` |
| LLM | `llm_config` | `projects."<name>".llm_config` | `llm_config` |
| prompt file/variant/vars | `prompt_config` | `projects."<name>".agents.<key>.prompt` | `agents.<key>.prompt` |
| agent enabled | — | `projects."<name>".agents.<key>.enabled` | `agents.<key>.enabled` |

- Project overrides are keyed by the project **name** (resolved via `GET 2/projects/{key}`),
  not by its key.
- Merges are field-wise (`model_dump(exclude_unset=True)`): a request `prompt_config` with only
  `variant` keeps the configured `file` and `vars`. `vars` is one field, so it is replaced as a
  **whole dict**: a request with any `vars` drops every configured preset, even for keys it
  didn't send.
- A request `prompt_config.file` replaces the configured prompt and is not schema-checked.
- The prompt file is resolved as `prompts_dir/<language>/<file>`, falling back to
  `prompts_dir/<file>`. Give each language its own file under the same relative path.

## LLM layer (`llm/`)

- `LLMClient` (`llm/base.py`): `async query_llm(model, messages, **kwargs) -> str` and
  `async close()`. Agents call it through `await self.get_ai_response(...)`, which returns an
  `AgentResult` (text in `.result`).
  Providers: `openai`, `azure_openai`, `anthropic`, `custom` (`llm_config.class_path`, see
  `docs/llm-providers/custom-client.md`).
- `LLMFactory.get_client` picks the provider from the **prompt variant's model**
  (`get_prompt_model`): `gpt-*`/`o<digit>…` → OpenAI (or Azure if configured), `claude-*` →
  Anthropic, otherwise `llm_config.provider`.
- `Agent.get_ai_response` sends `llm_config.model` if set, otherwise the variant's model.
  **Pitfall:** a request or project `llm_config.model` from another provider family than the
  prompt variant's model goes to the wrong client (e.g. `claude-*` sent to the OpenAI client).
  Change the variant's `model` instead, or keep both in the same family.
- Extra `llm_config` fields (`model_config = extra="allow"`) are passed to `query_llm` as
  keyword arguments, including client-construction keys (`timeout`, `max_retries`,
  `deployment_mapping`). Whether they take effect depends on the client: `OpenAIClient`
  forces `temperature=0` for known chat models and reads only `reasoning_effort` for reasoning
  models; it forwards the kwargs only for unknown (fallback) models.
- API keys come from the environment: `{PROVIDER}_API_KEY`, per project
  `{NORMALIZED_PROJECT_NAME}_{PROVIDER}_API_KEY` (name uppercased, non-alphanumerics → `_`).
  Clients are cached per provider/project.
- `query_llm` returns plain text. There is no structured-output helper: if the agent needs
  JSON, it must ask for it in the prompt and parse and validate it itself (fences, wrong case,
  invalid JSON → failure path).

## Prompt rendering (`utils/build_prompt_utils.py`)

- Jinja2 with `trim_blocks`/`lstrip_blocks` and **no autoescape**. Namespaces `agent` (the
  `AgentData` dict) and `vars` (`prompt_config.vars`).
- **A render error does not raise.** On `UndefinedError`, `TemplateSyntaxError`, a missing
  `file` or any other exception, the message falls back to `msg_template.text`: the raw inline
  text for `text:` messages, an **empty string** for `file:` messages (all built-in prompts).
  Only an error is logged. Check the DEBUG log line `Sending the following messages to the LLM`
  when output looks wrong.
- An undefined value (`{{ agent.missing }}`, an unset `vars.x`) renders as empty, without an
  error.
- `vars` semantics (strings only, `default_value` not applied, `required` bug): see
  `prompts-and-plugin.md`.
- Trigger-time validation (`agents/routes.validate_template_and_agent_vars`): every
  `agent.<key>` used in any variant must be a key of `AGENT_DATA_CLASS` → else `422`. Nested
  paths (`{{ agent.x.y }}`) are collected as `agent.x.y` and never match, so keep `agent.*`
  flat. Startup runs the same check for the configured language's default prompt.

## Outbound HTTP to TestBench (`transport.py`)

- Every `conn.session` request has a default timeout (`tb_connect_timeout` 10 s,
  `tb_read_timeout` 120 s) and retries failures up to `tb_max_retries` (3). **Connect** errors
  are retried for every method, `PATCH`/`POST` included (the request never reached TestBench);
  **read** errors only for idempotent methods. So a write is never applied twice, and a write
  that still fails goes to your `except` path.
- A stalled or unreachable TestBench surfaces as `requests` `Timeout`/`ConnectionError`. In the
  request phase (precheck) the router maps it to `502`.
- Long report exports and imports are jobs: poll them, don't raise the read timeout.

## Background execution (`tasks.run_agent`)

- Runs after the `202` response in FastAPI `BackgroundTasks`, in the same process. Nothing is
  persisted: a service restart loses running agents, and items stay in their "started" state
  and locked.
- Log lines `Agent started | agent=… | project=…`, `Agent completed … duration=…` and
  `Agent failed …` frame each run. Exceptions from `run()` end there.

## Testing an agent

| Level | Where | How |
|---|---|---|
| unit | `tests/unit/agents/<key>/` | instantiate the agent, mock `TBConnection` / helpers and `LLMClient.query_llm`; assert PATCH bodies and rendered HTML (lint it with `check_tb_html.py`) |
| integration | `tests/integration/test_<key>.py` | `app`/`client`/`post` fixtures (`conftest.py`) call the real FastAPI routes with TestBench mocked; `helpers.build_unlocked_structure_tree` builds trees; covers 202/403/404/409/422 |
| prompt engineering | `tests/prompt_engineering/` | `@pytest.mark.prompt_engineering`, real LLM (`OPENAI_API_KEY` from `.env`), excluded from CI; checks the answer quality of each variant |
