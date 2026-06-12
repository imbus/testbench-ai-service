---
sidebar_position: 8
title: CLI Commands
---
# CLI Commands

The executable is `testbench-ai-service`. All commands support `--help` for detailed usage.

```bash
testbench-ai-service [COMMAND] [OPTIONS]
```

---

## Commands overview

| Command               | Description                                             |
| --------------------- | ------------------------------------------------------- |
| [`init`](#init)        | Generate a default configuration file and prompt files. |
| [`start`](#start)      | Start the TestBench AI Service.                         |
| `--version`, `-v` | Print the installed version.                            |
| `--help`            | Show top-level help.                                    |

---

## `init`

Generate a default configuration file and copy built-in prompt files.

```bash
testbench-ai-service init [OPTIONS]
```

**What it does**

1. Copies built-in prompt YAML files to the specified prompts directory (default: `./prompts`).
2. Generates a `config.toml` with default settings, including the `prompts_dir` path.

### Options

| Option                 | Description                                                                                                    | Default         |
| ---------------------- | -------------------------------------------------------------------------------------------------------------- | --------------- |
| `--path PATH`        | Path to the configuration file to generate.                                                                    | `config.toml` |
| `--force`, `-f`    | Overwrite the configuration file and prompts directory if they exist.                                          | —              |
| `--prompts-dir PATH` | Copy default prompt files to PATH and set `prompts_dir` in the config. Pass an empty string to skip. | `prompts`     |

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

| Option                  | Description                                            | Default         |
| ----------------------- | ------------------------------------------------------ | --------------- |
| `--config PATH`       | Path to the app configuration file.                    | `config.toml` |
| `--host HOST`         | Host to bind to.                                       | `127.0.0.1`   |
| `--port PORT`         | Port to listen on.                                     | `8010`        |
| `--dev`               | Run in development mode (debug logging + auto-reload). | —              |
| `--tb-server-url URL` | Base URL of the TestBench REST API Server.             | from config     |

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
