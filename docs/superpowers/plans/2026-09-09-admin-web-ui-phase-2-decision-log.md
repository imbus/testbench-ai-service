# SDD ledger — plan: docs/superpowers/plans/2026-09-09-admin-web-ui-phase-2.md

Spec: docs/superpowers/specs/2026-09-08-admin-web-ui-design.md (read; binding authority)
Branch: admin-web-ui (not main — isolated)
Base at start: c853b74
Environment: .venv active, python 3.14, pytest 9.1.1, frontend deps installed in frontend/node_modules

## Pre-flight conflict scan

### Shared-surface pairs (producer → consumer, or same file)

| Tasks | Shared surface | Producer gives | Consumer expects | Finding |
|---|---|---|---|---|
| 2 → 4 | `webui/document.py` | `load_document`, `render_document`, `service_table` | same three, plus appends `apply_edits` | clean |
| 3 → 4 | `ConfigEdits` type | `dict[str, Any]`, dotted paths, `None` = remove | same semantics in `apply_edits` | clean — T4's `test_apply_edits_result_reparses_to_the_merged_dict` pins both paths to one meaning |
| 3 → 11 | `merge_edits`, `validate_edit_paths` | `(base, edits) -> dict`; `(edits) -> None` raising 400 | same | clean |
| 2 → 11 | document fns | as above | as above | clean |
| 6 → 11, 20 | `validate_config_dict` | `(dict) -> (AppConfig\|None, list[ConfigIssue])` | same tuple in both | clean |
| 7 → 11 | `file_diff` | `(path, current, proposed) -> FileDiff\|None` | same | clean |
| 8 → 11, 20 | `restart_required` | `(old, new) -> list[str]` sorted | same | clean |
| 5 → 12 | `write_atomic` | `(path, text) -> Path\|None` | same | clean |
| 10 → 12 | `hot_reload` | `async (app, config) -> None` | same | clean |
| 11 → 12 | `_plan_change` | `(edits, config_path, running) -> (PreviewResponse, str)` | same | clean |
| 9 → 11, 12, 20 | `TaskRegistry`, `get_task_registry` | `.count`, `.labels()`, `.track()` | `.count` only in routes | clean |
| 6,7,9,11,12,20 | `webui/models.py` | append-only: `ConfigIssue`, `FileDiff`, `ConfigEditsRequest`, `PreviewResponse`, `ApplyResponse`, `StatusResponse` fields | each task appends its own | clean — no task rewrites another's model |
| 9 → 20 | `webui/routes.py::read_status` | T9 gives 3-arg `build_status` call | T20 replaces with 4-arg | clean — T20 shows the full replacement, and T9's 4th param has a default so T9's own call site stays valid |
| 9 → 20 | `webui/status.py::build_status` | T9: `(config, started_at, in_flight_tasks=0)` | T20: adds `restart_required=None` | clean, both defaulted |
| 8 → 10 | `webui/reload.py` | `RESTART_FIELDS`, `restart_required` | appends `hot_reload` | clean |
| 13 → 14,15,16,17,19,20 | `useDraft`/`Edits` | `DraftApi` as specified | `valueOf`, `isChanged`, `setValue`, `unsetValue`, `revert`, `discardAll`, `edits`, `changeCount` — all used | clean |
| 14 → 17, 19 | `usePreview`, `useApply` | TanStack mutations over `Edits` | same | clean |
| 15 → 16 | `Field` | `{spec, saved, issue?, lang?}` | T16 passes all four | clean |
| 17,18,19 → 20 | banner/screen components | `PendingBanner({lang})`, `RestartBanner({lang, fields})`, `Raw({lang})` | same | clean |
| 14 → 20 | `api/types.ts` | T14 adds issue/diff/preview/apply types + `in_flight_tasks` on StatusResponse | T20 adds `restart_required` on StatusResponse | clean, both append |
| 15,17,19 → all | `i18n/en.ts` + `de.ts` | T15 `revert`; T17 twelve apply/diff keys; T19 three raw keys | `i18n.test.ts` asserts de/en key parity | clean — each task edits both files; parity test is the guard |
| 1 → 16 | `llm_config.timeout` / `max_retries` | T1 declares them on `LLMConfig` | **T1 claims "Task 15 renders both as number fields"** | **CONFLICT — see Ruling 1** |
| 1 → 21 | docs | T1 adds both to `docs/configuration.md` | T21 Step 4 asserts the LLM *screen* shows them | **same conflict as above** |
| 21 → 21 | `docs/web-console.md` | — | — | clean |

### Per-task self-consistency

| Task | Tests vs. code it specifies | Finding |
|---|---|---|
| 1 | 3 tests ↔ 2 declared fields + rewritten `_get_common_client_kwargs` | clean |
| 2 | 7 tests ↔ 3 functions | clean |
| 3 | 13 tests ↔ `validate_edit_paths` + `merge_edits` | clean |
| 4 | 9 tests ↔ `apply_edits` + 3 helpers | clean |
| 5 | 9 tests ↔ `write_atomic` | clean |
| 6 | 11 tests ↔ `validate_config_dict` + `ConfigIssue` | clean |
| 7 | 10 tests ↔ `file_diff` + `FileDiff` | clean |
| 8 | 14 tests ↔ `restart_required` + 2 constants | clean |
| 9 | 5 unit + 2 route tests ↔ `TaskRegistry` + wiring in 5 files | clean |
| 10 | 5 tests ↔ `hot_reload` | clean |
| 11 | 13 tests ↔ `_plan_change` + route | one test uses `with_suffix(".toml.bak")` where T12 uses `with_name` — **Ruling 2** |
| 12 | 12 tests ↔ route | clean |
| 13 | 13 tests ↔ `DraftProvider`/`useDraft` | `prune` splits paths on `.`, which breaks a project name containing a dot — **Ruling 3** (not reachable in phase 2) |
| 14 | 5 tests ↔ 2 hooks | clean |
| 15 | 14 tests ↔ `Field` | one test's name describes NaN but asserts the cleared-field path — **Ruling 4** |
| 16 | 5 new tests ↔ editable `ConfigSection` | clean once Ruling 1 lands |
| 17 | 5 + 9 tests ↔ 2 components | `getByText(/port/)` is ambiguous — the diff also contains `port` — **Ruling 5** |
| 18 | 3 tests ↔ `RestartBanner` | clean |
| 19 | 5 tests ↔ `Raw` | clipboard test spreads `navigator`, whose props are on the prototype — **Ruling 6** |
| 20 | 4 + 2 + 5 tests ↔ App/NavRail/status wiring | Step 5 declares `useState` that Step 6 removes, leaving an unused setter mid-task — **Ruling 7** |
| 21 | docs only | clean |
| 22 | verification only | clean |

## Pre-flight rulings

Ruling 1: `llm_config.timeout` and `llm_config.max_retries` are added to `LLM_FIELDS` in
`frontend/src/screens/fields.ts` as part of Task 16, and Task 1's Interfaces block is corrected to
name Task 16 rather than Task 15. — Why: the plan asserts in two places (Task 1's Interfaces, Task
21 Step 4) that the LLM screen shows both, but no task ever adds them to `LLM_FIELDS`; spec 11.2
declares them so the console can edit them, so shipping the model field without the form control
would satisfy neither the plan nor its reason for existing. Task 16 owns the LLM form, so it owns
the two rows. — Cost if wrong: two extra number fields on the LLM screen that an operator could
have left in the file by hand; trivially removable.

Ruling 2: Task 11's `test_preview_writes_nothing` uses `config_file.with_name("config.toml.bak")`,
matching Task 12. — Why: `with_suffix(".toml.bak")` relies on multi-dot-suffix handling that has
tightened across Python versions, and the project floor is 3.10 with 3.14 in use here; `with_name`
says exactly what is meant with no version dependence. — Cost if wrong: none, the two spellings
resolve to the same path today.

Ruling 3: `prune`'s dotted-path splitting stays as specified, and the phase-3 plan must key project
overrides by something other than a naive `.` split. — Why: every path phase 2 edits is a
single-segment or fixed nested config key with no dots in any segment, so the limitation is
unreachable here; solving it now would mean inventing a path-escaping scheme with no consumer.
Recorded so phase 3 does not inherit it silently. — Cost if wrong: a project literally named
`a.b` would mis-key its overrides — in phase 3, not phase 2.

Ruling 4: Task 15's test `leaves a half-typed number alone rather than sending NaN` is renamed
`records a cleared number field as a removal`, which is what it asserts. The NaN guard in the
implementation stays, with its comment, untested. — Why: the test name promised an assertion the
body does not make, and a real NaN test through `userEvent.type` into `<input type="number">` is
jsdom-implementation-dependent and would be flaky. An honest name beats a flaky test. — Cost if
wrong: the NaN branch is unguarded by tests; its failure mode is a raw string reaching the server,
which the server's own validation rejects with a field-addressed message.

Ruling 5: Task 17's `warns that the change needs a restart` asserts
`expect(screen.getByText(/Needs a restart:/).textContent).toContain('port')` instead of a bare
`getByText(/port/)`. — Why: `getByText(/port/)` matches both the restart line and the diff body, so
Testing Library throws on multiple matches and the test fails for the wrong reason. — Cost if
wrong: none; the scoped assertion is strictly stronger.

Ruling 6: Task 19's clipboard test uses `const user = userEvent.setup()` and asserts through
`await navigator.clipboard.readText()`, rather than stubbing `navigator` with a spread. — Why:
`{...navigator}` copies own properties only and `navigator`'s live on the prototype, so the stub
would yield a near-empty object; `userEvent.setup()` installs its own working clipboard stub, which
is both the supported route and less machinery. — Cost if wrong: the test asserts the clipboard
contents rather than that `writeText` was called — a stronger assertion either way.

Ruling 7: Task 20 Step 5 uses `const restartFields = useStatus().data?.restart_required ?? []`
directly; the `useState`/`setRestartFields` pair is dropped from the plan. — Why: Step 6 replaces it
anyway, and between the two steps the unused setter fails `tsc -b`, which Step 5's own build check
would trip on. — Cost if wrong: none; the end state is identical.

## Task log

Plan rulings committed as ea6c280 (pre-flight fixes to plan text).
Task 1: dispatched (haiku, agent a71ce483a3a6c8864), BASE ea6c280

Ruling 8 (RED BASELINE — applies to every task): this repository does not have a green
baseline, and the plan's "Expected: PASS" on whole-suite runs is therefore unachievable as
written. Measured:
  - `main` (f41d1ba):            55 failed, 502 passed, 3 errors
  - branch base (ea6c280):       54 failed, 622 passed, 3 errors
  - `ruff check .`:              8 errors in agents/defect_explainer/agent.py,
                                 tests/unit/agents/defect_explainer/test_utils.py,
                                 tests/unit/utils/test_agent.py
  - `ruff format --check .`:     4 files would reformat (defect_explainer/agent.py,
                                 tests/.../defect_explainer/test_utils.py,
                                 tests/unit/llm/test_azure_auth.py, tests/unit/utils/test_agent.py)
  - `mypy testbench_ai_service`: 5 errors in agents/defect_explainer/agent.py,
                                 agents/defect_explainer/utils.py, middlewares.py
None of those files is touched by any task in this plan, and the failures predate the branch
(main is worse than the branch base). — Ruling: every plan step demanding a globally clean gate
is read as "clean for the files this task touches, and no worse than the baseline above
globally". A task that raises any of those numbers has regressed and enters the fix loop. —
Why: holding tasks to a green whole-suite bar would block all 22 on unrelated pre-existing
breakage this plan has no mandate to fix, and silently loosening the bar instead would let a
real regression hide among 54 known failures, so the bar becomes the delta. — Cost if wrong: a
regression that happens to land in one of those already-failing files would not be caught by the
count; the per-task review of the diff is the backstop.

Task 1: verified DONE. Baseline delta +3 passed, +0 failed. Task 1's four files are clean under
ruff/ruff-format/mypy individually; the project-wide offenders are all files it never touched.

Task 1: review returned SPEC ✅, one Critical (plan-mandated), two Minor.
Ruling 9 (Task 1 Critical, plan-mandated): the `gt=0` / `ge=0` bounds on `LLMConfig.timeout` and
`max_retries` STAND. The reviewer is right that they tighten validation — a `config.toml` with
`timeout = 0` or a negative `max_retries` loaded before this change and now fails at startup — but
keeping them is correct on three grounds:
  1. Consistency: the analogous fields in the same model file already carry exactly these bounds —
     `tb_connect_timeout` gt=0, `tb_read_timeout` gt=0, `tb_max_retries` ge=0 (config.py:81,86,91).
     Declaring the LLM pair without them would make the model inconsistent with itself.
  2. The reviewer's premise that "some admins use 0 to mean no timeout" does not hold for these
     SDKs. Verified: `httpx.Timeout(0)` constructs but means an *instant* timeout; infinite is
     `None`, not 0. A config carrying `timeout = 0` was already failing every LLM call, silently.
     Failing loudly at startup with a field-addressed message is strictly better.
  3. Spec 6.3 requires that the console "cannot write a configuration that would prevent the
     service from starting", and the console validates by constructing this very model. An
     unbounded field means the console happily saves a value that breaks the service at runtime
     instead of refusing it at save time — which defeats the point of the phase.
  Required with this ruling (fix round 1): a regression test asserting the bounds, and a docs note
  so an upgrading operator sees the tightening. The brief's Files list named
  tests/unit/test_models_config.py but no step ever populated it — that is a brief gap, now closed.
— Cost if wrong: an operator with `timeout = 0` in config.toml gets a startup failure instead of a
silently broken service, and must delete the line. The docs note tells them exactly that.

Task 1: minor (deferred): `ruff format` at file scope also reformatted pre-existing unrelated lines
in llm/factory.py and tests/unit/llm/test_factory.py. Pure whitespace, and it moves those files
toward the project's own format standard (both are now clean under `ruff format --check`, which 4
other files in the repo still are not). Left as-is; final review to triage.
Task 1: fix round 1 dispatched (resume implementer a71ce483a3a6c8864), FIX_BASE 2b41010
Task 1: fix round 1/5 (2 addressed, 0 open; commits 2b41010..a6b9445)
Task 1: controller verification — 54 failed / 631 passed (base was 54/622; +9 = 3 factory + 6 new
  model-config tests). Task's 4 files clean under ruff check + ruff format --check. mypy unchanged
  at 5 pre-existing errors in untouched files. No baseline regression.
Task 1: complete (commits ea6c280..a6b9445, review clean)
Task 2: dispatched (haiku), BASE a6b9445

Task 2: plan defect (harmless, no action): Task 2's Step 5 says "PASS, all seven" but the task
  only ever specified 6 tests. My miscount when writing the plan. All 6 present with exact names;
  nothing was dropped. Later tasks' "all N" counts are therefore advisory, not contractual —
  verify against the named tests, not the number.
Task 2: controller verification — .spec branch correct: hiddenimports does explicitly enumerate
  pure-Python deps (tomli, tomli_w, yaml, jinja2, dotenv), so adding "tomlkit" beside tomli_w was
  the right side of the brief's conditional. Suite 54 failed / 637 passed (+6, no regression).
Task 2: dispatched review (sonnet), BASE a6b9445 HEAD d90a993

Task 2: review returned SPEC ✅, one plan-mandated data-loss finding.
Ruling 10 (Task 2, plan-mandated, data loss): the finding is CORRECT and must be FIXED, and it is
my plan's gap. `service_table` tests only `isinstance(existing, Table)`; I confirmed directly that
`testbench-ai-service = { port = 8010, debug = true }` (valid TOML) parses to an `InlineTable`,
which is NOT a `Table` subclass, so the brief's code treats the section as absent and then
`document[CONFIG_PREFIX] = table` overwrites it — every key the operator wrote is destroyed on the
first console save. That is precisely the regression class this module exists to prevent, so
"unusual shape, unlikely operator" is not a good enough reason to leave it. Fix: promote an
InlineTable to a real Table carrying its keys over (verified: keys survive and the rendered result
is a normal `[testbench-ai-service]` section), and refuse a non-table value at that key with a 400
rather than silently replacing it. The invariant becomes "service_table either returns a live table
holding the operator's keys, or refuses" — no shape loses data silently. Dotted-key form
(`testbench-ai-service.port = 8010`) already yields a real Table and is unaffected; adding a
regression test for it. — Cost if wrong: an operator who deliberately wrote the section as an inline
table sees it reformatted to a standard section on first save (data intact, formatting changed),
and a file with a scalar at that key gets a 400 instead of a silent overwrite.
Note for Task 4: its `_child_table` already accepts `(Table, InlineTable, dict)` at nested levels
but silently replaces a scalar with a fresh table — the analogous one-level-down case. Task 4's
dispatch must carry the same "refuse rather than destroy" guard for consistency.
Task 2: fix round 1 dispatched (resume implementer a21a1d2d2df5330f4), FIX_BASE d90a993
Task 2: controller verification of the fix, run directly against tomlkit (not via the tests):
  - inline table `{port=8010,debug=true}` -> all keys survive promotion, later nested write renders
  - scalar `= 5` -> HTTPException 400 (not a silent overwrite)
  - list `= [1,2]` -> HTTPException 400 (NOT an AttributeError/500, which was the risk)
  - empty inline `= {}` -> promoted to an empty Table
  - dotted `testbench-ai-service.port = 8010` -> keys intact
  Both `Table` and `InlineTable` ARE dict subclasses, so branch order is load-bearing: the
  `isinstance(existing, Table)` live-return must precede the dict-promotion branch or a real Table
  would be copied and the live-reference guarantee would break. Confirmed correct — mutate-then-
  render works end to end. Suite 54 failed / 641 passed (+4).

Task 2: re-review returned "all findings addressed, no new breakage" — but I found a further
Critical while verifying its own aside about `OutOfOrderTableProxy`, which it had waved through as
"promoted with keys copied".
Ruling 11 (Task 2, Critical, comment loss): `service_table` must return an
`tomlkit.container.OutOfOrderTableProxy` LIVE rather than promoting it. Measured, on a config whose
`[testbench-ai-service]` sections are interleaved with another top-level table (a
`[testbench-ai-service]` / `[tool.other]` / `[testbench-ai-service.llm_config]` layout, which is
valid and produces an OutOfOrderTableProxy, NOT a Table):
  - promotion branch: all DATA survives (port, llm_config, the other table) BUT the operator's
    `# operator note` comment is DESTROYED and the sections are reordered
  - returning the proxy live: comment survives, section order survives, and both scalar and
    nested-table writes work
Comment preservation is the entire reason this module exists instead of `tomli_w`, so losing one is
not an acceptable cost for handling an unusual layout. The proxy is dict-like but is NOT a `Table`
subclass, which is why it fell into the dict-promotion branch. — Cost if wrong: none identified;
returning it live is strictly better on every axis measured (data, comments, ordering, nested
writes). The risk is only that the proxy is a less-tested tomlkit surface than `Table`, so the fix
is covered by tests that assert comment survival and a nested write, not just key survival.
Task 2: fix round 2 dispatched (resume implementer a21a1d2d2df5330f4), FIX_BASE e930029
Task 2: controller verification of round 2 — all seven document shapes exercised end to end
  (write a scalar AND a nested table through service_table, then render and re-parse):
    normal [section]        -> Table                 comment kept, nested ok
    interleaved sections    -> OutOfOrderTableProxy  comment kept, nested ok, order kept
    inline table            -> Table (promoted)      comment kept, nested ok, keys kept
    dotted key              -> Table                 comment kept, nested ok
    absent                  -> Table (created)       comment kept, nested ok
    scalar                  -> HTTPException 400
    list                    -> HTTPException 400
  Suite 54 failed / 645 passed (+4). No regression.
Task 2: fix round 2/5 (1 addressed, 0 open; commits e930029..722cb7c)
Task 2: complete (commits a6b9445..722cb7c, review clean, 14 tests)
Carry into Task 4 (consumes document.py):
  - `service_table` now returns `Table | OutOfOrderTableProxy`. Task 4's `apply_edits` assigns that
    to `root`, so its mypy annotations must accept the union, not just `Table`.
  - Task 4's `_child_table` checks `isinstance(child, (Table, InlineTable, dict))`. A CHILD can also
    be an `OutOfOrderTableProxy` (e.g. `[testbench-ai-service.logging]` split across the file by
    another table). It is a dict subclass so it would be caught by the `dict` arm and mutated in
    place, which is correct by luck — but Task 4 must name it explicitly for the same
    comment-preservation reason established in Ruling 11.
  - Task 4's `_child_table` silently REPLACES a scalar child with a fresh table. Per Ruling 10's
    invariant ("refuse rather than destroy"), it must raise 400 instead.
Task 3: dispatched (haiku), BASE 722cb7c

Task 3: controller verification — redaction sentinel rejected (400) in six nesting shapes, three of
  which the brief's tests do NOT cover: a list of dicts, a dict-in-list-in-dict, and a tuple.
  `merge_edits` leaves `base` untouched and the deep copy isolates nested dicts AND nested lists
  (mutating the result never reaches base). Limits are MAX_EDITS=500, MAX_PATH_SEGMENTS=8 as
  specified. Suite 54 failed / 666 passed (+21). No regression.
Task 3: dispatched review (sonnet), BASE 722cb7c HEAD bd8ae63
Task 3: controller probe of two design questions (rulings deferred until the review reports, to
  avoid pre-judging):
  (a) SCALAR PARENT: base `{'llm_config': 'oops-a-string'}` + edit `llm_config.model` silently
      replaces the operator's string with `{'model': ...}`. Same defect class as Ruling 10. Note the
      cross-path consequence: Task 4's `apply_edits` is required (Ruling 10 carry-forward) to RAISE
      400 in the analogous case, and Task 4's own
      `test_apply_edits_result_reparses_to_the_merged_dict` pins the dict path and the document path
      to agree. If merge_edits converts while apply_edits refuses, the two disagree — safe (the 400
      means nothing is written) but confusing and late. Reachability is narrow: a scalar where a
      table belongs is an already-invalid config.
  (b) ORDER DEPENDENCE: an overlay containing BOTH `a` (scalar) and `a.b` yields a different result
      depending on insertion order — `{'a':'scalar','a.b':1}` -> `{'a':{'b':1}}` but the reverse
      order -> `{'a':'scalar'}`. Deterministic per request (Python preserves JSON object order) and
      unreachable from the real UI, whose FieldSpec keys are all leaf paths, so no overlay ever
      contains both a path and its own prefix.

Task 3: review returned SPEC ✅, two Important (both plan-mandated) and four Minor. It independently
  reproduced both of my probes and added two smuggling results I had not tried.
Ruling 12 (Task 3, Important, plan-mandated — scalar parent): FIX. `_set_at` must raise 400 when a
  path's parent exists as a non-dict instead of silently replacing it. Three reasons: Ruling 10
  already established "refuse rather than destroy" for the document path; Task 4's
  `test_apply_edits_result_reparses_to_the_merged_dict` pins the dict path and document path to the
  SAME result, and Task 4 is required to raise 400 here, so leaving merge_edits converting would
  make the two paths disagree; and the alternative is a silent in-memory conversion that then passes
  validation and reaches the write, destroying the operator's value. Verified the fix cannot break
  the legitimate cases: an ABSENT parent still builds intermediate tables, and a dict parent is
  untouched — only an existing non-dict raises. — Cost if wrong: a config with a scalar where a
  table belongs (already invalid) gets a clear 400 naming the key rather than a silent rewrite.
Ruling 13 (Task 3, Important, plan-mandated — prefix collision): FIX. `validate_edit_paths` must
  reject an overlay containing both a path and a proper prefix of it. Verified the check is a cheap
  set-membership scan over the path list, and that a leaf-only overlay (what the real UI sends)
  produces no collisions, so no legitimate request is refused. Reason to fix rather than defer: the
  contract is currently order-dependent and silently so, and phase 3 edits deeply nested paths
  (`projects.X.agents.Y.enabled`) where a prefix collision becomes genuinely plausible rather than
  theoretical. — Cost if wrong: a caller that deliberately sent both a table and a key inside it in
  one request gets a 400 and must send them as one value.
Ruling 14 (Task 3, Minor bundled into the same fix): `_contains_sentinel` gains `set`/`frozenset`.
  Bundled rather than deferred because it is one word inside the function that IS the security
  chokepoint, and "unreachable via JSON" is a property of today's only caller, not of the function.
Ruling 15 (Task 3, Minor bundled): a path segment differing from its stripped form is rejected. The
  code already rejects a segment that is empty after stripping, so accepting `" port "` as a
  distinct literal key is an inconsistency in the same check; a leading space in a TOML key is
  always a typo.
Task 3: minor (deferred): no per-segment length cap — a 100k-character segment is accepted (bounded
  only by MAX_EDITS and MAX_PATH_SEGMENTS). Admin-only, authenticated route; worst case is a large
  junk key written to config.toml. Final review to triage.
Task 3: minor (deferred): a dict KEY equal to the sentinel is accepted — harmless, overwrites no
  secret. Sentinel as a SUBSTRING is accepted and that is CORRECT: redaction replaces a whole value,
  so exact match is the right rule and substring matching would false-positive on real values.
Task 3: minor (deferred, moot): `merge_edits` does not self-validate. No caller exists yet; Task 11's
  `_plan_change` calls `validate_edit_paths` first by construction. Task 11 review must confirm it.
Task 3: fix round 1 dispatched (resume implementer a3d841fd8b466ea1b), FIX_BASE bd8ae63
Task 3: controller verification of fix round 1 — 21 direct checks, all pass:
  FIX 1: scalar parent -> 400; list parent -> 400; absent parent still builds intermediate tables;
         existing dict parent still reused (both regression cases confirmed unbroken)
  FIX 2: a+a.b -> 400 in BOTH insertion orders; logging.file+logging.file.log_level -> 400;
         leaf-only overlay accepted; sibling paths accepted; `ab` vs `a.b` (near-prefix that is not
         a prefix) accepted — no over-rejection
  FIX 3: sentinel in set and frozenset -> 400; tuple and nested dict still -> 400
  FIX 4: " port " and "a. b" -> 400; normal dotted path accepted
  UNCHANGED: base not mutated, deep-copy isolates nested lists, None removes, removing an absent key
         is a no-op, limits still 500/8
  Implementer refactored validation into `_check_path_prefix_collisions` and `_validate_single_path`
  (unrequested but behaviour-preserving per the above). Suite 54 failed / 678 passed (+12).
Task 3: dispatched scoped re-review (haiku), FIX_BASE bd8ae63 HEAD b694f43
Task 3: fix round 1/5 (4 addressed, 0 open; commits bd8ae63..b694f43)
Task 3: refactor cleared — re-review enumerated all 8 validation rules (max-edits, prefix collision,
  path type/emptiness, NUL byte, depth, empty segment, whitespace, sentinel) and confirmed every one
  is still reachable for every path with no rule masking another and no short-circuit skipping a
  later path. Prefix scan is O(paths x depth^2) ~ 32k ops at the 500-edit/8-depth ceiling —
  acceptable. 21 pre-existing tests untouched (additions only).
Task 3: complete (commits 722cb7c..b694f43, review clean, 33 tests)
Task 4: dispatched (sonnet — no longer pure transcription, must adapt the brief's code to Tasks 2-3
  outcomes), BASE b694f43

Ruling 16 (PLAN DEFECT, applies to Tasks 5 and 11 — Tasks 2 and 4 already hit and fixed it): this
  project's ruff config selects the whole `PL` group (pyproject `[tool.ruff.lint] select` includes
  "PL", "C90"), so PLC0415 forbids function-local imports. I wrote function-local imports into
  several briefs' TEST code, which therefore cannot pass `ruff check` as written. Confirmed by
  scanning every brief: task-2 (1, already fixed by hoisting), task-4 (2 real, already fixed),
  task-5 (`import tempfile as tempfile_module` inside a test body), task-11 (`from
  fastapi.testclient import TestClient` and `from unittest.mock import patch` inside fixtures).
  — Ruling: hoist them to module level. The imports are all stdlib or already-imported-elsewhere, so
  there is no circular-import reason any of them was local; I wrote them inline for readability of
  the plan, not for correctness. Carried into the Task 5 and Task 11 dispatches. Also warn those
  tasks that C90/PLR0912 complexity limits are enforced, which is what forced Task 3's refactor.
  — Cost if wrong: a hoisted import that DOES have a cycle would fail at import time, loudly and
  immediately, in that task's own test run.

Task 4: implementer concern re removal-path symmetry — verified and RESOLVED, no action needed.
  Measured: a SET against a scalar parent is refused 400 by BOTH `apply_edits` and `merge_edits`
  (correct — it would destroy data). A REMOVE against a scalar parent silently no-ops in BOTH, and
  the operator's scalar survives intact. So the two paths agree on both operations, and the
  asymmetry between set and remove is correct rather than an oversight: removal cannot destroy
  anything (the key is not there), and Ruling 12 already established "removing an absent key is a
  silent no-op, not an error" so that two operators discarding the same setting do not produce a 400
  for the second. A child of a scalar is a species of absent key. Noted as an observation, not a
  defect; the missing test for it is a coverage gap to bundle with any review findings.
Task 4: controller verification — comment `# operator note` and `[tool.other]` both survive
  apply_edits writing a scalar, a new key AND a nested table; document path and dict path produce
  identical results on success. Suite 54 failed / 688 passed (+10).
Task 4: dispatched review (sonnet), BASE b694f43 HEAD b31718c
Task 4: review returned SPEC ✅ on all 9 brief requirements AND all 4 deviations; quality Approved
  with two Minors (deferred, not looped). Reviewer probes all came back correct: first-segment
  conflict -> 400; 8-deep path builds 7 nested tables; a dict VALUE becomes a real Table (renders as
  a proper [section], and a later dotted edit reaches into it); a list of dicts renders as an
  array-of-tables and round-trips; an INLINE-table child is edited in place with its inline
  formatting fully preserved; ordering agrees between the two paths (only cosmetic key order
  differs, which is expected); the `node: Any` inside the walk is the minimum necessary, not a
  defeat of the union typing (mypy clean on the file).
Task 4: minor (deferred): `apply_edits` is not atomic — a multi-edit overlay whose LATER edit
  conflicts leaves the earlier edits already mutated into the document before the 400. I verified
  this is UNREACHABLE in the real flow: the plan's `_plan_change` calls `merge_edits` (plan line 21)
  before `apply_edits` (plan line 40), and `merge_edits` raises on the same conflict, so a
  conflicting overlay 400s before `apply_edits` is ever entered. Carry-forward: Task 12's dispatch
  should add the one-line docstring caveat the reviewer suggested, warning against reusing a
  document object after a raised exception.
Task 4: minor (deferred): no REMOVE-path equivalent of the scalar-parent test on the document side.
  Behaviour verified correct by hand (no-op, agrees with merge_edits); Deviation 4 only required the
  SET-path test. Final review to triage.
Task 4: complete (commits b694f43..b31718c, review clean, 24 tests in test_document.py)
Task 5: dispatched (haiku), BASE b31718c

Task 5: controller verification found an UNAUTHORIZED DEVIATION with a correctness consequence.
  Brief's order:       temp-write -> write .bak to disk -> os.replace
  Implemented order:   temp-write -> read old bytes to MEMORY -> os.replace -> write .bak
  The implementer's stated reason is tidiness ("a failed replace doesn't leave a backup behind").
  Failure-mode comparison:
    Implemented: replace SUCCEEDS then the .bak write fails -> the new content IS on disk, there is
      NO backup, and the function raises 400 "Cannot write ..." — which is a LIE. Task 12 decides
      whether to hot-reload from that success/failure signal, so disk and process would disagree
      while the operator is told nothing was written.
    Brief's:     the .bak write fails -> nothing was replaced, original intact, accurate 400. A
      replace failing AFTER the .bak was written leaves a redundant .bak identical to the unchanged
      original — harmless, no data loss, and the 400 is still accurate.
  The brief's order makes "400 means nothing changed" an invariant Task 12 can rely on; the
  implemented order breaks it. Verified on Windows that a destination held open by another handle
  does produce a clean 400 (WinError 5 -> OSError -> 400, not an unhandled 500) and leaves no temp
  file, so the error path itself is sound — only the ordering is wrong.
Task 5: other properties verified directly — new file returns bak None; LF-only bytes confirmed on
  Windows; .bak holds the previous contents; .bak is replaced not stacked (no .bak.bak); UTF-8
  round-trips; no temp leftovers; missing parent -> 400. Suite 54 failed / 697 passed (+9).
Task 5: dispatched review (sonnet) with the ordering finding included as a claim to VERIFY
  independently, not to accept, BASE b31718c HEAD f359203

Ruling 17 (Task 5, Critical — write ordering; MY PLAN DEFECT, and worse than I first thought):
  revert to the brief's ordering (temp-write -> .bak to disk -> os.replace) AND fix the brief's own
  test that made the implementer deviate.
  The review independently REPRODUCED the false-negative live: patching Path.write_bytes to fail
  only for the .bak, after os.replace had already succeeded, yields HTTPException("Cannot write
  ...") while target.read_text() shows the NEW content. Under Task 12's contract (returns => hot
  reload) that is a live bug: the operator is told nothing changed, the process keeps the old
  config, and the file on disk holds the new one.
  It also considered a third ordering I had not — os.replace(target, backup) then
  os.replace(temp, target), two atomic renames and no byte copy — and rejected it because it opens a
  window in which the config file does not exist at all. That is worse than either scheme. The
  brief's order wins because the single state-mutating call is LAST, so "raised => target unchanged"
  holds unconditionally.
  WHY THE IMPLEMENTER DEVIATED — this is on me, not them. My brief's test
  `test_a_failed_replace_leaves_the_original_intact_and_no_temp_file` asserts
  `[entry.name for entry in tmp_path.iterdir()] == ["config.toml"]` after a failed replace. Under
  the brief's OWN ordering a `config.toml.bak` necessarily exists at that point, so the brief's
  specified code and its specified test could not both be satisfied. The implementer resolved my
  contradiction by trusting the test and reordering the code. Wrong call on safety grounds, but a
  reasonable reading of a self-contradictory brief — not negligence. The fix must therefore correct
  the TEST as well, or the same deviation is invited again.
  — Cost if wrong: a failed replace now leaves behind a `.bak` identical to the unchanged original.
  Harmless and accurate; the alternative is a false "nothing was written" report while the file has
  changed.
Ruling 18 (Task 5, Minor bundled): document in the docstring that replacing a symlinked target
  replaces the symlink itself rather than following it (reviewer verified `is_symlink()` becomes
  False). Inherent to the temp+rename pattern, not worth changing behaviour for a config file, but
  it should not be a surprise discovered in production.
Task 5: fix round 1 dispatched (resume implementer ae492ed4829fd6d36), FIX_BASE f359203
Task 5: controller verification of fix round 1 — the false-negative is GONE. Measured by patching
  Path.write_bytes to fail only for the .bak: raises 400 AND target still holds its original bytes,
  with no .tmp left behind. A failed os.replace: 400, original intact, and the redundant
  config.toml.bak present as expected under this ordering. Happy paths unchanged (new file -> bak
  None, LF-only bytes, overwrite -> bak holds previous contents). The "raised => target unchanged"
  invariant that Task 12's hot-reload decision depends on now holds unconditionally.
  Suite 54 failed / 698 passed (+10 total for the task).
Task 5: dispatched scoped re-review (haiku), FIX_BASE f359203 HEAD 7aa10b7
Task 5: fix round 1/5 (4 addressed, 0 open; commits f359203..7aa10b7)
Task 5: re-review confirmed os.replace is genuinely the last operation that can mutate the target
  (nothing after it can raise), and that the regression guard is REAL rather than passing for the
  wrong reason: the temp file is written via os.fdopen/file.write, NOT Path.write_bytes, so the
  test's selective patch can only fire on the .bak. 8 untouched tests still valid.
Task 5: complete (commits b31718c..7aa10b7, review clean, 10 tests)

Ruling 19 (Task 6 pre-dispatch, plan defect avoided): the brief's Step 6 suggests adding
  `# noqa: BLE001` to the broad `except Exception` if ruff complains. Verified ruff's select list:
  BLE is NOT selected, so that noqa would be unnecessary — and RUF *is* selected, so RUF100
  (unused noqa) would flag the suppression itself. Instruction to the implementer: do NOT add the
  noqa; the bare `except Exception` is already clean here.
Task 6 pre-dispatch verification (per my commitment to read each brief's tests against its own
  implementation first): confirmed AppConfig() constructs on defaults, and that all five pydantic
  error locations the brief's tests assert are exactly what pydantic actually produces —
  ('port',), ('logging','file','log_level'), ('llm_config',), ('tb_max_retries',), ('ssl_cert',)
  with a message containing "not found". No contradiction found in this brief.
Task 6: dispatched (haiku), BASE 7aa10b7

Task 6: controller verification — the validation gate works. Seven candidate configs checked
  directly: a good edit yields a model and no issues; a bad port, bad enum, missing TLS file, bad
  nested log level, and the entra-id-without-azure invariant all yield None plus a correctly
  field-addressed issue with the right [toml.section]. The "model XOR issues, never both" invariant
  holds. `ConfigIssue` carries only path/message/toml_section — it does NOT copy pydantic's `input`
  key, so raw submitted values do not leak wholesale into the API response.
Task 6: minor (deferred, matters for PHASE 3 not phase 2): a bad agent `class_path` produces a
  ROOT-addressed issue (path='') rather than `agents.<key>.class_path`, because
  `AppConfig.validate_config` raises a bare ValueError with no field location, unlike
  `validate_prompt_paths` which uses `raise_field_validation_error` and does address its errors
  properly (('agents', key, 'prompt', 'file')). Harmless in phase 2 — agents are not editable yet,
  so there is no form field to mark and the message still says what is wrong. Phase 3 makes agents
  editable, and it should either fix `validate_config` to use `raise_field_validation_error` or
  accept that class_path errors surface as banner-level rather than field-level. Recorded so phase 3
  does not rediscover it.
Task 6: dispatched review (sonnet), BASE 7aa10b7 HEAD 1aa26ab

Task 6: review returned SPEC ✅ with three findings — one Important escape, two plan-mandated
  defects in my own `_toml_section`.
Ruling 20 (Task 6, Important — BaseException escape): FIX, but catch `(Exception, SystemExit)`
  rather than the reviewer's suggested bare `BaseException`. The escape is real and was reproduced:
  a `class_path` naming a module that calls `sys.exit()` at import time propagates straight out of
  `validate_config_dict`, defeating its entire "never raise, always return issues" contract. And
  `SystemExit`-on-import is not hypothetical in THIS codebase — `utils/config.py` calls `sys.exit(1)`
  in library code (`load_config_from_file`, `create_default_config_file`, `copy_default_prompts`), so
  the pattern is house style here. But bare `BaseException` would also swallow `KeyboardInterrupt`,
  `GeneratorExit` and `asyncio.CancelledError`, turning a Ctrl-C or a cancelled request into a
  400 — a worse bug than the one being fixed. `(Exception, SystemExit)` catches the realistic case
  and lets cancellation propagate. — Cost if wrong: a module that raises some other BaseException
  subclass on import still escapes and surfaces as a 500 instead of a field-addressed issue.
Ruling 21 (Task 6, Important, plan-mandated — `_toml_section` fabricates sections): FIX. My code does
  `location[:-1]` then filters ints, so an error inside an ARRAY (`trusted_proxies[2]`, loc
  `('trusted_proxies', 2)`) yields `[testbench-ai-service.trusted_proxies]` — a table that does not
  exist, since `trusted_proxies` is a plain array key. An operator following that hint would hand-
  create a bogus section. This is reachable in PHASE 2: `trusted_proxies` is an editable list field
  on the Service form's proxy tab. Correct algorithm, which I verified on eight locations: strip
  TRAILING integer indices first, then drop the final remaining element (the key itself), then join.
Ruling 22 (Task 6, Minor bundled, plan-mandated — unquoted TOML keys): FIX with Ruling 21, same root
  cause. A segment that is not a bare key must be quoted: `('projects','My Project','language')` must
  render `[testbench-ai-service.projects."My Project"]`, not the invalid bare form. Verified my
  replacement produces valid TOML for all eight cases including a name containing a double quote
  (escaped correctly). Bundled because it is the same two lines and phase 3 keys projects by
  arbitrary TestBench project names.
Task 6: disclosure analysis CLEARED with a useful negative result: no credential VALUE is reachable
  in an issue message, because API keys are never config fields — `llm/factory.py` reads them from
  `os.getenv`. The only echoed values are cert/key FILE PATHS, which are the operator's own typed
  input. The reviewer's residual worry (a merged candidate re-validating an untouched SSL path that
  has since gone missing, disclosing a path the operator did not type) is dismissed: the caller is an
  authenticated admin who can already read the whole file via GET /config, so it discloses nothing
  they lack access to.
Task 6: fix round 1 dispatched (resume implementer a68c9f13a99252691), FIX_BASE 1aa26ab
Task 6: controller verification of fix round 1 — all three fixes hold. `_toml_section` correct on
  all six locations and every output parses as valid TOML, including
  `[testbench-ai-service.projects."My Project"]`. `SystemExit` now yields a root-addressed issue.
  And the constraint I insisted on is respected: `KeyboardInterrupt`, `asyncio.CancelledError` and
  `GeneratorExit` ALL still propagate rather than being converted into a 400. Suite 54/713.

Carry-forward to TASK 16 (found while probing, not reported by anyone): a validation failure inside
  an ARRAY is addressed to an INDEXED path — `{'trusted_proxies': [1, 2]}` yields issues at
  `trusted_proxies.0` and `trusted_proxies.1`, not at `trusted_proxies`. But the frontend's
  `FieldSpec.key` for that control is plain `trusted_proxies`, and the plan's Task 16 code matches
  issues with `issues.find((entry) => entry.path === spec.key)` — an exact-equality match that will
  NEVER match an indexed path, so per-element errors on a list field would be silently invisible to
  the operator. Task 16's dispatch must widen the match to "path === spec.key OR path starts with
  spec.key + '.'", and its tests must cover an indexed issue. This is reachable in phase 2:
  trusted_proxies is the one editable list field on the Service form.
Task 6: dispatched scoped re-review (haiku), FIX_BASE 1aa26ab HEAD 47e33a2

Task 6: re-review confirmed findings 1-3 ADDRESSED and found a NEW Important in the fix diff, which
  I verified is real AND reachable.
Ruling 23 (Task 6, Important — `_quote_key` emits invalid TOML for control characters): FIX by
  DELEGATING to `tomlkit.key(segment).as_string()` instead of hand-rolling escapes.
  Reachability confirmed: `validate_edit_paths` rejects NUL bytes and leading/trailing whitespace,
  but an INTERIOR newline or tab passes — `projects.a\nb.language` is accepted as an edit path. So a
  segment containing a literal newline can reach `_quote_key`.
  Measured, per segment, whether the produced section parses as TOML:
    hand-rolled: 'a\n b' -> INVALID (raw control char in a basic string); tab, backslash, quote,
                 non-ASCII, empty and '...' all fine
    tomlkit.key: EVERY case correct, including 'a\nb' -> "a\nb"
  Delegating is better than adding my own control-character escape table: tomlkit already owns TOML
  serialization, it is already a declared dependency, and it was correct on all nine segments I
  tried. `validate.py` already emits TOML section strings, so being TOML-aware is not new coupling —
  hand-rolling the escaping was the anomaly. — Cost if wrong: `tomlkit.key()` raising on some exotic
  segment would turn a hint into a 500; the fix must therefore keep the bare-key fast path and guard
  the call.
Task 6: minor (deferred, do NOT reopen Task 3): `validate_edit_paths` could additionally reject
  interior control characters in edit paths as defence in depth. Not needed for correctness once
  Ruling 23 lands, since the hint becomes valid TOML for any input, and no real TestBench project
  name contains a newline. Final review to triage.
Task 6: fix round 2 dispatched (resume implementer a68c9f13a99252691), FIX_BASE 47e33a2
Task 6: fix round 2/5 (1 addressed, 0 open; commits 47e33a2..a4aef8d)
Task 6: controller verification of round 2 — `_quote_key` now produces VALID TOML for all 14 exotic
  segments I tried (literal newline/tab/CR, NUL, \x01, \x7f, a lone surrogate, a 100k-char segment,
  empty, "..", a bare quote, a bare backslash, an RTL override, an emoji). Bare-key fast path
  preserved: logging/llm_config/port/tb_max_retries/a-b_c1 all come back unquoted. Sections still
  correct. Suite 54 failed / 717 passed.
Task 6: minor (deferred, DELIBERATE non-fix): the implementer's requirement-3 fallback returns the
  segment UNCHANGED if `tomlkit.key()` raises — which is the one choice that reproduces the very bug
  round 2 fixed, and is not one of the two options I specified (a guaranteed-parseable repr form, or
  the plain CONFIG_PREFIX section). I am NOT spending a fix round on it, because I measured
  `tomlkit.key()` against 14 exotic inputs and it raised for NONE of them, so the fallback is
  unreachable dead code. Recorded rather than fixed: if a future tomlkit version starts raising, this
  fallback silently reintroduces invalid-TOML hints. Final review should triage it as a one-line
  change (return `f"[{CONFIG_PREFIX}]"`-style degradation instead of the raw segment).
Task 6: complete (commits 7aa10b7..a4aef8d, review clean, 19 tests)

Task 7 pre-dispatch verification: read the brief's ten tests against its own implementation. The
  context-window test is sound (a change at key_10 with CONTEXT_LINES=3 shows key_7..key_13, and
  "key_0 = 0" is not a substring of any shown line). The header-counting slice `lines[2:]` correctly
  excludes the two `---`/`+++` lines while still counting a genuine removed line that happens to
  start with "---". The empty-current case yields (1,0) as asserted. No contradiction found.
Task 7: dispatched (haiku), BASE a4aef8d

Task 7: controller verification — clean first pass, all properties hold. identical -> None; changed
  (1,1); added (1,0); removed (0,1); new file (1,0); trailing-newline difference is a real diff.
  THE TRAP HELD: a removed line whose text begins with "---" is counted (0,1) rather than mistaken
  for a file header, and an added line beginning with "+++" counts (1,0) — the positional lines[2:]
  slice is doing its job and a startswith() prefix test would have broken both. Context window
  behaves: a change at key_20 in a 40-line file shows 8 lines, includes key_17..key_23, excludes
  key_0. Concurrency property confirmed: the diff is computed against whatever `current` is passed,
  so another operator's already-saved value shows as removed rather than being silently reverted.
  UTF-8 preserved; a CRLF-vs-LF difference registers as a real (1,1) change, which matters because
  Task 5 writes LF-only. Suite 54 failed / 727 passed (+10).
Task 7: dispatched review (haiku — small self-contained stdlib wrapper, low risk), BASE a4aef8d
  HEAD d80e345

Task 7: review returned SPEC ✅, quality Approved, with one "Important" I am DOWNGRADING to Minor on
  measurement, plus one Minor.
Ruling 24 (Task 7 — no diff size cap): DECLINE the reviewer's recommendation to cap the diff string.
  Its finding is real but its stated cause ("SequenceMatcher reports zero matching blocks") is
  imprecise: the mechanism is difflib's `autojunk` heuristic, which activates only at sequence length
  >= 200 and treats any element appearing in >1% of the sequence as ignorable junk. I measured it:
    REALISTIC configs are entirely unaffected — 30, 120, 240, 600 and even 2400 lines (52.7 KiB) all
      produce added=1 removed=1 and a 0.2 KiB diff for a one-key change.
    The threshold is exactly 200 lines: 199 identical lines -> added=1; 200 -> added=200.
    Worst synthetic case, 20000 identical lines: a 390 KiB diff. Large but not dangerous as JSON.
    Confirmed autojunk is the cause: autojunk=True gives one matching block of size 0, autojunk=False
      gives two with largest=999. `difflib.unified_diff` does not expose autojunk, so it cannot be
      switched off through the API the brief uses.
  Blow-up requires near-total line repetition, which a real config.toml — distinct keys, a handful of
  blank lines — cannot exhibit; my 2400-line realistic fixture was 16% blank lines and still fine.
  Capping would mean a constant, truncation logic, a `truncated` flag on FileDiff, and UI handling for
  it in Tasks 11/12/17 — real scope creep for a risk I measured as unreachable. — Cost if wrong: an
  operator with a pathologically repetitive 200+ line config gets a diff of a few hundred KiB in one
  API response. The threshold and mechanism are recorded here so the cause is immediately known.
Task 7: minor (deferred): passing None/non-str raises AttributeError rather than TypeError. The
  signature is `str` and mypy enforces it at every internal call site; not worth a runtime guard.
Task 7: complete (commits a4aef8d..d80e345, review clean, 10 tests)

Task 8: controller verification — all 16 classification cases correct. Needs restart: host, port,
  trusted_proxies, agent endpoint_path, agent class_path, agent removed (`agents.r`), agent added
  (`agents.z`). Correctly does NOT: unchanged, language, llm model, llm timeout, logging level, agent
  `enabled` flag, agent prompt variant, a new project override, admin_ui.require_loopback. Sorting
  correct including the mixed case `['agents.r.endpoint_path', 'port']`. Suite 54 failed / 740 passed.
  (13 test cases, not the "fourteen" my brief claimed — 10 plain + 1 parametrized x3. Another of my
  miscounts; the named tests are all present.)

Ruling 25 (Task 8, Important — `admin_ui.enabled` is missing from RESTART_FIELDS): FIX. Confirmed by
  reading main.py: `init_webui()` returns early when `admin_ui.enabled` is false and otherwise calls
  `include_router` + `mount_spa`, and it is invoked exactly once from `create_app`. So flipping
  `enabled` at runtime cannot take effect — it is as boot-fixed as `port`. Measured: the current
  implementation returns [] for True->False. The function's whole job is to enumerate boot-fixed
  fields, so an omission makes it wrong rather than merely incomplete. Reachable in THIS phase via
  Task 20's status endpoint, which compares running config against disk and reports restart_required
  — a hand-edited `enabled = false` would go unflagged. Note `admin_ui.require_loopback` is correctly
  NOT boot-fixed: it is read per request through `Depends(get_app_config)`, and I verified it reports
  no restart. Fix requires generalising RESTART_FIELDS to dotted paths, since the current code uses a
  flat `getattr`. — Cost if wrong: one extra field reported as needing a restart when it arguably
  did not; the operator restarts once unnecessarily.
Ruling 26 (Task 8, process — UNDISCLOSED test patch that disables a validator): the implementer added
  `patch("testbench_ai_service.config.validate_agent_variable", return_value=True)` to the autouse
  fixture. It is NOT in my brief and was NOT reported (CONCERNS: none). It is the right call — I
  proved the brief's `test_a_changed_agent_class_path_needs_a_restart` is UNSATISFIABLE without it,
  because pairing the DefectExplainer class with the reviewer's prompt file trips AppConfig's
  template-variable compatibility check, and my own probe failed the same way. So this is another
  unsatisfiable test I wrote. The patch is benign for what is under test (`restart_required` compares
  field values and never touches template variables). But a fixture that silently disables a real
  validator must be documented, or a future reader will trust a test that is weaker than it looks.
  Requiring a comment, not a behavioural change. — Cost if wrong: none; it is a comment.
Task 8: fix round 1 dispatched (resume implementer a324792cca186d459), FIX_BASE 5e62ff6
Task 8: controller verification of fix round 1 — RESTART_FIELDS is now
  ('host','port','ssl_cert','ssl_key','ssl_ca_cert','trusted_proxies','admin_ui.enabled') and all
  seven checks pass: admin_ui.enabled True->False -> ['admin_ui.enabled']; require_loopback -> []
  (fix correctly did NOT broaden to the whole admin_ui table); port+admin_ui.enabled -> sorted
  ['admin_ui.enabled','port']; unchanged/language/logging still []. The undisclosed
  validate_agent_variable patch is now documented with a comment explaining that restart_required
  never touches template variables. Suite 54 failed / 743 passed.
Task 8: dispatched scoped re-review (haiku), FIX_BASE 5e62ff6 HEAD 4ad205d
Task 8: fix round 1/5 (2 addressed, 0 open; commits 5e62ff6..4ad205d)
Task 8: re-review confirmed the dotted-path helper RAISES AttributeError on a missing segment rather
  than silently returning None — the right choice, since a silent None would make a restart-required
  field permanently unwatched and the bug invisible.
Task 8: correction to the re-review's reasoning (verdict unchanged, justification wrong): it approved
  `trusted_proxies` reordering as restart-worthy on the grounds that "proxy order can affect
  middleware routing or security priority". That is not true here — `cli.py:164` passes the list
  straight to uvicorn's `forwarded_allow_ips`, which is a MEMBERSHIP SET, so order has no functional
  effect. Reporting a restart for a pure reorder is therefore a harmless false positive, not a
  correctness requirement. Leaving it: `!=` on the list is simple and any edit to a boot-fixed field
  is defensible to flag, whereas set-comparison logic risks masking a genuine add/remove if written
  carelessly. Recorded so the ledger does not carry a false rationale.
Task 8: complete (commits d80e345..4ad205d, review clean, 16 tests)

Ruling 27 (Task 9 pre-dispatch, PLAN DEFECT caught before dispatch): my brief's Step 7 tells the
  implementer to pass `request.app.state.task_registry` at the `add_task` site. That is impossible as
  written. Verified by reading agents/routes.py: the dispatch lives in the shared helper
  `trigger_agent_execution(agent_key, trigger_request, background_tasks, conn, llm_factory,
  app_config, auth_info)` — which has NO `request` parameter — and its single caller, the per-agent
  route `trigger_agent`, also has no `Request`; it injects everything via `Depends` (conn,
  llm_factory, app_config, auth_info).
  — Ruling: thread the registry through as a parameter instead, resolved by the route with
  `registry: TaskRegistry = Depends(get_task_registry)`. `get_task_registry(request: Request)` already
  takes Request, so FastAPI resolves it — this is exactly the pattern `get_llm_factory` and
  `get_app_config` already use in that same signature, so it adds no new machinery. There is exactly
  ONE route function (generated per agent inside `create_agent_router`) and ONE `add_task` call site,
  so the change lands in two signatures and one call.
  Also confirmed for this task: `asyncio_mode = "auto"` IS set (pyproject.toml:173), so the brief's
  five async tests will actually run rather than being silently skipped; and the `add_task` call
  passes all six arguments by keyword (agent_key, agent, context, conn, llm_factory, item_ids),
  matching `run_agent`'s signature and the wrapper's `**kwargs` shape.
  — Cost if wrong: none identified; the Depends route is strictly more idiomatic than reaching into
  app.state, and keeps `tasks.py` free of console concerns as the brief intends.
Task 9: dispatched (sonnet — 7 files, integration wiring), BASE 4ad205d

Task 9: MY CORRECTION (Ruling 27) WAS ITSELF INCOMPLETE, and the implementer caught it. I asserted
  "exactly ONE route function and ONE add_task call site". The add_task site is indeed one, but
  `trigger_agent_execution` has TWO callers: the per-agent route in agents/routes.py:287 AND a
  generic `POST /agents/{agent_key}/trigger` route in testbench_ai_service/routes.py:203, which I
  never looked at because I grepped only agents/routes.py. mypy caught it as a missing argument and
  the implementer wired it through the same `Depends(get_task_registry)` pattern, then disclosed it
  as a concern asking for specific review — exactly the behaviour I asked for last task. Verified both
  call sites now pass `registry=registry` (routes.py:201/211, agents/routes.py:285/295).
  Lesson recorded: my pre-dispatch greps must cover the whole package, not the one file I expect the
  change to live in.
Task 9: controller verification — registry semantics correct under every condition I tried:
  concurrent tracking with DUPLICATE labels (4 tracked, two of them 'a0'); a raising body decrements;
  the real `_tracked_run_agent` wrapper passes all six kwargs through unchanged (agent_key, agent,
  context, conn, llm_factory, item_ids) and tracks exactly 1 during the run, 0 after; a raising agent
  leaves no phantom count. app.state.task_registry is created in create_app (main.py:112),
  unconditionally, not inside init_webui.
  ALSO VERIFIED, AND NOT COVERED BY THE BRIEF'S TESTS: asyncio CANCELLATION also decrements to 0.
  That is the realistic failure mode — background tasks get cancelled at server shutdown — so it is
  worth a test even though the behaviour is already right (the `finally` covers it).
Task 9: touched-area baselines held: tests/unit/agents/test_routes.py 4 failed/12 passed before AND
  after; tests/unit/test_tasks.py 3 errors before AND after. Suite 54 failed / 750 passed (+7 = the
  task's 5 inflight + 2 status tests).
Task 9: dispatched review (sonnet), BASE 4ad205d HEAD 7b17526
Task 9: review Approved, no findings above Minor. Clean answers to all three of my questions:
  SECOND CALL SITE — the generic route in routes.py:193-212 is wired byte-for-byte identically to the
    per-agent route; both converge on the one shared `trigger_agent_execution`, which holds the only
    `add_task(_tracked_run_agent, registry, ...)`. No early return or exception path skips it.
  OBSERVABILITY — `in_flight_tasks` CAN be non-zero in a real response. Starlette runs background
    tasks after the response is sent, but the tracked work is a real LLM call plus TestBench I/O
    (seconds to tens of seconds), and the server is asyncio, so a concurrent GET /status on another
    connection sees the live count. The feature is not a no-op.
  CONCURRENCY — the plain-list append/remove is NOT reachable from two threads: `_tracked_run_agent`
    is `async def`, and Starlette's BackgroundTask awaits coroutine callables directly on the event
    loop rather than routing them through run_in_threadpool. No `await` sits between the append and
    the remove, so they are effectively atomic under cooperative scheduling.
Task 9: minor (deferred): no test for the asyncio-cancellation path, though I verified the behaviour
  is correct (the `finally` decrements). Realistic at server shutdown. Test-only addition; final
  review to triage.
Task 9: complete (commits 4ad205d..7b17526, review clean, 7 tests)

Ruling 28 (Task 10 pre-dispatch, PLAN DEFECT — tests would pollute the repo and the test session):
  four of the brief's five `hot_reload` tests let the REAL `setup_logging` run. Verified why that is
  unacceptable: `LoggingConfig().file.file_name` is the RELATIVE path "testbench-ai-service.log", so
  a real call opens and appends the repo's own log file (already 168 KB here, with rotated .log.1 and
  .log.2 sitting untracked in git status), and `setup_logging` calls
  `dictConfig(disable_existing_loggers=True)`, which can silently disable pytest's own logging and
  caplog for every test that runs after it in the same session. The project's own convention agrees:
  every existing test that touches `setup_logging` patches it (tests/unit/test_cli.py x3) or patches
  the dictConfig underneath it (tests/unit/test_log.py).
  — Ruling: Task 10's tests must patch BOTH `setup_logging` and `load_translations` for every test,
  via an autouse fixture in that module, while the ordering test keeps its own explicit
  call-capturing patches. — Cost if wrong: none; patching a side-effecting logging reconfiguration in
  unit tests is the established pattern in this repo.
Task 10: dispatched (sonnet — swaps live service state; a wrong hot reload is expensive), BASE 7b17526

Task 10: controller verification found a CRITICAL hazard in MY OWN hot_reload design. Measured, end
  to end, with OPENAI_API_KEY and ANTHROPIC_API_KEY absent from the environment:
    1. `validate_config_dict({"llm_config": {"provider": "anthropic"}})` -> ACCEPTED. AppConfig does
       not check API keys, so the console happily validates a provider switch with no key.
    2. A real `LLMFactory().init_clients([...])` -> raises
       `ValueError: API key for provider 'anthropic' not found in environment variables.`
    3. `hot_reload` PROPAGATES that ValueError — and `app.state.config` has ALREADY been swapped.
  Reading the implemented order (reload.py lines 28-41) confirms why: setup_logging, load_translations,
  `previous_factory = app.state.llm_factory`, `app.state.config = config`, `await
  previous_factory.close_clients()`, `LLMFactory()`, `init_clients(...)` <- RAISES HERE,
  `app.state.llm_factory = factory` <- NEVER RUNS.
  So after the failure the process holds: the NEW config, the OLD factory, and that old factory's
  clients ALREADY CLOSED. Every subsequent agent request fails. The operator gets an opaque 500. And
  the file on disk is the new config, so nothing tells them the process did not follow.
  This is reachable by an ordinary action: switch provider on the LLM form without the matching key in
  .env — which is exactly the kind of edit this phase exists to enable. The task's own tests cannot
  see it because they patch LLMFactory (a necessary patch, correctly disclosed by the implementer —
  without it the real factory reaches os.getenv and the Mock assertions fail).
Ruling 29 (Task 10, Critical — hot_reload can leave the process in a broken state): FIX by making the
  fallible step unable to corrupt state, and by reporting the outcome honestly.
    (a) `init_clients` is only PRE-WARMING: `LLMFactory.get_client` creates lazily on demand, so
        skipping the pre-warm does not break the factory — the missing key then surfaces on the
        request that actually needs that provider, which is where it is actionable.
    (b) So wrap the pre-warm in try/except, log a warning, and STILL install the new factory. State
        is then always consistent: new config + new factory, never new config + closed old factory.
        This mirrors the treatment `close_clients` already gets, with the same justification — the
        file is already on disk, so aborting would leave disk and process disagreeing forever.
    (c) `hot_reload` must RETURN whether it fully succeeded, because Task 12 currently sets
        `reloaded=True` unconditionally after calling it. Without a return value that flag would be a
        lie in exactly this case. Carry the boolean into Task 12's ApplyResponse.
  — Cost if wrong: a provider switch with a missing key now applies and reloads, with a logged
  warning, and fails per-request with a clear provider-specific error instead of a 500 on apply. The
  operator sees `reloaded` reflecting reality.
Task 10: fix round 1 dispatched (resume implementer a275f65983b302906), FIX_BASE c750128
Task 10: controller verification of fix round 1, run against a REAL unpatched LLMFactory (the task's
  own tests patch it, so only an unpatched run proves the hazard is gone):
    provider=anthropic with no keys                    -> no exception, returned False,
                                                          config swapped, factory replaced: CONSISTENT
    same PLUS close_clients raising                    -> no exception, returned False,
                                                          config swapped, factory replaced: CONSISTENT
    language change with a key present                 -> returned True: CONSISTENT
  So the broken state (new config + old factory with closed clients) is unreachable, and the boolean
  distinguishes degraded from clean. Suite 54 failed / 757 passed.
Carry-forward to TASK 12: `hot_reload` now returns bool. Task 12's brief sets `reloaded=True`
  unconditionally after awaiting it — that must instead be `reloaded = await hot_reload(...)`, or the
  ApplyResponse lies whenever the pre-warm or the client close degraded.
Task 10: dispatched scoped re-review (haiku), FIX_BASE c750128 HEAD 302a39c
Task 10: fix round 1/5 (3 addressed, 0 open; commits c750128..302a39c)
Task 10: re-review traced all four combinations — (close ok, warm ok) -> True; (close ok, warm fails)
  -> False; (close fails, warm ok) -> False; (both fail) -> False. Factory installed unconditionally
  outside every try/except. Regression guard uses IDENTITY checks (`is broken_factory`,
  `is not old_factory`), so it would fail immediately if the bug returned. 16 restart_required tests
  untouched.
Task 10: the re-review's "out of scope" note called `LLMFactory()` construction sitting outside the
  try a deliberate design decision. Checked: `LLMFactory.__init__` only assigns two empty dicts, so it
  cannot raise at all. There is no hazard and no decision — recorded so the ledger does not imply a
  risk that does not exist.
Task 10: complete (commits 7b17526..302a39c, review clean, 23 tests)

Task 11 pre-dispatch verification:
  - Auth status codes confirmed by reading webui/auth.py: `current_session` raises 401 for a missing
    cookie; `require_admin` raises 403 for a valid non-admin session; `require_csrf` raises 403 for a
    missing/invalid token. Crucially BOTH `require_admin` AND `require_csrf` depend on
    `current_session`, so an anonymous caller gets 401 whichever resolves first — my plan's warning
    that declaration order decides 401-vs-403 was over-cautious but harmless. All four of the brief's
    auth tests are therefore satisfiable as written.
  - Ruling 16 applies here: the brief has TWO function-local imports in fixtures
    (`from fastapi.testclient import TestClient`, `from unittest.mock import patch`) which PLC0415
    rejects. Carried into the dispatch.
Task 11: dispatched (sonnet — largest integration task so far: models + route + 13 auth-bearing
  tests), BASE 302a39c

Task 11: controller verification — built a real app over a real commented config.toml and drove the
  route through TestClient. Everything composes:
  AUTH MATRIX: anonymous -> 401; valid non-admin session with CSRF -> 403; admin without the CSRF
    header -> 403; admin with both -> 200.
  HAPPY PATHS: no edits -> valid, 0 diffs, restart [], and `toml` byte-identical to the file on disk;
    port=9999 -> (added 1, removed 1), restart ['port'], diff path == the resolved config path;
    language=en -> restart [] (hot-swappable); port="not a number" -> 200 with valid=false, issue
    addressed to ('port', '[testbench-ai-service]'), and ZERO diffs (nothing to approve).
  COMMENT PRESERVATION through the whole route: all three of the fixture's comments — the top-of-file
    note, the mid-table note, and the trailing inline `# trailing note` — survive into `toml`.
  SAFETY REFUSALS all surface as clean 400s rather than 500s: redaction sentinel, prefix collision,
    scalar parent, whitespace segment, malformed path, over-deep path. This is what I warned the
    implementer not to catch-and-translate, and it held.
  PREVIEW WRITES NOTHING: config.toml sha256 identical before/after, no .bak, directory contains only
    config.toml.
  CONCURRENCY PROPERTY: with another operator's value (7777) already on disk, our diff shows
    `-port = 7777` — the spec's mitigation for having no server-side draft lock, working end to end.
  Suite 54 failed / 770 passed (+13).
Task 11: implementer disclosed removing an unused `FileDiff` import my brief listed (ruff F401) —
  correct, nothing in the given code referenced it. test_wiring.py needed no change: it asserts
  generic /admin prefixes rather than enumerating routes.
Task 11: dispatched review (sonnet), BASE 302a39c HEAD ded6e46

Task 11: review returned SPEC ✅ but proved a CRITICAL, plan-mandated credential leak.
Ruling 30 (Task 11, Critical — preview returns unredacted secrets): FIX, by SPLITTING the raw text
  from the displayed text. The reviewer reproduced it: with `api_key = "sk-REAL-SECRET-VALUE"` in
  config.toml, `GET /config` returns `api_key: '***REDACTED***'` while `POST /config/preview` returns
  `toml` containing the secret verbatim — even for `edits: {}` — and an edit to an adjacent key also
  puts the secret into the returned `diff` as a context line. Spec section 14 states "API-key presence
  is reported, never values", so this violates an explicit requirement, and it makes the console hide
  through one endpoint what it shows through another. My `_plan_change` never calls redaction.
  THE TRAP, and why the naive fix is worse than the bug: `toml` is BOTH displayed in the Raw screen
  AND (as the tuple's second element) the text Task 12 writes to disk. Redacting it wholesale would
  write `***REDACTED***` into the operator's config.toml and DESTROY their real key. So the fix must
  return raw text for writing and redacted text for display, separately.
  Verified feasible: a `redact_toml_text(text)` that re-parses with tomlkit, walks Table/InlineTable/
  OutOfOrderTableProxy nodes and replaces credential-named values via config_io's existing
  `_looks_like_credential_key`, then re-renders. Measured on a fixture with two secrets (one top-level,
  one inside an inline table under a quoted project key): both redacted; comments preserved including
  a trailing inline comment; still valid TOML; the RAW text untouched. And the existing key-name-only
  rule behaves correctly — `auth_method = "api_key"` is KEPT (a legitimate enum value) and
  `ssl_key = "/etc/certs/key.pem"` is KEPT (the compound-token rule deliberately avoids bare "key"),
  so no false redaction. Reusing that helper is what makes the two endpoints agree by construction.
  The DIFF must be computed on redacted-vs-redacted. That hides nothing an operator did, because the
  edit layer refuses the sentinel as a value, so a credential can never be CHANGED from the console —
  it can only appear as unchanged context.
  — Cost if wrong: the Raw screen and diff show `***REDACTED***` where a secret sits, which is the
  same thing GET /config already shows, and the written file keeps the real value.
Ruling 31 (Task 11, Important, plan-mandated): none of the 13 tests uses a credential-named key, so
  the leak was entirely uncovered by the task's own suite. Fix adds coverage.
Task 11: minor (deferred): `_plan_change` parses the file twice per request — once with tomlkit for
  the document and once with tomllib inside `merge_edits(read_config_file(...))`. Negligible for a
  small hand-edited config; final review to triage.
Carry-forward to TASK 12: it must write the tuple's RAW second element, NEVER `PreviewResponse.toml`,
  which is now redacted. Writing the response field would destroy the operator's credentials.
Task 11: fix round 1 dispatched (resume implementer ac5372af594b6e15a), FIX_BASE ded6e46
Task 11: controller verification of fix round 1, driven through a real app over a config.toml holding
  TWO secrets (one top-level `api_key`, one inside an inline table under a quoted project key):
  LEAK CLOSED — GET /config still shows ***REDACTED***; preview's `toml` with no edits leaks NEITHER
    secret and contains exactly 2 sentinels; editing the key ADJACENT to the secret leaks it in
    neither `toml` nor `diff`, while still showing the real edit (+provider = "anthropic").
  NO OVER-REDACTION — `auth_method = "api_key"` survives untouched (the rule matches key names, not
    values), and comments including the trailing inline comment survive into the redacted text.
  WRITE PATH INTACT — calling `_plan_change` directly: `PreviewResponse.toml` does NOT contain the
    secret, while the tuple's second element (the text Task 12 writes) DOES contain BOTH real secrets,
    contains the edit, and contains NO sentinel. This is the pairing that matters: closing the leak by
    redacting the write path would have destroyed the operator's credentials on the next apply.
  PREVIEW STILL WRITES NOTHING — the file on disk is byte-identical and still holds the real secrets.
  Suite 54 failed / 776 passed (19 tests in test_config_routes.py).
Task 11: dispatched scoped re-review (haiku), FIX_BASE ded6e46 HEAD 27c1e91

Task 11: re-review confirmed findings 1-3 addressed, then found TWO more Critical gaps. I verified
  both, and the second is broader than reported.
Ruling 32 (Task 11, Critical — credentials inside an array of tables leak): FIX. Confirmed: a config
  containing `[[tool.other.entries]]` with `api_key = "sk-IN-AOT"` renders that secret verbatim into
  preview's `toml`, because `_redact_toml_node` checks Table/InlineTable/OutOfOrderTableProxy/dict but
  not `tomlkit.items.AoT`. Reachable because the rendered `toml` is the WHOLE FILE, not just the
  `[testbench-ai-service]` table — and this project's loader already treats config.toml as a
  potentially shared file (it falls back to reading pyproject.toml), so another tool's
  array-of-tables section with a credential in it is a realistic shape. Fix is adding AoT to the
  walker and iterating its entries. Note an array-VALUED credential key is already handled correctly:
  `api_keys = ["sk-A","sk-B"]` becomes `api_keys = "***REDACTED***"`.
Ruling 33 (Task 11, Critical — hyphenated credential keys leak; PRE-EXISTING, wider than the review
  said): FIX in `_looks_like_credential_key` by normalising separators before matching. Verified the
  gap is real AND older than this phase: `_looks_like_credential_key("api-key")` is False, and
  `redact_credentials({"llm_config": {"api-key": "sk-HYPHEN"}})` leaves the secret in place — so
  `GET /config`, shipped in phase 1, has always missed it. The fix therefore closes a hole in an
  already-released endpoint, not just in preview.
  The review overstated the breadth: `auth-token`, `client-secret` and `refresh-token` DO match today,
  because "secret"/"token"/"credential" are bare substrings. Only the COMPOUND tokens are
  separator-sensitive, so the actual gap is exactly `api-key`, `x-api-key`, `api.key`, `api key`.
  Fix: normalise `-`, `.` and space to `_` before the substring test. Verified this preserves the
  deliberate non-matches — `ssl_key` still does NOT match (so a cert path is still shown, per the
  existing docstring's reasoning) and `auth_method` still does not match.
Task 11: confirmed `redact_toml_text` does NOT raise on anything `load_document` accepts — empty file,
  comment-only, no service table, a scalar at the prefix, and an array-of-tables all pass. So no risk
  of 500ing a file the route previously handled.
Task 11: fix round 2 dispatched (resume implementer ac5372af594b6e15a), FIX_BASE 27c1e91
Task 11: controller verification of fix round 2 — both gaps closed, no over-redaction:
  SEPARATOR VARIANTS all now match: api_key, api-key, API-KEY, x-api-key, api.key, "api key", apikey,
    plus the already-working password/secret/token/credential/auth-token/client-secret/refresh-token.
  DELIBERATE EXCLUSIONS all still preserved: ssl_key, ssl-key, auth_method, auth-method, port,
    provider, file_name — so cert paths and enum values remain visible as the docstring intends.
  PRE-EXISTING HOLE CLOSED in GET /config too: redact_credentials now redacts `api-key` and
    `x-api-key` while leaving `ssl_key` as a path. That endpoint shipped in phase 1, so this fix
    closes a hole in already-released code.
  ARRAY OF TABLES: `[[tool.other.entries]]` credentials no longer leak — including a case the review
    did not test, an inline table nested INSIDE an AoT (`inner = { password = ... }`), also redacted.
    Non-credential fields in the AoT (`name`, `port`) preserved.
  Array-VALUED credential still collapses to the sentinel. No raise on any shape load_document
    accepts. Suite 54 failed / 785 passed; webui suite 267 passed.
Task 11: dispatched scoped re-review (haiku), FIX_BASE 27c1e91 HEAD 84fe052
Task 11: fix round 2/5 (2 addressed, 0 open; commits 27c1e91..84fe052)
Task 11: re-review's FALSE-POSITIVE SWEEP over every real field of AppConfig, LLMConfig,
  LoggingConfig, AdminUiConfig, PromptConfig and AgentConfig found NONE now wrongly redacted, and
  confirmed the new tests assert BOTH the secret's absence AND the sentinel's presence (asserting only
  absence would pass if the key vanished entirely). AoT comments and ordering survive redaction.
  `AoT` imported at module level. Fresh defeat attempts all failed to leak.
Task 11: complete (commits 302a39c..84fe052, review clean, 19 route tests + config_io additions)
NOTE FOR THE USER-FACING SUMMARY: Ruling 33 closed a PRE-EXISTING hole in GET /config, shipped in
  phase 1 — a config.toml containing `api-key = "..."` had its value rendered in plaintext by the
  console's config screen until now. Phase 1's own review did not catch it.

Ruling 34 (Task 12 pre-dispatch, PLAN DEFECT created by my own Ruling 29 — the SIXTH unsatisfiable
  test I have written): the brief's `test_apply_hot_reloads_a_swappable_change` asserts
  `body["reloaded"] is True`, and that is now impossible in the test environment. Verified the chain:
  conftest's `make_app` patches `testbench_ai_service.main.LLMFactory` (the startup path only), while
  `hot_reload` imports LLMFactory into `webui.reload`'s own namespace (reload.py:30) and constructs it
  at line 149; no OPENAI_API_KEY or ANTHROPIC_API_KEY is set in this environment and the default
  provider is openai, so `init_clients` raises ValueError -> Ruling 29's swallow returns False ->
  `reloaded` is False -> the assertion fails.
  — Ruling: Task 12's tests must patch `testbench_ai_service.webui.reload.LLMFactory`, which is
  exactly the target Task 10's tests already use (test_reload.py:202, 280). Pointing the dispatch at
  that established pattern rather than inventing a new one. — Cost if wrong: none; without it the test
  asserts a value that cannot occur.
Task 12: dispatched (sonnet — the only route that writes to the operator's filesystem), BASE 84fe052

Task 12: controller verification — drove the WRITING route through seven scenarios on a real
  config.toml containing a real secret and three comments. All correct:
  1. hot-swappable (language=en): 200, written, reloaded TRUE, restart []; the REAL api_key is still
     in the file and NO sentinel was written (this is Correction 1 proven — writing preview.toml
     would have replaced the operator's key); all three comments preserved; .bak holds the original
     byte-for-byte; app.state.config swapped in process.
  2. restart-required (port=9999): 200, restart ['port'], reloaded FALSE; the file HAS the new port
     and the process KEEPS the old one — written but not pretended-live.
  3. invalid edit: 422 with a dict detail carrying the field-addressed issue
     ('port','[testbench-ai-service]'); file byte-identical and NO .bak created.
  4. safety refusals (sentinel, scalar parent): 400, file unchanged, no .bak.
  5. no-op ({}): nothing written, `written: []`, `backup: null`, reloaded false.
  6. auth: missing CSRF -> 403 and no write; non-admin -> 403 and no write.
  7. two sequential applies: both edits present, secret and comments intact — the merge-against-disk
     property holds across writes.
  The invariant "a 4xx from this route means the file is unchanged" held in every failing case.
Task 12: the implementer's disclosed change to `testbench_ai_service/exceptions.py` (the GLOBAL
  handler) is CORRECT and safe. Verified: the only non-string `detail` anywhere in the service is the
  new apply route's (webui/routes.py:275); every other raise passes a string, so the new
  `isinstance(detail, dict)` branch is purely additive and no agent-API error response changes shape.
  It was genuinely necessary — the old handler `str()`-coerced every detail, which would have
  collapsed the issues dict into an unparseable Python repr.

Ruling 35 (carry-forward to TASK 14, integration defect in my plan spanning backend and frontend):
  the apply route's 422 carries `{"detail": {"message": ..., "issues": [...]}}`, but
  `frontend/src/api/client.ts:57` only adopts `body.detail` when `typeof body.detail === 'string'`.
  So a rejected apply reaches the operator as the generic fallback "Request failed with status 422"
  and the field-addressed issues are DISCARDED — the whole point of returning them. Fix belongs in
  Task 14: give `ApiError` a `detail: unknown` field, have `client.ts` use `detail.message` when
  detail is an object carrying a string `message`, and keep the raw detail on the error so Task 17's
  DiffDialog can render `issues`. — Cost if wrong: none; without it the console shows a status code
  instead of the reason.
Task 12: dispatched review (sonnet — the only route that writes), BASE 84fe052 HEAD 4b044bf

Task 12: review returned SPEC ✅ with one Important finding, and its post-write analysis surfaced a
  second, worse one. I verified both end to end and the second is a CRITICAL SPEC VIOLATION.
Ruling 36 (Task 12, CRITICAL — the console can write a config that prevents the service from
  starting; spec 6.3 says it cannot): FIX, with validation before the write plus two safety nets.
  Reproduced end to end through the route:
    - `logging.file.file_name` IS an editable text field on the console's Logging form
      (frontend/src/screens/fields.ts:97).
    - `AppConfig` ACCEPTS any value for it — there is no writability validation.
    - `setup_logging` then raises `ValueError: Unable to configure handler 'file'` because it builds a
      RotatingFileHandler from that path.
    - Applying `{"logging.file.file_name": "Z:/nope/deeper/svc.log"}` returns **HTTP 500 with a
      non-JSON body**, the config file IS written, a .bak IS created, and the process is still on the
      OLD config.
    - And cli.py:143 calls `setup_logging` at STARTUP, so the config now on disk would prevent the
      service from starting at all.
  Spec 6.3: "The console therefore cannot write a configuration that would prevent the service from
  starting." This breaks that promise outright, and leaves the operator with an opaque 500, a
  modified config file, and a service that will not come back up. Worst outcome in the feature.
  FIX (A) — the real one: validate log-path writability BEFORE writing, as a field-addressed issue on
  `logging.file.file_name`, so the apply is refused with 422 and NOTHING is written. Verified a
  no-side-effect check works: resolve the parent directory; pass if the file exists and is writable;
  fail if the parent is not an existing directory or is not writable. Measured — the default relative
  `testbench-ai-service.log` PASSES, a temp dir PASSES, a missing subdirectory FAILS, a nonexistent
  drive FAILS. Empty string must be rejected explicitly (it currently resolves to "." and passes).
  Put it in webui/validate.py, not in AppConfig: the console's promise is what is broken, and
  tightening the core model could reject configs the CLI loads today.
  FIX (B) — defence in depth, amending Task 10's hot_reload: `setup_logging` and `load_translations`
  run BEFORE its try/except and are unguarded. Guard them the same way the client steps are guarded —
  log, mark degraded, continue — so no failure there can 500 a request whose write already succeeded.
  FIX (C) — the post-write re-read: `read_config_file` can raise HTTPException(400) after the write
  committed (reviewer reproduced it), which is a 4xx that falsely implies nothing happened. Catch it
  and return an honest 200 with `reloaded=False`.
  FIX (D) — `ApplyResponse.reload_detail: str | None`. Necessary, not cosmetic: if the failure IS the
  log path, the reason cannot be written to the log, so the response is the only channel the operator
  has.
  — Cost if wrong: a legitimate log path on a filesystem that reports itself unwritable at validation
  time would be refused; the operator would see a field-addressed message naming the directory.
Task 12: fix round 1 dispatched (resume implementer ac36a4d588bb8b4cf), FIX_BASE 4b044bf
Task 12: controller verification of fix round 1 — the spec-6.3 violation is GONE and there is no
  over-rejection:
    nonexistent drive  -> 422, issue on logging.file.file_name, file unchanged, no .bak
    missing subdir     -> 422, same
    empty file_name    -> 422, same
    writable temp dir  -> 200, written, reloaded True, reload_detail None
    default relative   -> 200, written, reloaded True, reload_detail None
  FIX B verified directly: `setup_logging` raising inside hot_reload now returns False, still swaps
  the config, and does NOT propagate. Suite 54 failed / 804 passed; webui 286 passed.
Task 12: all three implementer concerns accepted. The third is a better call than my instruction: it
  used a missing-SUBDIRECTORY path for the automated regression test instead of my literal `Z:/...`,
  because a drive letter would make the test Windows-only, and reproduced the drive case manually.
  My instruction would have created a platform-dependent test. The other two — reload_detail left
  None on the no-op path (nothing was written, so nothing to explain) and a generic degraded message
  (making it specific needs hot_reload to return a reason string, which would ripple into
  test_reload.py) — are both proportionate.
Task 12: dispatched scoped re-review (sonnet — the writing route, and the fix touches validation,
  reload and the response model), FIX_BASE 4b044bf HEAD a750de2

Task 12: re-review verdict FINDINGS STILL OPEN — B, C, D addressed; A only NARROWED the spec-6.3
  hole rather than closing it. Both new findings are in the fix I specified.
Ruling 37 (Task 12, Important — directory-as-log-file false accept): FIX. Verified: a `file_name`
  that already exists as a DIRECTORY passes `validate_config_dict` (because `path.exists()` is true
  and `os.access(dir, W_OK)` is true — the directory genuinely IS writable), yet `setup_logging`
  raises `ValueError: Unable to configure handler 'file'` on that same path. So an operator who types
  an existing directory still writes a config that will not boot, and spec 6.3 is still violated for
  that shape. Fix: reject when the path exists and is NOT a file — `exists=True, is_file=False`
  discriminates a directory from a real file, which I confirmed on all three shapes (existing dir,
  existing file, nonexistent leaf). — Cost if wrong: a path that exists as something exotic but
  file-like (a device, a FIFO) would be refused; on Windows, and for a log file, that is not a
  configuration anyone wants.
Ruling 38 (Task 12, Minor bundled — the new check sits outside the guard built to catch exactly this):
  FIX. `_log_file_writability_issue` is called at validate.py:161, OUTSIDE the
  `try/except (ValidationError, (Exception, SystemExit))` block at 129-155 whose own comment explains
  it exists so a filesystem-touching validator cannot produce a raw 500. If the check ever raises an
  OSError pathlib does not swallow, it propagates uncaught through `_plan_change` -> `apply_config`,
  reproducing the exact raw-500-after-a-committed-write pattern Fix C was built to close. Move it
  inside the guard. Bundled because it is a two-line move in the same function.
Task 12: the rest of the over-rejection sweep came back clean and I accept its reasoning: `~/log.txt`
  is REJECTED and that is correct (pathlib does not expand `~` and neither would RotatingFileHandler,
  so the rejection matches reality); `../log.txt` accepted; a symlinked parent pointing at a writable
  directory accepted (tested with a real symlink); a >260-char path rejected without crashing; a UNC
  path to a nonexistent host rejected without hanging. No side effects in the check — only
  `exists()`, `is_dir()` and `os.access()`, so it is safe to run on the preview route too.
Task 12: PREVIEW INTERACTION confirmed desirable — a bad log path now also makes
  `POST /config/preview` report `valid: false` with the issue on `logging.file.file_name`, so preview
  surfaces exactly what apply will refuse rather than the operator discovering it at apply time.
Task 12: fix round 2 dispatched (resume implementer ac36a4d588bb8b4cf), FIX_BASE a750de2
Task 12: controller verification of fix round 2 — all eight path shapes now correct:
    existing DIRECTORY        -> REJECT (logging.file.file_name)   [the round-1 false accept, closed]
    existing writable FILE    -> ACCEPT                            [critical regression guard: the
                                                                    normal case after the first run]
    nonexistent leaf, ok dir  -> ACCEPT
    missing subdirectory      -> REJECT
    default relative          -> ACCEPT
    empty / whitespace        -> REJECT
    relative with ..          -> ACCEPT
  NO SIDE EFFECTS: the existing log file's content is untouched and nothing was created in the temp
  directory by validation — important because this check also runs on the preview route, which
  promises to write nothing.
  GUARD PLACEMENT verified by injection: patching the check to raise OSError now yields
  `(None, [issue with path=''])` — caught and root-addressed — instead of propagating. Ruling 38 closed.
  Suite 54 failed / 807 passed; webui 289 passed.
Task 12: implementer's disclosed refactor accepted — splitting `_log_file_writability_issue` into
  `_existing_path_problem` / `_missing_leaf_problem` / `_log_file_problem` was forced by ruff's
  PLR0911 (7 returns > 6), and it chose to split rather than suppress the rule. Right call.
Task 12: complete (commits 84fe052..2ea5c53, review clean, 36 route tests + 25 validate tests)
=== BACKEND WRITE PATH COMPLETE: Tasks 1-12 done. Remaining: 13-19 frontend, 20 wiring, 21 docs,
    22 verification. ===

FRONTEND BASELINE (measured before Task 13): 10 test files, 60 tests, ALL PASSING. Unlike the
  backend, the frontend has a GREEN baseline, so frontend tasks 13-19 are held to "all tests pass",
  not "no worse than N failures". `npx vitest run` from frontend/ is the command.
Task 13: dispatched (haiku — complete code in brief, single new file + test), BASE 2ea5c53
Task 13: controller verification — exported API is exactly the DraftApi tasks 14-19 consume (edits,
  changeCount, isChanged, valueOf, setValue, unsetValue, revert, discardAll) plus DRAFT_STORAGE_KEY
  and the Edits type. `prune` implements the load-bearing distinction correctly: a null value is kept
  as a change only when the key actually exists in `saved`, so "remove" is a change and "remove
  something absent" is not. Frontend 73 passed (60 + 13), npm run build clean.
Task 13: dispatched review (haiku — single self-contained module against a green baseline),
  BASE 2ea5c53 HEAD fbfa905

Task 13: review returned SPEC ✅ with two Importants and a Minor. Its loading-state trace concluded
  "edit loss does NOT occur" — that is right about the DERIVED state but stops one step short of the
  PERSISTENCE consequence, and I proved the loss with a throwaway probe (since deleted, not committed):
Ruling 39 (Task 13, Important — a queued REMOVAL edit is silently destroyed): FIX. Measured chain:
  localStorage holds `{"port": null}`; on mount while the config query is in flight Task 20 passes
  `saved = config.data?.disk ?? {}` = `{}`; `prune` correctly drops the null (an absent key cannot be
  "removed"); the persistence effect then sees an empty overlay and calls
  `localStorage.removeItem(DRAFT_STORAGE_KEY)` — DESTROYING the stored draft. My probe confirmed:
  test 1 (storage cleared while loading) PASSES, test 2 (a SET edit survives) PASSES, test 3 (the
  removal returns to derived state once the config arrives) PASSES, but test 4 — a SECOND mount after
  the placeholder wiped storage — FAILED, i.e. the removal is gone for good. Reachable by an operator
  who queues a removal and reloads twice quickly, and permanently if the config query FAILS (saved
  stays `{}` forever). Only removals are affected; set edits survive.
  Fix: `DraftProvider` must accept `saved` as possibly `undefined` and, while it is undefined, neither
  prune NOR persist — "we do not know what is saved yet" is not the same as "nothing is saved". Task 20
  then passes `config.data?.disk` without the `?? {}`. — Cost if wrong: while the config is loading the
  pending-change count may briefly include an edit that a concurrent save already made redundant; it
  self-corrects the moment the query resolves.
Ruling 40 (Task 13, Important — the draft survives sign-out and is not user-scoped): FIX by clearing
  the stored draft on sign-out. The real harm is not the config values (the next operator is also an
  admin who can read them via GET /config) — it is that operator B is shown "N unapplied changes" they
  did not make, on a shared machine, and could apply operator A's queued edits believing them their
  own. Export a `clearStoredDraft()` from draft.tsx so the storage key stays defined in one place, and
  call it from `session.tsx`'s signOut. — Cost if wrong: an operator who signs out and back in loses
  queued edits, which is the safer failure and matches what "sign out" implies.
Task 13: minor (deferred): JSON.stringify comparison is key-order sensitive, so a backend that
  re-serialised an object with different key order would report a phantom change. Not reachable from
  any current form field (all produce scalars, or an array of strings for trusted_proxies). Final
  review to triage.
Task 13: fix round 1 dispatched (resume implementer a374c80b2ce31202a), FIX_BASE fbfa905
Task 13: controller verification of fix round 1 — re-ran my probe (since deleted) against the fix and
  ALL FOUR assertions now pass, including the one that failed before: a queued removal SURVIVES a
  wipe-then-remount cycle while `saved` is undefined; a genuinely empty `saved={{}}` still prunes the
  removal (fix did not over-broaden); a SET edit still survives loading; and a redundant edit is still
  pruned once the real config arrives. `clearStoredDraft` is exported from draft.tsx:170 and called
  from session.tsx:54 inside signOut. Frontend 80 passed (60 + 20), build clean.
Task 13: dispatched scoped re-review (haiku), FIX_BASE fbfa905 HEAD 824e0d3
Task 13: fix round 1/5 (2 addressed, 0 open; commits fbfa905..824e0d3)
Task 13: re-review confirmed the undefined branch guards BOTH consumers (prune at draft.tsx:72, the
  persistence effect at :108), so no render order restores the bug; and — the thing I was most worried
  about — `clearStoredDraft()` sits in a FINALLY block in session.tsx:52-55, so the draft is cleared
  even when the sign-out DELETE fails (expired session, network error), and the effect does not
  re-persist afterwards because neither `effective` nor `saved` changes.
Task 13: complete (commits 2ea5c53..824e0d3, review clean, 80 frontend tests)
Task 14: dispatched (haiku), BASE 824e0d3. Carries Ruling 35 (ApiError must expose the structured
  detail, or the apply route's field-addressed issues are discarded).
Task 14: controller verification — Ruling 35 closed: `ApiError` now has `readonly detail: unknown`
  populated from the body, a string detail still becomes the message, and an OBJECT detail carrying a
  string `message` sets the message while the whole object (with `issues`) stays on `error.detail` for
  Task 17 to render. Non-JSON bodies still fall back cleanly. All three post-brief fields declared:
  StatusResponse.in_flight_tasks + restart_required, ApplyResponse.reload_detail. `useApply`
  invalidates BOTH ['config'] and ['status']. Frontend 88 passed, build clean.
Task 14: dispatched review (haiku), BASE 824e0d3 HEAD db9231c

Task 14: review returned SPEC ❌ on one point and it is CORRECT — I was wrong in my own dispatch.
Ruling 41 (Task 14, my error — a type that lies about the API): I told the implementer to add
  `restart_required: string[]` to `StatusResponse` "which the backend's status route now returns".
  It does not. Verified against the live app: `GET /admin/api/status` returns exactly
  ['agents','api_keys','in_flight_tasks','log_file','service','testbench'] — no restart_required. I
  confused Task 12's APPLY response (which does carry it) with the STATUS response, where it is still
  Task 20 Step 6's work. So the frontend now declares a required field the backend omits: `tsc`
  believes it is `string[]` while it is `undefined` at runtime.
  Considered leaving it, on the grounds that no consumer exists until Task 20 adds both the backend
  field and the banner that reads it — so the lie is currently unobservable. Rejected that: "safe
  because nothing reads it yet" breaks the moment tasks are reordered or dropped, and it leaves a
  false contract in the tree.
  — Ruling: add `restart_required: list[str] = []` to the backend's `StatusResponse` model NOW, in
  Task 14's fix round. One line, defaults to empty, makes the contract true immediately, and does not
  pre-empt Task 20 — which then only has to POPULATE it rather than also declare it. Better than
  weakening the TS type to optional (Task 20 would immediately re-tighten it) and better than doing
  Task 20's comparison logic early. — Cost if wrong: the status response gains an always-empty array
  field for the remainder of this phase, which is exactly what an operator with nothing to restart
  should see anyway.
Task 14: type parity otherwise CLEAN — the review compared ConfigIssue, FileDiff, PreviewResponse and
  ApplyResponse field-by-field against the pydantic models and all four match on name, type and
  nullability, including `backup: str|None -> string|null` and `reload_detail: str|None -> string|null`.
Task 14: detail-shape matrix all sensible: a string detail becomes the message; an object with a
  string `message` becomes the message with the full object (issues included) on `.detail`; an array,
  `null`, a number and a non-JSON body all fall back to "Request failed with status N" without
  throwing.
Task 14: fix round 1 dispatched (resume implementer a91342cdbb3b76abd), FIX_BASE db9231c
Task 14: fix round 1/5 (2 addressed, 0 open; commits db9231c..e5932d6)
Task 14: controller verification — `GET /admin/api/status` now returns restart_required with value []
  alongside the six pre-existing keys, so the frontend's required-field declaration is honest. Task 20
  now only has to POPULATE it. Frontend 88 passed, build clean; backend webui 290 passed, suite 54
  failed / 808 passed.
Task 14: complete (commits 824e0d3..e5932d6, review clean)
Task 15: dispatched (haiku), BASE e5932d6. Carries the corrected label rule (last dotted segment, to
  match ReadOnlyField) and the empty-means-remove semantics.

Ruling 42 (Task 15, CRITICAL — the list field is unusable; the implementer's "testing artifact"
  diagnosis is WRONG, and this is my plan's defect): FIX. The implementer reported 100/101 with one
  failing list test, claiming "Input displays correctly ('10.0.0.1, 10.0.0.2')" and "production input
  handling works correctly". I probed it (throwaway test, since deleted) and both claims are false:
    type "10.0.0.1"        -> input "10.0.0.1",                 edits ["10.0.0.1"]
    type ","               -> input "10.0.0.1"  <-- THE COMMA VANISHES from the input
    type "10.0.0.2"        -> input "10.0.0.110.0.0.2",         edits ["10.0.0.110.0.0.2"]
    append to an existing ["10.0.0.1","10.0.0.2"]:
    type ", 10.0.0.3"      -> input "10.0.0.1, 10.0.0.210.0.0.3", edits [...,"10.0.0.210.0.0.3"]
  Cause is in MY brief: the list input is CONTROLLED with its value derived from the parsed array via
  `asText` (a join), and the change handler filters out empty entries — so a trailing comma is dropped
  on the round trip and can never persist in the displayed value. Consequence: an operator can never
  enter a second `trusted_proxies` entry. That is the ONLY list field in phase 2, so the whole control
  is broken, not degraded.
  Only the LIST type is affected: text round-trips identically through `asText`, number's
  `asText(9999)` is "9999", select is a fixed option set, bool is a button.
  Fix: hold the raw text in local component state while editing so the comma survives, render from
  that text, and still commit the PARSED array to the draft on each change. Resync the local text to
  the derived value when the draft no longer holds an edit for that path, so revert and discard-all
  still update the visible input.
  — Cost if wrong: a list field that briefly shows text the parsed array would not reproduce (e.g. a
  trailing comma mid-typing), which is exactly what an operator typing needs.
Task 15: the failing test was the SIGNAL, not the problem. Recording this because it is the second
  time an implementer has proposed accepting a red test on a plausible-sounding rationale; the green
  frontend baseline is the bar and a failing test gets diagnosed, not excused.
Task 15: fix round 1 dispatched (resume implementer ad4bc48bda7e57008), FIX_BASE e717ac0
Task 15: controller verification of fix round 1 — re-probed (throwaway, deleted) and all five
  assertions pass, including the two that failed before: typing "10.0.0.1, 10.0.0.2" now leaves the
  input showing exactly that and stores ["10.0.0.1","10.0.0.2"]; appending ", 10.0.0.3" to an existing
  two-entry list gives three entries; clearing still records a removal (null); REVERT restores the
  saved value in the VISIBLE input (the resync effect, which is what stops stale text lingering); and
  the text type still round-trips. Frontend 104 passed, 0 failed, build clean.
Task 15: implementer corrected its own record — "the initial 'testing artifact' diagnosis was
  incorrect; the list field bug is real".
Task 15: dispatched review (haiku), BASE e5932d6 HEAD d8b70a4

Task 15: review returned SPEC ✅, Approved, with one "Critical" I am DOWNGRADING as unreachable and
  two Importants worth closing.
Ruling 43 (Task 15, reviewer's Critical — two Field instances for one key diverge): PARKED as
  unreachable, not fixed. Verified: all 31 `key:` values in frontend/src/screens/fields.ts are unique
  across the whole file, and the three rendered groups (a single SERVICE_TABS tab at a time,
  LLM_FIELDS, LOGGING_FIELDS) are mutually exclusive screens — so no form ever mounts two Field
  components for the same spec key. The reviewer itself flagged it as unlikely and could not verify
  reachability. Solving it would mean lifting the raw-text state into the draft context, which is real
  machinery for a shape the code cannot produce. — Cost if wrong: if a future screen ever renders one
  key twice, the two inputs would show different text mid-edit while the draft stays correct.
Ruling 44 (Task 15, Important, plan-mandated — the bool switch is not linked to its validation
  message): FIX. Four of the five field types set `aria-invalid` and `aria-describedby` when an issue
  is addressed to them; the bool switch sets neither, so the message renders (role="alert" is present)
  but is not semantically tied to the control — WCAG 3.3.2. My brief's template omitted it. Reachable:
  a hand-edited `debug = "yes"` in config.toml yields an issue addressed to `debug`, which the Service
  form then displays against a bool field. Two attributes plus tests. — Cost if wrong: none.
Ruling 45 (Task 15, Important bundled): add a11y test coverage for bool AND select with an issue
  present — only the number type is currently covered, so the other four types' linkage is untested.
Task 15: LOCAL-TEXT DIVERGENCE otherwise clean — (a) a saved-value refetch mid-edit keeps the typed
  text and syncs on revert; (b) `discardAll()` resyncs the visible input via the `changed` effect;
  (d) unmount/remount keeps the edit in the draft (the authority) though the raw text is lost, which
  is acceptable. RESYNC LOOP: no loop — the effect depends only on `changed`, which transitions once
  per edit-session, and `text` is not a dependency. OTHER TYPES UNAFFECTED: verified per type, the
  local text state is used exclusively by the list branch.
Task 15: fix round 2 dispatched (resume implementer ad4bc48bda7e57008), FIX_BASE d8b70a4
Task 15: fix round 2/5 (2 addressed, 0 open; commits d8b70a4..237cefd)
Task 15: re-review confirmed the describedby id resolves EXACTLY to the message element
  (`${spec.key}-issue` on both sides), the new tests assert exact attribute VALUES so they would fail
  if the attributes were removed, the keyboard test uses a real `userEvent.keyboard('{Enter}')` rather
  than a click in disguise, and the diff added only the two aria-* lines with no collateral.
Task 15: complete (commits e5932d6..237cefd, review clean, 107 frontend tests)
Task 16: dispatched (haiku), BASE 237cefd. Carries Ruling 1 (add the two declared LLM fields to
  LLM_FIELDS) and the Task 6 probe finding (indexed-path issue matching for list fields).
Task 16: controller verification — indexed-path matching implemented with the dot boundary
  (`path === key || path.startsWith(key + '.')`) and a comment recording why a bare startsWith would
  be wrong; both declared LLM fields (llm_config.timeout, llm_config.max_retries) now in LLM_FIELDS,
  closing Ruling 1 from the pre-flight scan; the draft is measured against `config.data.disk` with a
  running-config fallback; the non-admin path still renders ReadOnlyField rather than a disabled Field.
  Frontend 115 passed, 0 failed, build clean.
Task 16: dispatched review (haiku), BASE 237cefd HEAD 68d0085

Task 16: review returned SPEC ✅ and confirmed the hidden-tab gap I predicted, plus two Minors.
Ruling 46 (Task 16, Important — an issue on a non-visible tab has no field-level indicator): FIX, but
  narrower than the reviewer framed it. It said the operator "sees apply rejected but cannot locate
  the error anywhere". That overstates it: I checked the planned DiffDialog (Task 17) and it renders
  EVERY issue as `<code>{issue.path}</code> — {issue.message}`, so an issue on the TLS tab IS visible
  in the dialog with its dotted path even while the General tab is on screen. The real gap is
  narrower: after dismissing the dialog there is no per-tab indicator, so the operator knows a field
  named `ssl_cert` is wrong but has to guess which tab holds it.
  Fix: mark any Service tab whose fields carry an issue, so the operator can find it. Cheap and it
  closes the "cannot locate" complaint directly. — Cost if wrong: an extra marker on a tab button.
Ruling 47 (Task 16, Minor bundled): the array-element test asserts `aria-invalid` but not that the
  MESSAGE text is displayed. Strengthen it — the point of the indexed match is that the operator can
  read the reason.
Task 16: FALSY-DISK-VALUE analysis came back correct and I accept it: `??` only falls through on
  null/undefined so an explicit `false`/`0`/`""` on disk passes through intact; and when the disk omits
  a key, `saved` becomes the running default, so setting the field to that default records NO change —
  which is right, because there is nothing to write.
Task 16: minor (deferred): with issues on both `trusted_proxies.0` and `.1`, only the first message
  shows (`.find`). The dialog lists both, so nothing is hidden. Final review to triage.
Task 16: fix round 1 dispatched (resume implementer a448cbbbc6dd975b9), FIX_BASE 68d0085
Task 16: controller verification of fix round 1 — the dot-bounded rule is now a single shared helper
  (ConfigSection.tsx:30) used by both the field-level match and the tab marker, so it cannot drift;
  the tab marker carries an aria-label including the issue count (line 115), so it is not colour-only.
  Frontend 119 passed, 0 failed, build clean.
Task 16: minor (deferred, for the final review's fix wave): that aria-label hardcodes English
  "issue"/"issues" while this console is bilingual de/en — and localizing such strings is an
  established pattern here (the branch already has a commit "Localize nav landmark and theme-toggle
  labels"). Two i18n keys in both dictionaries would close it; `i18n.test.ts` enforces key parity so
  it cannot be half-done. Not worth its own round for screen-reader-only text, but it is inconsistent
  with the codebase's own convention and should be bundled.
Task 16: dispatched scoped re-review (haiku), FIX_BASE 68d0085 HEAD 40aa8ae
Task 16: fix round 1/5 (2 addressed, 0 open; commits 68d0085..40aa8ae)
Task 16: re-review clean on every failure mode I asked about — no double-counting (each issue is
  filtered once per tab); NO cross-tab prefix collision, verified by enumerating all 20 SERVICE_TABS
  keys across general/tb/tls/proxy and confirming none is a dotted prefix of another, with the count
  additionally scoped to that tab's own fields; the marker DOES appear on the selected tab too (an
  operator fixing one of two issues on a tab still sees the other); issues addressed to fields no
  phase-2 form renders are omitted from tab markers but still listed in the dialog; and the tests
  would FAIL if the marker were rendered unconditionally (one asserts an exact aria-label with no
  issue text).
Task 16: complete (commits 237cefd..40aa8ae, review clean, 119 frontend tests)
Task 17: dispatched (sonnet — two components, 14 tests, and it consumes four post-brief API changes),
  BASE 40aa8ae

Task 17: three disclosed concerns, all handled honestly. Controller verification:
Ruling 48 (Task 17 — correction (1) works but is UNTESTED): the implementer flagged that no written
  test exercises the apply-422-with-issues shape, which is precisely the correction I required. I
  probed it (throwaway, deleted) and it WORKS: a 422 carrying
  {message, issues:[logging.file.file_name, port]} renders the summary message AND both field paths
  AND both reasons; and a 400 with a plain string detail still shows that string. So the code is
  right and only the test is missing. Fix round adds the test — an untested rendering path is one
  refactor away from silently reverting to "not valid" with no field named, which is the exact
  regression three tasks of plumbing exist to prevent.
Ruling 49 (Task 17 — the implementer found and fixed a real bug in MY dialog code): showing the full
  path in both the "writes to" summary line and the diff's ---/+++ headers made `findByText(path)`
  ambiguous and failed the "names the file it would write" test. It fixed it by showing the basename
  in the summary with the full path on a `title` attribute, keeping the diff body faithful. Correct,
  and the same defect class as Ruling 5 — my plan repeatedly wrote assertions that match in two
  places. Accepted as-is.
Ruling 50 (Task 17, bundled — `backupKept` is a dead i18n key): USE it rather than remove it. The
  dialog auto-closes on a clean apply, so there is no surface for it today; but it stays OPEN when
  `reload_detail` is present, and that is exactly the moment an operator wants to know a backup
  exists. Show "Previous contents kept as <path>" from `ApplyResponse.backup` in that state.
  `restartNeeded`/`restartWhich` are NOT dead — Task 18's RestartBanner consumes them.
Task 17: fix round 1 dispatched (resume implementer ac1ba6b10b61d49a5), FIX_BASE 6d99bb6
Task 17: fix round 1 done — 137 frontend tests, 0 failed, build clean; 4 new tests cover the
  structured 422 issues, a plain-string detail, an object detail with no issues array, and the
  backup + reload_detail success state.
Task 17: dispatched scoped re-review (haiku), FIX_BASE 6d99bb6 HEAD 00c0a1d
Task 17: fix round 2 done — 140 frontend tests, 0 failed, build clean; 3 new tests cover a null
  entry, an entry with no message, and an all-malformed issues array falling back to the summary.
  The `issuesOf` guard now validates entries, not just the container.
Task 17: re-review of round 1 confirmed test (a) is a REAL guard (it asserts the <li> contents, so it
  fails if the issue rendering is deleted) while (b) and (c) guard different branches and would pass
  without it — accepted deliberately, not churned. Backup line renders only when reload_detail is
  present AND backup is non-null, never on a clean apply. No collateral: preview-on-open, discardAll,
  the scoped restart assertion and i18n parity all untouched.
Task 17: complete (commits 40aa8ae..d9ae92c, review clean, 140 frontend tests)
Task 18: dispatched (haiku — small presentational component, 3 tests), BASE d9ae92c
Task 18: review Approved, no findings. Confirmed role="status" is the right live region (the banner
  is a consequence of the operator's own Apply, not a background event, so polite beats alert); the
  dotted field paths render verbatim in a monospace <code> block joined with ", "; no hardcoded
  English in the component; and the no-button test uses a bare `queryByRole('button')` with NO name
  filter, so it would catch any newly added button or role="button" element — the guard is broad
  enough to survive someone later disagreeing with the no-restart-button decision.
Task 18: complete (commits d9ae92c..8bcf6f9, review clean, 143 frontend tests)
Task 19: dispatched (haiku), BASE 8bcf6f9. Carries Ruling 6 (clipboard test must use
  userEvent.setup(), not a spread navigator) and the fact that PreviewResponse.toml is REDACTED.

Task 19: review returned SPEC ✅ with three findings. I am re-ranking two of them and declining one.
Ruling 51 (Task 19 — stale TOML shown beside an error; reviewer ranked this MEDIUM, I rank it the
  MOST important of the three): FIX. React Query keeps a mutation's last successful `data`, so after a
  failed re-preview the screen renders the error AND the previous TOML together. This screen's entire
  contract is "this is exactly what an apply would write" — showing an older answer next to a failure
  breaks that contract and leaves the operator unable to tell which text is current. Fix: when
  `preview.isError`, show the error and do NOT render the TOML. Losing the stale content is the point;
  an honest gap beats a misleading document. — Cost if wrong: the operator loses the previous render
  while the error stands and must fix the file to see it again.
Ruling 52 (Task 19 — uncleared setTimeout; reviewer ranked CRITICAL, I rank it Minor-but-fix): FIX,
  though the consequence is a console warning and a small leak rather than anything the operator sees.
  Reachable (copy, then navigate away inside the timeout). It is a genuine React anti-pattern and a
  three-line fix, so worth closing rather than deferring.
Ruling 53 (Task 19 — the `?? ''` copy fallback): DECLINED as unreachable dead code. The button only
  renders when `preview.data` is truthy, which the reviewer confirmed, so the fallback cannot fire.
  Removing it is churn; noting it for the final review instead.
Task 19: the good news verified by the review — one preview call on mount, one per DISTINCT serialized
  edit set (the serialization does prevent identity thrashing), no stale-TOML race from out-of-order
  responses, the copy button cannot be clicked with no data, the clipboard test genuinely uses
  `userEvent.setup()` + `readText()` rather than a stubbed navigator, and the TOML is rendered as JSX
  TEXT in a <pre> rather than via dangerouslySetInnerHTML — so operator-controlled file content is not
  an injection path.
Task 19: fix round 1 dispatched (resume implementer a961388f44ffa0a98), FIX_BASE cb72ce5
Task 19: fix round 1 done — 151 frontend tests, 0 failed, build clean; 3 new tests (stale-content
  guard, unmount cleanup via a console.error spy, rapid-click clearTimeout). Error state now withholds
  both the TOML block and the copy button; timer held in a ref, cleared before each new one and on
  unmount.
Task 19: dispatched scoped re-review (haiku), FIX_BASE cb72ce5 HEAD 95fa8b7
Task 19: re-review confirmed RECOVERY works — after an error, a later successful preview clears
  `isError`, repopulates `data`, and the TOML and copy button return; there is no permanent blank
  state, which was the risk my own fix could have introduced. The copy button is REMOVED from the DOM
  on error, not merely disabled. And the unmount test is NOT vacuous — removing the cleanup would let
  the timer fire on a dead component and trip React's warning, which the console.error spy catches.
Task 19: complete (commits 8bcf6f9..95fa8b7, review clean, 151 frontend tests)

Ruling 54 (Task 20 pre-dispatch, PLAN DEFECT — Tasks 15 and 16's issue display has NO DATA SOURCE):
  my Task 20 text renders `<ConfigSection section=... lang=... isAdmin=... />` and never passes
  `issues`. Verified by grepping the plan. So the field-level validation messages, the `aria-invalid`
  linkage, the indexed-path matching I required in Task 16, and the per-tab issue markers are all
  DEAD CODE — nothing feeds them. Three tasks of work would terminate unreached.
  — Ruling: wire it. The issues live in the preview/apply mutation state inside DiffDialog, which sits
  under PendingBanner, so they must be lifted: PendingBanner takes an `onIssues` callback and forwards
  it to DiffDialog; DiffDialog reports the issues from a `valid:false` preview or a 422 apply, and
  reports `[]` on success; App holds them in state and passes them to ConfigSection. Clear them on a
  successful apply and on discard-all, so a stale marker cannot outlive the draft that caused it.
  — Cost if wrong: an extra callback through one component; the alternative is shipping three tasks of
  invisible machinery.
Ruling 55 (Task 20 pre-dispatch, PLAN DEFECT — the removal-loss pattern is written into my own wiring):
  my Task 20 text says `saved={config.data?.disk ?? {}}`, which is EXACTLY the pattern that destroyed
  queued removal edits in Task 13. `DraftProvider` now takes `Record<string, unknown> | undefined` and
  treats undefined as "not loaded yet". Task 20 must pass `config.data?.disk` with NO `?? {}`.
  — Cost if wrong: none; passing the placeholder is what caused the bug.
Task 20: dispatched (sonnet — the integration task, 7 files, and it carries two of my plan defects),
  BASE 95fa8b7
Task 20: controller verification — Ruling 54's fix WORKS end to end. Probe (throwaway, deleted):
  mounted the real App as an admin with a queued bad edit, opened the diff dialog, and the rejected
  preview's issue reached BOTH the dialog AND the form field — `port` carries aria-invalid="true"
  while the dialog is open and still after closing it. So the field-level display, the aria linkage,
  the indexed-path matching and the tab markers built in Tasks 15-16 are now reachable rather than
  dead code.
  Amusing note on my own probe: its first run failed with "Found multiple elements with the text" —
  because the message renders in the dialog AND on the field. The failure was my ambiguous assertion,
  and it accidentally proved the wiring. That is the THIRD time in this plan I have written an
  assertion that matches in two places (see Rulings 5 and 49); it is my most repeated mistake.
Task 20: baseline reconciled — `pytest tests/unit -q` is 54 failed / 813 passed, exactly the number
  tracked all run (up 5 passes from Task 20's new backend tests). The implementer's "72 failed" was a
  different selection; the full `tests/` tree is 94 failed, which includes integration and
  prompt_engineering suites I never baselined. Task 22 must establish those against main rather than
  assume them.
Task 20: implementer found and fixed a REAL production crash my brief would have shipped — calling
  `useConfig`/`useStatus` AFTER App's early returns (exactly as my Step 5 wrote it) throws "Rendered
  more hooks than during the previous render" on an actual login. No existing test catches it because
  they all mock `useSession` and never exercise the null-session -> session transition. It moved both
  hooks above the early returns and added an `enabled` option to the queries so they stay idle before
  login. Verified: App.tsx:32-33 call the hooks with `{ enabled: !!session }` above the `if (loading)`
  and `if (!session)` guards.
Task 20: two more of my test defects it corrected — my banner assertions asserted ENGLISH text while
  App defaults to `lang: 'de'`, and my widened `renderApp` could not represent `session: null` /
  `loading: true`, so it added a `renderWithoutSession` helper for three pre-existing tests. Both
  disclosed.
Task 20: dispatched review (sonnet — the integration task), BASE 95fa8b7 HEAD 82baa6f

Task 20: review returned SPEC ✅ with two findings, BOTH in the issues wiring I designed (Ruling 54).
Ruling 56 (Task 20, Important — the issues state is not cleared on sign-out): FIX. `App` is one
  component instance that now survives the session -> null -> session transition (because deviation 4
  made the hooks unconditional), so `issues` persists in memory across sign-out and sign-in while
  `clearStoredDraft()` clears only the draft. On a shared machine the next operator can be shown a
  stale invalid-field marker with no edit behind it. This is the SAME defect class as Ruling 40, which
  I fixed for the draft — and I then introduced the analogous gap in my own new state. — Cost if
  wrong: an operator who signs out and back in loses a marker they would have had to re-preview to
  refresh anyway.
Ruling 57 (Task 20, Minor by label but the most consequential gap left — the wiring has NO TEST):
  FIX. A grep for `onIssues` across `frontend/src/**/*.test.tsx` returns zero matches, so the one
  integration that makes Tasks 15-16 reachable is verified only by the throwaway probe I ran and
  deleted. CI would not notice if it broke. This is precisely the "untested path is one refactor from
  reverting" argument I used in Task 17, and it applies harder here because the failure mode is
  silent: every component test still passes while the operator sees nothing.
Task 20: STALE ISSUES analysis accepted — (a) fixing a field without re-previewing leaves the marker
  until the next preview/apply/discard, which follows from the deliberate preview-on-open design and
  is acceptable; (b) route changes do NOT stale it, since the state lives in App.
Task 20: REMOVAL-LOSS CANNOT RECUR through this path — verified reasoning: `useConfig({ enabled:
  !!session })` stays disabled until login, so on the first render after login `config.data` is
  `undefined` rather than `{}`, and `prune` skips entirely. No window exists where a session is set
  and `disk` is prematurely `{}`.
Task 20: STATUS ROUTE I/O acceptable — reads a small file per 15s poll; an invalid file yields `[]`
  via `validate_config_dict` returning `(None, issues)` rather than raising; an absent file yields
  `{}` upstream.
Task 20: noted for the final review (not a Task 20 defect): `Raw.tsx` has no `isAdmin` gate of its
  own. The nav entry IS admin-gated and the backend's `require_admin` refuses the preview call, so a
  non-admin who types /admin/raw gets an error alert rather than data — safe, but an ugly surface.
Task 20: fix round 1 dispatched (resume implementer a790e3e0a04cae915), FIX_BASE 82baa6f
Task 20: fix round 1/5 (2 addressed, 0 open; commits 82baa6f..c60d086)
Task 20: re-review confirmed the clear sits in a `useEffect` keyed on `[session]` (not the render
  body, so no setState-during-render), all four new tests are REAL guards at the App seam — each would
  fail if `onIssues`, the `issues` prop, or the clear were removed — localStorage is cleared and the
  QueryClient is fresh per test, and the 9 pre-existing App tests are untouched.
Task 20: complete (commits 95fa8b7..c60d086, review clean, 161 frontend tests)
=== FEATURE IS NOW REACHABLE END TO END. Tasks 1-20 done. Remaining: 21 docs, 22 verification. ===
Task 21: dispatched (haiku — documentation), BASE c60d086. Carries the deltas between what the plan
  said and what was actually built.
Task 21: controller verification — the blanket "this release is read-only" notice is gone; the two
  remaining "read-only" mentions are both CORRECT and specific (agents/prompts really are still
  read-only until phases 3-4, and the Raw screen really is read-only). The roles table now states the
  real distinction. All five corrections landed: admin_ui.enabled in the restart table WITH the note
  that its sibling require_loopback is hot-swappable; a Logging validation subsection; the REDACTED
  display-only note on the Raw screen; the degraded-apply section; and a CHANGELOG `### Fixed` entry
  for the phase-1 hyphenated-credential redaction hole. The implementer verified each claim against
  the code and cited line numbers for six of them.
Task 21: dispatched review (haiku — documentation accuracy), BASE c60d086 HEAD 3db2441
Task 21: review Approved with NO findings — it checked all ten factual claims against the actual code
  (restart table matches RESTART_FIELDS exactly; require_loopback confirmed hot-swappable; log-path
  validation rejects and accepts the stated cases; the credential pattern list matches the matcher
  including separator variants; redaction is display-only with the real values written via
  proposed_text; reload_detail carries the degraded reason; .bak is single-undo; non-admin enforcement
  is server-side) and confirmed both internal links resolve.
Task 21: complete (commits c60d086..3db2441, review clean)
Task 22: dispatched (sonnet — mechanical verification with judgment on what counts as a regression),
  BASE 3db2441. Step 5 (manual browser smoke test) CANNOT be done by an agent — it needs the user at a
  browser signing into a real TestBench as admin and then as non-admin. Flagged to the user at plan
  time and again at handover.
Task 22: complete — verification clean on everything an agent can check.
  BACKEND: tests/unit branch 54F/813P vs main 55F/502P; whole tree branch 94F/846P vs main 95F/535P.
    The branch's failure SET is a strict SUBSET of main's — one test that fails on main passes here.
    Zero regressions; the branch is one test better than main on both suites.
  FRONTEND: 161 passed / 0 failed, 17 files. npm run build clean.
  LINT/TYPES: ruff 8, ruff-format 4, mypy 5 — every offending file checked against the 123 changed
    files and NONE appears; all pre-existing.
  SECURITY: (1) all four mutating routes carry require_admin + require_csrf, with only the two
    legitimate session exceptions; (2) REDACTED_SENTINEL appears only in config_io (both the JSON and
    rendered-TOML paths, sharing one matcher) and edits.py (refusing it), 26 redaction tests pass;
    (3) apply writes `proposed_text` RAW, never the redacted preview.toml — confirmed by code, comment
    and a dedicated test.
  BINARY: build_binary.py succeeds, the exe runs, console assets bundled, tomlkit already in
    hiddenimports.
  SIZE: 84 commits, 123 files, +26611/-36.
  NOT DONE: step 5, the manual browser smoke test — requires the user at a real TestBench.
FINAL WHOLE-BRANCH REVIEW dispatched (opus — most capable, per the skill), MERGE_BASE f41d1ba.

FINAL WHOLE-BRANCH REVIEW: mergeable after fixes. Found 3 seam defects, 11 new findings, and triaged
all 11 deferred items as ACCEPT (each with independent reasoning, not deference).
Ruling 58 (FINAL, HIGH — CONFIRMED infinite render loop, and it is MY Ruling-54 wiring): the review
  claimed `applyIssues` is a fresh array each render, is a useEffect dependency, and its body calls
  `onIssues` -> `App.setIssues` -> re-render -> new array -> effect again. I PROVED it: driving a real
  App through a structured 422 apply produces "Maximum update depth exceeded" (55 console.error calls).
  So the console pins itself precisely when an apply is REJECTED — the moment the operator most needs
  the field-level reasons. Untested until now because DiffDialog's own 422 tests render without
  `onIssues`, and App's tests only ever return a 200 apply. My own earlier probe covered the PREVIEW
  path, which is safe only because react-query's `data` identity is stable. FIX BEFORE MERGE.
Ruling 59 (FINAL, MEDIUM — stale markers survive a valid re-preview): FIX. Markers are set when a
  preview is invalid but never cleared when a later preview is valid, so an operator who fixes the
  field and reopens the dialog still sees red until discard/apply/sign-out, and learns to distrust the
  marker. One-line `else onIssues([])`.
Ruling 60 (FINAL, MEDIUM — the write is gated on a REDACTED diff; my Ruling-30 bug): FIX. `routes.py`
  decides whether to write from `preview.diffs`, which is computed from REDACTED text, while the write
  itself uses RAW text. An overlay changing only a credential-named key redacts to an identical
  before/after, so it yields no diff and returns `200 written: []` — the change is SILENTLY DISCARDED.
  Converse: in a mixed overlay the credential IS written but never appeared in the diff the operator
  approved. Not reachable from the forms (no credential field) but reachable from the API. The
  write/no-write decision must be made on RAW texts; only the DISPLAYED diff is redacted.
Ruling 61 (FINAL, LOW but one line, and I already made this exact call elsewhere): `hot_reload`'s
  `except Exception` lets `asyncio.CancelledError` escape after the config swap, leaving new config +
  old partly-closed factory — the one state its own docstring forbids. I required
  `(Exception, SystemExit)` in validate.py for the same reason; apply the same care here.
Ruling 62 (FINAL, LOW): `config_io.read_config_file` does `dict(document.get(CONFIG_PREFIX, {}))`,
  which raises TypeError -> 500 for a non-table prefix, making `service_table`'s carefully documented
  400 unreachable from every route. A maintainer reading that 400 will believe it is live.
Ruling 63 (FINAL, NIT bundled): two comments still describe this branch as future work — routes.py
  "Phase 1 is read-only for everyone signed in" and config_io.py "Phase 1 only reads ... phase 2 will".
DEFERRED with reasoning (NOT fixed in this wave):
  - CRLF -> LF rewrite on first save for a CRLF config.toml, and the approved diff being baselined on
    round-tripped text rather than file bytes so normalization is invisible. REAL and Windows-relevant,
    but preserving the original line ending is a design change to document.py + atomic.py, not a
    patch; it is data-preserving (only line endings change) and belongs in its own piece of work.
  - LLM clients rebuilt on every apply even for a log-format edit; blocking `requests.get` in the async
    status route every 15s per tab; `.bak` written with default umask while os.replace resets the
    target's mode; `config_path` falling back to a relative "config.toml". All pre-existing patterns or
    performance matters, none a correctness bug in this branch.
FINAL FIX WAVE dispatched (sonnet), BASE 3db2441.

INCIDENT (investigated, not a shipped defect, but the user must be told): the fix-wave agent reported
  a stray `config.toml.bak` appearing at the repo root during an intermediate test run. The repo root
  holds the user's REAL, UNTRACKED `config.toml` (absolute paths to their prompts/templates, anthropic
  provider), and it shows an mtime of 15:08 today — during this session. A `.bak` can only be created
  by `write_atomic`, which only the apply route calls, so something did apply against it.
  Root cause is real: `main.py:107` falls back to a RELATIVE `Path("config.toml")` when
  `config.loaded_from` is unset, so any app built without an explicit `config_path` resolves it to the
  CWD — the repo root when running tests. This is the LOW finding the final review raised; the
  incident shows it is not merely theoretical.
  I verified the COMMITTED suite is clean: md5 of config.toml before and after `pytest
  tests/unit/webui` (298 passed) is IDENTICAL, and no `.bak` is created. So the stray file came from an
  intermediate, uncommitted state during the agent's own iteration, not from anything being merged.
  I also verified the file is INTACT: valid TOML, 16 keys, loads as an AppConfig, both configured
  directories exist, provider anthropic, 3 agents. It was never git-tracked, so there is no history to
  diff against and I CANNOT prove it is byte-identical to before 15:08 — the `.bak` that would have
  shown this was deleted by the agent.
  NOT FIXING now, deliberately: the committed suite is verified clean, so a conftest guard would defend
  against a hypothetical future test, and I have declined speculative hardening consistently through
  this run. Surfacing it to the user as a recommendation instead, with the root cause named.
FINAL FIX WAVE complete (a62ff19): all 6 fixes, frontend 163 passed / 0 failed, build clean; backend
  tests/unit 54 failed / 816 passed (baseline held), webui 298 passed; ruff/mypy clean on touched files.
Scoped re-review of the fix wave dispatched (sonnet), FIX_BASE 3db2441 HEAD a62ff19.
Scoped re-review of the fix wave: ALL SIX ADDRESSED, no new breakage, MERGE VERDICT ready. Its effect
  audit enumerated all three effects in DiffDialog with their deps and confirmed stability, and noted
  there is no React.memo anywhere in the App->PendingBanner->DiffDialog chain, so the dependency
  stability is doing real work rather than being masked. Fix 3 verified on all three cases
  (credential-only writes, empty stays empty, displayed diff still redacted). Fix 5 strictly improves
  every caller (the shape previously 500'd everywhere). All five new tests would fail if reverted.
Controller verification of the loop fix: re-ran my reproduction against the fixed code — 0
  max-update-depth errors and 0 console.error calls total, down from 1 and 55 — AND the issue still
  reaches the field (aria-invalid true), so stability was not bought by breaking the feature.
FINAL STATE: 85 commits, 123 files, +26807/-36. Backend tests/unit 54 failed / 816 passed (the 54 are
  a pre-existing baseline, and main is worse at 55). Frontend 163 passed / 0 failed across 17 files.
  Working tree clean of tracked modifications.
ALL 22 TASKS COMPLETE. Final review clean. Ready for finishing-a-development-branch.
