# Admin Web UI — Phase 4c (Live Test Run and Model Catalogue) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an operator run the prompt they are editing against a real model, pick from a catalogue derived from the LLM clients' own routing sets, and add models to that catalogue from the LLM provider view.

**Architecture:** Two new read/act routes (`GET /models`, `POST /prompts/test`) plus one new `LLMConfig` field (`extra_models`) edited through the LLM provider view's existing draft → preview → apply flow. The catalogue is *derived* from the four frozensets the LLM clients already dispatch on, never retyped. The test run renders the editor's unsaved draft through the existing sandboxed renderer, resolves its client through the production `get_llm_config` + `LLMFactory` path, and is bounded by a single-flight lock, a console-owned timeout, and a credential scrubber.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic v2, pytest + pytest-asyncio + pytest-mock, ruff (line-length 100). Frontend: React + TypeScript, vitest + @testing-library/react, TanStack Query.

**Spec:** `.superpowers/sdd/2026-09-14-admin-web-ui-phase-4c/design.md` (read it; it is the binding authority and every decision reference below — D1…D11, §3.1…§9 — points into it)

## Global Constraints

- **No test may make a real outbound LLM call.** Every test that reaches a client uses a fake or `AsyncMock`. A test that hit a provider would cost money and fail offline.
- **Presence, never values.** No route may return the contents of an environment variable. `key_present: bool` is the only credential fact the catalogue exposes (§3.4).
- Python line length **100** (`ruff`, `pyproject.toml:101`). Run `python -m ruff check` and `python -m ruff format --check` on every file you touch before committing.
- Backend tests live under `tests/unit/webui/` (console) and `tests/unit/llm/` (clients), matching the module they cover.
- Frontend strings must be added to **both** `frontend/src/i18n/en.ts` and `frontend/src/i18n/de.ts` — `i18n.test.ts` fails the build on any key present in one and not the other.
- Mutating console routes require admin **and** CSRF. `GET /models` and `POST /prompts/test` are both admin + CSRF (§5.1).
- Commit after every task. Never skip hooks.

---

### Task 1: The routing family and the derived built-in map

Creates the vocabulary the whole increment shares: a `RoutingFamily` enum in `llm/base.py` (which imports nothing heavy, so every other module can import it freely) and `llm/routing.py`, the single derived view over the four frozensets (§3.3).

`llm/routing.py` imports the two client modules. Nothing in `llm/openai.py` or `llm/anthropic.py` may import `llm/routing.py` back — that would be a cycle. The clients keep their own frozenset checks (Task 4).

**Files:**
- Modify: `testbench_ai_service/llm/base.py`
- Create: `testbench_ai_service/llm/routing.py`
- Test: `tests/unit/llm/test_routing.py`

**Interfaces:**
- Consumes: `LLMProvider` (existing, `llm/base.py`); `CHAT_MODELS`, `REASONING_MODELS` (`llm/openai.py:23,54`); `BUDGET_THINKING_MODELS`, `ADAPTIVE_THINKING_MODELS` (`llm/anthropic.py:14,27`)
- Produces:
  - `RoutingFamily(str, Enum)` with members `CHAT="chat"`, `REASONING="reasoning"`, `ADAPTIVE="adaptive"`, `BUDGET="budget"`, `FALLBACK="fallback"` — in `llm/base.py`
  - `BUILTIN_ROUTING: dict[str, RoutingFamily]` — in `llm/routing.py`
  - `builtin_routing(model: str) -> RoutingFamily | None`
  - `builtin_models_by_provider() -> dict[LLMProvider, dict[str, RoutingFamily]]`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/llm/test_routing.py`:

```python
from testbench_ai_service.llm.anthropic import (
    ADAPTIVE_THINKING_MODELS,
    BUDGET_THINKING_MODELS,
)
from testbench_ai_service.llm.base import LLMProvider, RoutingFamily
from testbench_ai_service.llm.openai import CHAT_MODELS, REASONING_MODELS
from testbench_ai_service.llm.routing import (
    BUILTIN_ROUTING,
    builtin_models_by_provider,
    builtin_routing,
)


class TestBuiltinRouting:
    def test_every_set_member_is_mapped(self):
        expected = (
            CHAT_MODELS | REASONING_MODELS | BUDGET_THINKING_MODELS | ADAPTIVE_THINKING_MODELS
        )
        assert set(BUILTIN_ROUTING) == expected

    def test_each_set_maps_to_its_own_family(self):
        assert BUILTIN_ROUTING["gpt-4o"] is RoutingFamily.CHAT
        assert BUILTIN_ROUTING["o3"] is RoutingFamily.REASONING
        assert BUILTIN_ROUTING["claude-haiku-4-5"] is RoutingFamily.BUDGET
        assert BUILTIN_ROUTING["claude-opus-4-6"] is RoutingFamily.ADAPTIVE

    def test_an_unknown_model_is_not_mapped(self):
        assert builtin_routing("no-such-model-9000") is None

    def test_lookup_matches_the_table(self):
        assert builtin_routing("gpt-4o") is RoutingFamily.CHAT


class TestBuiltinModelsByProvider:
    def test_openai_sets_land_under_openai(self):
        by_provider = builtin_models_by_provider()
        assert CHAT_MODELS | REASONING_MODELS == set(by_provider[LLMProvider.OPENAI])

    def test_anthropic_sets_land_under_anthropic(self):
        by_provider = builtin_models_by_provider()
        expected = BUDGET_THINKING_MODELS | ADAPTIVE_THINKING_MODELS
        assert expected == set(by_provider[LLMProvider.ANTHROPIC])

    def test_azure_and_custom_contribute_nothing(self):
        # Design 3.9: Azure dispatches on the canonical name after
        # deployment_mapping, which is per-installation data; CUSTOM loads an
        # arbitrary class. Neither can be enumerated here.
        by_provider = builtin_models_by_provider()
        assert by_provider[LLMProvider.AZURE_OPENAI] == {}
        assert by_provider[LLMProvider.CUSTOM] == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/llm/test_routing.py -v`
Expected: FAIL — `ImportError: cannot import name 'RoutingFamily'`

- [ ] **Step 3: Add `RoutingFamily` to `llm/base.py`**

Insert after the existing `AzureAuthMethod` enum:

```python
class RoutingFamily(str, Enum):
    """How a client shapes the request for a given model.

    Lives in ``base`` rather than in ``routing`` so the clients can name a
    family without importing ``routing``, which imports them back.
    """

    CHAT = "chat"
    REASONING = "reasoning"
    ADAPTIVE = "adaptive"
    BUDGET = "budget"
    FALLBACK = "fallback"

    def __str__(self):
        return self.value
```

- [ ] **Step 4: Write `llm/routing.py`**

```python
"""The models each client knows how to call, as one derived table.

**This module writes down no model names.** It reads the four frozensets the
clients already dispatch on, so "which models exist" and "which models route
properly" cannot drift apart (design D7). Adding a model to a client's set is
the single act that both routes it and lists it.

Import direction is one-way: this module imports the clients, never the other
way round. A client that needs to name a family imports ``RoutingFamily`` from
``llm.base``, which imports nothing of ours.
"""

from testbench_ai_service.llm.anthropic import (
    ADAPTIVE_THINKING_MODELS,
    BUDGET_THINKING_MODELS,
)
from testbench_ai_service.llm.base import LLMProvider, RoutingFamily
from testbench_ai_service.llm.openai import CHAT_MODELS, REASONING_MODELS

#: Every built-in model, mapped to the branch its client would take.
BUILTIN_ROUTING: dict[str, RoutingFamily] = {
    **{model: RoutingFamily.CHAT for model in CHAT_MODELS},
    **{model: RoutingFamily.REASONING for model in REASONING_MODELS},
    **{model: RoutingFamily.BUDGET for model in BUDGET_THINKING_MODELS},
    **{model: RoutingFamily.ADAPTIVE for model in ADAPTIVE_THINKING_MODELS},
}


def builtin_routing(model: str) -> RoutingFamily | None:
    """The family *model* routes to, or None when no client claims it."""
    return BUILTIN_ROUTING.get(model)


def builtin_models_by_provider() -> dict[LLMProvider, dict[str, RoutingFamily]]:
    """The built-in catalogue, grouped by the provider that serves it.

    Azure OpenAI and CUSTOM are present and empty rather than absent: both are
    real providers whose model list is per-installation (design 3.9), and a
    caller iterating this map should see them as "nothing built in" rather
    than have to know they were skipped.
    """
    return {
        LLMProvider.OPENAI: {
            **{model: RoutingFamily.CHAT for model in CHAT_MODELS},
            **{model: RoutingFamily.REASONING for model in REASONING_MODELS},
        },
        LLMProvider.ANTHROPIC: {
            **{model: RoutingFamily.BUDGET for model in BUDGET_THINKING_MODELS},
            **{model: RoutingFamily.ADAPTIVE for model in ADAPTIVE_THINKING_MODELS},
        },
        LLMProvider.AZURE_OPENAI: {},
        LLMProvider.CUSTOM: {},
    }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/unit/llm/test_routing.py -v`
Expected: PASS (9 tests)

- [ ] **Step 6: Lint and commit**

```bash
python -m ruff check testbench_ai_service/llm/base.py testbench_ai_service/llm/routing.py tests/unit/llm/test_routing.py
python -m ruff format --check testbench_ai_service/llm/base.py testbench_ai_service/llm/routing.py tests/unit/llm/test_routing.py
git add testbench_ai_service/llm/base.py testbench_ai_service/llm/routing.py tests/unit/llm/test_routing.py
git commit -m "Derive one routing table from the clients' model sets"
```

---

### Task 2: `extra_models` on `LLMConfig`, with its validation

The operator-supplied half of the catalogue (D10). It goes on `LLMConfig` — **not** `AppConfig` — because `LLMFactory.get_client` only ever receives an `LLMConfig` and `_get_common_client_kwargs` is the only channel into a client constructor (§5.3). That also puts it inside `[testbench-ai-service.llm_config]`, the table the LLM provider view already edits.

`builtin_routing` is imported **inside** the validator, not at module scope: `models/config.py` is imported early and everywhere, and a module-scope import would drag the OpenAI and Anthropic SDKs into that import graph. (4b's Task 4 established this function-local pattern for the same reason.)

**Files:**
- Modify: `testbench_ai_service/models/config.py`
- Test: `tests/unit/test_models_config.py`

**Interfaces:**
- Consumes: `RoutingFamily` (Task 1, `llm/base.py`), `builtin_routing` (Task 1, `llm/routing.py`), `LLMProvider` (existing)
- Produces:
  - `ExtraModel(BaseModel)` with `provider: LLMProvider` and `routing: RoutingFamily`
  - `LLMConfig.extra_models: dict[str, ExtraModel]` defaulting to `{}`
  - `ALLOWED_ROUTING: dict[LLMProvider, frozenset[RoutingFamily]]`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_models_config.py`:

```python
import pytest
from pydantic import ValidationError

from testbench_ai_service.llm.base import LLMProvider, RoutingFamily
from testbench_ai_service.models.config import ExtraModel, LLMConfig


class TestExtraModels:
    def test_defaults_to_empty(self):
        assert LLMConfig().extra_models == {}

    def test_accepts_a_valid_anthropic_entry(self):
        config = LLMConfig(
            extra_models={"claude-opus-6": {"provider": "anthropic", "routing": "adaptive"}}
        )
        entry = config.extra_models["claude-opus-6"]
        assert entry.provider is LLMProvider.ANTHROPIC
        assert entry.routing is RoutingFamily.ADAPTIVE

    def test_accepts_a_valid_openai_entry(self):
        config = LLMConfig(
            extra_models={"gpt-6": {"provider": "openai", "routing": "reasoning"}}
        )
        assert config.extra_models["gpt-6"].routing is RoutingFamily.REASONING

    @pytest.mark.parametrize(
        ("provider", "routing"),
        [
            ("anthropic", "chat"),
            ("anthropic", "reasoning"),
            ("openai", "adaptive"),
            ("openai", "budget"),
            ("azure_openai", "budget"),
            ("custom", "chat"),
            ("custom", "adaptive"),
        ],
    )
    def test_refuses_a_routing_family_the_provider_cannot_use(self, provider, routing):
        with pytest.raises(ValidationError) as excinfo:
            LLMConfig(extra_models={"m": {"provider": provider, "routing": routing}})
        assert "extra_models" in str(excinfo.value)

    @pytest.mark.parametrize(
        ("provider", "routing"),
        [
            ("anthropic", "fallback"),
            ("openai", "fallback"),
            ("azure_openai", "chat"),
            ("azure_openai", "reasoning"),
            ("custom", "fallback"),
        ],
    )
    def test_allows_every_family_its_provider_can_use(self, provider, routing):
        config = LLMConfig(extra_models={"m": {"provider": provider, "routing": routing}})
        assert config.extra_models["m"].routing is RoutingFamily(routing)

    def test_refuses_an_entry_that_shadows_a_builtin(self):
        # gpt-4o is in CHAT_MODELS; letting config redefine it would let a typo
        # silently change how a shipped model is called (design 6, 9).
        with pytest.raises(ValidationError) as excinfo:
            LLMConfig(extra_models={"gpt-4o": {"provider": "openai", "routing": "reasoning"}})
        assert "gpt-4o" in str(excinfo.value)

    def test_the_error_path_reaches_the_offending_row(self):
        # ConfigSection matches issues by path prefix, so a table-level loc
        # would mark every row instead of the broken one (design 5.3). Task 12
        # renders against exactly this path.
        with pytest.raises(ValidationError) as excinfo:
            LLMConfig(extra_models={"m": {"provider": "anthropic", "routing": "chat"}})
        assert excinfo.value.errors()[0]["loc"] == ("extra_models", "m", "routing")

    def test_a_shadow_error_names_the_offending_entry(self):
        with pytest.raises(ValidationError) as excinfo:
            LLMConfig(extra_models={"gpt-4o": {"provider": "openai", "routing": "chat"}})
        assert excinfo.value.errors()[0]["loc"] == ("extra_models", "gpt-4o")

    def test_the_field_is_declared_so_it_cannot_leak_into_a_provider_request(self):
        # agents/base.py:92 spreads **(llm_config.model_extra or {}) into
        # query_llm. A declared field stays out of model_extra; an undeclared
        # one would be sent to the provider as a request parameter.
        config = LLMConfig(
            extra_models={"claude-opus-6": {"provider": "anthropic", "routing": "adaptive"}}
        )
        assert "extra_models" not in (config.model_extra or {})


class TestExtraModelStandalone:
    def test_requires_both_fields(self):
        with pytest.raises(ValidationError):
            ExtraModel(provider="openai")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_models_config.py -k ExtraModel -v`
Expected: FAIL — `ImportError: cannot import name 'ExtraModel'`

- [ ] **Step 3: Implement in `models/config.py`**

Add the import at the top, alongside the existing `llm.base` import:

```python
from testbench_ai_service.llm.base import AzureAuthMethod, LLMProvider, RoutingFamily
```

Add above `class LLMConfig`:

```python
#: Which request shapes each provider's client can actually produce.
#: AZURE_OPENAI shares OpenAI's two branches (it dispatches on the canonical
#: name after deployment_mapping); CUSTOM implements its own dispatch, so
#: "fallback" is the only honest answer for it.
ALLOWED_ROUTING: dict[LLMProvider, frozenset[RoutingFamily]] = {
    LLMProvider.OPENAI: frozenset(
        {RoutingFamily.CHAT, RoutingFamily.REASONING, RoutingFamily.FALLBACK}
    ),
    LLMProvider.AZURE_OPENAI: frozenset(
        {RoutingFamily.CHAT, RoutingFamily.REASONING, RoutingFamily.FALLBACK}
    ),
    LLMProvider.ANTHROPIC: frozenset(
        {RoutingFamily.ADAPTIVE, RoutingFamily.BUDGET, RoutingFamily.FALLBACK}
    ),
    LLMProvider.CUSTOM: frozenset({RoutingFamily.FALLBACK}),
}


class ExtraModel(BaseModel):
    """One operator-supplied catalogue entry.

    ``routing`` is not decoration: it is the branch the client will take for
    this model. Without it a newly added model falls through to
    ``_query_fallback_model`` -- no thinking, no effort, max_tokens 4096 --
    which is the opposite of what an operator adding a new flagship wants
    (design D10).
    """

    provider: LLMProvider
    routing: RoutingFamily
```

Add the field to `LLMConfig`, after `max_retries`:

```python
    extra_models: dict[str, ExtraModel] = Field(
        default_factory=dict,
        description=(
            "Models to offer in the console beyond those the clients already route, "
            "keyed by model name. Each entry names its provider and the request shape "
            "the client should use for it."
        ),
    )
```

Add this validation inside the existing `validate_config` `model_validator`, before its `return self`:

```python
        # Imported here rather than at module scope: llm.routing imports both
        # client modules (and their SDKs), and models/config.py is imported by
        # nearly everything. Keeping it function-local keeps that weight out of
        # the common import path. Same pattern as 4b's template_refs import.
        from testbench_ai_service.llm.routing import builtin_routing

        for name, entry in self.extra_models.items():
            allowed = ALLOWED_ROUTING[entry.provider]
            if entry.routing not in allowed:
                # Full loc tuple, not the bare field name: the console renders a
                # ConfigIssue against the offending ROW (design 5.3), which needs
                # the model name and the field in the path. Same shape as
                # config.py:336's ("projects", ..., "prompt", "file").
                raise_field_validation_error(
                    self,
                    ("extra_models", name, "routing"),
                    ValueError(
                        f"'{name}': routing '{entry.routing}' is not available for provider "
                        f"'{entry.provider}'. Allowed: "
                        f"{', '.join(sorted(family.value for family in allowed))}."
                    ),
                )
            if builtin_routing(name) is not None:
                # The whole entry is the problem here, not one of its fields.
                raise_field_validation_error(
                    self,
                    ("extra_models", name),
                    ValueError(
                        f"'{name}' is already routed by its client and cannot be redefined "
                        "here. Remove the entry; the model is offered automatically."
                    ),
                )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_models_config.py -v`
Expected: PASS

- [ ] **Step 5: Run the full config + model suite for regressions**

Run: `python -m pytest tests/unit/test_config.py tests/unit/test_models_config.py tests/unit/webui -q`
Expected: PASS — no existing test constructs an `LLMConfig` this change breaks

- [ ] **Step 6: Lint and commit**

```bash
python -m ruff check testbench_ai_service/models/config.py tests/unit/test_models_config.py
python -m ruff format --check testbench_ai_service/models/config.py tests/unit/test_models_config.py
git add testbench_ai_service/models/config.py tests/unit/test_models_config.py
git commit -m "Let config declare models the clients do not know"
```

---

### Task 3: Teach the Anthropic client the current model generation (D8)

A frozenset addition, not a behaviour change. `claude-opus-5`, `claude-sonnet-5` and `claude-fable-5-1` take `thinking: {type: "adaptive"}` and `output_config.effort`, exactly what `_query_adaptive_thinking_model` already sends — and `claude-haiku-4-5` correctly stays in the budget set, because it is the one current model that still takes `budget_tokens`.

Without this the three current Claude models fall to `_query_fallback_model` (§3.3): a WARNING log, no thinking, and `max_tokens` capped at 4096 instead of 16000. Once Task 6 derives the catalogue from these sets, a missing entry also means the console cannot offer the model at all.

**Files:**
- Modify: `testbench_ai_service/llm/anthropic.py:27-34`
- Test: `tests/unit/llm/test_anthropic_routing.py`

**Interfaces:**
- Consumes: nothing new
- Produces: `ADAPTIVE_THINKING_MODELS` additionally contains `claude-opus-5`, `claude-sonnet-5`, `claude-fable-5-1`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/llm/test_anthropic_routing.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from testbench_ai_service.llm.anthropic import (
    ADAPTIVE_THINKING_MODELS,
    BUDGET_THINKING_MODELS,
    AnthropicClient,
)
from testbench_ai_service.models.prompt import Message

CURRENT_ADAPTIVE = ["claude-opus-5", "claude-sonnet-5", "claude-fable-5-1"]


def _client() -> AnthropicClient:
    with patch("testbench_ai_service.llm.anthropic.AsyncAnthropic"):
        return AnthropicClient(api_key="k")


def _text_response(text: str = "hi") -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


class TestCurrentGenerationIsRouted:
    @pytest.mark.parametrize("model", CURRENT_ADAPTIVE)
    def test_is_in_the_adaptive_set(self, model):
        assert model in ADAPTIVE_THINKING_MODELS

    def test_haiku_stays_on_the_budget_path(self):
        # Haiku 4.5 is the one current model that still takes budget_tokens.
        assert "claude-haiku-4-5" in BUDGET_THINKING_MODELS
        assert "claude-haiku-4-5" not in ADAPTIVE_THINKING_MODELS

    def test_the_two_sets_stay_disjoint(self):
        assert not (BUDGET_THINKING_MODELS & ADAPTIVE_THINKING_MODELS)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("model", CURRENT_ADAPTIVE)
    async def test_sends_adaptive_thinking_not_the_fallback_shape(self, model):
        client = _client()
        client.client.messages.create = AsyncMock(return_value=_text_response())

        await client.query_llm(model=model, messages=[Message(role="user", content="q")])

        kwargs = client.client.messages.create.call_args.kwargs
        assert kwargs["thinking"] == {"type": "adaptive"}
        assert kwargs["output_config"] == {"effort": "high"}
        # The fallback path would have left max_tokens at _create_response's 4096.
        assert kwargs["max_tokens"] == 16000

    @pytest.mark.asyncio
    @patch("testbench_ai_service.llm.anthropic.logger")
    async def test_does_not_warn_about_an_unsupported_model(self, mock_logger):
        client = _client()
        client.client.messages.create = AsyncMock(return_value=_text_response())

        await client.query_llm(
            model="claude-opus-5", messages=[Message(role="user", content="q")]
        )

        warnings = " ".join(str(call) for call in mock_logger.warning.call_args_list)
        assert "not explicitly supported" not in warnings
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/llm/test_anthropic_routing.py -v`
Expected: FAIL — `assert 'claude-opus-5' in ADAPTIVE_THINKING_MODELS`

- [ ] **Step 3: Add the three models**

In `testbench_ai_service/llm/anthropic.py`, extend `ADAPTIVE_THINKING_MODELS` so it reads:

```python
ADAPTIVE_THINKING_MODELS: frozenset[str] = frozenset(
    {
        "claude-fable-5-1",
        "claude-opus-4-6",
        "claude-opus-4-7",
        "claude-opus-4-8",
        "claude-opus-5",
        "claude-sonnet-4-6",
        "claude-sonnet-5",
    }
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/llm/test_anthropic_routing.py -v`
Expected: PASS

- [ ] **Step 5: Confirm Task 1's derived table picked them up**

Run: `python -m pytest tests/unit/llm/test_routing.py -v`
Expected: PASS — `test_every_set_member_is_mapped` now covers the three new ids with no change to `routing.py`

- [ ] **Step 6: Lint and commit**

```bash
python -m ruff check testbench_ai_service/llm/anthropic.py tests/unit/llm/test_anthropic_routing.py
python -m ruff format --check testbench_ai_service/llm/anthropic.py tests/unit/llm/test_anthropic_routing.py
git add testbench_ai_service/llm/anthropic.py tests/unit/llm/test_anthropic_routing.py
git commit -m "Route the current Claude generation as adaptive-thinking"
```

---

### Task 4: Clients dispatch on a routing map, config first (D11)

The narrowest shape that works: one lookup at the top of each `query_llm`, dispatching on a resolved family instead of testing set membership inline. The four `_query_*` methods are untouched and `LLMClient`'s interface is untouched.

The client receives `dict[str, RoutingFamily]` — not `dict[str, ExtraModel]` — because it already knows its own provider and must not import `models/config.py`.

**Files:**
- Modify: `testbench_ai_service/llm/anthropic.py` (`__init__`, `query_llm`)
- Modify: `testbench_ai_service/llm/openai.py` (`OpenAIClient.__init__`, `OpenAIClient.query_llm`, `AzureOpenAIClient.__init__`, `AzureOpenAIClient.query_llm`)
- Test: `tests/unit/llm/test_model_routing_override.py`

**Interfaces:**
- Consumes: `RoutingFamily` (Task 1)
- Produces: every client accepts `model_routing: dict[str, RoutingFamily] | None = None`; `query_llm` resolves `model_routing` first, then its own frozensets, then `FALLBACK`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/llm/test_model_routing_override.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from testbench_ai_service.llm.anthropic import AnthropicClient
from testbench_ai_service.llm.base import RoutingFamily
from testbench_ai_service.llm.openai import AzureOpenAIClient, OpenAIClient
from testbench_ai_service.models.prompt import Message

MESSAGES = [Message(role="user", content="q")]


def _anthropic(model_routing=None) -> AnthropicClient:
    with patch("testbench_ai_service.llm.anthropic.AsyncAnthropic"):
        return AnthropicClient(api_key="k", model_routing=model_routing)


def _openai(model_routing=None) -> OpenAIClient:
    with patch("testbench_ai_service.llm.openai.AsyncOpenAI"):
        return OpenAIClient(api_key="k", model_routing=model_routing)


def _azure(model_routing=None, deployment_mapping=None) -> AzureOpenAIClient:
    with patch("testbench_ai_service.llm.openai.AsyncAzureOpenAI"):
        return AzureOpenAIClient(
            api_key="k",
            azure_endpoint="https://example.invalid/",
            api_version="2024-02-01",
            deployment_mapping=deployment_mapping,
            model_routing=model_routing,
        )


def _anthropic_text() -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = "hi"
    response = MagicMock()
    response.content = [block]
    return response


class TestAnthropicRoutingOverride:
    @pytest.mark.asyncio
    async def test_config_routes_a_model_the_frozensets_never_heard_of(self):
        client = _anthropic({"claude-opus-6": RoutingFamily.ADAPTIVE})
        client.client.messages.create = AsyncMock(return_value=_anthropic_text())

        await client.query_llm(model="claude-opus-6", messages=MESSAGES)

        kwargs = client.client.messages.create.call_args.kwargs
        assert kwargs["thinking"] == {"type": "adaptive"}

    @pytest.mark.asyncio
    async def test_an_unmapped_model_still_falls_back(self):
        client = _anthropic({})
        client.client.messages.create = AsyncMock(return_value=_anthropic_text())

        await client.query_llm(model="claude-unknown", messages=MESSAGES)

        kwargs = client.client.messages.create.call_args.kwargs
        assert "thinking" not in kwargs

    @pytest.mark.asyncio
    async def test_the_frozensets_still_apply_when_no_map_is_given(self):
        client = _anthropic(None)
        client.client.messages.create = AsyncMock(return_value=_anthropic_text())

        await client.query_llm(model="claude-opus-4-6", messages=MESSAGES)

        kwargs = client.client.messages.create.call_args.kwargs
        assert kwargs["thinking"] == {"type": "adaptive"}


class TestOpenAIRoutingOverride:
    @pytest.mark.asyncio
    async def test_config_routes_an_unknown_model_as_reasoning(self):
        client = _openai({"gpt-6": RoutingFamily.REASONING})
        response = AsyncMock()
        response.output_text = "hi"
        client.client.responses.create = AsyncMock(return_value=response)

        await client.query_llm(model="gpt-6", messages=MESSAGES)

        assert client.client.responses.create.await_count == 1


class TestAzureRoutingOverride:
    @pytest.mark.asyncio
    async def test_an_entry_may_name_the_deployment(self):
        client = _azure({"my-deployment": RoutingFamily.REASONING})
        response = AsyncMock()
        response.output_text = "hi"
        client.client.responses.create = AsyncMock(return_value=response)

        await client.query_llm(model="my-deployment", messages=MESSAGES)

        assert client.client.responses.create.await_count == 1

    @pytest.mark.asyncio
    async def test_an_entry_may_name_the_canonical_target(self):
        client = _azure(
            {"gpt-6": RoutingFamily.REASONING},
            deployment_mapping={"my-deployment": "gpt-6"},
        )
        response = AsyncMock()
        response.output_text = "hi"
        client.client.responses.create = AsyncMock(return_value=response)

        await client.query_llm(model="my-deployment", messages=MESSAGES)

        assert client.client.responses.create.await_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/llm/test_model_routing_override.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'model_routing'`

- [ ] **Step 3: Implement in `llm/anthropic.py`**

Import `RoutingFamily`:

```python
from testbench_ai_service.llm.base import LLMClient, RoutingFamily
```

Add the parameter to `AnthropicClient.__init__` (after `_strict_response_validation`) and store it:

```python
        model_routing: dict[str, RoutingFamily] | None = None,
    ):
        self.model_routing = model_routing or {}
```

Add the resolver as a method on the class:

```python
    def _routing_family(self, model: str) -> RoutingFamily:
        """Config first, then this client's own sets (design D11).

        The frozensets keep their meaning -- they become the default answer
        rather than the only one.
        """
        configured = self.model_routing.get(model)
        if configured is not None:
            return configured
        if model in BUDGET_THINKING_MODELS:
            return RoutingFamily.BUDGET
        if model in ADAPTIVE_THINKING_MODELS:
            return RoutingFamily.ADAPTIVE
        return RoutingFamily.FALLBACK
```

Replace the dispatch in `query_llm` (the two `if model in ...` blocks) with:

```python
        family = self._routing_family(model)

        if family is RoutingFamily.BUDGET:
            return await self._query_budget_thinking_model(
                model=model,
                input_messages=anthropic_messages,
                system_prompt=system_prompt,
                reasoning_effort=kwargs.get("reasoning_effort", "medium"),
                **kwargs,
            )

        if family is RoutingFamily.ADAPTIVE:
            return await self._query_adaptive_thinking_model(
                model=model,
                input_messages=anthropic_messages,
                system_prompt=system_prompt,
                reasoning_effort=kwargs.get("reasoning_effort", "high"),
                **kwargs,
            )

        return await self._query_fallback_model(model, anthropic_messages, system_prompt, **kwargs)
```

- [ ] **Step 4: Implement in `llm/openai.py`**

Import `RoutingFamily` alongside the existing `LLMClient` import. Add `model_routing: dict[str, RoutingFamily] | None = None` to both `OpenAIClient.__init__` and `AzureOpenAIClient.__init__`, storing `self.model_routing = model_routing or {}` in each.

Add to `OpenAIClient`:

```python
    def _routing_family(self, model: str) -> RoutingFamily:
        configured = self.model_routing.get(model)
        if configured is not None:
            return configured
        if model in CHAT_MODELS:
            return RoutingFamily.CHAT
        if model in REASONING_MODELS:
            return RoutingFamily.REASONING
        return RoutingFamily.FALLBACK
```

and dispatch on it in `OpenAIClient.query_llm`:

```python
        family = self._routing_family(model)
        if family is RoutingFamily.CHAT:
            return await self._query_chat_model(model, input_messages)
        if family is RoutingFamily.REASONING:
            return await self._query_reasoning_model(
                model=model,
                input_messages=input_messages,
                reasoning_effort=kwargs.get("reasoning_effort", "medium"),
            )
        return await self._query_fallback_model(model, input_messages, **kwargs)
```

In `AzureOpenAIClient.query_llm`, resolve against the deployment name **and** its canonical target, then fall back to the canonical name's sets:

```python
        canonical_model = self.deployment_mapping.get(model, model)
        ...
        family = (
            self.model_routing.get(model)
            or self.model_routing.get(canonical_model)
        )
        if family is None:
            if canonical_model in CHAT_MODELS:
                family = RoutingFamily.CHAT
            elif canonical_model in REASONING_MODELS:
                family = RoutingFamily.REASONING
            else:
                family = RoutingFamily.FALLBACK

        if family is RoutingFamily.CHAT:
            return await self._query_chat_model(model, input_messages)
        if family is RoutingFamily.REASONING:
            return await self._query_reasoning_model(
                model=model,
                input_messages=input_messages,
                reasoning_effort=kwargs.get("reasoning_effort", "medium"),
            )
        return await self._query_fallback_model(model, input_messages, **kwargs)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/unit/llm -v`
Expected: PASS — including the pre-existing `test_openai.py` dispatch tests, which must be unaffected

- [ ] **Step 6: Lint and commit**

```bash
python -m ruff check testbench_ai_service/llm/ tests/unit/llm/
python -m ruff format --check testbench_ai_service/llm/ tests/unit/llm/
git add testbench_ai_service/llm/anthropic.py testbench_ai_service/llm/openai.py tests/unit/llm/test_model_routing_override.py
git commit -m "Let configured routing win over the clients' own model sets"
```

---

### Task 5: The factory hands each client its routing map

`_get_common_client_kwargs` is the only channel into every client constructor, so the map travels the same way `timeout` and `max_retries` already do. It gains a `provider` parameter, because the map must be filtered to the provider being built — an OpenAI entry must never reach the Anthropic client.

Forwarded **only when non-empty**, which keeps the default path byte-identical for third-party `CUSTOM` clients that may not accept the kwarg.

**Files:**
- Modify: `testbench_ai_service/llm/factory.py:248` (`_get_common_client_kwargs`) and its call site in `_create_client`
- Test: `tests/unit/llm/test_factory.py`

**Interfaces:**
- Consumes: `LLMConfig.extra_models` (Task 2), `model_routing` client kwarg (Task 4)
- Produces: `LLMFactory._get_common_client_kwargs(config: LLMConfig, provider: LLMProvider) -> dict[str, Any]`; `LLMFactory.has_project_credential(project_name: str, provider: LLMProvider, config: LLMConfig) -> bool`; `LLMFactory.resolve_provider(config: LLMConfig, prompt_model: str | None) -> LLMProvider`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/llm/test_factory.py`:

```python
from testbench_ai_service.llm.base import LLMProvider, RoutingFamily
from testbench_ai_service.llm.factory import LLMFactory
from testbench_ai_service.models.config import LLMConfig


class TestModelRoutingForwarding:
    def test_nothing_is_forwarded_when_no_extra_models_are_configured(self):
        factory = LLMFactory()
        kwargs = factory._get_common_client_kwargs(LLMConfig(), LLMProvider.OPENAI)
        assert "model_routing" not in kwargs

    def test_only_this_provider_s_entries_are_forwarded(self):
        config = LLMConfig(
            extra_models={
                "gpt-6": {"provider": "openai", "routing": "reasoning"},
                "claude-opus-6": {"provider": "anthropic", "routing": "adaptive"},
            }
        )
        factory = LLMFactory()

        openai_kwargs = factory._get_common_client_kwargs(config, LLMProvider.OPENAI)
        anthropic_kwargs = factory._get_common_client_kwargs(config, LLMProvider.ANTHROPIC)

        assert openai_kwargs["model_routing"] == {"gpt-6": RoutingFamily.REASONING}
        assert anthropic_kwargs["model_routing"] == {"claude-opus-6": RoutingFamily.ADAPTIVE}

    def test_declared_fields_still_do_not_leak_into_query_kwargs(self):
        # extra_models is declared, so it is not in model_extra and therefore
        # never spread into query_llm by agents/base.py:92.
        config = LLMConfig(
            extra_models={"gpt-6": {"provider": "openai", "routing": "reasoning"}}
        )
        assert "extra_models" not in (config.model_extra or {})


class TestResolveProvider:
    def test_delegates_to_the_private_resolver(self):
        factory = LLMFactory()
        config = LLMConfig(provider=LLMProvider.OPENAI)
        assert factory.resolve_provider(config, "claude-opus-5") is LLMProvider.ANTHROPIC
        assert factory.resolve_provider(config, "gpt-4o") is LLMProvider.OPENAI

    def test_falls_back_to_the_configured_provider(self):
        # class_path is required for CUSTOM by LLMConfig's own validator, and is
        # inert here: _resolve_provider reads only prompt_model and provider.
        factory = LLMFactory()
        config = LLMConfig(
            provider=LLMProvider.CUSTOM,
            class_path="testbench_ai_service.llm.openai.OpenAIClient",
        )
        assert factory.resolve_provider(config, "something-unknown") is LLMProvider.CUSTOM


class TestHasProjectCredential:
    def test_true_when_the_project_variable_is_set(self, monkeypatch):
        monkeypatch.setenv("CAR_CONFIGURATOR_OPENAI_API_KEY", "sk-project")
        factory = LLMFactory()
        assert factory.has_project_credential(
            "Car Configurator", LLMProvider.OPENAI, LLMConfig()
        )

    def test_false_when_only_the_global_variable_is_set(self, monkeypatch):
        monkeypatch.delenv("CAR_CONFIGURATOR_OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-global")
        factory = LLMFactory()
        assert not factory.has_project_credential(
            "Car Configurator", LLMProvider.OPENAI, LLMConfig()
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/llm/test_factory.py -k "ModelRouting or ProjectCredential" -v`
Expected: FAIL — `TypeError: _get_common_client_kwargs() takes 2 positional arguments but 3 were given`

- [ ] **Step 3: Implement in `llm/factory.py`**

Import `RoutingFamily` from `llm.base`. Change the signature and add the forwarding:

```python
    def _get_common_client_kwargs(
        self, config: LLMConfig, provider: LLMProvider
    ) -> dict[str, Any]:
        """Kwargs passed to every provider SDK client.

        'timeout' and 'max_retries' are declared fields (the console renders
        them), so they are read off the model. Only an explicitly-set value is
        forwarded: passing None would override the SDK's own default with
        nothing. '_strict_response_validation' stays undeclared -- it is a
        private SDK flag, not a configuration surface -- so it still comes from
        model_extra.

        'model_routing' is filtered to *provider* so an OpenAI entry never
        reaches the Anthropic client, and is omitted entirely when empty: a
        third-party CUSTOM client should see exactly the kwargs it saw before
        this field existed.
        """
        kwargs: dict[str, Any] = {}
        if config.timeout is not None:
            kwargs["timeout"] = config.timeout
        if config.max_retries is not None:
            kwargs["max_retries"] = config.max_retries

        model_routing: dict[str, RoutingFamily] = {
            name: entry.routing
            for name, entry in config.extra_models.items()
            if entry.provider == provider
        }
        if model_routing:
            kwargs["model_routing"] = model_routing

        extra = config.model_extra or {}
        if "_strict_response_validation" in extra:
            kwargs["_strict_response_validation"] = extra["_strict_response_validation"]
        return kwargs
```

Update the one call site at the top of `_create_client`:

```python
        common_kwargs = self._get_common_client_kwargs(config, provider)
```

Add the two public probes the console needs (both are thin wrappers over the exact paths
`get_client` already takes, so the console can report what a run resolved without restating the
rules or reaching into a private method):

```python
    def has_project_credential(
        self, project_name: str, provider: LLMProvider, config: LLMConfig
    ) -> bool:
        """Whether a project-specific credential exists for this provider.

        A thin wrapper over the exact call ``get_client`` makes, so the console
        can report which credential a run used without restating the
        environment-variable naming rules (design D4). A credential resolver
        that raises is reported as "no project credential" rather than
        propagating: this is a reporting aid, and the real failure surfaces on
        the call itself.
        """
        try:
            return self._get_project_credential(project_name, provider, config) is not None
        except Exception:
            return False

    def resolve_provider(self, config: LLMConfig, prompt_model: str | None) -> LLMProvider:
        """Which provider this model routes to -- the same answer get_client uses.

        Public because the console reports the resolved route back to the
        operator (design D4) and must not reach into a private method to do
        it. Delegates rather than reimplements: a second copy of the prefix
        rules would be a second thing to keep in step.
        """
        return self._resolve_provider(config, prompt_model)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/llm/test_factory.py -v`
Expected: PASS

- [ ] **Step 5: Run the wider suite for regressions**

Run: `python -m pytest tests/unit -q`
Expected: PASS

- [ ] **Step 6: Lint and commit**

```bash
python -m ruff check testbench_ai_service/llm/factory.py tests/unit/llm/test_factory.py
python -m ruff format --check testbench_ai_service/llm/factory.py tests/unit/llm/test_factory.py
git add testbench_ai_service/llm/factory.py tests/unit/llm/test_factory.py
git commit -m "Forward configured model routing to each provider client"
```

---

### Task 6: `webui/catalogue.py` — the derived catalogue

No model names are written in this module. It groups `builtin_models_by_provider()` and overlays `config.llm_config.extra_models`, annotating each provider with key presence via `status.api_key_statuses` so presence-not-values stays enforced in one place (§3.4, D7).

**Files:**
- Create: `testbench_ai_service/webui/catalogue.py`
- Modify: `testbench_ai_service/webui/models.py` (append response models)
- Test: `tests/unit/webui/test_catalogue.py`

**Interfaces:**
- Consumes: `builtin_models_by_provider` (Task 1), `LLMConfig.extra_models` (Task 2), `status.api_key_statuses` (existing, `webui/status.py:38`), `normalize_project_name` (existing, `utils/naming.py:4`)
- Produces:
  - `CatalogueModel(BaseModel)`: `id: str`, `routing: RoutingFamily`, `source: Literal["builtin", "config"]`
  - `CatalogueProvider(BaseModel)`: `provider: LLMProvider`, `key_present: bool`, `models: list[CatalogueModel]`
  - `ModelCatalogueResponse(BaseModel)`: `providers: list[CatalogueProvider]`
  - `build_catalogue(config: AppConfig, project: str | None = None) -> ModelCatalogueResponse`
  - `PROVIDER_KEY_NAMES: dict[LLMProvider, str | None]`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/webui/test_catalogue.py`:

```python
import pytest

from testbench_ai_service.config import AppConfig
from testbench_ai_service.llm.base import LLMProvider, RoutingFamily
from testbench_ai_service.llm.routing import BUILTIN_ROUTING
from testbench_ai_service.models.config import LLMConfig
from testbench_ai_service.webui.catalogue import build_catalogue

TB_URL = "https://localhost:9443/api/"


@pytest.fixture(autouse=True)
def no_tb_probe(monkeypatch):
    monkeypatch.setattr("testbench_ai_service.config.validate_tb_server_url", lambda *a, **k: None)


def _config(**llm_kwargs) -> AppConfig:
    return AppConfig(tb_server_url=TB_URL, llm_config=LLMConfig(**llm_kwargs))


def _models(response, provider: LLMProvider) -> dict[str, RoutingFamily]:
    entry = next(p for p in response.providers if p.provider == provider)
    return {model.id: model.routing for model in entry.models}


class TestDerivation:
    def test_every_catalogue_entry_comes_from_a_routing_set(self):
        # The test that fails if anyone reintroduces a hand-maintained list.
        response = build_catalogue(_config())
        listed = {
            model.id
            for provider in response.providers
            for model in provider.models
        }
        assert listed == set(BUILTIN_ROUTING)

    def test_every_routing_set_member_is_listed(self):
        response = build_catalogue(_config())
        listed = {
            model.id
            for provider in response.providers
            for model in provider.models
        }
        for model in BUILTIN_ROUTING:
            assert model in listed

    def test_each_entry_reports_the_family_it_would_use(self):
        response = build_catalogue(_config())
        assert _models(response, LLMProvider.OPENAI)["gpt-4o"] is RoutingFamily.CHAT
        assert (
            _models(response, LLMProvider.ANTHROPIC)["claude-haiku-4-5"] is RoutingFamily.BUDGET
        )

    def test_builtins_are_marked_as_builtin(self):
        response = build_catalogue(_config())
        entry = next(p for p in response.providers if p.provider == LLMProvider.OPENAI)
        assert all(model.source == "builtin" for model in entry.models)

    def test_azure_and_custom_have_no_builtin_models(self):
        response = build_catalogue(_config())
        assert _models(response, LLMProvider.AZURE_OPENAI) == {}
        assert _models(response, LLMProvider.CUSTOM) == {}


class TestExtraModelsOverlay:
    def test_a_configured_model_appears_and_is_marked(self):
        config = _config(
            extra_models={"claude-opus-6": {"provider": "anthropic", "routing": "adaptive"}}
        )
        response = build_catalogue(config)
        entry = next(p for p in response.providers if p.provider == LLMProvider.ANTHROPIC)
        added = next(model for model in entry.models if model.id == "claude-opus-6")
        assert added.source == "config"
        assert added.routing is RoutingFamily.ADAPTIVE

    def test_a_configured_model_gives_azure_a_picker(self):
        config = _config(
            extra_models={"my-deployment": {"provider": "azure_openai", "routing": "chat"}}
        )
        response = build_catalogue(config)
        assert "my-deployment" in _models(response, LLMProvider.AZURE_OPENAI)

    def test_builtins_survive_the_overlay(self):
        config = _config(
            extra_models={"claude-opus-6": {"provider": "anthropic", "routing": "adaptive"}}
        )
        response = build_catalogue(config)
        assert "claude-haiku-4-5" in _models(response, LLMProvider.ANTHROPIC)


class TestKeyPresence:
    def test_reports_presence_for_the_provider_variable(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-global")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        response = build_catalogue(_config())
        by_provider = {p.provider: p.key_present for p in response.providers}
        assert by_provider[LLMProvider.ANTHROPIC] is True
        assert by_provider[LLMProvider.OPENAI] is False

    def test_never_returns_a_key_value(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")
        response = build_catalogue(_config())
        assert "sk-secret-value" not in response.model_dump_json()

    def test_a_project_variable_counts_as_present(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("CAR_CONFIGURATOR_OPENAI_API_KEY", "sk-project")
        response = build_catalogue(_config(), project="Car Configurator")
        by_provider = {p.provider: p.key_present for p in response.providers}
        assert by_provider[LLMProvider.OPENAI] is True

    def test_the_global_variable_still_counts_for_a_project(self, monkeypatch):
        # Mirrors get_client's silent fallback (design 3.2): the question the
        # operator is asking is "will a run find a key at all".
        monkeypatch.delenv("CAR_CONFIGURATOR_OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-global")
        response = build_catalogue(_config(), project="Car Configurator")
        by_provider = {p.provider: p.key_present for p in response.providers}
        assert by_provider[LLMProvider.OPENAI] is True

    def test_custom_needs_no_key(self):
        response = build_catalogue(_config())
        by_provider = {p.provider: p.key_present for p in response.providers}
        assert by_provider[LLMProvider.CUSTOM] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/webui/test_catalogue.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'testbench_ai_service.webui.catalogue'`

- [ ] **Step 3: Append the response models to `webui/models.py`**

```python
class CatalogueModel(BaseModel):
    """One offerable model and the request shape it will be called with."""

    id: str
    routing: RoutingFamily
    #: "builtin" comes from a client's own routing set; "config" from
    #: llm_config.extra_models, which is the only kind the console can remove.
    source: Literal["builtin", "config"]


class CatalogueProvider(BaseModel):
    provider: LLMProvider
    #: Whether a credential exists. Presence only, never a value.
    key_present: bool
    models: list[CatalogueModel]


class ModelCatalogueResponse(BaseModel):
    providers: list[CatalogueProvider]
```

Add `Literal` to the `typing` import and import `LLMProvider` / `RoutingFamily` from `testbench_ai_service.llm.base` at the top of the file.

- [ ] **Step 4: Write `webui/catalogue.py`**

```python
"""The model catalogue the console offers, derived rather than retyped.

**No model name is written in this module.** The built-in half comes from
``llm.routing.builtin_models_by_provider``, which reads the four frozensets the
clients dispatch on; the operator's half comes from
``llm_config.extra_models``. A hand-maintained constant here would be a third
list that goes stale independently of the two the service actually uses
(design D7).

Key presence goes through ``status.api_key_statuses`` so the
presence-never-values rule is enforced in one place (design 3.4).
"""

import os

from testbench_ai_service.config import AppConfig
from testbench_ai_service.llm.base import LLMProvider
from testbench_ai_service.llm.routing import builtin_models_by_provider
from testbench_ai_service.utils.naming import normalize_project_name
from testbench_ai_service.webui.models import (
    CatalogueModel,
    CatalogueProvider,
    ModelCatalogueResponse,
)
from testbench_ai_service.webui.status import api_key_statuses

#: The global credential each provider authenticates with. CUSTOM is None:
#: LLMFactory._get_api_key deliberately does not demand a 'CUSTOM_API_KEY',
#: so there is no variable whose absence would mean anything.
PROVIDER_KEY_NAMES: dict[LLMProvider, str | None] = {
    LLMProvider.OPENAI: "OPENAI_API_KEY",
    LLMProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
    LLMProvider.AZURE_OPENAI: "AZURE_OPENAI_API_KEY",
    LLMProvider.CUSTOM: None,
}


def _key_present(config: AppConfig, provider: LLMProvider, project: str | None) -> bool:
    """Whether a run for this provider would find a credential at all.

    With a project, the project variable OR the global one counts -- which
    mirrors ``get_client``'s silent fallback (design 3.2) rather than
    contradicting it.
    """
    name = PROVIDER_KEY_NAMES[provider]
    if name is None:
        return True

    statuses = {status.name: status.present for status in api_key_statuses(config)}
    if statuses.get(name, False):
        return True

    if project is not None:
        scoped = f"{normalize_project_name(project)}_{name}"
        return bool(os.environ.get(scoped))
    return False


def build_catalogue(config: AppConfig, project: str | None = None) -> ModelCatalogueResponse:
    """Every model the console can offer, grouped by provider."""
    grouped = builtin_models_by_provider()

    entries: dict[LLMProvider, dict[str, CatalogueModel]] = {
        provider: {
            model: CatalogueModel(id=model, routing=family, source="builtin")
            for model, family in models.items()
        }
        for provider, models in grouped.items()
    }

    for name, extra in config.llm_config.extra_models.items():
        # setdefault, not assignment: LLMConfig refuses an entry that shadows a
        # built-in, so this can only ever add. Belt and braces -- a built-in
        # must never be displaceable by config.
        entries.setdefault(extra.provider, {}).setdefault(
            name, CatalogueModel(id=name, routing=extra.routing, source="config")
        )

    return ModelCatalogueResponse(
        providers=[
            CatalogueProvider(
                provider=provider,
                key_present=_key_present(config, provider, project),
                models=sorted(models.values(), key=lambda model: model.id),
            )
            for provider, models in entries.items()
        ]
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/unit/webui/test_catalogue.py -v`
Expected: PASS

- [ ] **Step 6: Lint and commit**

```bash
python -m ruff check testbench_ai_service/webui/catalogue.py testbench_ai_service/webui/models.py tests/unit/webui/test_catalogue.py
python -m ruff format --check testbench_ai_service/webui/catalogue.py testbench_ai_service/webui/models.py tests/unit/webui/test_catalogue.py
git add testbench_ai_service/webui/catalogue.py testbench_ai_service/webui/models.py tests/unit/webui/test_catalogue.py
git commit -m "Derive the model catalogue from the clients' routing sets"
```

---

### Task 7: `GET /models`

Admin + CSRF. It is a read, but it is the catalogue for the one paid action and it reports which credentials exist, so it follows `POST /prompts/render`'s gate rather than lint's (§5.1).

**Files:**
- Modify: `testbench_ai_service/webui/routes.py`
- Test: `tests/unit/webui/test_models_route.py`

**Interfaces:**
- Consumes: `build_catalogue` (Task 6), `ModelCatalogueResponse` (Task 6), `require_admin` / `require_csrf` / `get_app_config` (all existing in `routes.py`)
- Produces: `GET /admin/api/models?project=<name>` returning `ModelCatalogueResponse`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/webui/test_models_route.py`:

```python
def csrf(client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["tbai_admin_csrf"]}


class TestGates:
    def test_anonymous_is_refused(self, client):
        assert client.get("/admin/api/models").status_code == 401

    def test_a_non_admin_is_refused(self, client, login):
        login(roles=[])
        response = client.get("/admin/api/models", headers=csrf(client))
        assert response.status_code == 403

    def test_missing_csrf_is_refused(self, client, login):
        login(roles=["Administrator"])
        assert client.get("/admin/api/models").status_code == 403

    def test_an_admin_with_csrf_is_allowed(self, client, login):
        login(roles=["Administrator"])
        response = client.get("/admin/api/models", headers=csrf(client))
        assert response.status_code == 200


class TestPayload:
    def test_groups_models_by_provider(self, client, login):
        login(roles=["Administrator"])
        body = client.get("/admin/api/models", headers=csrf(client)).json()
        providers = {entry["provider"] for entry in body["providers"]}
        assert {"openai", "anthropic", "azure_openai", "custom"} == providers

    def test_reports_the_routing_family_per_model(self, client, login):
        login(roles=["Administrator"])
        body = client.get("/admin/api/models", headers=csrf(client)).json()
        openai = next(e for e in body["providers"] if e["provider"] == "openai")
        gpt4o = next(m for m in openai["models"] if m["id"] == "gpt-4o")
        assert gpt4o["routing"] == "chat"
        assert gpt4o["source"] == "builtin"

    def test_never_returns_a_key_value(self, client, login, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")
        login(roles=["Administrator"])
        response = client.get("/admin/api/models", headers=csrf(client))
        assert "sk-secret-value" not in response.text

    def test_a_project_query_is_accepted(self, client, login):
        login(roles=["Administrator"])
        response = client.get(
            "/admin/api/models", params={"project": "Car Configurator"}, headers=csrf(client)
        )
        assert response.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/webui/test_models_route.py -v`
Expected: FAIL — 404 on `/admin/api/models`

- [ ] **Step 3: Add the route**

Import at the top of `routes.py`:

```python
from testbench_ai_service.webui.catalogue import build_catalogue
```

and add `ModelCatalogueResponse` to the existing `webui.models` import block. Then add the route beside `read_prompt_tree`:

```python
@router.get("/models", response_model=ModelCatalogueResponse)
def read_model_catalogue(
    project: str | None = None,
    _session: Session = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    config: AppConfig = Depends(get_app_config),
) -> ModelCatalogueResponse:
    """Every model the console can offer, grouped by provider.

    Admin-gated despite being a read: it is the catalogue for the one console
    action that spends money, and it reports which provider credentials are
    present. Presence only -- no endpoint returns a credential value.
    """
    return build_catalogue(config, project)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/webui/test_models_route.py -v`
Expected: PASS

- [ ] **Step 5: Confirm route wiring did not disturb the others**

Run: `python -m pytest tests/unit/webui -q`
Expected: PASS

- [ ] **Step 6: Lint and commit**

```bash
python -m ruff check testbench_ai_service/webui/routes.py tests/unit/webui/test_models_route.py
python -m ruff format --check testbench_ai_service/webui/routes.py tests/unit/webui/test_models_route.py
git add testbench_ai_service/webui/routes.py tests/unit/webui/test_models_route.py
git commit -m "Serve the model catalogue to the console"
```

---

### Task 8: `webui/prompt_test.py` — the guarded call

> **Deviation from the design, deliberate.** §5 calls this module `webui/test_run.py`. A source
> file matching `test_*.py` is importable by pytest as a test module — harmless under the current
> `testpaths = ["tests"]`, but `asyncio_mode = "auto"` would turn its async helpers into
> collected "tests" the moment anyone runs `pytest testbench_ai_service/` or an IDE collects the
> package. `prompt_test.py` carries the same meaning with no collision.

Everything that makes a paid call safe, with no FastAPI route yet: the single-flight lock, the console-owned timeout, the credential scrubber, and the resolved-route result.

The lock gets its **own** primitive rather than reusing `TaskRegistry`: that registry's docstring promises it is "a counter with labels, not a task manager" whose worst failure is a wrong count, and making it a mutex would turn a wrong count into a permanently locked-out session (§3.6).

**Files:**
- Create: `testbench_ai_service/webui/prompt_test.py`
- Test: `tests/unit/webui/test_prompt_test_run.py`

**Interfaces:**
- Consumes: `RenderedMessage` (existing, `webui/models.py`), `Message` (existing, `models/prompt.py`)
- Produces:
  - `PROMPT_TEST_TIMEOUT: float = 60.0`
  - `SingleFlight` with `hold(key: str)` — a context manager raising `HTTPException(409)` when *key* is already held
  - `scrub(message: str, secret: str | None) -> str`
  - `scrub_all(message: str, secrets: Iterable[str | None]) -> str`
  - `to_messages(rendered: list[RenderedMessage]) -> list[Message]`
  - `RunOutcome` dataclass: `text: str`, `latency_ms: int`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/webui/test_prompt_test_run.py`:

```python
import asyncio

import pytest
from fastapi import HTTPException

from testbench_ai_service.webui.models import RenderedMessage
from testbench_ai_service.webui.prompt_test import (
    PROMPT_TEST_TIMEOUT,
    RunOutcome,
    SingleFlight,
    run_query,
    scrub,
    scrub_all,
    to_messages,
)


class TestSingleFlight:
    def test_a_free_key_is_admitted(self):
        flight = SingleFlight()
        with flight.hold("sid-1"):
            pass

    def test_a_held_key_is_refused_with_409(self):
        flight = SingleFlight()
        with flight.hold("sid-1"):
            with pytest.raises(HTTPException) as excinfo:
                with flight.hold("sid-1"):
                    pass
        assert excinfo.value.status_code == 409

    def test_a_different_key_is_unaffected(self):
        # Per session, not per process: the lock stops a stuck UI repeating,
        # it does not serialise the organisation (design 9).
        flight = SingleFlight()
        with flight.hold("sid-1"), flight.hold("sid-2"):
            pass

    def test_the_key_is_released_after_a_raise(self):
        flight = SingleFlight()
        with pytest.raises(RuntimeError):
            with flight.hold("sid-1"):
                raise RuntimeError("boom")
        with flight.hold("sid-1"):
            pass


class TestScrub:
    def test_replaces_every_occurrence_of_the_credential(self):
        assert scrub("bad key sk-abc and sk-abc", "sk-abc") == "bad key *** and ***"

    def test_leaves_the_message_alone_when_there_is_no_credential(self):
        assert scrub("model not found", None) == "model not found"

    def test_an_empty_credential_is_not_treated_as_a_match(self):
        assert scrub("model not found", "") == "model not found"

    def test_unrelated_text_survives(self):
        assert scrub("404 model not found", "sk-abc") == "404 model not found"


class TestScrubAll:
    def test_masks_every_candidate_credential(self):
        # A project run may have used either key; both must be masked.
        message = "global sk-global project sk-project"
        assert scrub_all(message, ["sk-global", "sk-project"]) == "global *** project ***"

    def test_skips_absent_candidates(self):
        assert scrub_all("bad key sk-global", ["sk-global", None]) == "bad key ***"

    def test_an_empty_candidate_list_leaves_the_message_alone(self):
        assert scrub_all("model not found", []) == "model not found"


class TestToMessages:
    def test_maps_role_and_content(self):
        rendered = [RenderedMessage(role="system", content="hello", error=None)]
        assert [(m.role, m.content) for m in to_messages(rendered)] == [("system", "hello")]


class TestRunQuery:
    @pytest.mark.asyncio
    async def test_returns_text_and_a_latency(self):
        class FakeClient:
            async def query_llm(self, model, messages, **kwargs):
                return "the answer"

        outcome = await run_query(FakeClient(), "claude-opus-5", [])

        assert isinstance(outcome, RunOutcome)
        assert outcome.text == "the answer"
        assert outcome.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_a_slow_call_times_out(self):
        class SlowClient:
            async def query_llm(self, model, messages, **kwargs):
                await asyncio.sleep(5)
                return "never"

        with pytest.raises(HTTPException) as excinfo:
            await run_query(SlowClient(), "claude-opus-5", [], timeout=0.01)

        assert excinfo.value.status_code == 504
        assert "0.01" in str(excinfo.value.detail)

    def test_the_default_timeout_is_a_bounded_number(self):
        assert 0 < PROMPT_TEST_TIMEOUT <= 300
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/webui/test_prompt_test_run.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'testbench_ai_service.webui.prompt_test'`

- [ ] **Step 3: Write `webui/prompt_test.py`**

```python
"""The one console action that spends money, and what bounds it.

Three guardrails, each closing a different hole (design D5):

* a single-flight lock per session, so a stuck browser cannot bill twice;
* a timeout this module owns, because the SDK's own wall-clock reaches
  ``timeout x (max_retries + 1)`` and is therefore not a bound;
* a credential scrubber, so a provider error cannot become the first route
  that discloses an environment variable's contents (design D9).

The lock is deliberately NOT ``TaskRegistry``: that registry promises it is a
counter whose worst failure is a wrong count, and a mutex built on it would
turn a wrong count into a session locked out forever (design 3.6).
"""

import asyncio
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from fastapi import HTTPException, status

from testbench_ai_service.models.prompt import Message
from testbench_ai_service.webui.models import RenderedMessage

#: The console's own ceiling on a test run, in seconds.
PROMPT_TEST_TIMEOUT: float = 60.0


@dataclass(frozen=True)
class RunOutcome:
    """What a completed call produced."""

    text: str
    latency_ms: int


class SingleFlight:
    """At most one held key at a time, refusing the second with a 409."""

    def __init__(self) -> None:
        self._held: set[str] = set()

    @contextmanager
    def hold(self, key: str) -> Iterator[None]:
        """Hold *key* for the duration of the block, or refuse.

        The release is in a ``finally``: a raising run must not leave the key
        held, or that session could never test again without a restart.
        """
        if key in self._held:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A test run is already in flight for this session.",
            )
        self._held.add(key)
        try:
            yield
        finally:
            self._held.discard(key)


def scrub(message: str, secret: str | None) -> str:
    """Replace every occurrence of *secret* in *message*.

    Exact substring, never a pattern: a heuristic that tries to recognise
    "things that look like keys" both misses real ones and mangles innocent
    text. An empty or absent secret matches nothing -- ``"".replace`` would
    otherwise splice the mask between every character.
    """
    if not secret:
        return message
    return message.replace(secret, "***")


def scrub_all(message: str, secrets: Iterable[str | None]) -> str:
    """Mask every candidate credential in *message*.

    A run resolves either a project credential or the global one, and the
    console cannot see which the SDK actually sent -- so both are masked
    rather than guessed between (design D9).
    """
    for secret in secrets:
        message = scrub(message, secret)
    return message


def to_messages(rendered: list[RenderedMessage]) -> list[Message]:
    """The rendered preview, as the messages a client accepts."""
    return [Message(role=item.role, content=item.content) for item in rendered]


async def run_query(
    client, model: str, messages: list[Message], timeout: float = PROMPT_TEST_TIMEOUT
) -> RunOutcome:
    """Call *client* under the console's own ceiling.

    ``latency_ms`` is wall-clock around the await, so it includes whatever
    retries the SDK performed -- which is what the operator experiences.
    """
    started = time.perf_counter()
    try:
        text = await asyncio.wait_for(
            client.query_llm(model=model, messages=messages), timeout
        )
    # asyncio.TimeoutError is only an alias of the builtin from 3.11 on, and
    # pyproject declares support back to 3.10 -- catch both.
    except (asyncio.TimeoutError, TimeoutError) as e:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"The model did not answer within {timeout} seconds.",
        ) from e
    return RunOutcome(text=text, latency_ms=int((time.perf_counter() - started) * 1000))
```

> **Python floor (pre-flight ruling P3):** this uses `asyncio.wait_for`, not `asyncio.timeout`. `asyncio.timeout` requires 3.11 and `pyproject.toml:12` declares support from 3.10, so the newer API would fail to import on a supported interpreter. Semantics here are identical.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/webui/test_prompt_test_run.py -v`
Expected: PASS

- [ ] **Step 5: Lint and commit**

```bash
python -m ruff check testbench_ai_service/webui/prompt_test.py tests/unit/webui/test_prompt_test_run.py
python -m ruff format --check testbench_ai_service/webui/prompt_test.py tests/unit/webui/test_prompt_test_run.py
git add testbench_ai_service/webui/prompt_test.py tests/unit/webui/test_prompt_test_run.py
git commit -m "Bound the console's paid call with lock, timeout and scrubber"
```

---

### Task 9: `POST /prompts/test`

Wires Task 8's pieces to the production resolution path. The ordering is the money-safety property of the whole increment: **render first, refuse before any client is created.** The test asserts that against the factory, not against the status code.

**Files:**
- Modify: `testbench_ai_service/webui/models.py` (request/response models)
- Modify: `testbench_ai_service/webui/routes.py`
- Modify: `testbench_ai_service/main.py` (install the `SingleFlight` on `app.state`)
- Test: `tests/unit/webui/test_prompt_test_route.py`

**Interfaces:**
- Consumes: `render_messages` (existing, `webui/prompt_render.py`), `get_llm_config` (existing, `utils/config.py:368`), `LLMFactory.get_client` / `has_project_credential` (Task 5), `SingleFlight` / `run_query` / `scrub_all` / `to_messages` / `PROMPT_TEST_TIMEOUT` (Task 8), `TaskRegistry` (existing, `webui/inflight.py`)
- Produces:
  - `PromptTestRequest(RenderRequest)`: `model: str`, `project: str | None = None`
  - `ResolvedRoute(BaseModel)`: `provider: LLMProvider`, `model: str`, `credential_scope: Literal["project", "global"]`
  - `PromptTestResponse(BaseModel)`: `text: str`, `latency_ms: int`, `resolved: ResolvedRoute`
  - `POST /admin/api/prompts/test`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/webui/test_prompt_test_route.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

MESSAGE = {"role": "user", "source": "inline", "file": None, "content": "Hallo {{ vars.name }}"}


def csrf(client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["tbai_admin_csrf"]}


def body(**overrides) -> dict:
    payload = {
        "messages": [MESSAGE],
        "vars": {"name": "Welt"},
        "agent_context": {},
        "model": "claude-opus-5",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def fake_client(app):
    """Install a fake LLM client and return it."""
    client = MagicMock()
    client.query_llm = AsyncMock(return_value="the answer")
    app.state.llm_factory.get_client = MagicMock(return_value=client)
    app.state.llm_factory.has_project_credential = MagicMock(return_value=False)
    return client


class TestGates:
    def test_a_non_admin_is_refused(self, client, login):
        login(roles=[])
        response = client.post("/admin/api/prompts/test", json=body(), headers=csrf(client))
        assert response.status_code == 403

    def test_missing_csrf_is_refused(self, client, login):
        login(roles=["Administrator"])
        assert client.post("/admin/api/prompts/test", json=body()).status_code == 403


class TestHappyPath:
    def test_returns_the_text_and_a_latency(self, client, login, fake_client):
        login(roles=["Administrator"])
        response = client.post("/admin/api/prompts/test", json=body(), headers=csrf(client))
        assert response.status_code == 200
        payload = response.json()
        assert payload["text"] == "the answer"
        assert payload["latency_ms"] >= 0

    def test_sends_the_rendered_draft_not_the_raw_template(self, client, login, fake_client):
        login(roles=["Administrator"])
        client.post("/admin/api/prompts/test", json=body(), headers=csrf(client))
        sent = fake_client.query_llm.await_args.kwargs["messages"]
        assert sent[0].content == "Hallo Welt"

    def test_lets_the_factory_resolve_the_provider(self, client, login, app, fake_client):
        login(roles=["Administrator"])
        client.post("/admin/api/prompts/test", json=body(), headers=csrf(client))
        kwargs = app.state.llm_factory.get_client.call_args.kwargs
        assert kwargs["prompt_model"] == "claude-opus-5"

    def test_reports_global_credential_scope_by_default(self, client, login, fake_client):
        login(roles=["Administrator"])
        response = client.post("/admin/api/prompts/test", json=body(), headers=csrf(client))
        assert response.json()["resolved"]["credential_scope"] == "global"

    def test_reports_project_scope_when_a_project_key_exists(
        self, client, login, app, fake_client
    ):
        app.state.llm_factory.has_project_credential = MagicMock(return_value=True)
        login(roles=["Administrator"])
        response = client.post(
            "/admin/api/prompts/test",
            json=body(project="Car Configurator"),
            headers=csrf(client),
        )
        assert response.json()["resolved"]["credential_scope"] == "project"


class TestMoneySafety:
    def test_a_render_failure_creates_no_client(self, client, login, app, fake_client):
        # The money-safety property, asserted against the factory rather than
        # the status code: a broken template must cost nothing (design 5.5).
        login(roles=["Administrator"])
        broken = dict(MESSAGE, content="{% if %}")
        response = client.post(
            "/admin/api/prompts/test", json=body(messages=[broken]), headers=csrf(client)
        )
        assert response.status_code == 400
        app.state.llm_factory.get_client.assert_not_called()

    def test_an_undefined_variable_is_a_render_failure(self, client, login, app, fake_client):
        login(roles=["Administrator"])
        response = client.post(
            "/admin/api/prompts/test", json=body(vars={}), headers=csrf(client)
        )
        assert response.status_code == 400
        app.state.llm_factory.get_client.assert_not_called()


class TestProductionResolution:
    def test_a_partial_project_override_merges_rather_than_replaces(
        self, make_app, tb_connection
    ):
        """The regression test D3 exists to prevent.

        get_llm_config merges the project block onto the global one with
        exclude_unset=True, so a project overriding only `model` keeps the
        global timeout and max_retries. A console that read
        config.projects[...].llm_config directly would REPLACE, and the test
        run would resolve differently from the agent it is meant to predict --
        silently, and only for projects with partial overrides. This fails
        loudly if the route ever stops calling get_llm_config.

        Builds its own app because the shared `client` fixture has no projects
        table to override.
        """
        app = make_app(
            llm_config={"provider": "anthropic", "timeout": 42.0, "max_retries": 7},
            projects={"Car Configurator": {"llm_config": {"model": "claude-sonnet-5"}}},
        )
        fake = MagicMock()
        fake.query_llm = AsyncMock(return_value="ok")
        app.state.llm_factory.get_client = MagicMock(return_value=fake)
        app.state.llm_factory.has_project_credential = MagicMock(return_value=False)

        with TestClient(app, raise_server_exceptions=False) as scoped:
            with patch(
                "testbench_ai_service.webui.auth.TBConnection", return_value=tb_connection
            ):
                scoped.post("/admin/api/session", json={"username": "a", "password": "p"})
            scoped.post(
                "/admin/api/prompts/test",
                json=body(project="Car Configurator"),
                headers={"X-CSRF-Token": scoped.cookies["tbai_admin_csrf"]},
            )

        resolved = app.state.llm_factory.get_client.call_args.kwargs["config"]
        assert resolved.model == "claude-sonnet-5"   # the project's own override
        assert resolved.timeout == 42.0              # inherited, not dropped
        assert resolved.max_retries == 7             # inherited, not dropped

    def test_the_factory_resolves_the_provider_from_the_model_name(
        self, client, login, app, fake_client
    ):
        # Provider resolution stays in _resolve_provider (design D3): the
        # console never branches on a model prefix itself.
        login(roles=["Administrator"])
        response = client.post("/admin/api/prompts/test", json=body(), headers=csrf(client))
        assert response.json()["resolved"]["provider"] == "anthropic"

    def test_a_gpt_model_resolves_to_openai(self, client, login, app, fake_client):
        login(roles=["Administrator"])
        response = client.post(
            "/admin/api/prompts/test", json=body(model="gpt-4o"), headers=csrf(client)
        )
        assert response.json()["resolved"]["provider"] == "openai"

    def test_the_run_is_counted_while_in_flight(self, client, login, app, fake_client):
        """Design D6: the reload path's in-flight count must include a test run.

        Captured from inside query_llm, because the count is back to zero by
        the time the response is returned -- which is exactly the property
        TaskRegistry.track's finally guarantees.
        """
        seen = []

        async def counting_query(model, messages, **kwargs):
            seen.append(app.state.task_registry.labels())
            return "ok"

        fake_client.query_llm = AsyncMock(side_effect=counting_query)
        login(roles=["Administrator"])

        client.post("/admin/api/prompts/test", json=body(), headers=csrf(client))

        assert seen == [["prompt-test"]]
        assert app.state.task_registry.count == 0


class TestSingleFlightOverTheWire:
    def test_a_second_concurrent_run_for_one_session_is_refused(
        self, client, login, app, fake_client
    ):
        import threading

        started = threading.Event()
        release = threading.Event()

        async def blocking_query(model, messages, **kwargs):
            started.set()
            release.wait(timeout=5)
            return "ok"

        fake_client.query_llm = AsyncMock(side_effect=blocking_query)
        login(roles=["Administrator"])
        headers = csrf(client)

        first: list = []
        worker = threading.Thread(
            target=lambda: first.append(
                client.post("/admin/api/prompts/test", json=body(), headers=headers)
            )
        )
        worker.start()
        assert started.wait(timeout=5)

        second = client.post("/admin/api/prompts/test", json=body(), headers=headers)
        release.set()
        worker.join(timeout=5)

        assert second.status_code == 409
        assert first[0].status_code == 200


class TestFailures:
    def test_a_provider_error_is_a_502(self, client, login, app, fake_client):
        fake_client.query_llm = AsyncMock(side_effect=RuntimeError("404 model not found"))
        login(roles=["Administrator"])
        response = client.post("/admin/api/prompts/test", json=body(), headers=csrf(client))
        assert response.status_code == 502
        assert "model not found" in response.text

    def test_a_provider_error_never_echoes_the_credential(
        self, client, login, app, fake_client, monkeypatch
    ):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret-value")
        fake_client.query_llm = AsyncMock(
            side_effect=RuntimeError("401 bad key sk-secret-value")
        )
        login(roles=["Administrator"])
        response = client.post("/admin/api/prompts/test", json=body(), headers=csrf(client))
        assert response.status_code == 502
        assert "sk-secret-value" not in response.text
        assert "***" in response.text

    def test_a_missing_credential_is_a_400_naming_the_variable(
        self, client, login, app, fake_client
    ):
        app.state.llm_factory.get_client = MagicMock(
            side_effect=ValueError(
                "API key for provider 'anthropic' not found in environment variables."
            )
        )
        login(roles=["Administrator"])
        response = client.post("/admin/api/prompts/test", json=body(), headers=csrf(client))
        assert response.status_code == 400
        assert "anthropic" in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/webui/test_prompt_test_route.py -v`
Expected: FAIL — 404 on `/admin/api/prompts/test`

- [ ] **Step 3: Append the request/response models to `webui/models.py`**

```python
class PromptTestRequest(RenderRequest):
    """A render request plus where to send the result.

    Inherits RenderRequest deliberately: the preview pane and the test run
    must send the same messages, vars and agent_context, or the operator
    tested something other than what they saw (design D1).
    """

    model: str
    project: str | None = None


class ResolvedRoute(BaseModel):
    provider: LLMProvider
    model: str
    #: Which credential the factory actually found. get_client falls back to
    #: the global key silently, so without this a project test that used the
    #: global key is indistinguishable from one that used the project's own.
    credential_scope: Literal["project", "global"]


class PromptTestResponse(BaseModel):
    text: str
    latency_ms: int
    resolved: ResolvedRoute
```

- [ ] **Step 4: Install the lock in `main.py`**

Beside the existing `app.state.task_registry` assignment:

```python
    app.state.prompt_test_flight = SingleFlight()
```

with `from testbench_ai_service.webui.prompt_test import SingleFlight` at the top.

- [ ] **Step 5: Add the route to `routes.py`**

```python
@router.post("/prompts/test", response_model=PromptTestResponse)
async def test_prompt(
    body: PromptTestRequest,
    request: Request,
    session: Session = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    config: AppConfig = Depends(get_app_config),
    registry: TaskRegistry = Depends(get_task_registry),
) -> PromptTestResponse:
    """Run the editor's draft against a real model.

    The one console action that spends money, so the order matters: render
    first and refuse on failure BEFORE a client is created. Rendering goes
    through the same sandboxed environment as POST /prompts/render -- a test
    run is not a hole in that sandbox.
    """
    rendered = render_messages(body.messages, dict(body.vars), body.agent_context)
    failed = [item for item in rendered if item.error is not None]
    if failed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "The prompt did not render, so nothing was sent.",
                "messages": [item.model_dump() for item in rendered],
            },
        )

    # Resolution goes through the production helper, never a local re-merge:
    # the project step is a merge, not a replacement, and re-implementing it
    # would diverge silently for partial overrides (design 3.7).
    llm_config = get_llm_config(config, project_name=body.project)
    factory: LLMFactory = request.app.state.llm_factory

    try:
        client = factory.get_client(
            config=llm_config, prompt_model=body.model, project_name=body.project
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    provider = factory.resolve_provider(llm_config, body.model)
    scope = "global"
    if body.project is not None and factory.has_project_credential(
        body.project, provider, llm_config
    ):
        scope = "project"

    # Both candidates, not just the global one: a project run may have used the
    # project variable, and scrubbing only the global key would leave exactly
    # the credential this run used exposed in the 502 (design D9).
    secrets = _credential_values(provider, body.project)

    flight: SingleFlight = request.app.state.prompt_test_flight
    with flight.hold(session.sid):
        async with registry.track("prompt-test"):
            try:
                outcome = await run_query(client, body.model, to_messages(rendered))
            except HTTPException:
                raise
            except Exception as e:
                logger.error("Prompt test run failed: %r", e, exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=scrub_all(f"{type(e).__name__}: {e}", secrets),
                ) from e

    return PromptTestResponse(
        text=outcome.text,
        latency_ms=outcome.latency_ms,
        resolved=ResolvedRoute(
            provider=provider, model=body.model, credential_scope=scope
        ),
    )
```

Add this module-level helper to `routes.py`, above the route:

```python
def _credential_values(provider: LLMProvider, project: str | None) -> list[str]:
    """Every credential value a run for this provider could have used.

    Returned so the 502 path can mask each one (design D9). Values never leave
    this process: they are matched against an error message and discarded.
    An unknown provider (CUSTOM has no variable) yields an empty list, and
    scrub_all then leaves the message untouched.
    """
    name = PROVIDER_KEY_NAMES.get(provider)
    if name is None:
        return []
    candidates = [os.environ.get(name)]
    if project is not None:
        candidates.append(os.environ.get(f"{normalize_project_name(project)}_{name}"))
    return [value for value in candidates if value]
```

Add the imports this needs: `os`, `PROVIDER_KEY_NAMES` from `webui.catalogue`, `get_llm_config` from `utils.config`, `LLMFactory` from `llm.factory`, `LLMProvider` from `llm.base`, `normalize_project_name` from `utils.naming`, `TaskRegistry` / `get_task_registry` from `webui.inflight`, and `SingleFlight` / `run_query` / `scrub_all` / `to_messages` from `webui.prompt_test`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/unit/webui/test_prompt_test_route.py -v`
Expected: PASS

- [ ] **Step 7: Run the full backend suite**

Run: `python -m pytest tests/unit tests/integration -q`
Expected: PASS

- [ ] **Step 8: Lint and commit**

```bash
python -m ruff check testbench_ai_service/webui/ testbench_ai_service/main.py tests/unit/webui/
python -m ruff format --check testbench_ai_service/webui/ testbench_ai_service/main.py tests/unit/webui/
git add testbench_ai_service/webui/routes.py testbench_ai_service/webui/models.py testbench_ai_service/main.py tests/unit/webui/test_prompt_test_route.py
git commit -m "Run the edited prompt against a real model"
```

---

### Task 10: Frontend API layer

Types plus one query hook and one mutation hook, so the two UI tasks can be reviewed on their own.

**Corrected against the real codebase** (the plan's first draft assumed a different layout):
`api/queries.ts` holds `useQuery` hooks, `api/mutations.ts` holds `useMutation` hooks, and
`api/prompts.ts` is pure domain helpers with no API calls in it at all. There is no standalone
`api/models.ts` and none is added. `apiFetch(path, init)` takes a plain `RequestInit`, so a POST
body is `body: JSON.stringify(...)` — there is no `json:` option — and `apiFetch` attaches the
CSRF header itself for unsafe methods, so no hook sets it.

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/queries.ts`
- Modify: `frontend/src/api/mutations.ts`
- Test: `frontend/src/api/models.test.tsx`

**Interfaces:**
- Consumes: `apiFetch` (`frontend/src/api/client.ts`)
- Produces:
  - `RoutingFamily = 'chat' | 'reasoning' | 'adaptive' | 'budget' | 'fallback'`
  - `CatalogueModel`, `CatalogueProvider`, `ModelCatalogue`, `ResolvedRoute`, `PromptTestResult`, `ExtraModelEntry`
  - `useModels(project?: string, opts?)` in `queries.ts` — query key `['models', project ?? null]`
  - `useTestPrompt()` in `mutations.ts` — mutation taking `{messages, vars, agent_context, model, project}`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/api/models.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, expect, test, vi } from 'vitest'
import { useTestPrompt } from './mutations'
import { useModels } from './queries'

afterEach(() => vi.unstubAllGlobals())

const CATALOGUE = {
  providers: [
    {
      provider: 'openai',
      key_present: true,
      models: [{ id: 'gpt-4o', routing: 'chat', source: 'builtin' }],
    },
  ],
}

function stubFetch(body: unknown) {
  const spy = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  vi.stubGlobal('fetch', spy)
  return spy
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

test('useModels fetches the catalogue', async () => {
  stubFetch(CATALOGUE)
  const { result } = renderHook(() => useModels(), { wrapper })
  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  expect(result.current.data?.providers[0].models[0].id).toBe('gpt-4o')
})

test('useModels passes the project through as a query parameter', async () => {
  const spy = stubFetch(CATALOGUE)
  const { result } = renderHook(() => useModels('Car Configurator'), { wrapper })
  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  expect(String(spy.mock.calls[0][0])).toContain('project=Car%20Configurator')
})

test('useModels omits the query parameter when no project is given', async () => {
  const spy = stubFetch(CATALOGUE)
  const { result } = renderHook(() => useModels(), { wrapper })
  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  expect(String(spy.mock.calls[0][0])).not.toContain('project=')
})

test('useTestPrompt posts the body as JSON', async () => {
  const spy = stubFetch({
    text: 'ok',
    latency_ms: 12,
    resolved: { provider: 'anthropic', model: 'claude-opus-5', credential_scope: 'global' },
  })
  const { result } = renderHook(() => useTestPrompt(), { wrapper })

  result.current.mutate({
    messages: [],
    vars: {},
    agent_context: {},
    model: 'claude-opus-5',
    project: null,
  })

  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  const init = spy.mock.calls[0][1] as RequestInit
  expect(init.method).toBe('POST')
  expect(JSON.parse(init.body as string).model).toBe('claude-opus-5')
  expect(result.current.data?.resolved.credential_scope).toBe('global')
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/api/models.test.tsx`
Expected: FAIL — `useModels` / `useTestPrompt` are not exported

- [ ] **Step 3: Add the types to `api/types.ts`**

```ts
export type RoutingFamily = 'chat' | 'reasoning' | 'adaptive' | 'budget' | 'fallback'

export interface CatalogueModel {
  id: string
  routing: RoutingFamily
  /** `builtin` comes from a client's routing set; only `config` is removable. */
  source: 'builtin' | 'config'
}

export interface CatalogueProvider {
  provider: string
  /** Whether a credential exists. Presence only — never a value. */
  key_present: boolean
  models: CatalogueModel[]
}

export interface ModelCatalogue {
  providers: CatalogueProvider[]
}

export interface ResolvedRoute {
  provider: string
  model: string
  /** Which credential the run actually used; `global` means the fallback hit. */
  credential_scope: 'project' | 'global'
}

export interface PromptTestResult {
  text: string
  latency_ms: number
  resolved: ResolvedRoute
}

/** One `llm_config.extra_models` entry as the LLM view edits it. */
export interface ExtraModelEntry {
  provider: string
  routing: RoutingFamily
}
```

- [ ] **Step 4: Add `useModels` to `api/queries.ts`**

Follow `usePromptMeta`'s shape — it is the existing parameterised query in this file.

```ts
/**
 * The model catalogue, optionally scoped to a project.
 *
 * With a project, `key_present` reflects the project variable OR the global
 * one — matching the backend's silent credential fallback, so the answer is
 * "will a run find a key at all".
 */
export function useModels(
  project?: string,
  { enabled = true }: { enabled?: boolean } = {},
) {
  const query = project ? `?project=${encodeURIComponent(project)}` : ''
  return useQuery({
    queryKey: ['models', project ?? null],
    queryFn: () => apiFetch<ModelCatalogue>(`/models${query}`),
    staleTime: Infinity,
    enabled,
  })
}
```

Add `ModelCatalogue` to the existing `./types` import in that file.

- [ ] **Step 5: Add `useTestPrompt` to `api/mutations.ts`**

Follow `useRenderPrompt`'s shape — it is the closest existing mutation.

```ts
/**
 * Run the current draft against a real model.
 *
 * The one console action that spends money, so it is never called implicitly —
 * only from the editor's explicit Test run button.
 */
export function useTestPrompt() {
  return useMutation({
    mutationFn: (body: {
      messages: PromptMessageDoc[]
      vars: Record<string, unknown>
      agent_context: Record<string, unknown>
      model: string
      project: string | null
    }) =>
      apiFetch<PromptTestResult>('/prompts/test', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
  })
}
```

Add `PromptTestResult` to the existing `./types` import in that file.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/api && npx tsc -b`
Expected: PASS, no type errors

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/queries.ts frontend/src/api/mutations.ts frontend/src/api/models.test.tsx
git commit -m "Add the catalogue query and test-run mutation hooks"
```

### Task 11: `TestRunPanel` in the prompt editor

Read-only against the catalogue: the picker consumes `GET /models` and offers free-text entry, but has no add control — adding lives on the LLM provider view (Task 12).

**Files:**
- Create: `frontend/src/components/TestRunPanel.tsx`
- Modify: `frontend/src/screens/PromptEditor.tsx`
- Modify: `frontend/src/i18n/en.ts`, `frontend/src/i18n/de.ts`
- Test: `frontend/src/components/TestRunPanel.test.tsx`

**Interfaces:**
- Consumes: `useModels`, `useTestPrompt`, `PromptTestResult`, `CatalogueModel` (Task 10)
- Produces: `<TestRunPanel messages vars agentContext isAdmin lang />`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/TestRunPanel.test.tsx`. It mocks the two **hooks** from Task 10 —
not any bare fetcher — so the component is tested in isolation and no `QueryClient` is needed:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ComponentProps } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { TestRunPanel } from './TestRunPanel'

const mutate = vi.fn()
let runState: Record<string, unknown> = {}
let modelsState: Record<string, unknown> = {}

vi.mock('../api/queries', () => ({
  useModels: () => modelsState,
  useProjects: () => ({ data: { projects: [] }, isLoading: false, isError: false }),
}))

vi.mock('../api/mutations', () => ({
  useTestPrompt: () => ({ mutate, ...runState }),
}))

beforeEach(() => {
  mutate.mockReset()
  runState = { isPending: false, data: undefined, error: null }
  modelsState = {
    isLoading: false,
    isError: false,
    data: {
      providers: [
        {
          provider: 'anthropic',
          key_present: true,
          models: [
            { id: 'claude-opus-5', routing: 'adaptive', source: 'builtin' },
            { id: 'my-model', routing: 'fallback', source: 'config' },
          ],
        },
      ],
    },
  }
})

function renderPanel(props: Partial<ComponentProps<typeof TestRunPanel>> = {}) {
  return render(
    <MemoryRouter>
      <TestRunPanel
        messages={[
          { role: 'user', source: 'inline', file: null, content: 'hi', readable: true },
        ]}
        vars={{}}
        agentContext={{}}
        isAdmin
        lang="en"
        {...props}
      />
    </MemoryRouter>,
  )
}

test('lists catalogue models with their routing family', async () => {
  renderPanel()
  expect(await screen.findByRole('option', { name: /claude-opus-5/ })).toBeInTheDocument()
})

test('marks a fallback model so a degraded call is visible', async () => {
  renderPanel()
  const option = await screen.findByRole('option', { name: /my-model/ })
  expect(option.textContent).toMatch(/fallback/i)
})

test('a free-text model reaches the request', async () => {
  renderPanel()
  const user = userEvent.setup()

  const field = screen.getByLabelText(/model/i)
  await user.clear(field)
  await user.type(field, 'typed-model')
  await user.click(screen.getByRole('button', { name: /test run/i }))

  await waitFor(() =>
    expect(mutate).toHaveBeenCalledWith(expect.objectContaining({ model: 'typed-model' })),
  )
})

test('shows the resolved route including the credential scope', async () => {
  runState = {
    isPending: false,
    error: null,
    data: {
      text: 'the answer',
      latency_ms: 42,
      resolved: {
        provider: 'anthropic',
        model: 'claude-opus-5',
        credential_scope: 'global',
      },
    },
  }
  renderPanel()

  expect(await screen.findByText(/the answer/)).toBeInTheDocument()
  expect(screen.getByText(/42/)).toBeInTheDocument()
  expect(screen.getByText(/global key/i)).toBeInTheDocument()
})

test('the button is disabled while a run is in flight', () => {
  runState = { isPending: true, data: undefined, error: null }
  renderPanel()
  expect(screen.getByRole('button', { name: /test run/i })).toBeDisabled()
})

test('a non-admin cannot start a run', () => {
  renderPanel({ isAdmin: false })
  expect(screen.getByRole('button', { name: /test run/i })).toBeDisabled()
})

test('has no add-model control — that lives on the LLM view', async () => {
  renderPanel()
  await screen.findByRole('option', { name: /claude-opus-5/ })
  expect(screen.queryByRole('button', { name: /add model/i })).not.toBeInTheDocument()
})

test('the hint to add a model is an in-app link, not a full page load', async () => {
  // A plain <a href> would bypass PromptEditor's useBlocker and fire
  // beforeunload, losing the operator's unsaved draft. react-router's Link
  // keeps the guard in charge.
  renderPanel()
  const link = await screen.findByRole('link', { name: /llm/i })
  expect(link).toHaveAttribute('href', '/admin/llm')
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/TestRunPanel.test.tsx`
Expected: FAIL — cannot resolve `./TestRunPanel`

- [ ] **Step 3: Add the i18n keys**

To **both** `en.ts` and `de.ts` (English then German):

```ts
  testRun: 'Test run' / 'Testlauf',
  testRunModel: 'Model' / 'Modell',
  testRunProject: 'Project' / 'Projekt',
  testRunProjectGlobal: 'Global configuration' / 'Globale Konfiguration',
  testRunGo: 'Test run' / 'Testlauf starten',
  testRunPending: 'Running…' / 'Läuft…',
  testRunLatency: 'Latency' / 'Antwortzeit',
  testRunRoute: 'Resolved route' / 'Aufgelöste Route',
  testRunScopeProject: 'project key' / 'Projektschlüssel',
  testRunScopeGlobal: 'global key' / 'globaler Schlüssel',
  testRunFallbackHint: 'no tuned routing' / 'keine abgestimmte Route',
  testRunAdminOnly: 'Only administrators can start a test run.'
    / 'Nur Administratoren können einen Testlauf starten.',
  testRunAddHint: 'Missing a model? Add it under LLM.'
    / 'Modell nicht dabei? Unter LLM hinzufügen.',
```

- [ ] **Step 4: Write `TestRunPanel.tsx`**

Build the component to satisfy the test above:

- `useModels(project)` from `api/queries.ts` — do not call `apiFetch` directly.
- A `<select>` labelled by `t.testRunModel`, with one `<optgroup>` per provider whose label carries the provider name and, when `key_present` is false, a "no key" marker. Each `<option>` renders `` `${model.id} · ${model.routing}` `` so a `fallback` entry reads as such (`t.testRunFallbackHint` for the `fallback` family).
- A free-text `<input>` bound to the same state as the select, so typing a model not in the catalogue still submits — the select writes into the input's state rather than replacing it.
- A project `<select>` defaulting to `t.testRunProjectGlobal` (value `null`).
- A submit button labelled `t.testRunGo`, `disabled={!isAdmin || isPending}`, showing `t.testRunPending` while in flight; when `!isAdmin`, render `t.testRunAdminOnly` beside it.
- On success, render the text in a `<pre>`, plus `t.testRunLatency` with `latency_ms`, and `t.testRunRoute` with `provider`, `model` and the scope word (`t.testRunScopeProject` / `t.testRunScopeGlobal`).
- On error, surface the message the way `RenderPreview` already surfaces its mutation error.
- Render `t.testRunAddHint` as a link to `/admin/llm`. No add control here.

- [ ] **Step 5: Mount it in `PromptEditor.tsx`**

Render `<TestRunPanel …/>` directly after the existing `<RenderPreview …/>`, passing the same `messages`, `vars` and `agent_context` values `RenderPreview` receives, plus `isAdmin` and `lang` from the props already in scope.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd frontend && npx vitest run && npx tsc -b`
Expected: PASS — including `i18n.test.ts`, which enforces en/de key parity

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/TestRunPanel.tsx frontend/src/components/TestRunPanel.test.tsx frontend/src/screens/PromptEditor.tsx frontend/src/i18n/en.ts frontend/src/i18n/de.ts
git commit -m "Run the edited prompt from the editor"
```

---

### Task 12: `ModelTable` on the LLM provider view

The add-a-model surface. It writes **draft edits** and never calls an API: the LLM provider view is already a draft → preview → apply screen over `[testbench-ai-service.llm_config]`, which is exactly where `extra_models` lives (D10). A dedicated write route would bypass the unified diff the operator sees before every other change to that table.

Only operator entries are listed. Built-ins are not shown here, because showing them would imply they are editable.

**Files:**
- Create: `frontend/src/components/ModelTable.tsx`
- Modify: `frontend/src/screens/ConfigSection.tsx`
- Modify: `frontend/src/i18n/en.ts`, `frontend/src/i18n/de.ts`
- Test: `frontend/src/components/ModelTable.test.tsx`

**Interfaces:**
- Consumes: `useDraft` (existing, `frontend/src/state/draft.tsx`), `ExtraModelEntry`, `RoutingFamily` (Task 10), `ConfigIssue` (existing, `api/types.ts`)
- Produces: `<ModelTable entries issues readOnly lang />` writing draft edits at `llm_config.extra_models.<model>.provider` / `.routing`, and `llm_config.extra_models.<model>` = `null` to remove

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/ModelTable.test.tsx`:

```tsx
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ComponentProps } from 'react'
import { expect, test, vi } from 'vitest'
import { ModelTable } from './ModelTable'

const setEdit = vi.fn()
const removeKey = vi.fn()

vi.mock('../state/draft', () => ({
  useDraft: () => ({ setEdit, removeKey, edits: {} }),
}))

function renderTable(props: Partial<ComponentProps<typeof ModelTable>> = {}) {
  return render(
    <ModelTable
      entries={{ 'claude-opus-6': { provider: 'anthropic', routing: 'adaptive' } }}
      issues={[]}
      lang="en"
      {...props}
    />,
  )
}

test('lists the configured models', () => {
  renderTable()
  expect(screen.getByDisplayValue('claude-opus-6')).toBeInTheDocument()
})

test('does not list built-in models', () => {
  renderTable()
  expect(screen.queryByDisplayValue('gpt-4o')).not.toBeInTheDocument()
})

test('adding a model writes both draft edits', async () => {
  renderTable()
  const user = userEvent.setup()

  await user.type(screen.getByLabelText(/new model/i), 'gpt-6')
  await user.selectOptions(screen.getByLabelText(/new provider/i), 'openai')
  await user.selectOptions(screen.getByLabelText(/new routing/i), 'reasoning')
  await user.click(screen.getByRole('button', { name: /add/i }))

  expect(setEdit).toHaveBeenCalledWith('llm_config.extra_models.gpt-6.provider', 'openai')
  expect(setEdit).toHaveBeenCalledWith('llm_config.extra_models.gpt-6.routing', 'reasoning')
})

test('removing a model queues a null edit', async () => {
  renderTable()
  const user = userEvent.setup()

  await user.click(screen.getByRole('button', { name: /remove/i }))

  // null means "remove this key" on both sides of the wire.
  expect(setEdit).toHaveBeenCalledWith('llm_config.extra_models.claude-opus-6', null)
})

test('routing choices are filtered to what the provider accepts', async () => {
  renderTable()
  const user = userEvent.setup()

  await user.selectOptions(screen.getByLabelText(/new provider/i), 'anthropic')

  const routing = screen.getByLabelText(/new routing/i)
  expect(within(routing).queryByRole('option', { name: 'chat' })).not.toBeInTheDocument()
  expect(within(routing).getByRole('option', { name: 'adaptive' })).toBeInTheDocument()
})

test('renders a config issue against the offending row', () => {
  renderTable({
    issues: [
      {
        path: 'llm_config.extra_models.claude-opus-6.routing',
        message: 'routing is not available for provider',
      },
    ],
  })
  expect(screen.getByRole('alert')).toHaveTextContent(/not available/)
})

test('a read-only operator cannot add or remove', () => {
  renderTable({ readOnly: true })
  expect(screen.getByRole('button', { name: /add/i })).toBeDisabled()
  expect(screen.getByRole('button', { name: /remove/i })).toBeDisabled()
})
```


- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/ModelTable.test.tsx`
Expected: FAIL — cannot resolve `./ModelTable`

- [ ] **Step 3: Add the i18n keys**

To **both** `en.ts` and `de.ts`:

```ts
  models: 'Models' / 'Modelle',
  modelsHint: 'Models offered in addition to those the service already knows.'
    / 'Modelle zusätzlich zu denen, die der Dienst bereits kennt.',
  modelsEmpty: 'No additional models configured.'
    / 'Keine zusätzlichen Modelle konfiguriert.',
  modelName: 'Model' / 'Modell',
  modelProvider: 'Provider' / 'Anbieter',
  modelRouting: 'Request shape' / 'Anfrageform',
  modelNewName: 'New model' / 'Neues Modell',
  modelNewProvider: 'New provider' / 'Neuer Anbieter',
  modelNewRouting: 'New routing' / 'Neue Anfrageform',
  modelAdd: 'Add' / 'Hinzufügen',
  modelRemove: 'Remove' / 'Entfernen',
```

- [ ] **Step 4: Write `ModelTable.tsx`**

```tsx
import { useState } from 'react'

import type { ConfigIssue, ExtraModelEntry, RoutingFamily } from '../api/types'
import { useDraft } from '../state/draft'
import { useTranslations, type Lang } from '../i18n'

/**
 * Which request shapes each provider's client can produce. Mirrors
 * `ALLOWED_ROUTING` in models/config.py — the server refuses a bad pairing as
 * a ConfigIssue, and filtering here keeps the operator from queuing one.
 *
 * Wire tokens, not prose: kept in English regardless of `lang`, the same way
 * Field.tsx never translates `spec.key`.
 */
const ALLOWED_ROUTING: Record<string, RoutingFamily[]> = {
  openai: ['chat', 'reasoning', 'fallback'],
  azure_openai: ['chat', 'reasoning', 'fallback'],
  anthropic: ['adaptive', 'budget', 'fallback'],
  custom: ['fallback'],
}

const PROVIDERS = Object.keys(ALLOWED_ROUTING)

/** The draft path one entry's field lives at. */
function path(model: string, field?: 'provider' | 'routing'): string {
  const base = `llm_config.extra_models.${model}`
  return field ? `${base}.${field}` : base
}
```

Then the component: it renders `t.models` as a heading with `t.modelsHint`, one row per entry (model name read-only, provider and routing shown, a `t.modelRemove` button), an add row (`t.modelNewName` text input, `t.modelNewProvider` select over `PROVIDERS`, `t.modelNewRouting` select over `ALLOWED_ROUTING[provider]`, and a `t.modelAdd` button), and `t.modelsEmpty` when `entries` is empty.

- `onAdd` calls `setEdit(path(name, 'provider'), provider)` then `setEdit(path(name, 'routing'), routing)`, then clears the add-row state.
- `onRemove` calls `setEdit(path(name), null)` — `null` is *remove this key* in both `state/draft.tsx` and the backend's `merge_edits`, so removal needs no special case.
- Issues are matched against a row with the same prefix rule `ConfigSection` uses (`issue.path === key || issue.path.startsWith(key + '.')`) and rendered in a `role="alert"`.
- Every control takes `disabled={readOnly}`.

- [ ] **Step 5: Mount it in `ConfigSection.tsx`**

Render it only for the LLM section, below the existing field rows:

```tsx
{section === 'llm' && (
  <ModelTable
    entries={
      (valueAt(config.data.config, 'llm_config.extra_models') ?? {}) as Record<
        string,
        ExtraModelEntry
      >
    }
    issues={issues}
    readOnly={!isAdmin}
    lang={lang}
  />
)}
```

Match `valueAt`'s actual signature from `./fields`; if it takes the config object first and a dotted path second as written above, use it as-is.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd frontend && npx vitest run && npx tsc -b`
Expected: PASS — including `i18n.test.ts`

- [ ] **Step 7: Full verification**

```bash
cd /e/Testbench-ecosystem/testbench-ai-service
python -m pytest tests/unit tests/integration -q
python -m ruff check testbench_ai_service tests
python -m ruff format --check testbench_ai_service tests
cd frontend && npx vitest run && npx tsc -b && npm run build
```

Expected: all green. Record the actual pass/fail counts — do not claim success without reading the output.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/ModelTable.tsx frontend/src/components/ModelTable.test.tsx frontend/src/screens/ConfigSection.tsx frontend/src/i18n/en.ts frontend/src/i18n/de.ts
git commit -m "Add and remove catalogue models from the LLM view"
```

---

## Manual verification

After Task 12, confirm the increment end-to-end against a running service:

1. `GET /admin/api/models` as an admin returns Claude 5 ids under `anthropic` with `routing: "adaptive"` — proving Task 3 reached the catalogue through Task 1's derivation with no list edited by hand.
2. On `/admin/llm`, add `claude-opus-6` / `anthropic` / `adaptive`. The pending-changes banner appears; `POST /config/preview` shows it as a TOML diff under `[testbench-ai-service.llm_config.extra_models]`; apply writes and hot-reloads it.
3. The prompt editor's model picker now offers `claude-opus-6` with `source: "config"`.
4. Add a deliberately invalid entry (`anthropic` / `chat`). The preview refuses it with an issue rendered against that row, and nothing is written.
5. With no `ANTHROPIC_API_KEY` set, a test run returns 400 naming the variable — and never its value.

## Deferred to a later increment

Recorded here so an executor does not treat them as gaps: streaming; token usage and cost; multi-turn; persisted test history; rate limiting; per-project `llm_config` editing (4d); variant repointing; raw-text repair mode for an unparseable `prompt.yaml`. Also unchanged from 4b: the CRLF→LF rewrite on first save, `main.py:107`'s relative `Path("config.toml")` fallback, and `config.py:360` bypassing `resolve_prompt_file_path`.
