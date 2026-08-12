---
sidebar_position: 3
title: Azure OpenAI Setup
---

# Azure OpenAI Setup

This guide walks you through connecting the TestBench AI Service to an Azure OpenAI resource.

---

## Requirements

- An active [Azure subscription](https://azure.microsoft.com/free/)
- An **Azure OpenAI resource** with at least one model deployment
- The TestBench AI Service installed and a `config.toml` present

---

## 1. Create an Azure OpenAI resource

1. Open the [Azure portal](https://portal.azure.com) and navigate to **Azure OpenAI**.
2. Click **Create** and fill in the required details (subscription, resource group, region, name).
3. Once the resource is created, open it and go to **Keys and Endpoint**.
4. Copy the **Endpoint URL** (e.g. `https://your-resource.openai.azure.com`) and one of the **API keys**.

## 2. Create a model deployment

1. In your Azure OpenAI resource, navigate to **Azure OpenAI Studio** → **Deployments** → **Deploy model**.
2. Select a base model (e.g. `gpt-4o` or `gpt-4.1-mini`) and give it a deployment name (e.g. `my-gpt4o`).
3. Note down the **deployment name**. This is what you will reference in prompt variants and in `config.toml`.

## 3. Choose an authentication method

The service supports two ways to authenticate against Azure OpenAI:

| Method | `auth_method` | When to use |
| --- | --- | --- |
| API key | `api_key` (default) | Direct integration scenarios where a key is explicitly required |
| Microsoft Entra ID | `entra_id` | Application development, and wherever your security policy mandates Entra ID |

Managed identity is not supported, because the service runs on-premise where no
managed identity is available. Entra ID authentication therefore uses a service
principal (app registration) with a client secret.

### Option A: API key

The service reads the Azure OpenAI API key from the environment variable
`AZURE_OPENAI_API_KEY`.

Create or update a `.env` file in the root of your installation directory:

```bash
# .env
AZURE_OPENAI_API_KEY=your_azure_openai_api_key
```

:::tip
Never commit API keys to version control. Add `.env` to your `.gitignore`.
:::

### Option B: Microsoft Entra ID

#### Prepare the app registration in Azure

These steps happen in your own Azure tenant and are your responsibility. The
AI service does not perform them.

1. In the [Azure portal](https://portal.azure.com), go to **Microsoft Entra ID**
   → **App registrations** → **New registration**. Give the application a name
   and register it.
2. On the application's **Overview** page, note the
   **Application (client) ID** and the **Directory (tenant) ID**.
3. Go to **Certificates & secrets** → **New client secret**. Note the secret
   **value** immediately; it is shown only once.
4. Open your **Azure OpenAI resource** → **Access control (IAM)** →
   **Add role assignment**. Assign the role
   **Cognitive Services OpenAI User** to the application you registered.

:::warning
Step 4 is the one that is most often missed. Without the role assignment the
configuration looks correct in every respect and every request still fails with
`401 Unauthorized` or `403 Forbidden`.
:::

#### Configure the service

Set `auth_method` in `config.toml`:

```toml
# config.toml
[testbench-ai-service.llm_config]
provider = "azure_openai"
auth_method = "entra_id"
azure_endpoint = "https://your-resource.openai.azure.com"
api_version = "2025-04-01-preview"
```

Supply the service principal through environment variables:

```bash
# .env
AZURE_TENANT_ID=your_directory_tenant_id
AZURE_CLIENT_ID=your_application_client_id
AZURE_CLIENT_SECRET=your_client_secret
```

| Variable | Azure portal name |
| --- | --- |
| `AZURE_TENANT_ID` | Directory (tenant) ID |
| `AZURE_CLIENT_ID` | Application (client) ID |
| `AZURE_CLIENT_SECRET` | Client secret **value** |

`AZURE_OPENAI_API_KEY` is not read in this mode and does not need to be set.

:::tip
Client secrets expire. Note the expiry date from **Certificates & secrets** and
plan the rotation — the service will start failing on the expiry date otherwise.
:::

## 4. Configure `config.toml`

Update the `[testbench-ai-service.llm_config]` section in your `config.toml`:

```toml
# config.toml
[testbench-ai-service.llm_config]
provider = "azure_openai"
azure_endpoint = "https://your-resource.openai.azure.com"
api_version = "2025-04-01-preview"
```

Both `azure_endpoint` and `api_version` are **required** when `provider = "azure_openai"`.

### Choosing an API version

Microsoft releases new API versions regularly. Check the [Azure OpenAI REST API reference](https://learn.microsoft.com/azure/ai-services/openai/reference) for the latest stable version. A commonly used recent version is `2025-04-01-preview`.

## 5. Map deployment names to canonical models

In prompt YAML files you reference your Azure **deployment name**. The service needs to know the underlying canonical model name in order to route requests correctly (for example, reasoning models like `o3` require different API parameters than chat models like `gpt-4o`).

If your deployment name is identical to a known canonical model name no mapping is required. Otherwise, add a `deployment_mapping` table:

```toml
# config.toml
[testbench-ai-service.llm_config]
provider = "azure_openai"
azure_endpoint = "https://your-resource.openai.azure.com"
api_version = "2025-04-01-preview"

[testbench-ai-service.llm_config.deployment_mapping]
"my-gpt4o-deployment"    = "gpt-4o"
"my-gpt41-mini"          = "gpt-4.1-mini"
"my-o3-deployment"       = "o3"
```

The key is the deployment name you use in prompt variants; the value is the canonical OpenAI model identifier that the deployment is based on.

### Known canonical chat models

| Canonical name    | Type          |
| ----------------- | ------------- |
| `gpt-4o`        | Chat          |
| `gpt-4o-mini`   | Chat          |
| `gpt-4o-search-preview` | Chat |
| `gpt-4o-mini-search-preview` | Chat |
| `gpt-4.1`       | Chat          |
| `gpt-4.1-mini`  | Chat          |
| `gpt-4.1-nano`  | Chat          |
| `gpt-4-turbo`   | Chat          |
| `gpt-4`         | Chat          |
| `gpt-3.5-turbo` | Chat          |
| `gpt-3.5-turbo-16k` | Chat      |
| `gpt-3.5-turbo-instruct` | Chat  |

### Known canonical reasoning models

| Canonical name           | Type      |
| ------------------------ | --------- |
| `gpt-5`                | Reasoning |
| `gpt-5-mini`           | Reasoning |
| `gpt-5-nano`           | Reasoning |
| `gpt-5-codex`          | Reasoning |
| `gpt-5-pro`            | Reasoning |
| `gpt-5.1`              | Reasoning |
| `gpt-5.1-codex`        | Reasoning |
| `gpt-5.1-codex-max`    | Reasoning |
| `gpt-5.1-codex-mini`   | Reasoning |
| `gpt-5.2`              | Reasoning |
| `gpt-5.2-codex`        | Reasoning |
| `gpt-5.2-pro`          | Reasoning |
| `gpt-5.3-codex`        | Reasoning |
| `gpt-5.4`              | Reasoning |
| `gpt-5.4-mini`         | Reasoning |
| `gpt-5.4-nano`         | Reasoning |
| `gpt-5.4-pro`          | Reasoning |
| `gpt-5.5`              | Reasoning |
| `gpt-5.5-pro`          | Reasoning |
| `o1`                   | Reasoning |
| `o1-pro`               | Reasoning |
| `o3`                   | Reasoning |
| `o3-mini`              | Reasoning |
| `o4-mini`              | Reasoning |

## 6. Reference the deployment in a prompt variant

In your prompt YAML file, set `model` to the Azure **deployment name**:

```yaml
variants:
  - name: "Full Description"
    model: "my-gpt4o-deployment"   # Azure deployment name
    messages:
      - role: "system"
        file: "system.jinja"
      - role: "user"
        file: "user.jinja"
```

---

## Minimal complete example

**`.env`**

```bash
AZURE_OPENAI_API_KEY=abc123yourkey
```

**`config.toml`**

```toml
# config.toml
[testbench-ai-service]
tb_server_url = "https://localhost:9443/api/"
host = "127.0.0.1"
port = 8010
language = "en"

[testbench-ai-service.llm_config]
provider = "azure_openai"
azure_endpoint = "https://your-resource.openai.azure.com"
api_version = "2025-04-01-preview"

[testbench-ai-service.llm_config.deployment_mapping]
"gpt-4o-tb" = "gpt-4o"
```

**`prompts/en/test_case_set_describer/prompt.yaml`** (excerpt)

```yaml
variants:
  - name: "Full Description"
    model: "gpt-4o-tb"
    messages:
      - role: "system"
        file: "system.jinja"
      - role: "user"
        file: "full_description_user.jinja"
```

---

## Project-specific configuration

You can override the Azure OpenAI settings per TestBench project. This is useful when different projects use different Azure resources or deployments.

**`config.toml`**

```toml
# config.toml
# Global Azure OpenAI configuration
[testbench-ai-service.llm_config]
provider = "azure_openai"
azure_endpoint = "https://shared-resource.openai.azure.com"
api_version = "2025-04-01-preview"

[testbench-ai-service.llm_config.deployment_mapping]
"gpt-4o-tb" = "gpt-4o"

# Override for a specific project
[testbench-ai-service.projects."My Project".llm_config]
provider = "azure_openai"
azure_endpoint = "https://project-specific-resource.openai.azure.com"
api_version = "2025-04-01-preview"

[testbench-ai-service.projects."My Project".llm_config.deployment_mapping]
"gpt-4o-project" = "gpt-4o"
```

A **project-specific API key** can also be set via environment variable using the pattern `{NORMALIZED_PROJECT_NAME}_AZURE_OPENAI_API_KEY`, where the project name is uppercased and all non-alphanumeric characters are replaced with underscores:

```bash
# .env
# For a project named "My Project":
MY_PROJECT_AZURE_OPENAI_API_KEY=project-specific-azure-key
```

If a project-specific key is present the service creates a dedicated client for that project; otherwise the global `AZURE_OPENAI_API_KEY` is used.

When `auth_method = "entra_id"` is configured, a project can likewise use its
own service principal. All three variables must be set together:

```bash
# .env
# For a project named "My Project":
MY_PROJECT_AZURE_TENANT_ID=project_specific_tenant_id
MY_PROJECT_AZURE_CLIENT_ID=project_specific_client_id
MY_PROJECT_AZURE_CLIENT_SECRET=project_specific_secret
```

If none of the three are set, the project uses the global service principal. If
only some are set, the service reports an error naming the missing variables
rather than falling back — a partially configured project principal would
otherwise authenticate silently as an unintended identity.

:::warning
This check does not run at service startup for project overrides. The global
service principal is validated at startup, because the global Azure OpenAI
client is created then. Project credentials are resolved lazily, the first
time a request runs against that project — so the service starts cleanly even
with a half-configured project override, and the error only surfaces on that
project's first request.
:::

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `API key for provider 'azure_openai' not found` | `AZURE_OPENAI_API_KEY` is not set | Set the variable in your `.env` file or system environment |
| `'azure_endpoint' must be set for provider 'azure_openai'` | Missing endpoint in `config.toml` | Add `azure_endpoint` to `[testbench-ai-service.llm_config]` |
| `'api_version' must be set for provider 'azure_openai'` | Missing API version in `config.toml` | Add `api_version` to `[testbench-ai-service.llm_config]` |
| `DeploymentNotFound` from Azure API | Wrong deployment name in prompt variant | Verify the deployment name in Azure OpenAI Studio and update the prompt YAML |
| Empty or unexpected response | Deployment mapped to wrong canonical model | Check and correct the `deployment_mapping` in `config.toml` |
| `Entra ID authentication ... is incompletely configured` | One or two of the three service principal variables are missing | Set all of `AZURE_TENANT_ID`, `AZURE_CLIENT_ID` and `AZURE_CLIENT_SECRET` (or all three project-prefixed variants) |
| `'auth_method = entra_id' is only supported for provider 'azure_openai'` | `auth_method` set on a non-Azure provider | Remove `auth_method`, or set `provider = "azure_openai"` |
| `The 'azure-identity' package is required` | Running from source without the dependency installed | Run `pip install azure-identity` |
| `401 Unauthorized` / `403 Forbidden` with correct credentials | The app registration has no role on the Azure OpenAI resource | Assign the **Cognitive Services OpenAI User** role (step 4 above) |
| `ClientAuthenticationError: AADSTS7000215` | Invalid client secret, or the secret value was confused with the secret ID | Copy the secret **value** from **Certificates & secrets** |
| `ClientAuthenticationError` after months of working | The client secret expired | Create a new secret and update `AZURE_CLIENT_SECRET` |
