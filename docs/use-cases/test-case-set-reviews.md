---
sidebar_position: 2
title: Test Case Set Reviews
---

# Test Case Set Reviews

AI-powered quality reviews of test case sets. The service analyzes test case structure, steps, parameters, and naming against best practices (ISTQB, ISO 29119) and writes the review notes back into the TestBench review comment section.

**Endpoint:** `POST /test-case-set-reviews`

## How It Works

1. The service retrieves all test case sets from the specified test-object-version (and optional cycle / subtree).
2. For each test case set, it checks that the **specification tab** is not locked by another user.
3. Items that pass the precheck are processed concurrently in the background:
   - The current review comment is saved as a backup.
   - A "review started" marker is written to the review comment.
   - Test case data (steps, parameters, parameter combinations) is rendered into the prompt template.
   - The prompt is sent to the configured LLM.
   - The AI response is written to the review comment section.
   - If an error occurs, the previous review comment is restored.

## Configuration

### Default Configuration

```toml
[testbench-ai-service.usecases.test_case_set_reviews]
enabled = true
endpoint_path = "/test-case-set-reviews"
class_path = "testbench_ai_service.usecases.test_case_set_reviews.service.TestCaseSetReviewer"
summary = "Trigger test case set reviews"
description = "Triggers asynchronous reviews for the specified test case sets."

[testbench-ai-service.usecases.test_case_set_reviews.prompt]
file = "test_case_set_reviews.yaml"
name = "TestCaseSetReviews"
```

### Prompt Placeholders

The review prompt supports the following automatically populated placeholders:

| Placeholder | Description |
|-------------|-------------|
| `test_case_set` | Formatted string representation of the test case set (name, steps, parameters) |
| `parameter_combinations` | Formatted parameter combination table |
| `description` | The existing test case set description (if any) |
| `glossary` | Contents of a glossary file (when configured via `placeholder_data`) |

### Optional: Glossary

You can provide a glossary file that the LLM uses as domain-specific context during the review. Configure it in the prompt section:

```toml
[testbench-ai-service.usecases.test_case_set_reviews.prompt]
file = "test_case_set_reviews.yaml"
name = "TestCaseSetReviews"
variant = "step-based-tests-detailed-prompt"
glossary = "glossary.txt"
```

### Project-Specific Override

```toml
[testbench-ai-service.projects."My Project".usecases.test_case_set_reviews]
enabled = false

[testbench-ai-service.projects."My Project".usecases.test_case_set_reviews.prompt]
variant = "simple-generic-prompt-no-glossary"
```

## Prompt Variants

The built-in prompt file (`test_case_set_reviews.yaml`) ships with variants tailored for different test case styles. Each variant specifies the LLM model and review criteria. See [Prompts](../prompts.md) for details on how to customize or create your own variants.
