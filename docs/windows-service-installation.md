---
sidebar_position: 9
title: Windows Service Installation
---

# Windows Service Installation

The TestBench AI Service can be deployed as a Windows service for automatic startup and process management.

For the full installation guide covering NSSM, FireDaemon, YAJSW, and Windows Task Scheduler, see the [**Windows Service Installation Guide**](/testbench-ecosystem-documentation/docs/windows-service-installation).

Use these values when following the central guide:

| Placeholder              | Value                                                      |
| ------------------------ | ---------------------------------------------------------- |
| `<serviceName>`        | `TestBenchAIService`                                     |
| `<serviceDisplayName>` | `TestBench AI Service`                                   |
| `<serviceExecutable>`  | `testbench-ai-service.exe`                               |
| `<servicePort>`        | `8010`                                                   |
| `<serviceInstallDir>`  | Your installation directory, e.g. `C:\TestBenchAIService` |

:::note[Executable path]

- **Ready-to-use executable**: `C:\TestBenchAIService\testbench-ai-service.exe`
- **Python venv**: `C:\TestBenchAIService\.venv\Scripts\testbench-ai-service.exe`

See [Installation](getting-started/installation.md) for details.
:::
