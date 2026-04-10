---
sidebar_position: 4
title: Defect Explanations
---

# Defect Explanations

AI-generated explanations for defects found during test execution. The service analyzes failed test cases and writes human-readable explanations back into the TestBench execution overview comments.

**Endpoint:** `POST /defect-explanations`

## How It Works

1. The service retrieves all test case sets from the specified test-object-version and **cycle** (a `cycle_key` is required).
2. For each test case set, it checks that the **execution tab** is not locked by another user.
3. Items that pass the precheck are processed concurrently in the background:
   - Failed test cases are extracted from the execution comments.
   - For each failed test case, the test data and error message are rendered into the prompt template.
   - Each prompt is sent to the configured LLM.
   - All AI-generated explanations are aggregated and written to the comment section of the execution overview.

:::note
Unlike the other use cases, defect explanations require a `cycle_key` in the request. If `cycle_key` is not provided, the precheck fails with a `409 Conflict` response.
:::

## Configuration

### Default Configuration

```toml
[testbench-ai-service.usecases.defect_explanations]
enabled = true
endpoint_path = "/defect-explanations"
class_path = "testbench_ai_service.usecases.defect_explanations.service.DefectExplainer"
summary = "Trigger generation of defect explanations"
description = "Triggers asynchronous generation of defect explanations."

[testbench-ai-service.usecases.defect_explanations.prompt]
file = "defect_explanations.yaml"
name = "DefectExplanations"
```

### Prompt Placeholders

The defect explanation prompt supports the following automatically populated placeholders:

| Placeholder | Description |
|-------------|-------------|
| `failed_test_case` | Formatted string representation of the failed test case (name, steps, parameters) |
| `error_message` | The error message extracted from the failed test case |

### Project-Specific Override

```toml
[testbench-ai-service.projects."My Project".usecases.defect_explanations]
enabled = false

[testbench-ai-service.projects."My Project".usecases.defect_explanations.prompt]
variant = "my-custom-variant"
```

## Prompt Variants

The built-in prompt file (`defect_explanations.yaml`) ships with variants for different explanation styles. See [Prompts](../prompts.md) for details on how to customize or create your own variants.
