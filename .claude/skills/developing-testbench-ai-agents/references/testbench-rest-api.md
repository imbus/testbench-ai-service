# TestBench REST API for agents

Source: `openapi.yml` in this directory (TestBench WebServer 4.2.0.1). This file is an index;
look up request/response schemas in `openapi.yml` (search for the `operationId` or the schema
name, e.g. `grep -n "SpecificationDetailsForUpdate:" references/openapi.yml`).

## Calling the API from an agent

Use the authenticated connection the service passes to `precheck()` and `run()`:

```python
# conn: testbench_cli_reporter.testbench.Connection
# conn.server_url already ends with ".../api/", so append the path WITHOUT "/api/":
url = f"{conn.server_url}2/projects/{project_key}/specifications/{spec_key}"
response = await asyncio.to_thread(conn.session.patch, url, json=body)  # requests is sync
```

- `conn.session` has a response hook that calls `raise_for_status()`: every 4xx/5xx (e.g. a
  `409` because the spec is locked) raises `requests.exceptions.HTTPError`. No extra status
  check is needed, but the exception will end up in your `except` path.

- `conn.session` is a `requests.Session` carrying the user's token, so every call runs **as the
  triggering user**, with their roles and their JWT permissions.
- `requests` is blocking: inside `async` code wrap calls in `asyncio.to_thread(...)`.
- Build request bodies from the Pydantic models in `testbench_ai_service/models/testbench.py`
  (e.g. `SpecificationDetailsForUpdate`) and send `model.model_dump(exclude_unset=True)`, so
  fields you did not set are not overwritten.
- Prefer the existing helpers in `testbench_ai_service/utils/testbench.py` over raw calls
  (`get_test_case_set_nodes`, `get_test_case_set_catalog`, `get_test_case_set_details`,
  `patch_test_structure_element_spec`, `get_tov_details`, `get_project_roles`, ...). Add a new
  helper there when you need a new endpoint.
- **Sync or async?** Almost every helper is a plain (blocking) function; only a few are
  `async def` and already run their request in a thread:

  | Kind | Helpers | Call as |
  |---|---|---|
  | `async def` | `utils.testbench.patch_test_structure_element_spec`; the reviewer/describer write-backs `patch_*_started/result/previous_*` (`agents/*/utils.py`); defect explainer `import_data`, `update_description` | `await helper(...)`. **Never** wrap them in `asyncio.to_thread` (that returns an un-awaited coroutine) |
  | sync, does HTTP | everything else in `utils/testbench.py`: `get_user_key`, `has_any_allowed_role`, `get_project_name`, `get_project_details`, `get_tov_details`, `is_json_based_tov`, `get_test_case_set_details`, `get_test_case_set_nodes`, `get_test_structure_tree`, `post_project_*_structure`, `get_json_report_data`, `get_json_report_reader`, `get_test_case_set_catalog`, `get_project_roles`, `get_own_*` | `await asyncio.to_thread(helper, ...)` in `run()`; in `precheck()` too when it calls several of them |
  | sync, no I/O | `utils/testbench_helpers.py` (`test_case_set_as_str`, …), `utils/html_utils.py`, `render_template`, `get_translation`, defect explainer `build_protocol_json`/`create_import_zip` (writes a local file) | call directly |

  Check with `grep -nE "^(async )?def " testbench_ai_service/utils/testbench.py` when you add or use a helper.
- HTTP errors: let `requests.exceptions.HTTPError` propagate from `precheck()` (the router maps
  it), or call `testbench_ai_service.exceptions.handle_requests_http_error(e)`.
- Every endpoint you call adds its **JWT permission** to the agent's `REQUIRED_PERMISSIONS`.
  Helpers count too: `get_test_case_set_catalog` uses the report endpoints (`ReadTovReport` or
  `ReadCycleReport`, `ReadReportingJobDetails`, `DownloadReportFile`), `get_test_case_set_nodes`
  uses `ReadTestThemeTree`.

## Endpoints the built-in agents use

| Purpose | Call |
|---|---|
| Current user (key) | `GET 2/users/self` |
| Own project roles | `GET 2/users/self/projectRoles` |
| Project / TOV details (name, exchange format) | `GET 2/projects/{projectKey}`, `GET 2/projects/{projectKey}/tovs/{tovKey}` |
| Test structure tree (scope, locks, spec keys) | `POST 2/projects/{projectKey}/tovs/{tovKey}/structure` or `.../cycles/{cycleKey}/structure` |
| Full test case set data (steps, parameters, results) | report job: `POST .../tovs/{tovKey}/report` or `.../cycles/{cycleKey}/report` → poll `GET .../report/job/{jobId}` → `GET .../report/{fileName}` (done by `get_test_case_set_catalog`) |
| Current spec of one test case set (spec key, description, review comment) | `GET 2/projects/{projectKey}/testCaseSets/{testCaseSetKey}` |
| Write description / review comment / reviewer / locker | `PATCH 2/projects/{projectKey}/specifications/{specificationKey}` (`ModifySpecifications`; setting `locker`/`reviewer` also needs `ModifySpecManagementInfo`, which the built-in spec agents require) |
| Write execution comments / results | upload zip + `POST 2/projects/{projectKey}/cycles/{cycleKey}/import` (Defect Explainer uses `testbench_cli_reporter`'s `ImportJSONExecutionResults`, which does not poll the import job; see `testbench-json-report.md`) |

## Rich-text fields

- `RichTextInfo` (PATCH spec `description`, `reviewComment`): `{"html": "...", "images": []}`.
  `images` is **required** — send `[]` when there are none.
- `RichTextForImport` (execution import `comments` etc.): `{"html": "...", "plain": "..."}`.
- The HTML must be a full `<html><body>…</body></html>` document and follow the
  `testbench-rich-text-html` skill.

## Endpoint index

Paths are relative to `conn.server_url`. "Allowed callers" is the role rule from the endpoint
description; "JWT permission" is what the token must contain.

### Login

| Method | Path (after `/api/`) | operationId | JWT permission | Allowed callers | Summary |
|---|---|---|---|---|---|
| POST | `2/login/session` | `postLoginSession` | - | Every TestBench user | Logs on a TestBench user. |
| GET | `2/login/session` | `getLoginSession` | - | Every TestBench user | Reads the login data of the user. |
| DELETE | `2/login/session` | `deleteLoginSession` | - | Every TestBench user | Logs out a TestBench user from the system. |
| GET | `2/login/session/activeUsers` | `getActiveUsers` | ReadUserSessions | Every TestBench user | Reads the active login sessions. |
| DELETE | `2/login/session/activeUsers` | `logoutActiveUser` | DeleteUserSession | Only application admin | Logs out another TestBench user from the system. |
| PUT | `2/login/password` | `putOwnPassword` | - |  | Changes the own password. |

### JSON Web Token

| Method | Path (after `/api/`) | operationId | JWT permission | Allowed callers | Summary |
|---|---|---|---|---|---|
| POST | `2/jwt/token` | `generateJWT` | - |  | Generate JWT access token |
| POST | `2/jwt/invalidate` | `invalidateJWT` | AdministerServer |  | Invalidate all JWT access tokens |

### Cycles

| Method | Path (after `/api/`) | operationId | JWT permission | Allowed callers | Summary |
|---|---|---|---|---|---|
| GET | `2/projects/{projectKey}/cycles/{cycleKey}` | `getCycleDetails` | ReadProjectDetails | Only application admin, project admin or user with project roles | Returns the test cycle with the given key. |
| PATCH | `2/projects/{projectKey}/cycles/{cycleKey}` | `updateCycleDetails` | ModifyProjectDetails | Only application admin, project admin or manager | Returns the updated test cycle. |

### Defects

| Method | Path (after `/api/`) | operationId | JWT permission | Allowed callers | Summary |
|---|---|---|---|---|---|
| POST | `2/projects/{projectKey}/cycles/{cycleKey}/defects` | `getAssignedDefects` | ReadProjectDefectsAndTheirAssignments | Only application admin, project admin or user with project roles | Returns the assigned defect of the test cycle structure. |

### Import

| Method | Path (after `/api/`) | operationId | JWT permission | Allowed callers | Summary |
|---|---|---|---|---|---|
| POST | `2/projects/{projectKey}/executionResults` | `uploadExecutionResults` | ImportExecutionResults | Only application admin, manager or tester | Uploads a zip archive containing the json based execution results. |
| POST | `2/projects/{projectKey}/cycles/{cycleKey}/simulate-import` | `simulateExecutionResults` | - | Only application admin, manager or tester | Simulates the json based execution results in the given zip archive. |
| POST | `2/projects/{projectKey}/cycles/{cycleKey}/import` | `importExecutionResults` | ImportExecutionResults | Only application admin, manager or tester | Imports the json based execution results in the given zip archive. |
| GET | `2/projects/{projectKey}/import/job/{jobId}` | `getImportingJob` | ReadExecutionImportingJobDetails | Only the owner of the job | Returns the details of the given background importing job. |

### Keywords

| Method | Path (after `/api/`) | operationId | JWT permission | Allowed callers | Summary |
|---|---|---|---|---|---|
| GET | `2/projects/{projectKey}/keywords/{keywordKey}` | `getKeywordDetails` | ReadTestElements | Only application admin or user with project roles | Returns the details of the given keyword of the given project. |
| PATCH | `2/projects/{projectKey}/keywords/{keywordKey}` | `updateKeywordDetails` | ModifyTestElements | Only application admin or manager or designer | Updates the details of the given keyword of the given project. |
| POST | `2/projects/{projectKey}/tovs/{tovKey}/keywords` | `createKeyword` | ModifyTestElements | Only application admin or manager or designer | Creates a new keyword and returns the created keyword. |

### Labels

| Method | Path (after `/api/`) | operationId | JWT permission | Allowed callers | Summary |
|---|---|---|---|---|---|
| GET | `2/projects/{projectKey}/labels/{labelKey}` | `getTestLabel` | ReadTestLabels | Only application admin or user with project roles | Returns the details of the given test label of the given project. |
| DELETE | `2/projects/{projectKey}/labels/{labelKey}` | `deleteTestLabel` | ModifyTestLabels | Only application administrator or user with writing project roles | Deletes the given test label. |
| PATCH | `2/projects/{projectKey}/labels/{labelKey}` | `updateTestLabel` | ModifyTestLabels | Only application admin or user with writing project roles | Updates the data of a test label and returns the updated test label. |
| GET | `2/projects/{projectKey}/labels` | `getTestLabels` | ReadTestLabels | Only application admin or user with project roles | Returns the test labels of the given project. |
| POST | `2/projects/{projectKey}/labels` | `createTestLabel` | ModifyTestLabels | Only application admin or user with writing project roles | Creates a new test label and returns the created test label. |

### Metrics

| Method | Path (after `/api/`) | operationId | JWT permission | Allowed callers | Summary |
|---|---|---|---|---|---|
| POST | `2/projects/{projectKey}/tovs/{tovKey}/metrics/specification` | `getSpecificationStatusDistribution` | ReadTestThemeStatusDistribution | Only application admin or user with project roles | Returns the specification status distribution. |
| POST | `2/projects/{projectKey}/tovs/{tovKey}/metrics/automation` | `getAutomationStatusDistribution` | ReadTestThemeStatusDistribution | Only application admin or user with project roles | Returns the automation status distribution. |
| POST | `2/projects/{projectKey}/cycles/{cycleKey}/metrics/execution` | `getExecutionStatusDistribution` | ReadTestThemeStatusDistribution | Only application admin or user with project roles | Returns the execution status distribution. |
| POST | `2/projects/{projectKey}/cycles/{cycleKey}/metrics/specification` | `getCycleSpecificationStatusDistribution` | ReadTestThemeStatusDistribution | Only application admin or user with project roles | Returns the specification status distribution. |
| GET | `2/projects/{projectKey}/metrics/defectDistributions` | `getDefectDistributions` | ReadDefectsMetricDistribution | All roles, except project admins | Returns the defects metrics distribution of a project. |

### Projects

| Method | Path (after `/api/`) | operationId | JWT permission | Allowed callers | Summary |
|---|---|---|---|---|---|
| GET | `2/projects` | `getProjectsList` | ReadOwnProjectsList, ReadCompleteProjectsList | Any TestBench user | Returns the list of projects and their summaries. |
| GET | `2/projects/{projectKey}` | `getProjectDetails` | ReadProjectDetails | Only application admin, project admin or user with project roles | Returns the details of the given project. |
| PATCH | `2/projects/{projectKey}` | `patchProjectDetails` | ModifyProjectDetails | Only application admin, project admin or manager | Updates the project and returns the updated object. |
| GET | `2/projects/{projectKey}/members` | `getProjectMembers` | ReadProjectMembers | Only application admin, project admin or user with project roles | Returns the members of the given project. |
| PATCH | `2/projects/{projectKey}/members` | `updateProjectMembers` | ModifyUserRolesInProject | Only application admin, project admin or test manager in the given project | Updates the project roles of the given users in the given project in a single call. |
| GET | `2/projects/{projectKey}/members/{userKey}` | `getProjectMember` | ReadProjectMembers | Only application admin, project admin or a user with project roles | Returns a single member of the given project. |
| GET | `2/projects/{projectKey}/tovs` | `getProjectTOVs` | ReadProjectHierarchy | Only application admin, project admin or user with project roles | Returns the test object versions of the given project. |
| GET | `2/projects/{projectKey}/export` | `exportProject` | ReadProjectExportOverRMI | Only application admin or user with project roles | Export the project with the given key. |

### Project Tree

| Method | Path (after `/api/`) | operationId | JWT permission | Allowed callers | Summary |
|---|---|---|---|---|---|
| GET | `2/projects/{projectKey}/tree` | `getProjectTree` | ReadProjectHierarchy | Only application admin, project admin or user with project roles | Returns the project tree of the given project. |

### Project UDF

| Method | Path (after `/api/`) | operationId | JWT permission | Allowed callers | Summary |
|---|---|---|---|---|---|
| POST | `2/projects/{projectKey}/udfs` | `postUDFToProject` | ModifyProjectUDFs | Only application admin, project admin or manager | Creates new user defined field. |
| GET | `2/projects/{projectKey}/udfs` | `getUDFsList` | ReadProjectUDFs | Only application admin, project admin or user with project roles | Returns the list of user defined fields of the given project. |
| GET | `2/projects/{projectKey}/udfs/{udfKey}` | `getUDFForUser` | ReadProjectUDFs | Only application admin, project admin or user with project roles | Returns the user defined field. |
| DELETE | `2/projects/{projectKey}/udfs/{udfKey}` | `deleteUDF` | ModifyProjectUDFs | Only application admin, project admin or manager | Deletes a user defined field. |
| PATCH | `2/projects/{projectKey}/udfs/{udfKey}` | `updateUDF` | ModifyProjectUDFs | Only application admin, project admin or manager | Updates a user defined field. |
| PATCH | `2/projects/{projectKey}/udfs/ordering` | `moveUDFS` | ModifyProjectUDFs | Only application admin, project admin or manager | Moves a user defined field. |
| PATCH | `2/projects/{projectKey}/udfs/restriction` | `updateUDFRestriction` | RestrictProjectUDFs | Only application admin or project admin | Updates the restriction of user defined fields. |

### Report

| Method | Path (after `/api/`) | operationId | JWT permission | Allowed callers | Summary |
|---|---|---|---|---|---|
| POST | `2/projects/{projectKey}/tovs/{tovKey}/report` | `postTovReport` | ReadTovReport | Only application admin or user with project roles | Package the tov elements structure to zip archive. |
| POST | `2/projects/{projectKey}/specifications/{specificationKey}/report` | `reportSpecification` | ReadTovReport | Only application admin or user with project roles | Package the specification report into a zip archive. |
| POST | `2/projects/{projectKey}/cycles/{cycleKey}/report` | `postCycleReport` | ReadCycleReport | Only application admin or user with project roles | Package the test instructions to zip archive. |
| POST | `2/projects/{projectKey}/executions/{executionKey}/report` | `reportExecution` | ReadCycleReport | Only application admin or user with project roles | Package the execution report into a zip archive. |
| POST | `2/projects/{projectKey}/tovs/{tovKey}/csvReport` | `fromTOV` | ReadTovReportOverRMI | Only application admin or user with project roles | Export the test object version CSV report with the given key. |
| POST | `2/projects/{projectKey}/cycles/{cycleKey}/csvReport` | `fromCycle` | ReadCycleReportOverRMI | Only application admin or user with project roles | Export the cycle CSV report with the given key. |
| GET | `2/projects/{projectKey}/report/{fileName}` | `getFile` | DownloadReportFile | Only the owner of the file | Downloads the report archive. |
| GET | `2/projects/{projectKey}/report/job/{jobId}` | `getReportingJob` | ReadReportingJobDetails | Only the owner of the job | Returns the details of the given background reporting job. |

### Requirements

| Method | Path (after `/api/`) | operationId | JWT permission | Allowed callers | Summary |
|---|---|---|---|---|---|
| POST | `2/projects/{projectKey}/tovs/{tovKey}/requirements` | `getObjectVersionRequirements` | ReadTovRequirements | Only application admin, project admin or user with project roles | Returns the assigned requirements of the structure of the given test object version. |
| POST | `2/projects/{projectKey}/cycles/{cycleKey}/requirements` | `getCycleRequirements` | ReadCycleRequirements | Only application admin, project admin or user with project roles | Returns the assigned requirements of the structure of the given test cycle. |

### Server Info

| Method | Path (after `/api/`) | operationId | JWT permission | Allowed callers | Summary |
|---|---|---|---|---|---|
| GET | `2/serverLocations` | `getServerLocations` | - | Every TestBench user | Returns the locations of the other installed servers. |
| GET | `serverVersion` | `getServerVersion` | - | Every TestBench user | Returns the current release version of the TestBench web server. |
| GET | `2/serverVersions` | `getServerVersions` | - | Every TestBench user | Returns the current versions of the TestBench web server. |

### Structure

| Method | Path (after `/api/`) | operationId | JWT permission | Allowed callers | Summary |
|---|---|---|---|---|---|
| POST | `2/projects/{projectKey}/tovs/{tovKey}/structure` | `getTovStructure` | ReadTestThemeTree | Only application admin, project admin or user with project roles | Returns the test structure of the given test object version. |
| POST | `2/projects/{projectKey}/cycles/{cycleKey}/structure` | `getCycleStructure` | ReadTestThemeTree | Only application admin, or user with project roles | Returns the test structure of the given test cycle. |

### Subdivisions

| Method | Path (after `/api/`) | operationId | JWT permission | Allowed callers | Summary |
|---|---|---|---|---|---|
| GET | `2/projects/{projectKey}/subdivisions/{subdivisionKey}` | `getSubdivisionDetails` | ReadTestElements | Only application admin or user with project roles | Returns the details of the given subdivision of the given project. |
| PATCH | `2/projects/{projectKey}/subdivisions/{subdivisionKey}` | `updateSubdivisionDetails` | ModifyTestElements | Only application admin or manager or designer | Updates the details of the given subdivision of the given project. |
| DELETE | `2/projects/{projectKey}/subdivisions/{subdivisionKey}` | `deleteSubdivision` | ModifyTestElements | Only application administrator or user with writing project roles | Deletes the given subdivision. |
| POST | `2/projects/{projectKey}/tovs/{tovKey}/subdivisions` | `createSubdivision` | ModifyTestElements | Only application admin or manager or designer | Creates a new subdivision and returns the created subdivision. |

### TOVs

| Method | Path (after `/api/`) | operationId | JWT permission | Allowed callers | Summary |
|---|---|---|---|---|---|
| GET | `2/projects/{projectKey}/tovs/{tovKey}` | `getTOVDetails` | ReadProjectDetails | Only application admin, project admin or user with project roles | Returns the test object version with the given key. |
| PATCH | `2/projects/{projectKey}/tovs/{tovKey}` | `updateTOVDetails` | ModifyProjectDetails | Only application admin, project admin or manager | Returns the updated test object version. |
| GET | `2/projects/{projectKey}/tovs/{tovKey}/cycles` | `getTOVCycles` | ReadProjectHierarchy | Only application admin, project admin or user with project roles | Returns the test cycles the given test object version. |

### Test Structure Elements

| Method | Path (after `/api/`) | operationId | JWT permission | Allowed callers | Summary |
|---|---|---|---|---|---|
| PATCH | `2/projects/{projectKey}/specifications/{specificationKey}` | `updateSpecificationDetails` | ModifySpecifications | Only application admin or user with writing project roles | Updates the details of the given specification of the given project. |
| GET | `2/projects/{projectKey}/testCaseSets/{testCaseSetKey}` | `getTestCaseSetDetails` | ReadTestCaseSetDetails | Only application admin or user with project roles | Returns the details of the given test case set. |
| GET | `2/projects/{projectKey}/testThemes/{testThemeKey}` | `getTestThemeDetails` | ReadTestThemeDetails | Only application admin or user with project roles | Returns the details of the given test theme. |
| GET | `2/projects/{projectKey}/testCaseSets/{testCaseSetKey}/testCases/{testCaseSpecificationKey}` | `getTestCaseDetails` | ReadTestCaseDetails | Only application admin or user with project roles | Returns the details of the given test case. |

### Users

| Method | Path (after `/api/`) | operationId | JWT permission | Allowed callers | Summary |
|---|---|---|---|---|---|
| GET | `2/users` | `getUsers` | ReadActiveUsersList, ReadCompleteUsersList | Every Testbench user | Returns the list of all users. |
| POST | `2/users` | `postUserAccount` | ModifyUserData | Only application admin | Creates a new user account and returns the created user. |
| PUT | `2/users/sync` | `syncUsers` | SynchronizeUsers | Only application admin | Synchronizes the users from LDAP. |
| GET | `2/users/{userKey}` | `getUserDetails` | ReadUserDetails | Only application admin | Returns the data of the given user. |
| PATCH | `2/users/{userKey}` | `patchUserData` | ModifyUserData | Only application admin | Updates the data of a user and returns the updated user. |
| DELETE | `2/users/{userKey}` | `deleteUser` | DeleteUserAccount | Only application admin | Deletes user account of the given user. |
| GET | `2/users/{userKey}/globalRoles` | `getUserGlobalRoles` | ReadUserDetails | Only application admin or project admin | Returns the global roles of the given user. |
| PUT | `2/users/{userKey}/globalRoles` | `updateUserGlobalRole` | ModifyUserData | Only application admin | Updates the global roles of the given user. |
| GET | `2/users/{userKey}/projectRoles` | `getUserProjectRoles` | ReadUserMemberships | Only application admin or project admin | Returns the project roles of the given user. |
| PUT | `2/users/{userKey}/password` | `putPasswordForAUser` | ModifyUserData | Only application admin | Changes the password of the given user. |
| GET | `2/users/self` | `getOwnUserDetails` | ReadOwnUserDetails | Any user | Returns the own user data. |
| GET | `2/users/self/globalRoles` | `getOwnGlobalRoles` | ReadOwnUserDetails | Any TestBench user | Returns the own global roles. |
| GET | `2/users/self/projectRoles` | `getOwnProjectRoles` | ReadOwnUserDetails | Any TestBench user | Returns the own project roles. |
