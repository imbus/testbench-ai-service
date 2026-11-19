---
sidebar_position: 4
title: Custom LLM Client
---

# Custom LLM Client

If none of the built-in providers fit your needs, you can implement your own LLM client and plug it in via configuration.

---

## Requirements

- The TestBench AI Service installed and a `config.toml` present
- A Python package containing your client implementation, importable from the service's working directory

---

## Interface

Your class must extend `LLMClient` from `testbench_ai_service.llm.base` and implement three methods:

```python
from abc import ABC, abstractmethod
from testbench_ai_service.models.prompt import Message

class LLMClient(ABC):
    @abstractmethod
    def __init__(self, api_key: str | None = None, *args, **kwargs):
        """
        Called once when the client is first needed.
        api_key is always None for custom providers (the service does not load
        a CUSTOM_API_KEY environment variable). Read your own key from the
        environment inside __init__ if authentication is required.
        Additional kwargs from llm_config (timeout, max_retries,
        _strict_response_validation) are forwarded here if set.
        """

    @abstractmethod
    async def query_llm(self, model: str, messages: list[Message], *args, **kwargs) -> str:
        """
        Send messages to the model and return the plain-text response.
        """

    @abstractmethod
    async def close(self):
        """
        Release connections or resources (called on service shutdown).
        """
```

The `Message` model has two fields:

| Field | Type | Description |
|---|---|---|
| `role` | `"system"` \| `"user"` \| `"assistant"` | Message role |
| `content` | String | Message text |

---

## 1. Implement the client

```python
# my_llm/client.py
import httpx
from testbench_ai_service.llm.base import LLMClient
from testbench_ai_service.models.prompt import Message


class MyCustomLLMClient(LLMClient):
    def __init__(self, api_key: str | None = None, **kwargs):
        self.api_key = api_key
        self.http = httpx.AsyncClient(
            base_url="https://my-llm-api.example.com",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=kwargs.get("timeout", 30),
        )

    async def query_llm(self, model: str, messages: list[Message], **kwargs) -> str:
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        response = await self.http.post("/v1/chat/completions", json=payload)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    async def close(self):
        await self.http.aclose()
```

## 2. Make the module importable

Place your file so it is importable from the directory where the service is started. For example, put `my_llm/client.py` next to `config.toml`, or add its parent directory to `PYTHONPATH`:

```bash
# Windows
$env:PYTHONPATH = "C:\path\to\my_llm_parent"

# Linux / macOS
export PYTHONPATH="/path/to/my_llm_parent"
```

## 3. Register in `config.toml`

```toml
# config.toml
[testbench-ai-service.llm_config]
provider = "custom"
class_path = "my_llm.client.MyCustomLLMClient"
```

`class_path` must be the fully-qualified Python class path (dotted module path + class name).

## 4. Optional: pass extra configuration

The service forwards three specific keys from `llm_config` as `**kwargs` to `__init__`: `timeout`, `max_retries`, and `_strict_response_validation`. Add any of these to your `config.toml` to configure them:

```toml
# config.toml
[testbench-ai-service.llm_config]
provider = "custom"
class_path = "my_llm.client.MyCustomLLMClient"
timeout = 60
```

For any other configuration your client needs (for example, base URLs or custom credentials), read the values from environment variables directly inside `__init__`.

---

## Upload as a package

Instead of steps 2 and 3 you can pack the client into a Python wheel and install it from the [web console](../web-console.md). You need no shell access to the server and you do not edit `config.toml` by hand. The mechanism is the one [agent packages](../agents/agent-packages.md) use: same upload switch (`agent_packages.allow_upload`), same checks, same storage. Read that page for how to turn uploads on, the limits and the security note. A wheel may carry agents, LLM clients or both.

The service supports **one** custom provider. Using a package's client replaces a custom provider configured before, and it applies globally, not per project.

### Entry point

The service finds the clients of a package through the entry-point group `testbench_ai_service.llm_clients`:

```toml
# pyproject.toml
[project.entry-points."testbench_ai_service.llm_clients"]
acme_llm = "acme_llm.client:AcmeLLMClient"
```

A complete example is in [`examples/llm_client_package`](https://github.com/imbus/testbench-ai-service/tree/main/examples/llm_client_package). Build it with `python -m build --wheel`.

At upload the wheel is examined in a separate process. For each client the check requires that

- the class can be imported and is a subclass of `LLMClient`,
- `query_llm` and `close` are implemented,
- the constructor accepts what the service passes: the API key as first argument and the keywords `timeout` and `max_retries`. Accept `**kwargs` to be safe.

### Use it as the provider

1. **Upload.** On the console's **LLM** screen, in the **Provider packages** section, click **Import provider wheel** and choose the `.whl`. The same packages also appear on the **Agents** screen.
2. **Use as LLM provider.** Enter the model names the client serves, one per line. These are the names you later pick for agents; the service passes the chosen name to `query_llm` as `model`. By default the first name also becomes the default model.
3. **Restart the service.** The package code is not imported before the restart. An administrator can restart from the console's "restart needed" strip (**Restart now**).

The console writes this for you:

```toml
[testbench-ai-service.llm_config]
provider = "custom"
class_path = "acme_llm.client.AcmeLLMClient"
package = "acme-llm"        # set by the console only
model = "acme-large"

[testbench-ai-service.llm_config.extra_models]
acme-large = { provider = "custom", routing = "fallback" }
```

:::note
Model names starting with `gpt-`, `claude-` or `o<digit>` (such as `o3-mini`) always go to OpenAI or Anthropic, whatever the configured provider is. The console refuses them for a custom client; give your models other names.
:::

**Stop using as provider** returns the service to the default provider (OpenAI) and removes the package's models from the configuration, including where one is set as default model or as an agent's model. Project overrides are left alone. A package cannot be removed while its client is in use. Switching to another version of the package is refused if that version no longer has the client.

If the package is missing or its client cannot be created, the service still starts. Requests that need the client fail with a message naming the reason, and the **Status** and **LLM** screens show it.

---

## API key

No environment variable is required for custom clients — the service passes `None` as `api_key` by default. If your provider requires authentication, read the key from the environment yourself inside `__init__`:

```python
import os

class MyCustomLLMClient(LLMClient):
    def __init__(self, api_key: str | None = None, **kwargs):
        self.api_key = api_key or os.getenv("MY_CUSTOM_API_KEY")
        ...
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError` on startup | Module not on `sys.path` | Set `PYTHONPATH` or place the file in the working directory |
| `AttributeError: module has no attribute 'MyCustomLLMClient'` | Wrong class name in `class_path` | Verify the exact class name in your file |
| `NotImplementedError` | Abstract method not implemented | Implement all three required methods |
| Client never closed | `close()` raised an exception | Ensure `close()` handles errors gracefully and always completes |
