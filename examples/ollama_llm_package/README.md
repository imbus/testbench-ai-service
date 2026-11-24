# Ollama LLM client for the TestBench AI Service

A wheel that lets the TestBench AI Service use models served by [Ollama](https://ollama.com). It talks to Ollama's native chat API (`POST /api/chat`) and reports token usage back to the service.

## Build

```bash
cd examples/ollama_llm_package
python -m build --wheel        # or: uv build --wheel
```

The wheel is written to `dist/ollama_llm-1.0.0-py3-none-any.whl`.

## Install

1. Uploads must be on: `agent_packages.allow_upload = true` in `config.toml`.
2. In the web console open **LLM provider**, section **Upload custom LLM provider**, click **Import provider wheel** and choose the wheel.
3. Click **Use as LLM provider** and enter the Ollama model tags the service may use, one per line, exactly as `ollama list` prints them (for example `llama3.1:8b`).
4. Restart the service.

Model names starting with `gpt-`, `claude-` or `o<digit>` always go to OpenAI or Anthropic, so the console refuses them. An Ollama model with such a tag (`gpt-oss:20b`) needs another name: `ollama cp gpt-oss:20b oss:20b`.

## Settings

The console does not manage settings of custom clients. Set them in the environment of the service:

| Variable            | Meaning                                                                                              | Default                  |
| ------------------- | ---------------------------------------------------------------------------------------------------- | ------------------------ |
| `OLLAMA_HOST`       | Where Ollama listens. A full URL, or a bare `host` or `host:port`.                                   | `http://localhost:11434` |
| `OLLAMA_API_KEY`    | Bearer token, for Ollama behind a proxy that asks for one.                                           | none                     |
| `OLLAMA_NUM_CTX`    | Context window in tokens. Ollama's default is small and a longer prompt is cut off without an error. | Ollama's default         |
| `OLLAMA_KEEP_ALIVE` | How long the model stays loaded after a call (`10m`, `-1` for ever).                                 | Ollama's default (5 min) |
| `OLLAMA_THINK`      | Thinking of models that support it: `true`, `false`, or `low`/`medium`/`high` where the model has levels. | Ollama's default (on) |

A thinking model (`qwen3`, `deepseek-r1`, ...) reasons before it answers, and the prompt, the thinking and the answer share the context window. With Ollama's small default window the thinking alone can fill it; the client then fails with "ran out of tokens" instead of handing an empty answer to the agent. Set `OLLAMA_THINK=false`, or raise `OLLAMA_NUM_CTX` far enough for all three.

`timeout` and `max_retries` come from `llm_config` as for every provider. Without a `timeout` the client waits up to 300 seconds, because a local model may first have to be loaded. `max_retries` retries a connection that could not be opened, not a failed answer.
