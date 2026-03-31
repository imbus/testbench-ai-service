---
sidebar_position: 1
title: Installation
---

# Installation

## Requirements

- **Python 3.10** or higher
- **pip** (included with Python)

## Install from PyPI

```bash
pip install testbench-ai-service
```

## Install from Source (Development)

Clone the repository and install in editable mode with development dependencies:

```bash
git clone https://git.imbus.de/testbench/testbench-ai-service.git
cd testbench-ai-service
```

Create a virtual environment and install the package:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
```

## Verify the Installation

```bash
testbench-ai-service --version
```

If the installation was successful, this prints the installed version.

You can also run:

```bash
testbench-ai-service --help
```

## Next Steps

Head to the [Quickstart](quickstart.md) to configure and start the service.
