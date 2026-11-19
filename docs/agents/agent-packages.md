---
sidebar_position: 5.5
title: Agent Packages
---

# Agent Packages

An agent package is a Python wheel (`.whl`) that carries one or more custom agents together with their prompts and write-back templates. An administrator uploads the wheel in the [web console](../web-console.md), registers its agents and restarts the service. You do not need shell access to the server and you do not edit `config.toml` by hand.

Use a package when the agent author and the service operator are different people, or when you cannot install into the service's Python environment. If you can, the plain [Custom Agent](custom-agent.md) route (`class_path` in `config.toml`) stays available and is unaffected.

A wheel can also carry a custom LLM client, alone or next to agents, through the entry-point group `testbench_ai_service.llm_clients`. See [Custom LLM Client](../llm-providers/custom-client.md#upload-as-a-package).

:::warning
Registered package code runs inside the service with the service's rights: it can read the configuration, the environment (including API keys) and everything the service user can access. Turn on uploads only for administrators you trust, and only install packages from sources you trust.
:::

---

## Turning uploads on

Uploads are off by default. Enable them in `config.toml`:

```toml
# config.toml
[testbench-ai-service.agent_packages]
allow_upload = true                  # default: false
dir = "data/agent_packages"          # where wheels and the package manifest are stored
max_upload_mb = 20                   # largest accepted wheel
```

| Field | Description |
|---|---|
| `allow_upload` | Enables the upload of wheels in the console. Registering, activating, deleting and removing already uploaded packages work regardless. |
| `dir` | Storage directory for the uploaded wheels and the manifest. Changing it needs a restart. |
| `max_upload_mb` | Size limit of one wheel. |

These settings are not editable in the console. Change them in `config.toml`.

Registering a package copies its prompt and template files into your `prompts_dir` and `templates_dir`. Both must therefore be your own directories, not the defaults inside the installed package. If you have not done so yet:

```bash
testbench-ai-service init --prompts-dir ./prompts --templates-dir ./templates
```

See [CLI](../cli.md#init) for the details. Without custom directories the console refuses to register or activate a package.

---

## Package layout

The wheel must be self-contained. The agent module sits in one top-level Python package; the prompts and templates live inside that package next to the code.

```text
acme_rater/
  pyproject.toml
  acme_rater/
    __init__.py
    agent.py                 # the Agent subclass
    prompts/
      en/prompt.yaml         # + the .jinja files it references
      de/prompt.yaml
    templates/
      en/started.jinja       # started, failed and template, per language
      en/failed.jinja
      en/template.jinja
      de/started.jinja
      de/failed.jinja
      de/template.jinja
```

- Prompts: `<module dir>/prompts/{en,de}/prompt.yaml` plus the `.jinja` files the YAML references. The format is the same as for [built-in prompts](../prompts.md).
- Templates: `<module dir>/templates/{en,de}/{started,failed,template}.*`, the write-back templates of the agent.
- Both languages, `en` and `de`, must be present.

A runnable example lives in the repository under `examples/agent_package/`.

### Entry point

The service finds the agents of a wheel through the entry-point group `testbench_ai_service.agents`. Each entry is `<agent name> = "<module>:<Class>"`:

```toml
# pyproject.toml
[project.entry-points."testbench_ai_service.agents"]
acme_rater = "acme_rater.agent:RaterAgent"
```

One wheel can declare several agents. The agent class follows the same contract as any [custom agent](custom-agent.md): `AGENT_DATA_CLASS`, `precheck()` and `run()`.

Optionally, the class can set a default URL for the trigger endpoint, which the console offers when you register the agent:

```python
class RaterAgent(Agent):
    DEFAULT_ENDPOINT_PATH = "/rater"
```

### Resolve templates with `context.agent_key`

At registration the administrator chooses the agent's key. It can differ from the entry-point name, and the console copies the prompt and template files into `<prompts_dir>/<lang>/<key>/` and `<templates_dir>/<lang>/<key>/` for that key. An agent must therefore never hard-code its own name when it looks up a template. Use `context.agent_key`:

```python
from testbench_ai_service.utils.template_utils import resolve_template_path

path = resolve_template_path(
    "template.jinja",
    templates_dir=context.templates_dir,
    language=context.language,
    agent_key=context.agent_key,
)
```

---

## Building the wheel

Any build backend works. The example uses [flit](https://flit.pypa.io/); `setuptools` is fine too as long as the prompt and template files end up in the wheel (`package-data`).

```bash
cd examples/agent_package
python -m pip install build
python -m build --wheel
```

The wheel appears in `dist/`.

### Limits

- **Self-contained wheels only.** The service does not install dependencies. `Requires-Dist` entries are checked: every requirement must already be satisfied by the service's environment, otherwise the upload is refused. In the binary distribution the metadata of a bundled library may be missing; a requirement whose metadata cannot be found only produces a warning there, while a version mismatch still fails.
- **Wheel tags must fit the service's interpreter.** A pure-Python wheel (`py3-none-any`) always fits. A wheel with compiled code must match the Python version, platform and architecture of the running service, which in the binary distribution is the bundled interpreter.
- **No clashing module names.** No top-level module of the wheel may have the name of a module the service already contains (for example `testbench_ai_service`, `fastapi` or `jinja2`).

---

## Installing a package

1. **Upload.** On the console's **Agents** screen, click **Import agent wheel** and choose the `.whl`. The uploaded packages are listed in the **Agent packages** section below the agent table. The wheel is examined in a separate process with a 30 second timeout. No package code runs inside the service during this check. The result lists the agents found and any errors or warnings.
2. **Register.** Choose the key and the endpoint path of each agent. The console copies the prompt and template files to `prompts_dir/<lang>/<key>/` and `templates_dir/<lang>/<key>/`. If a target file already exists and differs, you decide per file whether to keep the existing file or replace it.
3. **Restart the service.** The package code is not imported before the restart. Until then the agent has no route. An administrator can restart from the console's "restart needed" strip (**Restart now**); see [the web console](../web-console.md).

After the restart the agent behaves like any other agent: enable it per project, edit its prompts in the console, trigger it from TestBench.

### Updating to a new version

1. Upload the new version of the wheel.
2. **Activate** it. This is refused if the new version lacks a class a registered agent uses, and also while `prompts_dir`/`templates_dir` are the defaults. Activation copies the new version's prompt and template files for every configured agent of the package, like registration does. If a target file already exists and differs, the console lists the conflicts and you decide per file whether to keep the existing file or replace it. Activation proceeds only once every differing file is decided.
3. Restart.

### Removing

- **Delete a version.** Allowed for every version except the active one and the one the running service has loaded.
- **Remove the package.** The package's agents are deregistered together with their project overrides. The stored versions and the copied prompt and template files stay on disk. Delete the versions explicitly if you want them gone.

---

## When something is wrong at runtime

A missing or broken package never stops the service from starting. Its agents just get no route:

- `POST /agents/{key}/trigger` answers **503** with "not loaded yet, restart" if the package was registered after the last start, or with "missing or failed to load" if the import failed.
- The agent status in the console lists packages that are not loaded and agents that failed to load, with the reason. The service log has the full traceback.
