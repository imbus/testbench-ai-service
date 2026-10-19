# TestBench JSON report and `protocol.json`

The **JSON report** is a zip that TestBench exports for a TOV or a cycle. It has two uses:

1. **Read**: it is the complete, offline picture of a test structure, including the test
   sequence with keywords and parameter values. `get_test_case_set_catalog` and
   testbench2robotframework read it.
2. **Write back**: the same file format, plus a **`protocol.json`**, is uploaded to import
   execution results and execution comments into a cycle. This is the only write path for
   execution data. There is no PATCH for executions.

Real example: `examples/json-report/` (a cycle report on test theme `iTB-TT-5`) and
`examples/protocol.json` (a matching *result* import built from that report's keys). The example
was exported with `executionMode=execute` after the test case had been planned/assigned in the
cycle, so it is not empty, and its executions show the exporting user as `exec.locker`. The
service's own export (`view`, see below) has the same file structure.

## Creating a report

`POST 2/projects/{p}/cycles/{c}/report` (or `.../tovs/{t}/report`) with export options returns
a job. Poll `GET .../report/job/{jobId}`, then download `GET .../report/{fileName}`.
`utils.testbench.get_json_report_data` does all three steps. Permissions: `ReadCycleReport` or
`ReadTovReport`, `ReadReportingJobDetails`, `DownloadReportFile`.

The options used are echoed in `manifest.json → reportCreation.exportOptions.cycleExport`:

| Option | Meaning |
|---|---|
| `treeRootUID` | export only this subtree (the element the user right-clicked: `root_uid`) |
| `executionMode` | `view` (read everything), `execute` (export what the user can execute now), `simulate` |
| `suppressNotExecutable` | leave out elements that are not executable |
| `suppressFilteredData`, `filters`/`filtering` | apply the TestBench UI filters |
| `suppressEmptyTestThemes` | leave out themes with no test case sets |
| `basedOnExecution` | cycle report based on the execution data |

The service exports with `executionMode=view`, `suppressNotExecutable=False`,
`basedOnExecution=True`, `suppressEmptyTestThemes=True` and `suppressFilteredData=True` with the
user's UI filters (`utils/testbench.py`), so it gets every test case set in scope that the
active filters don't hide. With
`executionMode=execute` and `suppressNotExecutable=true`, a report is **empty** (`root: null`,
summary counts 0, only metadata files) as long as nothing in scope can be executed yet. Example:
a cycle where the test cases are not yet planned or assigned.

## File structure

```
report.zip
├── manifest.json              format version, server version, creator, scope keys, export options, counts
├── project.json               project key/name/status, projectContext {tovName, cycleName, executionMode}, exchangeFormat
├── cycle_structure.json       the test structure tree (TOV report: tov_structure.json)
├── <TT-UID>.json              one per test theme, e.g. iTB-TT-5.json
├── <TCS-UID>.json             one per test case set, e.g. iTB-TC-1.json
├── <TC-UID>.json              one per test case (parameter combination), e.g. iTB-TC-1-PC-3.json
├── image/<id>.png             images referenced from HTML as src="itb:/image/<id>.png"
├── users.json                 users in the project with their project roles
├── udfs.json                  user-defined field definitions (String/Enumeration/Boolean, definedFor)
├── requirements.json          requirements assigned to elements in scope
├── references.json            attached references (files, links)
├── defects.json               defects assigned in scope
├── defect-config.json         allowed defect status/classification/priority values
└── protocol.json              ONLY in import zips (or in a report that already carries results)
```

File names are the elements' **UIDs**. Inside the files, `key` values are the database keys
that the REST API and the import expect.

### `cycle_structure.json` / `tov_structure.json`: what is in scope

`{"root": <node> | null, "nodes": [<node>, ...]}`. `nodes` is flat and depth-first, and
`parentKey` links each node to its parent. The root node also carries `filters`. Nodes have
(a `TestCaseNode` has no `base.key`/`base.path` and no `aut`, and its `spec` holds only `key`):

| Part | Fields | Use |
|---|---|---|
| `elementType` | `TestThemeNode`, `TestCaseSetNode`, `TestCaseNode` | which file to open |
| `base` | `key`, `uniqueID`, `name`, `numbering` (`1.1.1`), `path`, `parentKey`, `matchesFilter` | identity and position |
| `spec` | `key` (specification key, used for the spec PATCH), `locker`, `status` | design state and lock |
| `aut` | `key`, `locker`, `status` | automation state |
| `exec` | `key` (execution key), `status`, `execStatus`, `verdict`, `locker` | execution state and lock (cycle reports only) |

### `<TCS-UID>.json`: test case set (the design)

| Field | Content |
|---|---|
| `key`, `uniqueID`, `name`, `numbering`, `path` | identity; `key` is the `testCaseSetKey` |
| `spec` | `key`, `description` (HTML), `reviewComment` (HTML), `status`, `priority`, `dueDate`, `responsible`, `reviewer`, `udfs`, `tags`, `requirements`, `references`, `preConditions`, `postConditions` |
| `exec` | `key` (the `executionKey` for the protocol), `comments` (HTML execution comment), `udfs`, `tags` |
| `testCases[]` | per parameter combination: `uniqueID`, `index`, `spec.key`, `spec.comments`, `exec.key` (the `testCaseExecutionKey`), `exec.status/execStatus/verdict`, `exec.tester`, `exec.defects`, `exec.comments` |
| `testSequence[]` | the steps as **designed**: keyword calls with `sequenceID`, `parentID`, `numbering`, `spec.name`, `spec.sequencePhase` (`TestStep`, …), `spec.callParameters` (`representativeValue`/`parameterValue`, data types; `value` is `null`). `keywordType` and `exec` are `null` |
| `parameters[]` | the test case set's formal parameters (data type, definition type) |
| `keywords[]` | the interactions (keywords) used: key, `uniqueID` (`…-IA-…`), path, parameters, description |

### `<TC-UID>.json`: one test case (what is executed)

Like the test case set file, but without top-level `key`/`name` (identity is `uniqueID`, plus
`origin`), and **resolved for one parameter combination**:
`testSequence[]` is fully expanded. `spec.keywordType` is set (`Atomic`/`Compound`). A `Compound` keyword call is followed by its `Atomic` child
calls (`parentID` = the compound's `sequenceID`, `numbering` `2.1`, `2.2`, …), and a call over
an instance table is repeated once per row (`alle[0]` … `alle[4]`). In the example, the 3 designed
steps become 22 calls. `callParameters[].value` holds the concrete value, and every call has an `exec` (`verdict`, `duration`, `tester`, `comments`,
`defects`, `time`). The `exec` block carries the test case result: `status`, `execStatus`,
`verdict`, `tester`, `comments`, `defects`, `udfs`, `plannedDuration`, `actualDuration`.

### `<TT-UID>.json`: test theme

`key`, `uniqueID`, `name`, `path`, `spec` (description, review comment, status, priority,
UDFs, …) and `exec` (key, `comments`, status, verdict).

### Rich text in the report

All HTML fields (`description`, `reviewComment`, `comments`) are full `<html><body>…</body></html>`
strings written by the desktop editor (`<font>` tags, whitespace). An empty field is
`<html><body/></html>` or a body that contains only an empty `<font>`. Read them with
`extract_text_from_html_body` and check emptiness with `has_visible_text`. Never copy the
`<font>` style into output you generate (see `testbench-rich-text-html`).

## Reading the report in an agent

```python
catalog = await asyncio.to_thread(get_test_case_set_catalog, conn=conn, project_key=..., tov_key=...,
                                  cycle_key=context.cycle_key, root_uid=context.root_uid,
                                  filtering=context.filtering)   # dict[UID, TestCaseSet]
tcs = catalog[uid]
tcs.details        # TestCaseSetDetails  = <TCS-UID>.json
tcs.test_cases     # dict[TC-UID, TestCaseDetails] = <TC-UID>.json
                   # (tcs.details.testCases is the testCases[] list inside the TCS file)
```

The models are in `testbench2robotframework.json_reader` / `.model`. `test_case_set_as_str`
and `parameter_combinations_as_str` (`utils/testbench_helpers.py`) turn them into prompt text.
The report is a snapshot: read the **current** spec right before writing it
(`get_test_case_set_details`), not from the report.

## Writing execution data back: `protocol.json` + import

`protocol.json` is a **list of `TestCaseSetExecutionForImport`**. It tells TestBench which
executions to update and with what values:

```json
[{
  "testCaseSetKey": "<TCS file: key>",
  "executionKey":   "<TCS file: exec.key>",
  "durationMillis": 4200,
  "testerKey": "<optional user key>",
  "comments": {"html": "<html><body>…</body></html>", "plain": "…"},
  "udfs": [{"udfKey": "10011", "value": "…"}],
  "testCases": [{
    "uniqueID": "<TC UID>",
    "testCaseExecutionKey": "<TCS file: testCases[].exec.key>",
    "durationMillis": 4200,
    "result": {"status": "Performed", "execStatus": "NotBlocked", "verdict": "Pass", "timestamp": "…"},
    "comments": {"html": "<html><body>…</body></html>", "plain": "…"},
    "defects": ["<defect key>"], "references": [], "udfs": [], "parameters": []
  }]
}]
```

Required: `testCaseSetKey`, `executionKey`, `durationMillis`, `testCases`, and per test case
`uniqueID`, `testCaseExecutionKey`, `result` (`status`, `execStatus`, `verdict`) and
`durationMillis`. The schemas are in `openapi.yml` (`TestCaseSetExecutionForImport`,
`TestCaseExecutionForImport`, `ExecutionResultForImport`, `RichTextForImport`). The Python
dataclasses are in `testbench2robotframework.model`.

Result values (as testbench2robotframework maps them):

| Outcome | `status` | `verdict` | `execStatus` |
|---|---|---|---|
| passed | `Performed` | `Pass` | `NotBlocked` |
| failed | `Performed` | `Fail` | `NotBlocked` |
| not finished / unknown | `Running` | `Undefined` | `NotBlocked` |

To change only a comment, copy the current `status`/`execStatus`/`verdict` from the report into
`result`, so the result is not changed. The proven way is the Defect Explainer
(`agents/defect_explainer/utils.py`, `build_protocol_json` / `create_import_zip`). It sends
`durationMillis: 0` on both levels and a `timestamp` (a model field default evaluated once at
import, so in practice the service start time, local time with a literal `Z`: a known bug;
compute it per call in new code), copies status/execStatus/verdict of every
test case, sets only the test case set `comments.html`, and leaves out `udfs`, `defects` and
`parameters`. Anything beyond that (e.g. per-test-case comments only) is untested in this
service, so try it on a test cycle first.

Where a comment lives:

| Protocol field | Same value in the report file |
|---|---|
| `[].comments` (test case set execution) | `<TCS-UID>.json` → `exec.comments` |
| `[].testCases[].comments` (test case execution) | `<TC-UID>.json` → `exec.comments` and `<TCS-UID>.json` → `testCases[].exec.comments` |

### Import zip and calls

1. Zip: `protocol.json` plus one report file per element whose data you change, with the
   same change applied as in the protocol (e.g. `exec.comments`). Keep every key from the
   report. Never invent keys.

   | Zip content | When |
   |---|---|
   | `protocol.json` | always |
   | `<TCS-UID>.json` | you change the test case set execution (its `comments`). **Proven minimum:** the Defect Explainer's `create_import_zip` sends exactly `protocol.json` + `<TCS-UID>.json`, nothing else |
   | `<TC-UID>.json` | you change a single test case execution (`testCases[].comments`/`result`); untested in this service |
   | `project.json` | optional; testbench2robotframework adds it so the target can be found without a cycle key. Not needed here, because the service always imports into `context.cycle_key` |
2. `POST 2/projects/{p}/executionResults` (body `application/zip`) → `{"fileName": …}`.
3. `POST 2/projects/{p}/cycles/{c}/import` with `ExecutionImportOptions`: `fileName`
   (required), `treeRootUID`, `useExistingDefect`, `discardTesterInformation`, `defaultTester`,
   `updateReferencesList`, `filtering`, `filters`, `checkInData` → job id.
4. Poll `GET 2/projects/{p}/import/job/{jobId}` until it completes and check it for errors.

`testbench_cli_reporter.actions.ImportJSONExecutionResults(ImportJsonParameters(inputPath=zip,
projectKey=…, cycleKey=…)).trigger(connection)` runs steps 2 and 3 only. The Defect Explainer
(`import_data`) stops there: it never polls or checks the import job, so a failed import is
invisible to it (it still declares `ReadExecutionImportingJobDetails`). New agents should add
step 4. Permissions: `ImportExecutionResults`, `ReadExecutionImportingJobDetails`. Roles:
manager or tester.
`POST .../cycles/{c}/simulate-import` lists the elements the import would check in, without
importing anything.

### Rules

- Execution import works only for **JSON-based TOVs**. `is_json_based_tov` reads the TOV
  (`GET 2/projects/{p}/tovs/{t}`, `ReadProjectDetails`): its `exchangeFormat` is `json`, or
  `inherited` and the project's (`project.json → exchangeFormat`) is `default_json`. The example
  project is `default_xml`, so `examples/protocol.json` is only importable into a TOV set
  explicitly to `json`. Reject other TOVs in precheck.
- Precheck pattern for execution agents (Defect Explainer): require `cycle_key`, check the TOV
  format, select nodes by `exec.status`/`exec.verdict`, and skip nodes whose `exec.locker` is
  another user (warning). Roles: `TestManager`, `Tester`.
- Failure path for imports: there is no "started" state (no lock to set). On an exception,
  the Defect Explainer imports once more, with the original comment plus a translated error
  note (`add_error_message`), then logs and re-raises, so the user sees the failure in TestBench.
- The import runs as the triggering user, with their roles (manager or tester). Take the
  execution keys and locks from the current cycle structure, and check the finished import job
  for errors. A successful upload does not mean the import succeeded.
- Every `comments.html` must be a full `<html><body>…</body></html>` document from the safe
  vocabulary (`testbench-rich-text-html`). The `&#10004; passed` in `examples/protocol.json` is
  part of it (a BMP symbol paired with a word); colour emoji (✅ ❌) are not. Embedded
  `data:image/png;base64` images are stored as `itb:/image/…`. `RichTextForImport` also has
  `plain`; the Defect Explainer's `Comments` model sends only `html`, which works.
- To keep existing protocol entries when you add results, merge by `testCaseSetKey` (replace
  only the entries you executed), as testbench2robotframework's `merge_protocol` does.
