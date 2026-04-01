---
sidebar_position: 7
title: CLI Commands
---

# CLI Commands

The executable is `testbench-ai-service`. All commands support `--help` for detailed usage.

```bash
testbench-ai-service [COMMAND] [OPTIONS]
```

---

## Commands overview

| Command | Description |
|---------|-------------|
| [`init`](#init) | Generate a default configuration file and prompt files. |
| [`start`](#start) | Start the TestBench AI Service. |
| `--version`, `-v` | Print the installed version. |
| `--help` | Show top-level help. |

---

## `init`

Generate a default configuration file and copy built-in prompt files.

```bash
testbench-ai-service init [OPTIONS]
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--path PATH` | String | `config.toml` | Path to the configuration file to generate |
| `--force`, `-f` | Flag | — | Overwrite the configuration file and prompts directory if they exist |
| `--prompts-dir PATH` | String | `prompts` | Copy default prompt files to PATH and set `prompts_dir` in the config. Pass an empty string to skip. |

### What it does

1. Copies built-in prompt YAML files to the specified prompts directory (default: `./prompts`).
2. Generates a `config.toml` with default settings, including the `prompts_dir` path.

### Examples

```bash
# Create config.toml and copy prompts to ./prompts
testbench-ai-service init

# Custom paths
testbench-ai-service init --path my_config.toml --prompts-dir ./my-prompts

# Overwrite existing files
testbench-ai-service init --force

# Skip prompt copy
testbench-ai-service init --prompts-dir ""
```

---

## `start`

Start the TestBench AI Service.

```bash
testbench-ai-service start [OPTIONS]
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--config PATH` | String | `config.toml` | Path to the app configuration file |
| `--host HOST` | String | `127.0.0.1` | Host to bind to |
| `--port PORT` | Integer | `8010` | Port to listen on |
| `--dev` | Flag | — | Run in development mode (debug logging + auto-reload) |
| `--tb-server-url URL` | String | from config | Base URL of the TestBench REST API Server |

Command-line arguments take **precedence** over configuration file settings.

### Examples

```bash
# Start with defaults
testbench-ai-service start

# Start with a specific config file
testbench-ai-service start --config my_config.toml

# Override host and port
testbench-ai-service start --host 0.0.0.0 --port 9000

# Development mode (with auto-reload)
testbench-ai-service start --dev

# Override TestBench server URL
testbench-ai-service start --tb-server-url https://testbench.example.com/api/
```

---

## Getting help

```bash
# General help
testbench-ai-service --help

# Help for a specific command
testbench-ai-service start --help
testbench-ai-service init --help
```
