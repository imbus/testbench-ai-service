---
sidebar_position: 3
title: Configuration
---
# Configuration

The TestBench AI Service is configured through a single TOML file (default: `config.toml` in the installation directory). This page documents every available option.

:::tip
Use the `init` command to generate a default configuration file instead of writing one from scratch:

```bash
testbench-ai-service init
```

See [CLI Commands](cli.md) for all options.
:::

---

## Configuration precedence

The following order shows which source takes precedence when the same setting is defined in multiple places (highest priority first):

1. **Request-level overrides** (per-request `prompt_config` and `llm_config` in the API body)
2. **Project-specific overrides** (`[testbench-ai-service.projects.<name>]`)
3. **Command-line flags** (`start --host ... --port ...`)
4. **Environment variables** (for API keys: `OPENAI_API_KEY`, `AZURE_OPENAI_API_KEY`)
5. **`config.toml`**
6. **Built-in defaults**

---

## Full example

```toml
[testbench-ai-service]
tb_server_url = "https://localhost:9443/api/"
host = "127.0.0.1"
port = 8010
debug = false
language = "de"
prompts_dir = "prompts"

# LLM provider configuration
[testbench-ai-service.llm_config]
provider = "openai"

# Console logging
[testbench-ai-service.logging.console]
log_level = "INFO"
log_format = "%(levelname)s: %(message)s"

# File logging
[testbench-ai-service.logging.file]
file_name = "testbench-ai-service.log"
log_level = "INFO"
log_format = "%(asctime)s - %(levelname)8s - %(name)s - %(message)s"

# agent: Test Case Set Reviewer
[testbench-ai-service.agents.test_case_set_reviewer]
enabled = true
endpoint_path = "/test-case-set-reviews"
class_path = "testbench_ai_service.agents.test_case_set_reviewer.agent.TestCaseSetReviewer"

[testbench-ai-service.agents.test_case_set_reviewer.prompt]
file = "test_case_set_reviewer/prompt.yaml"
name = "TestCaseSetReviewer"

# agent: Test Case Set Describer
[testbench-ai-service.agents.test_case_set_describer]
enabled = true
endpoint_path = "/test-case-set-descriptions"
class_path = "testbench_ai_service.agents.test_case_set_describer.agent.TestCaseSetDescriber"
summary = "Trigger generation of test case set descriptions"
description = "Triggers asynchronous generation of descriptions for specified test case sets."

[testbench-ai-service.agents.test_case_set_describer.prompt]
file = "test_case_set_describer/prompt.yaml"
name = "TestCaseSetDescriber"

# agent: Defect Explainer
[testbench-ai-service.agents.defect_explainer]
enabled = true
endpoint_path = "/defect-explanations"
class_path = "testbench_ai_service.agents.defect_explainer.agent.DefectExplainer"
summary = "Trigger generation of defect explanations"
description = "Triggers asynchronous generation of defect explanations."

[testbench-ai-service.agents.defect_explainer.prompt]
file = "defect_explainer/prompt.yaml"
name = "DefectExplainer"

# Project-specific overrides
[testbench-ai-service.projects."My Project"]
language = "en"
```

---

## Service settings

**`[testbench-ai-service]`**

| Option            | Type    | Description                                                                                                   | Default                           |
| ----------------- | ------- | ------------------------------------------------------------------------------------------------------------- | --------------------------------- |
| `tb_server_url` | String  | Base URL of the TestBench REST API server.                                                                    | `"https://localhost:9443/api/"` |
| `host`          | String  | Host address to bind to.                                                                                      | `"127.0.0.1"`                   |
| `port`          | Integer | Port number to listen on.                                                                                     | `8010`                          |
| `debug`         | Boolean | Enable debug mode (verbose logging, auto-reload).                                                             | `false`                         |
| `language`      | String  | Default language for prompt resolution and localization (`"en"` or `"de"`).                               | `"de"`                          |
| `prompts_dir`   | String  | Directory containing prompt YAML files. Relative paths in prompt configs are resolved against this directory. | Built-in prompts directory        |

**Example:**

```toml
# config.toml
[testbench-ai-service]
tb_server_url = "https://localhost:9443/api/"
host = "127.0.0.1"
port = 8010
debug = false
language = "de"
prompts_dir = "C:\\TestBenchAIService\\prompts"
...
```

### HTTPS / TLS

| Option          | Type   | Description                                                                    | Default |
| --------------- | ------ | ------------------------------------------------------------------------------ | ------- |
| `ssl_cert`    | String | Path to the certificate file.                                                  | —      |
| `ssl_key`     | String | Path to the private key file.                                                  | —      |
| `ssl_ca_cert` | String | Path to the CA certificate. When set, client certificates are required (mTLS). | —      |

**Example:**

```toml
# config.toml
[testbench-ai-service]
ssl_cert = "certs/server.crt"
ssl_key = "certs/server.key"
ssl_ca_cert = "certs/ca.crt"   # optional — enables mTLS
...
```

Set both `ssl_cert` and `ssl_key` to enable HTTPS. Add `ssl_ca_cert` to require client certificates (mTLS).

### Reverse proxy

Only needed when the service runs behind a load balancer or reverse proxy (e.g., Nginx).

| Option              | Type         | Description                                                | Default |
| ------------------- | ------------ | ---------------------------------------------------------- | ------- |
| `trusted_proxies` | List[String] | List of trusted proxy IPs for proper client IP forwarding. | —      |

When set, Uvicorn enables proxy header processing and only trusts `X-Forwarded-*` headers from the listed IPs.

**Example:**

```toml
# config.toml
[testbench-ai-service]
trusted_proxies = ["10.0.0.1"]
...
```

:::warning[Security]
Without proxy configuration, the service ignores all proxy headers. This is safe. Only enable proxy settings when actually behind a proxy.
:::

#### Nginx example

**Nginx configuration:**

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /path/to/certificate.crt;
    ssl_certificate_key /path/to/private.key;

    location / {
        proxy_pass http://127.0.0.1:8010;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Service configuration:**

```toml
# config.toml
[testbench-ai-service]
host = "127.0.0.1"   # bind to localhost only
port = 8010
trusted_proxies = ["10.0.0.1"]
...
```

---

## LLM provider

:::tip Provider setup guides
For step-by-step instructions on configuring each provider see the [LLM Providers](llm-provider/index.md) section:
- [OpenAI Setup](llm-provider/openai-setup.md)
- [Anthropic (Claude) Setup](llm-provider/anthropic-setup.md)
- [Azure OpenAI Setup](llm-provider/azure-openai-setup.md)
- [Custom LLM Client](llm-provider/custom-client.md)
:::

**`[testbench-ai-service.llm_config]`**

| Option             | Type    | Description                                                                               | Default          |
| ------------------ | ------- | ----------------------------------------------------------------------------------------- | ---------------- |
| `provider`       | String  | LLM provider:`"openai"`, `"azure_openai"`, `"anthropic"`, or `"custom"`.          | `"openai"`     |
| `model`          | String  | Override the default model (if not set, the model from the prompt variant is used).       | —               |
| `azure_endpoint` | String  | Azure OpenAI endpoint URL (required when `provider = "azure_openai"`).                  | —               |
| `api_version`    | String  | Azure OpenAI API version (required when `provider = "azure_openai"`).                   | —               |
| `class_path`     | String  | Full Python class path for a custom LLM client (required when `provider = "custom"`).   | —               |
| `timeout`        | Float   | HTTP request timeout in seconds, passed through to the underlying client.                 | Provider default |
| `max_retries`    | Integer | Number of automatic retries on transient errors, passed through to the underlying client. | Provider default |

**OpenAI example:**

```toml
# config.toml
[testbench-ai-service.llm_config]
provider = "openai"
```

**Anthropic example:**

```toml
[testbench-ai-service.llm_config]
provider = "anthropic"
```

**Azure OpenAI example:**

```toml
[testbench-ai-service.llm_config]
provider = "azure_openai"
azure_endpoint = "https://your-resource.openai.azure.com"
api_version = "2024-10-21"
model = "gpt-4o"  # use your Azure deployment name here
```

### Automatic provider detection

The service automatically routes each request to the correct client based on the model name specified in the prompt variant, regardless of the globally configured `provider`. This lets you mix models from different providers across prompt variants without changing the global config:

| Model name prefix | Routed to                |
| ----------------- | ------------------------ |
| `gpt-*`         | OpenAI                   |
| `claude-*`      | Anthropic                |
| anything else     | uses `config.provider` |

For example, if `provider = "openai"` is configured globally but a prompt variant specifies `model: "claude-sonnet-4-6"`, the service automatically uses the Anthropic client for that variant. The corresponding API key (`ANTHROPIC_API_KEY`) must be set in the environment.

### Setting the API key

API keys are loaded from environment variables using the pattern `{PROVIDER}_API_KEY`:

| Provider         | Environment variable                          |
| ---------------- | --------------------------------------------- |
| `openai`       | `OPENAI_API_KEY`                            |
| `azure_openai` | `AZURE_OPENAI_API_KEY`                      |
| `anthropic`    | `ANTHROPIC_API_KEY`                         |
| `custom`       | Not required (handled by your implementation) |

**Recommended:** Create a `.env` file at the root of your installation directory:

```bash
# .env
OPENAI_API_KEY=your_openai_api_key
AZURE_OPENAI_API_KEY=your_azure_openai_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
```

### Project-specific API keys

You can set a separate API key per TestBench project using the pattern `{NORMALIZED_PROJECT_NAME}_{PROVIDER}_API_KEY`. The project name is normalized by replacing all non-alphanumeric characters with underscores and uppercasing:

```bash
# .env
# For a project named "Car Configurator" using OpenAI:
CAR_CONFIGURATOR_OPENAI_API_KEY=sk-project-specific-key

# For a project named "Car Configurator" using Anthropic:
CAR_CONFIGURATOR_ANTHROPIC_API_KEY=sk-ant-project-specific-key

# For a project named "Car Configurator" using Azure OpenAI:
CAR_CONFIGURATOR_AZURE_OPENAI_API_KEY=azure-project-specific-key
```

If a project-specific key is found, the service creates a dedicated LLM client for that project. Otherwise, the global client is used.

### Azure OpenAI deployment mapping

In prompt variants you always use your Azure **deployment name** (as configured in the Azure portal). The service needs to know which canonical model each deployment corresponds to so it can choose the correct API call routing (chat vs. reasoning).

If your deployment names don't match any known canonical model name, add a `deployment_mapping` that maps each deployment name to the canonical model it represents:

```toml
[testbench-ai-service.llm_config]
provider = "azure_openai"
azure_endpoint = "https://your-resource.openai.azure.com"
api_version = "2024-10-21"

[testbench-ai-service.llm_config.deployment_mapping]
"my-gpt4-deployment" = "gpt-4.1"
"my-gpt4-mini-deployment" = "gpt-4.1-mini"
```

When the deployment name from a prompt variant matches a key in `deployment_mapping`, the corresponding canonical model name is used for routing decisions. The deployment name itself is still what gets sent to the Azure API.

### Custom LLM provider

To use a custom LLM provider, implement the `LLMClient` abstract class and point the config to your implementation:

```toml
# config.toml
[testbench-ai-service.llm_config]
provider = "custom"
class_path = "my_module.MyCustomLLMClient"
...
```

Your class must implement:

- `__init__(self, api_key, *args, **kwargs)`
- `async query_llm(self, model, messages, *args, **kwargs) -> str`
- `async close(self)`

:::tip
The module must be importable from the working directory where the service is started. Place your custom client file in the same directory or add its location to `PYTHONPATH`.
:::

---

## Agent settings

**`[testbench-ai-service.agents.<agent_key>]`**

Each agent is configured under its own key. The three built-in Agents are `test_case_set_reviewer`, `test_case_set_describer`, and `defect_explainer`.

| Option            | Type    | Description                                                 | Required |
| ----------------- | ------- | ----------------------------------------------------------- | -------- |
| `enabled`       | Boolean | Whether this agent is active.                               | Yes      |
| `endpoint_path` | String  | The HTTP endpoint path (e.g.,`"/test-case-set-reviews"`). | Yes      |
| `class_path`    | String  | Full Python class path to the agent service implementation. | Yes      |
| `summary`       | String  | Short summary shown in OpenAPI docs.                        | No       |
| `description`   | String  | Detailed description shown in OpenAPI docs.                 | No       |

**`[testbench-ai-service.agents.<agent_key>.prompt]`**

| Option      | Type   | Description                                                                                          | Required |
| ----------- | ------ | ---------------------------------------------------------------------------------------------------- | -------- |
| `file`    | String | Path to the prompt YAML file (relative to `prompts_dir/<language>/`).                              | Yes      |
| `name`    | String | Name of the prompt definition within the YAML file.                                                  | Yes      |
| `variant` | String | Prompt variant to use (falls back to `default_variant` in the YAML file).                          | No       |
| `vars`    | Table  | Key-value pairs for user-provided variables, accessible as `{{ vars.<key> }}` in prompt templates. | No       |

For details on how prompts work, see the [Prompts](prompts.md) page.

**Example:**

```toml
# config.toml
[testbench-ai-service.agents.test_case_set_reviewer]
enabled = true
endpoint_path = "/test-case-set-reviews"
class_path = "testbench_ai_service.agents.test_case_set_reviewer.agent.TestCaseSetReviewer"
summary = "Trigger test case set reviews"
description = "This endpoint triggers asynchronous reviews for the specified test case sets."

[testbench-ai-service.agents.test_case_set_reviewer.prompt]
file = "test_case_set_reviewer/prompt.yaml"
name = "TestCaseSetReviewer"
...
```

---

## Project-specific overrides

**`[testbench-ai-service.projects."<project_name>"]`**

Any global setting can be overridden per TestBench project. The project name must match exactly as it appears in TestBench (including spaces and special characters — use quotes in TOML).

| Option                          | Type    | Description                                     |
| ------------------------------- | ------- | ----------------------------------------------- |
| `language`                    | String  | Override the default language for this project. |
| `llm_config`                  | Table   | Override the LLM provider configuration.        |
| `agents.<key>.enabled`        | Boolean | Enable or disable a specific agent.             |
| `agents.<key>.prompt.file`    | String  | Override the prompt file.                       |
| `agents.<key>.prompt.name`    | String  | Override the prompt definition name.            |
| `agents.<key>.prompt.variant` | String  | Override the prompt variant.                    |
| `agents.<key>.prompt.vars`    | Table   | Override prompt variables.                      |

**Example:**

```toml
# config.toml

# Global: German, reviews enabled
[testbench-ai-service]
language = "de"

# Project "Car Configurator": English, reviews disabled
[testbench-ai-service.projects."Car Configurator"]
language = "en"

[testbench-ai-service.projects."Car Configurator".agents.test_case_set_reviewer]
enabled = false

# Use a different prompt variant for this project
[testbench-ai-service.projects."Car Configurator".agents.test_case_set_reviewer.prompt]
file = "CarConfigurator_reviews_prompt/prompt.yaml"
name = "TestCaseSetReviewer"
variant = "Separated Roles"
```

---

## Logging

### Console

**`[testbench-ai-service.logging.console]`**

| Option         | Type   | Description                                                                          | Default                          |
| -------------- | ------ | ------------------------------------------------------------------------------------ | -------------------------------- |
| `log_level`  | String | Minimum log level. One of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. | `"INFO"`                       |
| `log_format` | String | Python `logging` format string.                                                    | `"%(levelname)s: %(message)s"` |

**Example:**

```toml
# config.toml
[testbench-ai-service.logging.console]
log_level = "INFO"
log_format = "%(levelname)s: %(message)s"
```

### File

**`[testbench-ai-service.logging.file]`**

| Option         | Type   | Description                                                                          | Default                                                     |
| -------------- | ------ | ------------------------------------------------------------------------------------ | ----------------------------------------------------------- |
| `file_name`  | String | Path to the log file. Relative paths are resolved from the working directory.        | `"testbench-ai-service.log"`                              |
| `log_level`  | String | Minimum log level. One of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. | `"INFO"`                                                  |
| `log_format` | String | Python `logging` format string.                                                    | `"%(asctime)s - %(levelname)8s - %(name)s - %(message)s"` |

**Example:**

```toml
# config.toml
[testbench-ai-service.logging.file]
file_name = "testbench-ai-service.log"
log_level = "INFO"
log_format = "%(asctime)s - %(levelname)8s - %(name)s - %(message)s"
```
