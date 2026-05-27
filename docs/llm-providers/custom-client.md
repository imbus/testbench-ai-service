---
sidebar_position: 4
title: Custom LLM Client
---

# Custom LLM Client

If none of the built-in providers fit your needs you can implement your own LLM client and plug it in via configuration.

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
        Additional kwargs from llm_config (e.g. timeout, max_retries) are forwarded here.
        """

    @abstractmethod
    async def query_llm(self, model: str, messages: list[Message], **kwargs) -> str:
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
| `content` | `str` | Message text |

---

## Minimal example

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

---

## Register the client

### 1. Make the module importable

Place your file so it is importable from the directory where the service is started. For example, put `my_llm/client.py` next to `config.toml`, or add its parent directory to `PYTHONPATH`:

```bash
# Windows
$env:PYTHONPATH = "C:\path\to\my_llm_parent"

# Linux / macOS
export PYTHONPATH="/path/to/my_llm_parent"
```

### 2. Update `config.toml`

```toml
[testbench-ai-service.llm_config]
provider = "custom"
class_path = "my_llm.client.MyCustomLLMClient"
```

`class_path` must be the fully qualified Python class path (dotted module path + class name).

### 3. Optional — pass extra configuration

Any extra keys in `llm_config` that are listed in the allowed set (`timeout`, `max_retries`, `_strict_response_validation`) are forwarded as `**kwargs` to `__init__`. Add your own keys to `config.toml` and read them from `**kwargs` in `__init__` if needed:

```toml
[testbench-ai-service.llm_config]
provider = "custom"
class_path = "my_llm.client.MyCustomLLMClient"
timeout = 60
```

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
