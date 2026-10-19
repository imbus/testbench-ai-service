# TestBench domain model (for agent developers)

imbus **TestBench** is a test management tool. Users design tests (specification) and run
them (execution) in a desktop client (Java Swing) or web client. TestBench exposes a REST API
(`/api/2/...`, see `testbench-rest-api.md`) which the AI Service uses to read data and write
results back.

## Hierarchy

```
Project (projectKey)
└── Test Object Version, TOV (tovKey)       = a version of the system under test
    ├── Test structure tree (TESTTHEMES)    = what is specified
    │   ROOT
    │   └── Test theme (TESTTHEME)          folder-like grouping, can nest
    │       └── Test case set (TESTCASESET) one test design: steps (keyword calls) + parameters
    │           └── Test cases              one row of parameter combinations each
    ├── Test elements tree (TESTELEMENTS)   reusable building blocks
    │   SUBDIVISION, INTERACTION (keyword), DATATYPE, CONDITION
    ├── Requirements (REQUIREMENTS)         assigned from a requirement tool
    └── Test cycle (cycleKey)               one execution run of the TOV's tests
        └── same structure tree, with execution data: verdicts, protocols, comments, defects
```

`element_type` / `tree_type` in a trigger request use exactly these enum names
(`models.agent.ElementType`, `TreeType`). `DEFECTMANAGEMENT` is the defects tree.

## Specification vs. execution

|                | Specification (in the TOV)                                                                                 | Execution (in a cycle)                                                                                   |
| -------------- | ---------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| What           | Test design: description, review comment, responsible, reviewer, locker, priority, due date, status        | Test results: status, verdict (`Pass`/`Fail`/`ToVerify`/`Undefined`), comments/protocol, defects |
| Key            | `specificationKey` (`node.spec.key`, `TestCaseSetDetails.spec.key`)                                  | `executionKey`, `testCaseExecutionKey`                                                               |
| How to write   | `PATCH 2/projects/{projectKey}/specifications/{specificationKey}` with `SpecificationDetailsForUpdate` | No PATCH. Import a zip with `protocol.json` (`testbench-json-report.md`)                     |
| Built-in agent | Reviewer (`reviewComment`), Describer (`description`)                                                  | Defect Explainer (execution comment)                                                                     |

Spec status values: `NotPlanned`, `Planned`, `InProgress`, `InReview`, `Released`.

## Identifiers

- **Keys** (`projectKey`, `tovKey`, `cycleKey`, `specificationKey`, `testCaseSetKey`, …) are
  numeric database ids (int64 in the API, strings in the service). Use them in URLs.
- **UID** (`uniqueID`, `root_uid`) is the stable, human-visible id of a structure element
  (e.g. a test case set UID). The precheck returns UIDs as item ids; the report catalog is
  keyed by UID.
- A UID is not a key. To PATCH a spec you need the spec key, which you get from the structure
  node or `GET 2/projects/{projectKey}/testCaseSets/{testCaseSetKey}`.

## Locking

A specification can be **locked** by one user (`spec.locker`). Writing to a spec locked by
someone else fails with `409`. Agents therefore:

1. skip items locked by another user in `precheck()` (add a warning, don't fail the whole run);
2. set `locker` to the triggering user when they start writing ("started" state);
3. release the lock (`locker = OptionalUser(optional=None)`) in the final write **and** in the
   failure path.

The API also returns `409` when the spec is checked in, or when a designer is neither
responsible nor reviewer, etc. (see the endpoint's 409 list in `openapi.yml`). Exception: a
spec locked by a user who is logged out can still be written by an admin or manager.

## Users, roles, permissions

- **Global roles**: `Administrator`, `ProjectAdministrator`, `ProjectUser`.
- **Project roles**: `TestManager`, `TestDesigner`, `TestProgrammer`, `Tester`, and read-only
  roles. The service's `ProjectRole` (`models/testbench.py`) names them `ReadOnlyDesigner`,
  `ReadOnlyImplementer`, `ReadOnlyTester`, but `openapi.yml` (4.2.0.1) has
  `ReadOnlyTestDesigner`, `ReadOnlyTestProgrammer`: check the enum before relying on these
  names. Agents' `ALLOWED_ROLES` only match project roles. Who may call which endpoint is in
  the "Allowed callers" column of the endpoint index. Writing spec descriptions/review comments
  needs a writing role (manager/designer); testers can only write review comments when they are
  the reviewer.
- **JWT permissions** (`PermissionWithCode`): a JWT is created with an explicit list of
  permissions. Every endpoint names the one it needs (`JWTAuth: [ "ModifySpecifications" ]`).
  An agent's `REQUIRED_PERMISSIONS` must contain the permission of **every** endpoint it calls,
  directly or through a helper. Session tokens skip this check but still need the role.

## Test object version formats

A TOV has an exchange format: `xml`, `json` or `inherited`. The JSON test report (used by
`get_test_case_set_catalog`) and the JSON execution import only work with JSON-based TOVs —
execution-level agents must reject XML TOVs (`utils.testbench.is_json_based_tov`).

## How an agent is started from TestBench

1. The user enables the AI plugin ("Used by me" in report management).
2. They right-click an element → **Export** → the AI plugin (or Plugin Quick Access).
3. They pick a prompt **variant** and fill in **prompt variables** (from the variant's `vars`).
4. TestBench POSTs to the agent endpoint with the user's JWT in `Authorization` and the context:
   `project_key`, `tov_key`, `cycle_key` (if in a cycle), `root_uid`/`root_key`,
   `element_type`, `tree_type`, `filtering` (active UI filters), `language`, `prompt_config`.
5. The precheck result is shown immediately: `202` warnings or the `409` message. Results
   appear in TestBench when the background run writes them.

The dialog itself is described in `prompts-and-plugin.md`.
