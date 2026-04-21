---
sidebar_position: 2
title: Test Case Set Reviews
---

# Test Case Set Reviews

AI-powered quality reviews of test case sets. The service analyzes test case structure, steps, parameters, and naming against best practices (ISTQB, ISO 29119) and writes the review notes back into the TestBench review comment section.

**Endpoint:** `POST /test-case-set-reviews`

## How it works

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

### Default configuration

```toml
# config.toml
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

### Prompt placeholders

The review prompt supports the following automatically populated placeholders:

| Placeholder | Description |
|-------------|-------------|
| `test_case` | Formatted string representation of the test case set (name, steps, parameters). |
| `parameter_combinations` | Formatted parameter combination table. |
| `test_case_set_description` | The existing test case set description, if one is present (plain text, stripped of HTML). |
| `glossary` | Glossary content resolved from the `glossary` prompt config field (file path or inline text); falls back to a built-in default glossary. |

### Optional: glossary

You can provide a glossary file that the LLM uses as domain-specific context during the review. Configure it in the prompt section:

```toml
# config.toml
[testbench-ai-service.usecases.test_case_set_reviews.prompt]
file = "test_case_set_reviews.yaml"
name = "TestCaseSetReviews"
variant = "interaction-based-tests-detailed-prompt"
glossary = "glossary.txt"
```

```
# glossary.txt
- 'Start': Used for application startups. Examples: Start Application, Start Project Management
- 'Set': Used for text fields, checkboxes, or similar elements. Examples: Set Login, Set Description
- 'Click': Used for buttons, icons, or similar elements. Examples: Click Ok, Click Update
- 'Select': Used for radio buttons, tab pages, menu entries, or similar elements. Examples: Select Project Tab, Select Project Tree Element
- 'Remove': Used for checkboxes, specific assignments, or similar elements. Examples: Remove Rights Option, Remove Checkbox, Remove Requirements Assignment
- 'Open': Used for dialogs, context menus, or similar elements; not used for application startups. Examples: openProjectManagement, openProjectTreeContextMenu
- 'Check': Used for verifying the state of any component. Examples: Check Rights Allocation Is Editable, Check Activity Status
- 'Create': Used for creating business-related entities. Examples: Create Test Topic, Create User Assignment
- 'Delete': Used for deleting business-related entities. Examples: Delete Test Topic, Delete User
- 'Close': Used for closing dialogs or business-related processes. Examples: Close Variant Management, Close Issue List
- 'Expand' for tree structures. Examples: Expand project tree, Expand folder
- 'Collapse' for tree structures. Examples: Collapse project tree, Collapse folder
```

### Project-specific override

```toml
# config.toml
[testbench-ai-service.projects."My Project".usecases.test_case_set_reviews]
enabled = false

[testbench-ai-service.projects."My Project".usecases.test_case_set_reviews.prompt]
variant = "simple-generic-prompt-no-glossary"
```

## Prompt variants

The built-in prompt file (`test_case_set_reviews.yaml`) ships with variants tailored for different test case styles. Each variant specifies the LLM model and review criteria. See [Prompts](../prompts.md) for details on how to customize or create your own variants.
