---
sidebar_position: 3
title: Test Case Set Describer
---

# Test Case Set Describer

Automatic generation of descriptive summaries for test case sets. The service analyzes the test case structure, steps, and parameters and writes a concise description back into the TestBench specification.

**Endpoint:** `POST /test-case-set-descriptions`

## How it works

1. The service retrieves all test case sets from the specified test-object-version (and optional cycle / subtree).
2. For each test case set, it checks that the **specification tab** is not locked by another user.
3. Items that pass the precheck are processed concurrently in the background:
   - The current description is saved as a backup.
   - A "generation started" marker is written.
   - Test case data (steps, parameters, parameter combinations) is rendered into the prompt template.
   - The prompt is sent to the configured LLM.
   - The AI-generated description is written to the description field of the test structure element specification.
   - If an error occurs, the previous description is restored.

## Configuration

### Default configuration

```toml
# config.toml
[testbench-ai-service.agents.test_case_set_describer]
enabled = true
endpoint_path = "/test-case-set-descriptions"
class_path = "testbench_ai_service.agents.test_case_set_describer.agent.TestCaseSetDescriber"
summary = "Trigger generation of test case set descriptions"
description = "Triggers asynchronous generation of descriptions for the specified test case sets."

[testbench-ai-service.agents.test_case_set_describer.prompt]
file = "test_case_set_describer.yaml"
name = "TestCaseSetDescriber"
```

### Prompt placeholders

The description prompt supports the following automatically populated placeholders:

| Placeholder | Description |
|-------------|-------------|
| `step_sequence` | Formatted string representation of the test case set (name, steps, parameters). |
| `parameter_combinations` | Formatted parameter combination table. |

### Project-specific override

```toml
# config.toml
[testbench-ai-service.projects."My Project".agents.test_case_set_describer]
enabled = false

[testbench-ai-service.projects."My Project".agents.test_case_set_describer.prompt]
variant = "my-custom-variant"
```

## Prompt variants

The built-in prompt file (`test_case_set_describer.yaml`) ships with variants for different description styles. See [Prompts](../prompts.md) for details on how to customize or create your own variants.
