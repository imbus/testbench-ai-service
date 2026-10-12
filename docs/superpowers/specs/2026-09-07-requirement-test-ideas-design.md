# Requirement Test Ideas Agent — Design

**Date:** 2026-09-07
**Status:** Approved for implementation planning
**Agent key:** `requirement`

## 1. Purpose

Generate test ideas for a single requirement and write them into the description of
the test theme(s) that link that requirement.

The user triggers the agent from the REQUIREMENTS tree; `ExecutionContext.root_uid`
identifies the requirement. Output lands in the test structure tree, so the agent
bridges the two trees via the requirement links TestBench already maintains.

## 2. The context problem

Requirements in a TestBench baseline carry no prose. Every node in
`agents/requirement/model.py` (`Requirement`) holds only:

- `id`, `extendedID` — e.g. `ER_WHY299`
- `name` — a *title*, e.g. `"Automatic discount"`
- `version`, `status`, `owner`, `priority`
- `udfs` — in practice a handful of characters (`Business Units`, `Owner Priorität`)

A requirement is roughly ten words. Similarity retrieval over such a corpus adds
little on its own, because there is almost no text to retrieve. The context that
does exist is structural, and it is nearly free:

- the ancestor chain (`3. Functional Requirements` → `Source of basic data` →
  `File import`) carries most of the semantic weight
- siblings define scope boundaries (`Automatic discount` vs `Dealer allows discount`)
- `Baseline.reqProjectName` / `repository` frame the domain
- `RequirementReference` (`models/testbench.py:201`) links test themes, test case
  sets and test cases back to requirements, making existing tests available as both
  coverage information and house-style examples

Baselines reach thousands of requirements, so the whole tree cannot simply be sent.
Selection is required.

## 3. Architecture

```
   precheck  ->  PrecheckResult(passed=True)          # no gating (deliberate, see 3.1)

   run(context, conn, llm_client, item_ids=[])        # item_ids unused
     |
     +-- 1. load the CURRENT baseline tree + UDFs     (existing requirement/utils.py)
     +-- 2. locate the target requirement by context.root_uid
     +-- 3. resolve target theme(s) via RequirementReference links
     +-- 4. assemble context (tiers 1-6, budget-trimmed)
     |        tier 6 -> Ranker: LexicalRanker | LlmRerankRanker
     +-- 5. patch theme description: generation-started marker
     +-- 6. generation LLM call -> test ideas
     +-- 7. patch success  |  on exception patch rollback
```

### 3.1 Empty precheck

`precheck` returns `PrecheckResult(passed=True)` with no items and performs no
validation. All work, including the gates that would naturally belong in a precheck
(requirement resolvable, linked theme exists, spec not locked), happens in `run`.

Consequence: the endpoint never returns 409. `routes.py` has already returned 202
by the time any gate fails, so failures are visible only in the log. Specific,
loud logging at each abort point is therefore part of the contract, not a nicety.
The gates can be lifted into `precheck` later without touching any other module.

### 3.2 Modules

| Module | Kind | Responsibility |
|---|---|---|
| `agents/requirement/utils.py` | exists, I/O | baseline load, loader-job polling, `iter_requirements`, `attach_udfs` |
| `agents/requirement/model.py` | exists, pure | `Requirement`, `Baseline`, loader-job models |
| `agents/requirement/tree.py` | new, pure | `ancestors()`, `siblings()`, `subtree()`, `outline()`, node rendering |
| `agents/requirement/ranking.py` | new, mostly pure | `Ranker` protocol, `LexicalRanker`, `LlmRerankRanker` |
| `agents/requirement/context.py` | new, pure | tiered budget assembler producing `RequirementAgentData` |
| `agents/requirement/linking.py` | new, I/O | requirement key → test structure element lookup |
| `agents/requirement/agent.py` | exists as stub | orchestration of steps 1-7 and write-back |

Of the five new and changed modules, `tree.py` and `context.py` are fully pure and
`ranking.py` is pure apart from the one LLM strategy, so budget trimming, tier
priority, ranking and rendering are all testable with fixture trees, no network and
no LLM. Only `linking.py` and `agent.py` require TestBench.

## 4. Context assembly

### 4.1 Tiers

Spent in order against a token budget. Each tier has its own cap so a later tier
cannot starve an earlier one.

| Tier | Content | Cost |
|---|---|---|
| 1 | Target requirement, full: name, id, version, status, owner, priority, all UDFs | fixed |
| 2 | Ancestor chain root→target, plus the target's own subtree | tens of nodes |
| 3 | Siblings with UDFs | tens of nodes |
| 4 | Target theme's current description + names of test case sets already under it | 1-2 calls |
| 5 | Test *themes* linked to tier-2/3 requirements, plus the test case set names below them | no extra calls |
| 6 | Top-N related requirements elsewhere in the baseline (titles + UDFs), filling the remaining budget | no extra calls |

Tiers 1-3 always fit. Tier 6 contributes titles only and never triggers test
lookups.

Tier 5 is narrower than first planned, and deliberately so. Reading the requirement
links of *test case sets* would cost one specification request per test case set
across the whole TOV — the unbounded fan-out this design rules out. Tier 5 therefore
uses theme-level links only, taken from the theme specifications already read to
locate the target, and adds the names of the test case sets below those themes, which
the structure tree supplies for free. Cost: zero requests beyond the theme scan.

That theme scan is itself one specification read per test theme, because the tree
endpoint returns only `spec.key`, `locker` and `status` per node. It is bounded by the
number of themes in the TOV — typically tens — and never by baseline size.

A tier that does not fit renders as an empty string rather than being truncated
mid-node. Empty tiers are legitimate: a requirement with no siblings and no linked
tests still yields a valid prompt.

### 4.2 Two-stage tier 6

Tier 6 is a retrieve-then-generate pipeline. A `Ranker` returns an *ordering* of
candidate requirements; the budget alone decides how many of them are included, so
neither strategy truncates the tier itself.

- `LexicalRanker` (default) — orders all baseline requirements by token overlap of
  name and UDF values against the target. Deterministic, ties broken stably by `id`.
- `LlmRerankRanker` (opt-in) — takes the lexical ranker's top ~80 as a shortlist and
  asks a cheap model to reorder it by relevance. Shortlist entries the model omits
  keep their lexical order below the ones it ranked, so the tier can still be filled
  to budget.

Which ranker is used is a module-level constant in v1 (see 4.4), not a per-request
or per-project setting.

The lexical stage is not optional even when reranking is enabled: at thousands of
requirements the full outline does not fit in a selector call either, so the
lexical ranker acts as the prefilter that makes reranking possible.

`LlmRerankRanker` failures — timeout, malformed output, IDs absent from the
shortlist — fall back to the lexical ordering and log. Tier 6 is an enhancement,
never a dependency, so a ranker failure must not abort a run.

Keeping ranking behind a protocol means an embedding-based ranker can be added
later, and measured against the other two, without touching `context.py` or
`agent.py`.

### 4.3 Signature and agent data

```python
assemble_context(
    baseline: Baseline,
    target: Requirement,
    theme_context: ThemeContext | None,   # tiers 4-5, from linking.py
    ranker: Ranker,
    budget: TokenBudget,
) -> RequirementAgentData
```

`RequirementAgentData` carries rendered strings, one per tier group, so Python owns
selection and the Jinja template owns presentation:

| Field | Content |
|---|---|
| `requirement` | the target, fully rendered (tier 1) |
| `requirement_path` | ancestor chain, one line per level (tier 2) |
| `requirement_subtree` | children, indented (tier 2) |
| `requirement_siblings` | siblings with UDFs (tier 3) |
| `existing_tests` | target theme description + TCS names under it (tier 4) |
| `related_tests` | TCS linked to structural-core requirements (tier 5) |
| `related_requirements` | tier 6 output, post-ranking |
| `requirement_obj` | the `Requirement` model itself, mirroring how the describer passes `test_case_set_obj` |

`validate_template_and_agent_vars` (`routes.py:213`) checks `AGENT_DATA_CLASS` type
hints against the prompt template placeholders **at request time**. These fields and
`prompts/{en,de}/requirement/prompt.yaml` must match exactly, or every trigger
returns 422 before `run` is reached. The current `hello` placeholder is replaced.

### 4.4 Configuration

Budget size, per-tier caps, shortlist size and ranker selection are
module-level constants in `context.py` and `ranking.py` for v1, following the
precedent of `REQUIREMENTS_JOB_TIMEOUT` in `utils.py`. Promoting them to
`AgentConfig` would require extending that model, which has no `extra="allow"`;
that is deferred until there is a demonstrated need to vary them per project.

## 5. Baseline selection

`run` loads exactly one baseline: the one whose `type` is `CURRENT`.

The current stub iterates every baseline and loads each. Each load starts a loader
job polled at 1s intervals with a 120s timeout (`utils.py:26-30`), so several
baselines of thousands of requirements cost minutes per trigger for trees that are
then discarded. This must be fixed as part of the implementation.

If the target requirement is not in the `CURRENT` baseline, the agent logs a
warning naming the `root_uid` and stops. It deliberately does **not** fall back to
scanning the remaining baselines: the same requirement exists in multiple baselines
at different versions, so an arbitrary pick would silently generate test ideas from
a stale requirement. No answer is preferable to a wrong one here.

## 6. Error handling

In flow order:

| Failure | Handling |
|---|---|
| Baseline load times out, or job returns `Left` | `RuntimeError` from `parse_loader_job`, logged with baseline serial; abort before any patch |
| `root_uid` matches no requirement | Log error with the `root_uid` and the baseline searched; abort |
| No test theme links the requirement | Log warning; abort before any patch |
| Several themes link the requirement | Process each concurrently via `asyncio.gather`, one generation call per theme |
| A theme's spec is locked by another user | Skip that theme with a warning; continue with the rest |
| `LlmRerankRanker` fails, times out, or returns unknown IDs | Fall back to lexical ordering, log; never abort |
| Generation call fails | Rollback patch restoring the previous description, then re-raise |
| Rollback patch itself fails | Log it and re-raise the *original* exception so the root cause is not masked |

Because `precheck` no longer gates, none of these aborts reach the caller.

## 7. Open items to verify against a live TestBench

Status after implementation. Only item 2 still needs a live server:

1. **Which key `RequirementReference.key` holds** — *resolved without needing the
   answer.* Because `requirementKey.serial` and `key.serial` share no values, matching
   a reference against both is safe: it can match at most one, so no false positive is
   possible. `linking.requirement_keys` does exactly that.
2. **The read endpoint for a test theme's spec details** — *still open.*
   `linking.get_theme_specification` assumes
   `GET /2/projects/{project_key}/specifications/{spec_key}`, mirroring the `PATCH`
   this repo already issues at that path. It is the only place that URL is built, so
   correcting it is a one-line change. Verify before first real use.
3. **What `root_uid` contains for a requirement** — *handled by trying each
   candidate.* `tree.find_requirement` matches `extendedID`, then `id`, then
   `requirementKey.serial`, then `key.serial`, each across the whole tree before the
   next, and logs which field matched, so the first real trigger answers this without
   a guess having been baked in.
4. **Whether the baselines listing carries `type`** — *new, found during
   implementation.* `load_current_baseline` selects the entry whose `type` is
   `CURRENT`, and raises with the observed types when none is, rather than falling
   back to an arbitrary baseline.

## 8. Testing

| Target | Approach |
|---|---|
| Fixture | `tmp/test.json` becomes `tests/unit/data/requirement_baseline.json` (VSR-Dreamcar: 17 nodes, 4 levels, populated and empty UDFs). A synthetic ~3000-node tree is generated in-test for budget behaviour. |
| `tree.py` | `ancestors`/`siblings`/`subtree`/`outline` against the fixture, including a root-level node with no siblings, empty UDF values, and a childless leaf |
| `ranking.py` | `LexicalRanker` determinism and stable tie-breaking by `id`; `LlmRerankRanker` against a fake `LLMClient` returning valid IDs, malformed output, hallucinated IDs, and a timeout — each asserting fallback rather than an exception |
| `context.py` | tier priority under a tight budget; tier 6 cannot starve tiers 4-5; an overflowing tier renders empty, not truncated mid-node; the 3000-node tree respects the budget |
| `linking.py` | mocked TestBench responses, plus a test asserting the call count stays bounded to the structural core as baseline size grows — this is the N+1 regression guard |
| `agent.py` | orchestration with fakes: patch sequence is start→success on the happy path, start→rollback on generation failure, and no patch at all when requirement or theme cannot be resolved |
| Prompt contract | run `validate_template_and_agent_vars` for both `prompts/en/requirement/prompt.yaml` and the `de` equivalent against `RequirementAgentData`, catching the 422-before-`run` trap in CI |

Existing style is followed: the `MagicMock`-based `_conn` helper from
`tests/unit/agents/requirement/test_utils.py`, and `asyncio_mode = "auto"` so async
tests need no marker.

## 9. Out of scope

- Creating test structure elements. No write path for this exists in the repo;
  `post_project_tov_structure` is a read disguised as a POST. Ideas go into an
  existing theme's description only.
- Writing back into the requirement tree. Baselines are read-only imports from the
  RE repository.
- Batch operation over a requirement folder. One requirement per trigger.
- Embedding-based ranking. The `Ranker` protocol leaves room for it; the payoff is
  unproven on a corpus of ten-word titles.
- Per-project configuration of budget and ranker settings.
