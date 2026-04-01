---
sidebar_position: 3
title: Configuration
---

# Configuration

The service is configured with a TOML file (default: `config.toml`). All settings live under the `[testbench-ai-service]` section.

:::tip
Use the `init` command to generate a default configuration file instead of writing one from scratch:

```bash
testbench-ai-service init
```

See [CLI Commands](cli.md) for all options.
:::

---

## Configuration precedence

Highest priority first:

1. **Request-level overrides** (per-request `prompt_config` and `llm_config` in the API body)
2. **Project-specific overrides** (`[testbench-ai-service.projects.<name>]`)
3. **Command-line flags** (`start --host ... --port ...`)
4. **Environment variables** (for API keys: `OPENAI_API_KEY`)
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

# Use case: Test Case Set Reviews
[testbench-ai-service.usecases.test_case_set_reviews]
enabled = true
endpoint_path = "/test-case-set-reviews"
class_path = "testbench_ai_service.usecases.test_case_set_reviews.service.TestCaseSetReviewer"
summary = "Trigger test case set reviews"
description = "Triggers asynchronous reviews for specified test case sets."

[testbench-ai-service.usecases.test_case_set_reviews.prompt]
file = "test_case_set_reviews.yaml"
name = "TestCaseSetReviews"

# Use case: Test Case Set Descriptions
[testbench-ai-service.usecases.test_case_set_descriptions]
enabled = true
endpoint_path = "/test-case-set-descriptions"
class_path = "testbench_ai_service.usecases.test_case_set_descriptions.service.TestCaseSetDescriber"
summary = "Trigger generation of test case set descriptions"
description = "Triggers asynchronous generation of descriptions for specified test case sets."

[testbench-ai-service.usecases.test_case_set_descriptions.prompt]
file = "test_case_set_descriptions.yaml"
name = "TestCaseSetDescriptions"

# Use case: Defect Explanations
[testbench-ai-service.usecases.defect_explanations]
enabled = true
endpoint_path = "/defect-explanations"
class_path = "testbench_ai_service.usecases.defect_explanations.service.DefectExplainer"
summary = "Trigger generation of defect explanations"
description = "Triggers asynchronous generation of defect explanations."

[testbench-ai-service.usecases.defect_explanations.prompt]
file = "defect_explanations.yaml"
name = "DefectExplanations"

# Project-specific overrides
[testbench-ai-service.projects."My Project"]
language = "en"
```

---

## Service settings

**`[testbench-ai-service]`**

| Option | Type | Description | Default |
|--------|------|-------------|---------|
| `tb_server_url` | String | Base URL of the TestBench REST API server | `"https://localhost:9443/api/"` |
| `host` | String | Host address to bind to | `"127.0.0.1"` |
| `port` | Integer | Port number to listen on | `8010` |
| `debug` | Boolean | Enable debug mode (verbose logging, auto-reload in dev) | `false` |
| `language` | String | Default language for prompt resolution and localization (`"en"` or `"de"`) | `"de"` |
| `prompts_dir` | String | Directory containing prompt YAML files. Relative paths in prompt configs are resolved against this directory. | Built-in prompts directory |

**Example:**

```toml
[testbench-ai-service]
tb_server_url = "https://localhost:9443/api/"
host = "127.0.0.1"
port = 8010
debug = false
language = "de"
```

### HTTPS / TLS

| Option | Type | Description | Default |
|--------|------|-------------|---------|
| `ssl_cert` | String | Path to SSL certificate file | — |
| `ssl_key` | String | Path to SSL private key file | — |
| `ssl_ca_cert` | String | Path to CA certificate for client verification (mutual TLS) | — |

**Example:**

```toml
[testbench-ai-service]
ssl_cert = "certs/server.crt"
ssl_key = "certs/server.key"
ssl_ca_cert = "certs/ca.crt"
```

Set both `ssl_cert` and `ssl_key` to enable HTTPS. Add `ssl_ca_cert` to require client certificates (mTLS).

| `ssl_cert` | `ssl_key` | `ssl_ca_cert` | Mode |
|:---:|:---:|:---:|---|
| — | — | — | Plain HTTP |
| ✓ | ✓ | — | HTTPS (one-way TLS) |
| ✓ | ✓ | ✓ | HTTPS with mTLS (client certificates required) |

### Reverse proxy

| Option | Type | Description | Default |
|--------|------|-------------|---------|
| `trusted_proxies` | List of Strings | List of trusted proxy IPs for proper client IP forwarding | — |

When set, Uvicorn enables proxy header processing and only trusts `X-Forwarded-*` headers from the listed IPs.

**Example:**

```toml
[testbench-ai-service]
trusted_proxies = ["10.0.0.1"]
```

:::warning Security
Without proxy configuration, the service ignores all proxy headers. This is safe. Only enable proxy settings when actually behind a proxy.
:::

**Nginx example**

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
[testbench-ai-service]
host = "127.0.0.1"   # bind to localhost only
port = 8010
trusted_proxies = ["10.0.0.1"]
```

---

## LLM provider

**`[testbench-ai-service.llm_config]`**

| Option | Type | Description | Default |
|--------|------|-------------|---------|
| `provider` | String | LLM provider to use: `"openai"` or `"custom"` | `"openai"` |
| `model` | String | Override the default model (if not set, the model from the prompt variant is used) | — |
| `class_path` | String | Full Python class path for a custom LLM client (required when `provider = "custom"`) | — |

Additional provider-specific keys can be added to this section and will be passed through to the client.

**Example:**

```toml
[testbench-ai-service.llm_config]
provider = "openai"
```

### Setting the API key

API keys are loaded from environment variables using the pattern `{PROVIDER}_API_KEY`:

| Provider | Environment variable |
|----------|---------------------|
| `openai` | `OPENAI_API_KEY` |
| `custom` | Not required (handled by your implementation) |

**Recommended:** Create a `.env` file at the project root:

```bash
OPENAI_API_KEY=your_openai_api_key
```

### Project-specific API keys

You can set a separate API key per TestBench project using the pattern `{NORMALIZED_PROJECT_NAME}_{PROVIDER}_API_KEY`. The project name is normalized by replacing all non-alphanumeric characters with underscores and uppercasing:

```bash
# For a project named "Car Configurator" using OpenAI:
CAR_CONFIGURATOR_OPENAI_API_KEY=sk-project-specific-key
```

If a project-specific key is found, the service creates a dedicated LLM client for that project. Otherwise, the global client is used.

### Custom LLM provider

To use a custom LLM provider, implement the `LLMClient` abstract class and point the config to your implementation:

```toml
[testbench-ai-service.llm_config]
provider = "custom"
class_path = "my_module.MyCustomLLMClient"
```

Your class must implement:
- `__init__(self, api_key, *args, **kwargs)`
- `async query_llm(self, model, messages, *args, **kwargs) -> str`
- `async close(self)`

:::tip
The module must be importable from the working directory where the service is started. Place your custom client file in the same directory or add its location to `PYTHONPATH`.
:::

---

## Use case settings

**`[testbench-ai-service.usecases.<usecase_key>]`**

Each use case is configured under its own key. The three built-in use cases are `test_case_set_reviews`, `test_case_set_descriptions`, and `defect_explanations`.

| Option | Type | Description | Required |
|--------|------|-------------|----------|
| `enabled` | Boolean | Whether this use case is active | Yes |
| `endpoint_path` | String | The HTTP endpoint path (e.g., `"/test-case-set-reviews"`) | Yes |
| `class_path` | String | Full Python class path to the use case service implementation | Yes |
| `summary` | String | Short summary shown in OpenAPI docs | No |
| `description` | String | Detailed description shown in OpenAPI docs | No |

**`[testbench-ai-service.usecases.<usecase_key>.prompt]`**

| Option | Type | Description | Required |
|--------|------|-------------|----------|
| `file` | String | Path to the prompt YAML file (relative to `prompts_dir/<language>/`) | Yes |
| `name` | String | Name of the prompt definition within the YAML file | Yes |
| `variant` | String | Prompt variant to use (falls back to `default_variant` in the YAML file) | No |
| `placeholder_data` | Table | Key-value pairs for Jinja2 placeholder rendering in prompt blocks | No |

Additional custom attributes (like `glossary`) are supported and can be utilized by the use case implementation.

For details on how prompts work, see the [Prompts](prompts.md) page.

---

## Project-specific overrides

**`[testbench-ai-service.projects."<project_name>"]`**

Any global setting can be overridden per TestBench project. The project name must match exactly as it appears in TestBench (including spaces and special characters — use quotes in TOML).

| Option | Type | Description |
|--------|------|-------------|
| `language` | String | Override the default language for this project |
| `llm_config` | Table | Override the LLM provider configuration |
| `usecases.<key>.enabled` | Boolean | Enable or disable a specific use case |
| `usecases.<key>.prompt.file` | String | Override the prompt file |
| `usecases.<key>.prompt.name` | String | Override the prompt definition name |
| `usecases.<key>.prompt.variant` | String | Override the prompt variant |
| `usecases.<key>.prompt.placeholder_data` | Table | Override placeholder values |

**Example:**

```toml
# Global: German, reviews enabled
[testbench-ai-service]
language = "de"

# Project "Car Configurator": English, reviews disabled
[testbench-ai-service.projects."Car Configurator"]
language = "en"

[testbench-ai-service.projects."Car Configurator".usecases.test_case_set_reviews]
enabled = false

# Use a different prompt variant for this project
[testbench-ai-service.projects."Car Configurator".usecases.test_case_set_reviews.prompt]
file = "CarConfigurator_reviews_prompt.yaml"
name = "TestCaseSetReviews"
variant = "simple-generic-prompt-no-glossary"
```

---

## Logging

### Console

**`[testbench-ai-service.logging.console]`**

| Option | Type | Description | Default |
|--------|------|-------------|---------|
| `log_level` | String | Minimum severity: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | `"INFO"` |
| `log_format` | String | Python logging format string | `"%(levelname)s: %(message)s"` |

**Example:**

```toml
[testbench-ai-service.logging.console]
log_level = "INFO"
log_format = "%(levelname)s: %(message)s"
```

### File

**`[testbench-ai-service.logging.file]`**

| Option | Type | Description | Default |
|--------|------|-------------|---------|
| `file_name` | String | Log file path | `"testbench-ai-service.log"` |
| `log_level` | String | Minimum severity: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | `"INFO"` |
| `log_format` | String | Python logging format string | `"%(asctime)s - %(levelname)8s - %(name)s - %(message)s"` |

**Example:**

```toml
[testbench-ai-service.logging.file]
file_name = "testbench-ai-service.log"
log_level = "INFO"
log_format = "%(asctime)s - %(levelname)8s - %(name)s - %(message)s"
```
