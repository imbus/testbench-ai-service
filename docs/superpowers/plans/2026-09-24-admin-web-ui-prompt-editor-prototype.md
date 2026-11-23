# Admin Web UI — Prompt Editor to Prototype Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the prompt editor's long single-column form with the prototype's full-height, IDE-style workbench: toolbar, variant/message tree, one-message CodeMirror editor, variable sidebar, and a preview/test-run pane — with the prototype's Split/Tabs layout switch.

**Architecture:** Frontend only. `PromptEditor.tsx` keeps everything it owns today — the `promptDraftReducer` draft, load/reset, dirty tracking, `useBlocker`, lint, plan-then-save, 422 field marking — and stops rendering one long form. Its JSX is split into focused presentational components under `frontend/src/components/prompt/`, driven by a new `Selection` (`meta` | `variant` | `message`) that decides what the centre pane shows. No API, reducer or backend change.

**Tech Stack:** React 18 + TypeScript + Vite + TanStack Query + react-router 7 (data router) + CodeMirror 6 + vitest + @testing-library/react.

**Spec:** The Claude Design prototype `TestBench AI Service Console.dc.html` (project `474074a4-dc03-4e6f-b0c9-3b36a780a114`, section `<!-- ---- PROMPTS EDITOR ---- -->` and `buildEditor()`), read against the parent spec `docs/superpowers/specs/2026-09-08-admin-web-ui-design.md` (§3.1 deliberate deviations, §9 prompt editor, §12.3). The prototype is the layout authority; the spec stays the behaviour authority wherever they disagree — see "Deviations" below.

## Prototype reference (what we are matching)

Screen root: `display:flex; flex-direction:column; height:calc(100vh - 52px); min-height:600px` (52px = `TopBar` height).

1. **Toolbar** (`padding:10px 16px`, bottom divider, wraps): `h3` "Prompts" (22px) · language select · agent select · variant stepper (`‹` button, bold variant select, `›` button inside one bordered group) · muted monospace path `prompts/<lang>/<agent>/prompt.yaml` · spacer · `.seg` Split | Tabs.
2. **Split layout** (default), row below the toolbar:
   - **Left tree**, 250px, right divider, scrolls, 13px: a `prompt.yaml` row (subtitle "name · summary · default_model · default_variant"); a "VARIANTS" caps header with `+`; each variant row = chevron `▾`/`▸` + name + muted monospace model; the selected variant expanded into message rows (indent 34px, `tag tag-neutral` role chip, monospace label = file name or first 28 chars of text, red `●` when lint failed) and a muted `+ message`; footer "Files: a.jinja, b.jinja".
   - **Centre**: message toolbar (6px 12px, 12px font: monospace message path · role select · `.seg` text | file · file-name input when file · spacer · "Insert variable…" select · red "Delete message") above the CodeMirror editor filling the rest.
   - **Right var sidebar**, 230px, `--color-surface`, left divider: `AGENT.*` caps header + monospace insert buttons with accent `●` when used; `VARS.* (VARIANT)` the same; amber "Undeclared: … [declare]" box; spacer; red "Line n: msg" boxes or green "✓ Jinja OK".
   - **Bottom pane**, 230px tall, top divider: surface header row "Preview" + selects + model line + primary "Test run"; body = rendered messages, response beside it.
3. **Tabs layout**: no left tree; a tab strip (`prompt.yaml` tab + one tab per message: number, role chip, label, error dot, `+ message`); editor; a surface status bar (✓/errors · "x/y declared vars used · n undeclared" · spacer · "jinja · UTF-8"); a 340px right drawer with tabs Variables | Preview | Test run (Variables tab also edits declarations: key, name, type, required, ✕, `+ Add`).
4. **prompt.yaml pane**: `padding:20px 24px; display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:16px 24px; max-width:900px` — name, summary, description (full row), default_model, default_variant.

## Deviations (deliberate — do not "fix" them toward the prototype)

| # | Prototype | This plan | Why |
|---|---|---|---|
| D1 | Lint is a live client regex on every keystroke | On-demand server lint (`POST /prompts/lint`), one button in the var sidebar / status bar | Spec §9: the regex linter is replaced by real `jinja2` parse errors; the endpoint is a network round trip |
| D2 | Preview picks project + test case set and renders mocked context | Existing `RenderPreview` (editable `agent_context` JSON, admin-only, sandboxed render) | Spec §12.3; no test-case-set data source exists |
| D3 | Test run is mocked | Existing `TestRunPanel` (project + model picker, real run) | Phase 5 folded into 4: the real run ships |
| D4 | Generated `prompt.yaml` preview under the meta fields | Omitted | Spec: serialization is server-side; the save confirm dialog already shows the server's plan |
| D5 | `default_model` opens a model-picker modal | Plain text input (as today) | No picker component exists for prompt fields; out of scope |
| D6 | Variant rename/description/remove live on the Agent detail screen | A **variant settings pane** in the centre, opened by a gear button on the variant row: name, model, remove, `VarDeclTable` | This screen already owns those edits (and their tests); Split mode has no other place for var declarations |
| D7 | `+` adds "New variant" silently | `+` adds a uniquely named variant (`t.newVariantDefault`, then ` 2`, ` 3`…) and opens its settings pane so it can be renamed | Our reducer requires a name; same result for the operator |
| D8 | No message reordering | Move up / Move down buttons in the message toolbar | Existing feature, keep it |
| D9 | Language/agent selects change internal state | They **navigate** to `/admin/prompts/:lang/:agent` | Our editor is URL-routed; `useBlocker` then guards unsaved edits for free |
| D10 | Save lives in the global top bar | Save button at the right end of the editor toolbar (admin only) | This screen has its own save flow (plan → confirm) |
| D11 | `/admin/prompts` nav goes straight into the editor | The existing prompt list at `/admin/prompts` stays unchanged | It is the only place a prompt that fails to parse is listed with its error |

## Global Constraints

- Frontend only; do not touch `webui/`, `api/*.ts` request shapes, or `state/promptDraft.ts` actions.
- Every user-visible string goes through `useTranslations`; add each new key to BOTH `frontend/src/i18n/de.ts` and `frontend/src/i18n/en.ts` (the `Translations` type is derived from `de`). Wire tokens stay untranslated: `prompt.yaml`, `agent.*`, `vars.*`, role names, `text`/`file` source tokens shown as monospace.
- Write access unchanged: every mutating control renders only when `isAdmin`; `RenderPreview`/`TestRunPanel` keep their own admin gating.
- Colours only via existing CSS variables and the literal error/warn colours already used in this screen (`#a33a2b`, `#c0392b`, `#2e8b5e`, `#c9a227`/`#7a5a00`). Classes from `industry.css`: `input`, `btn btn-primary|btn-secondary|btn-ghost|btn-icon`, `seg`/`seg-opt`, `tag tag-neutral|tag-accent`, `text-muted`.
- Inline `style={{…}}` objects, matching the rest of the console. No new stylesheet, no new dependency.
- `localStorage` access wrapped in `try/catch`, key prefixed `tbai-console-` (as `theme.ts` does).
- Screen tests keep mocking `CodeEditor` (CM6 needs DOM APIs jsdom lacks).
- Run from `frontend/`: `npx tsc -b` and `npx vitest run` must both pass at the end of every task.

## Review Focus

1. **Switching agent or language with unsaved edits** — the toolbar selects navigate, so `useBlocker` must show the unsaved-changes modal, and "Cancel" must leave the selects showing the *current* agent (they are controlled by route params). Tests in Tasks 7 and 8.
2. **A variant with zero messages** (loads that way, or its last message removed) — the tree shows only `+ message`, the centre shows the variant settings pane, nothing throws. Tests in Tasks 4 and 8.
3. **Removing the selected message** — selection moves to the previous message; removing index 0 of a one-message variant moves to the variant settings pane; diagnostics are cleared. Test in Task 8.
4. **Renaming the selected variant in its settings pane** — the selection follows the new name on every keystroke (the existing `setSelectedVariant(event.target.value)` rule), the tree row and the toolbar variant select show the new name. Test in Task 8.
5. **Unreadable file-backed message / read-only session** — the unreadable alert stays visible above the editor, the source switch is disabled, and "Insert variable" is disabled when the editor is read-only (insertion would silently do nothing). Tests in Tasks 5 and 6.

---

## File Structure

| File | Responsibility |
|---|---|
| Create `frontend/src/components/prompt/selection.ts` | `Selection` type, `messageLabel()`, `messagePath()`, `uniqueVariantName()` |
| Create `frontend/src/components/prompt/templateVars.ts` | `usedTemplateVars()`, `undeclaredVars()` — pure, client-side hints only |
| Create `frontend/src/state/editorLayout.ts` | `useEditorLayout()` — Split/Tabs preference in `localStorage` |
| Modify `frontend/src/components/CodeEditor.tsx` | `forwardRef` + `insert(text)` handle; `fill` prop to fill its container |
| Create `frontend/src/components/prompt/PromptTree.tsx` | Left tree (Split) |
| Create `frontend/src/components/prompt/MessagePane.tsx` | One message: toolbar + editor (replaces `MessageList`) |
| Create `frontend/src/components/prompt/VarSidebar.tsx` | agent.* / vars.* insert lists, undeclared box, lint status |
| Create `frontend/src/components/prompt/MetaPane.tsx` | prompt.yaml header fields |
| Create `frontend/src/components/prompt/VariantPane.tsx` | Variant settings: name, model, remove, `VarDeclTable` |
| Create `frontend/src/components/prompt/EditorToolbar.tsx` | Title, lang/agent selects, variant stepper, path, layout switch, Save |
| Create `frontend/src/components/prompt/TabsLayout.tsx` | Tabs-mode tab strip, status bar and right drawer |
| Modify `frontend/src/screens/PromptEditor.tsx` | State owner; composes the panes |
| Delete `frontend/src/components/MessageList.tsx` + `.test.tsx` | Superseded by `MessagePane` (tests ported) |
| Modify `frontend/src/i18n/de.ts`, `en.ts` | New keys |
| Modify `frontend/src/dev/preview.tsx` | Prompt fixtures for the visual check |

New i18n keys (add in Task 1 so every later task can use them):

| key | de | en |
|---|---|---|
| `layoutSplit` | `Geteilt` | `Split` |
| `layoutTabs` | `Tabs` | `Tabs` |
| `promptLanguage` | `Sprache` | `Language` |
| `promptAgent` | `Agent` | `Agent` |
| `prevVariant` | `Vorherige Variante` | `Previous variant` |
| `nextVariant` | `Nächste Variante` | `Next variant` |
| `promptMetaHint` | `Name · Zusammenfassung · Standardmodell · Standardvariante` | `name · summary · default_model · default_variant` |
| `variantSettings` | `Varianteneinstellungen` | `Variant settings` |
| `newVariantDefault` | `Neue Variante` | `New variant` |
| `addMessageShort` | `+ Nachricht` | `+ message` |
| `emptyMessage` | `(leer)` | `(empty)` |
| `promptFiles` | `Dateien` | `Files` |
| `insertVar` | `Variable einfügen…` | `Insert variable…` |
| `deleteMessage` | `Nachricht löschen` | `Delete message` |
| `undeclaredVars` | `Nicht deklariert:` | `Undeclared:` |
| `declareVars` | `deklarieren` | `declare` |
| `lintLine` | `Zeile` | `Line` |
| `varsUsed` | `deklarierte Variablen genutzt` | `declared vars used` |
| `undeclaredCount` | `nicht deklariert` | `undeclared` |
| `previewPane` | `Vorschau` | `Preview` |
| `drawerVariables` | `Variablen` | `Variables` |
| `noMessages` | `Diese Variante hat keine Nachrichten.` | `This variant has no messages.` |

---

### Task 1: Pure helpers + i18n keys

**Files:**
- Create: `frontend/src/components/prompt/selection.ts`, `frontend/src/components/prompt/templateVars.ts`
- Test: `frontend/src/components/prompt/selection.test.ts`, `frontend/src/components/prompt/templateVars.test.ts`
- Modify: `frontend/src/i18n/de.ts`, `frontend/src/i18n/en.ts`

**Interfaces:**
- Produces:
  - `type Selection = { kind: 'meta' } | { kind: 'variant' } | { kind: 'message'; index: number }`
  - `messageLabel(message: PromptMessageDoc, empty: string): string`
  - `messagePath(docFile: string, variant: string, index: number, message: PromptMessageDoc): string`
  - `uniqueVariantName(base: string, existing: string[]): string`
  - `usedTemplateVars(text: string): string[]` — e.g. `['agent.defect', 'vars.tone']`, first-appearance order, unique
  - `undeclaredVars(used: string[], declaredKeys: string[]): string[]` — bare keys, e.g. `['tone']`

- [ ] **Step 1: Write the failing tests**

`frontend/src/components/prompt/templateVars.test.ts`:
```ts
import { describe, expect, it } from 'vitest'
import { undeclaredVars, usedTemplateVars } from './templateVars'

describe('usedTemplateVars', () => {
  it('finds agent.* and vars.* inside expressions and statements', () => {
    const text = 'Hi {{ agent.defect }}\n{% for c in agent.test_cases %}{{ c }}{% endfor %}{{ vars.tone | upper }}'
    expect(usedTemplateVars(text)).toEqual(['agent.defect', 'agent.test_cases', 'vars.tone'])
  })

  it('ignores names outside template tags', () => {
    expect(usedTemplateVars('see agent.defect in the docs')).toEqual([])
  })

  it('returns each name once, in first-appearance order', () => {
    expect(usedTemplateVars('{{ vars.b }}{{ vars.a }}{{ vars.b }}')).toEqual(['vars.b', 'vars.a'])
  })

  it('handles an unterminated tag without throwing', () => {
    expect(usedTemplateVars('{{ agent.defect ')).toEqual([])
  })
})

describe('undeclaredVars', () => {
  it('returns bare keys of used vars.* not declared on the variant', () => {
    expect(undeclaredVars(['agent.defect', 'vars.tone', 'vars.depth'], ['depth'])).toEqual(['tone'])
  })
})
```

`frontend/src/components/prompt/selection.test.ts`:
```ts
import { describe, expect, it } from 'vitest'
import type { PromptMessageDoc } from '../../api/types'
import { messageLabel, messagePath, uniqueVariantName } from './selection'

const inline = (content: string): PromptMessageDoc => ({ role: 'user', source: 'inline', file: null, content, readable: true })
const file: PromptMessageDoc = { role: 'system', source: 'file', file: 'sys.jinja', content: 'x', readable: true }

describe('messageLabel', () => {
  it('uses the file name for a file-backed message', () => {
    expect(messageLabel(file, '(empty)')).toBe('sys.jinja')
  })
  it('uses the first line, cut to 28 characters, for inline text', () => {
    expect(messageLabel(inline('A very long first line that keeps going\nsecond'), '(empty)')).toBe('A very long first line that ')
  })
  it('falls back to the empty label', () => {
    expect(messageLabel(inline(''), '(empty)')).toBe('(empty)')
  })
})

describe('messagePath', () => {
  it('points a file-backed message at its template next to prompt.yaml', () => {
    expect(messagePath('de/explainer/prompt.yaml', 'Thorough', 0, file)).toBe('prompts/de/explainer/sys.jinja')
  })
  it('points an inline message into prompt.yaml', () => {
    expect(messagePath('de/explainer/prompt.yaml', 'Thorough', 1, inline('x'))).toBe('prompt.yaml › Thorough › messages[1]')
  })
})

describe('uniqueVariantName', () => {
  it('returns the base when free, else the first free numbered name', () => {
    expect(uniqueVariantName('New variant', ['A'])).toBe('New variant')
    expect(uniqueVariantName('New variant', ['New variant', 'New variant 2'])).toBe('New variant 3')
  })
})
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd frontend && npx vitest run src/components/prompt`
Expected: FAIL — cannot resolve `./templateVars` / `./selection`.

- [ ] **Step 3: Implement**

`frontend/src/components/prompt/templateVars.ts`:
```ts
/**
 * Which `agent.*` / `vars.*` names a template references.
 *
 * A HINT for the variable sidebar's "used" dots and the undeclared warning --
 * never a validation. The server's real Jinja parse (lint, render) stays the
 * authority; a regex cannot see `{% set %}` aliases or attribute chains, and
 * that is acceptable for a hint.
 */
const TAG = /\{\{([\s\S]*?)\}\}|\{%([\s\S]*?)%\}/g
const NAME = /\b(agent|vars)\.([A-Za-z_]\w*)/g

export function usedTemplateVars(text: string): string[] {
  const seen: string[] = []
  for (const tag of text.matchAll(TAG)) {
    const body = tag[1] ?? tag[2] ?? ''
    for (const name of body.matchAll(NAME)) {
      const full = `${name[1]}.${name[2]}`
      if (!seen.includes(full)) seen.push(full)
    }
  }
  return seen
}

/** Bare keys of every `vars.*` reference the variant does not declare. */
export function undeclaredVars(used: string[], declaredKeys: string[]): string[] {
  return used
    .filter((name) => name.startsWith('vars.'))
    .map((name) => name.slice('vars.'.length))
    .filter((key) => !declaredKeys.includes(key))
}
```

`frontend/src/components/prompt/selection.ts`:
```ts
import type { PromptMessageDoc } from '../../api/types'

/** What the editor's centre pane shows. `message.index` is into the SELECTED variant. */
export type Selection = { kind: 'meta' } | { kind: 'variant' } | { kind: 'message'; index: number }

/** The tree/tab label: a file-backed message by its file, an inline one by its first line. */
export function messageLabel(message: PromptMessageDoc, empty: string): string {
  if (message.source === 'file' && message.file) return message.file
  return message.content.split('\n')[0].slice(0, 28) || empty
}

/**
 * Where a message's text lives on disk, for the message toolbar.
 *
 * `docFile` is the document's own `file` (`de/explainer/prompt.yaml`, relative
 * to `prompts_dir`); a template sits next to it.
 */
export function messagePath(docFile: string, variant: string, index: number, message: PromptMessageDoc): string {
  if (message.source === 'file' && message.file) {
    const dir = docFile.includes('/') ? docFile.slice(0, docFile.lastIndexOf('/')) : ''
    return `prompts/${dir ? `${dir}/` : ''}${message.file}`
  }
  return `prompt.yaml › ${variant} › messages[${index}]`
}

export function uniqueVariantName(base: string, existing: string[]): string {
  if (!existing.includes(base)) return base
  let n = 2
  while (existing.includes(`${base} ${n}`)) n += 1
  return `${base} ${n}`
}
```

Add the 22 i18n keys from the table above to the end of the objects in `de.ts` and `en.ts` (before `} as const`).

- [ ] **Step 4: Run to verify they pass**

Run: `cd frontend && npx vitest run src/components/prompt src/i18n && npx tsc -b`
Expected: PASS, no type errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/prompt frontend/src/i18n
git commit -m "feat(webui): Add prompt editor selection and template-var helpers"
```

---

### Task 2: CodeEditor insert handle + fill mode, editor layout preference

**Files:**
- Modify: `frontend/src/components/CodeEditor.tsx`
- Create: `frontend/src/state/editorLayout.ts`
- Test: `frontend/src/state/editorLayout.test.ts`
- Modify (mocks only): `frontend/src/screens/PromptEditor.test.tsx:28-54`, `frontend/src/components/MessageList.test.tsx:13` (deleted later in Task 8, but must keep compiling now)

**Interfaces:**
- Produces:
  - `export type CodeEditorHandle = { insert: (text: string) => void }`
  - `CodeEditor` is now `forwardRef<CodeEditorHandle, Props>`; new optional prop `fill?: boolean`
  - `type EditorLayout = 'split' | 'tabs'`; `useEditorLayout(): [EditorLayout, (next: EditorLayout) => void]`; `LAYOUT_STORAGE_KEY = 'tbai-console-prompt-layout'`

- [ ] **Step 1: Write the failing test**

`frontend/src/state/editorLayout.test.ts`:
```ts
import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { LAYOUT_STORAGE_KEY, useEditorLayout } from './editorLayout'

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

describe('useEditorLayout', () => {
  it('defaults to split', () => {
    expect(renderHook(() => useEditorLayout()).result.current[0]).toBe('split')
  })

  it('remembers the choice across mounts', () => {
    const first = renderHook(() => useEditorLayout())
    act(() => first.result.current[1]('tabs'))
    expect(localStorage.getItem(LAYOUT_STORAGE_KEY)).toBe('tabs')
    expect(renderHook(() => useEditorLayout()).result.current[0]).toBe('tabs')
  })

  it('ignores an unknown stored value', () => {
    localStorage.setItem(LAYOUT_STORAGE_KEY, 'grid')
    expect(renderHook(() => useEditorLayout()).result.current[0]).toBe('split')
  })

  it('still works when storage throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    const hook = renderHook(() => useEditorLayout())
    expect(hook.result.current[0]).toBe('split')
    act(() => hook.result.current[1]('tabs'))
    expect(hook.result.current[0]).toBe('tabs')
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/state/editorLayout.test.ts`
Expected: FAIL — cannot resolve `./editorLayout`.

- [ ] **Step 3: Implement**

`frontend/src/state/editorLayout.ts`:
```ts
import { useCallback, useState } from 'react'

export type EditorLayout = 'split' | 'tabs'

export const LAYOUT_STORAGE_KEY = 'tbai-console-prompt-layout'

function storedLayout(): EditorLayout {
  try {
    return localStorage.getItem(LAYOUT_STORAGE_KEY) === 'tabs' ? 'tabs' : 'split'
  } catch {
    return 'split'
  }
}

/** The prompt editor's Split/Tabs choice -- a per-viewer convenience, so browser storage is enough. */
export function useEditorLayout(): [EditorLayout, (next: EditorLayout) => void] {
  const [layout, setLayout] = useState<EditorLayout>(storedLayout)
  const update = useCallback((next: EditorLayout) => {
    setLayout(next)
    try {
      localStorage.setItem(LAYOUT_STORAGE_KEY, next)
    } catch {
      // Private window or blocked storage: the choice just lasts this visit.
    }
  }, [])
  return [layout, update]
}
```

`frontend/src/components/CodeEditor.tsx` — change the export to a `forwardRef`, add the handle and `fill`:
```tsx
import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'
// ...existing imports and `theme`...

// Fill mode: the editor takes its container's full height and scrolls
// internally, instead of growing with its content.
const fillTheme = EditorView.theme({ '&': { height: '100%' }, '.cm-scroller': { overflow: 'auto' } })

type Props = {
  value: string
  onChange: (value: string) => void
  diagnostics?: LintError[]
  readOnly?: boolean
  ariaLabel: string
  fill?: boolean
}

export type CodeEditorHandle = {
  /** Replaces the selection (or inserts at the cursor) and focuses the editor. No-op when read-only. */
  insert: (text: string) => void
}

export const CodeEditor = forwardRef<CodeEditorHandle, Props>(function CodeEditor(
  { value, onChange, diagnostics, readOnly, ariaLabel, fill },
  ref,
) {
  // ...existing refs...

  useImperativeHandle(
    ref,
    () => ({
      insert(text: string) {
        const editor = view.current
        if (!editor || readOnly) return
        editor.dispatch(editor.state.replaceSelection(text))
        editor.focus()
      },
    }),
    [readOnly],
  )

  // In the build effect's `extensions` array add, after `theme`:
  //   ...(fill ? [fillTheme] : []),
  // and change its dependency list to `[readOnly, ariaLabel, fill]`.

  // ...existing value/diagnostics effects unchanged...

  return <div ref={host} data-testid="code-editor" style={fill ? { height: '100%' } : undefined} />
})
```
Keep the doc comment on the component; add one line: "The `insert` handle is the one imperative entry point, used by the variable sidebar."

Update the `CodeEditor` mock in `PromptEditor.test.tsx` (and identically in `MessageList.test.tsx`) so a `ref` works and `insert` is observable:
```tsx
vi.mock('../components/CodeEditor', async () => {
  const { forwardRef, useImperativeHandle } = await import('react')
  return {
    CodeEditor: forwardRef(function MockCodeEditor(
      { value, onChange, ariaLabel, readOnly, diagnostics }: {
        value: string
        onChange: (value: string) => void
        ariaLabel: string
        readOnly?: boolean
        diagnostics?: LintError[]
      },
      ref,
    ) {
      useImperativeHandle(ref, () => ({ insert: (text: string) => onChange(value + text) }), [value, onChange])
      return (
        <div>
          <textarea aria-label={ariaLabel} value={value} readOnly={readOnly} onChange={(e) => onChange(e.target.value)} />
          {(diagnostics ?? []).map((error, index) => (
            <div key={index} role="alert">{error.message}</div>
          ))}
        </div>
      )
    }),
  }
})
```
(In `MessageList.test.tsx` the mock path is `'./CodeEditor'`.)

- [ ] **Step 4: Run to verify**

Run: `cd frontend && npx vitest run && npx tsc -b`
Expected: all tests PASS (existing 648 + 4 new), no type errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/CodeEditor.tsx frontend/src/state/editorLayout.ts frontend/src/state/editorLayout.test.ts frontend/src/screens/PromptEditor.test.tsx frontend/src/components/MessageList.test.tsx
git commit -m "feat(webui): Give CodeEditor an insert handle and fill mode"
```

---

### Task 3: VarSidebar

**Files:**
- Create: `frontend/src/components/prompt/VarSidebar.tsx`
- Test: `frontend/src/components/prompt/VarSidebar.test.tsx`

**Interfaces:**
- Consumes: `LintError` from `api/types`
- Produces:
```ts
export type LintState = { running: boolean; checked: boolean; error: string | null; errors: LintError[] }
export function VarSidebar(props: {
  agentVars: string[]        // ['agent.defect', ...] from the skeleton's keys
  declaredVars: string[]     // ['vars.tone', ...]
  used: string[]             // usedTemplateVars(current message)
  undeclared: string[]       // bare keys
  canInsert: boolean         // false when the editor is read-only or no message is open
  canDeclare: boolean        // isAdmin
  lint: LintState            // errors = the CURRENT message's diagnostics
  lang?: Lang
  onInsert: (name: string) => void
  onDeclare: () => void
  onLint: () => void
}): JSX.Element
```

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { VarSidebar, type LintState } from './VarSidebar'

const idle: LintState = { running: false, checked: false, error: null, errors: [] }

function setup(overrides: Partial<Parameters<typeof VarSidebar>[0]> = {}) {
  const props = {
    agentVars: ['agent.defect', 'agent.test_case'],
    declaredVars: ['vars.tone'],
    used: ['agent.defect'],
    undeclared: [],
    canInsert: true,
    canDeclare: true,
    lint: idle,
    lang: 'en' as const,
    onInsert: vi.fn(),
    onDeclare: vi.fn(),
    onLint: vi.fn(),
    ...overrides,
  }
  render(<VarSidebar {...props} />)
  return props
}

describe('VarSidebar', () => {
  it('inserts a variable wrapped in an expression tag', async () => {
    const props = setup()
    await userEvent.click(screen.getByRole('button', { name: /agent\.test_case/ }))
    expect(props.onInsert).toHaveBeenCalledWith('{{ agent.test_case }}')
  })

  it('marks used variables', () => {
    setup()
    expect(screen.getByRole('button', { name: /agent\.defect/ })).toHaveAttribute('data-used', 'true')
    expect(screen.getByRole('button', { name: /vars\.tone/ })).toHaveAttribute('data-used', 'false')
  })

  it('disables insertion when the editor cannot take it', () => {
    setup({ canInsert: false })
    expect(screen.getByRole('button', { name: /agent\.defect/ })).toBeDisabled()
  })

  it('offers to declare undeclared vars, admin only', async () => {
    const props = setup({ undeclared: ['depth'] })
    expect(screen.getByText('depth')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'declare' }))
    expect(props.onDeclare).toHaveBeenCalled()
  })

  it('hides the declare button for a non-admin', () => {
    setup({ undeclared: ['depth'], canDeclare: false })
    expect(screen.queryByRole('button', { name: 'declare' })).not.toBeInTheDocument()
  })

  it('shows lint errors by line', () => {
    setup({ lint: { ...idle, checked: true, errors: [{ line: 3, column: 1, message: 'unexpected end' }] } })
    expect(screen.getByText('Line 3: unexpected end')).toBeInTheDocument()
  })

  it('shows the clean result only after a check', () => {
    setup({ lint: { ...idle, checked: true } })
    expect(screen.getByText(/No syntax errors\./)).toBeInTheDocument()
  })

  it('shows no result before a check', () => {
    setup()
    expect(screen.queryByText(/No syntax errors\./)).not.toBeInTheDocument()
  })

  it('runs lint on demand and surfaces a failed run', async () => {
    const props = setup({ lint: { ...idle, error: 'boom' } })
    await userEvent.click(screen.getByRole('button', { name: /^lint$/i }))
    expect(props.onLint).toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('boom')
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/components/prompt/VarSidebar.test.tsx`
Expected: FAIL — cannot resolve `./VarSidebar`.

- [ ] **Step 3: Implement**

```tsx
import type { LintError } from '../../api/types'
import { useTranslations, type Lang } from '../../i18n'

export type LintState = { running: boolean; checked: boolean; error: string | null; errors: LintError[] }

const caps = { fontSize: 11, letterSpacing: '.08em', textTransform: 'uppercase' as const }
const mono = 'ui-monospace, Menlo, monospace'

function VarButton({ name, used, disabled, onInsert }: { name: string; used: boolean; disabled: boolean; onInsert: () => void }) {
  return (
    <button
      type="button"
      data-used={used}
      disabled={disabled}
      onClick={onInsert}
      style={{ textAlign: 'left', border: 0, background: 'transparent', color: 'inherit', fontFamily: mono, fontSize: 12, padding: '2px 0', cursor: disabled ? 'default' : 'pointer', display: 'flex', justifyContent: 'space-between' }}
    >
      <span>{name}</span>
      {used && <span aria-hidden style={{ color: 'var(--color-accent)' }}>●</span>}
    </button>
  )
}

/** The Split layout's right column: insertable variables and the syntax check. */
export function VarSidebar({ agentVars, declaredVars, used, undeclared, canInsert, canDeclare, lint, lang = 'de', onInsert, onDeclare, onLint }: {
  agentVars: string[]
  declaredVars: string[]
  used: string[]
  undeclared: string[]
  canInsert: boolean
  canDeclare: boolean
  lint: LintState
  lang?: Lang
  onInsert: (name: string) => void
  onDeclare: () => void
  onLint: () => void
}) {
  const t = useTranslations(lang)
  const list = (names: string[]) =>
    names.map((name) => (
      <VarButton key={name} name={name} used={used.includes(name)} disabled={!canInsert} onInsert={() => onInsert(`{{ ${name} }}`)} />
    ))

  return (
    <aside
      data-testid="var-sidebar"
      style={{ width: 230, flex: 'none', borderLeft: '1px solid var(--color-divider)', background: 'var(--color-surface)', padding: 12, display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12, overflow: 'auto' }}
    >
      <div className="text-muted" style={caps}>agent.*</div>
      {list(agentVars)}
      <div className="text-muted" style={{ ...caps, marginTop: 8 }}>vars.* (variant)</div>
      {list(declaredVars)}
      {undeclared.length > 0 && (
        <div style={{ border: '1px solid #c9a227', padding: 6, color: '#7a5a00', background: 'color-mix(in srgb, #c9a227 12%, transparent)' }}>
          {t.undeclaredVars} <span style={{ fontFamily: mono }}>{undeclared.join(', ')}</span>{' '}
          {canDeclare && (
            <button type="button" className="btn btn-ghost" style={{ fontSize: 11, padding: '0 4px' }} onClick={onDeclare}>
              {t.declareVars}
            </button>
          )}
        </div>
      )}
      <div style={{ flex: 1 }} />
      <button type="button" className="btn btn-ghost" disabled={lint.running} onClick={onLint} style={{ alignSelf: 'flex-start', fontSize: 12 }}>
        {lint.running ? t.linting : t.lint}
      </button>
      {lint.error && <div role="alert" style={{ color: '#a33a2b' }}>{lint.error}</div>}
      {lint.errors.map((error, index) => (
        <div key={index} style={{ border: '1px solid #c0392b', background: 'color-mix(in srgb, #c0392b 10%, transparent)', padding: '6px 8px', color: '#a33a2b' }}>
          {`${t.lintLine} ${error.line}: ${error.message}`}
        </div>
      ))}
      {lint.checked && !lint.error && lint.errors.length === 0 && <div style={{ color: '#2e8b5e' }}>✓ {t.lintClean}</div>}
    </aside>
  )
}
```
- [ ] **Step 4: Run to verify it passes**

Run: `cd frontend && npx vitest run src/components/prompt/VarSidebar.test.tsx && npx tsc -b`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/prompt/VarSidebar.tsx frontend/src/components/prompt/VarSidebar.test.tsx
git commit -m "feat(webui): Add the prompt editor variable sidebar"
```

---

### Task 4: PromptTree

**Files:**
- Create: `frontend/src/components/prompt/PromptTree.tsx`
- Test: `frontend/src/components/prompt/PromptTree.test.tsx`

**Interfaces:**
- Consumes: `Selection`, `messageLabel` (Task 1)
- Produces:
```ts
export function PromptTree(props: {
  variants: PromptVariantDoc[]
  selectedVariant: string
  selection: Selection
  flagged: number[]            // message indexes (selected variant) with lint errors
  readOnly: boolean
  lang?: Lang
  onOpenMeta: () => void
  onPickVariant: (name: string) => void
  onOpenVariantSettings: (name: string) => void
  onPickMessage: (index: number) => void
  onAddVariant: () => void
  onAddMessage: () => void
}): JSX.Element
```

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { PromptVariantDoc } from '../../api/types'
import { PromptTree } from './PromptTree'

const VARIANTS: PromptVariantDoc[] = [
  { name: 'Thorough', description: null, model: 'gpt-5.5', vars: {}, messages: [
    { role: 'system', source: 'file', file: 'sys.jinja', content: 'x', readable: true },
    { role: 'user', source: 'inline', file: null, content: 'Explain {{ agent.defect }}', readable: true },
  ] },
  { name: 'Quick', description: null, model: null, vars: {}, messages: [] },
]

function setup(overrides = {}) {
  const props = {
    variants: VARIANTS, selectedVariant: 'Thorough', selection: { kind: 'message' as const, index: 1 },
    flagged: [], readOnly: false, lang: 'en' as const,
    onOpenMeta: vi.fn(), onPickVariant: vi.fn(), onOpenVariantSettings: vi.fn(),
    onPickMessage: vi.fn(), onAddVariant: vi.fn(), onAddMessage: vi.fn(), ...overrides,
  }
  render(<PromptTree {...props} />)
  return props
}

describe('PromptTree', () => {
  it('lists only the selected variant’s messages, by file or first line', () => {
    setup()
    const tree = screen.getByTestId('prompt-tree')
    expect(within(tree).getByRole('button', { name: /sys\.jinja/ })).toBeInTheDocument()
    expect(within(tree).getByRole('button', { name: /Explain \{\{ agent\.defect \}\}/ })).toHaveAttribute('aria-current', 'true')
  })

  it('picks a variant, a message, the meta row and the settings', async () => {
    const props = setup()
    await userEvent.click(screen.getByRole('button', { name: 'Quick' }))
    expect(props.onPickVariant).toHaveBeenCalledWith('Quick')
    await userEvent.click(screen.getByRole('button', { name: /sys\.jinja/ }))
    expect(props.onPickMessage).toHaveBeenCalledWith(0)
    await userEvent.click(screen.getByRole('button', { name: /prompt\.yaml/ }))
    expect(props.onOpenMeta).toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Variant settings: Thorough' }))
    expect(props.onOpenVariantSettings).toHaveBeenCalledWith('Thorough')
  })

  it('flags a message with lint errors', () => {
    setup({ flagged: [0] })
    expect(screen.getByRole('button', { name: /sys\.jinja/ })).toHaveAttribute('aria-invalid', 'true')
  })

  it('renders a selected variant with no messages', () => {
    setup({ selectedVariant: 'Quick', selection: { kind: 'variant' } })
    expect(screen.getByRole('button', { name: '+ message' })).toBeInTheDocument()
  })

  it('lists the referenced template files', () => {
    setup()
    expect(screen.getByText('sys.jinja', { selector: '[data-testid="tree-files"] *' })).toBeInTheDocument()
  })

  it('hides every add button in a read-only session', () => {
    setup({ readOnly: true })
    expect(screen.queryByRole('button', { name: '+ message' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'New variant' })).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/components/prompt/PromptTree.test.tsx`
Expected: FAIL — cannot resolve `./PromptTree`.

- [ ] **Step 3: Implement**

```tsx
import type { PromptVariantDoc } from '../../api/types'
import { useTranslations, type Lang } from '../../i18n'
import { messageLabel, type Selection } from './selection'

const mono = 'ui-monospace, Menlo, monospace'
const rowButton = { border: 0, background: 'transparent', color: 'inherit', font: 'inherit', cursor: 'pointer', textAlign: 'left' as const }

/** The Split layout's left column: prompt.yaml, then variants with the selected one expanded. */
export function PromptTree({ variants, selectedVariant, selection, flagged, readOnly, lang = 'de', onOpenMeta, onPickVariant, onOpenVariantSettings, onPickMessage, onAddVariant, onAddMessage }: {
  variants: PromptVariantDoc[]
  selectedVariant: string
  selection: Selection
  flagged: number[]
  readOnly: boolean
  lang?: Lang
  onOpenMeta: () => void
  onPickVariant: (name: string) => void
  onOpenVariantSettings: (name: string) => void
  onPickMessage: (index: number) => void
  onAddVariant: () => void
  onAddMessage: () => void
}) {
  const t = useTranslations(lang)
  const files = [...new Set(variants.flatMap((v) => v.messages.filter((m) => m.source === 'file' && m.file).map((m) => m.file as string)))]

  return (
    // No aria-label: `t.variants` already names the toolbar's variant select,
    // and a second element with that label makes getByLabelText ambiguous.
    <nav
      data-testid="prompt-tree"
      style={{ width: 250, flex: 'none', borderRight: '1px solid var(--color-divider)', display: 'flex', flexDirection: 'column', overflow: 'auto', fontSize: 13 }}
    >
      <button
        type="button"
        aria-current={selection.kind === 'meta' || undefined}
        onClick={onOpenMeta}
        style={{ ...rowButton, padding: '8px 14px', display: 'flex', flexDirection: 'column', background: selection.kind === 'meta' ? 'var(--color-surface)' : 'transparent' }}
      >
        <span style={{ fontFamily: mono, fontSize: 12 }}>prompt.yaml</span>
        <span className="text-muted" style={{ fontSize: 11 }}>{t.promptMetaHint}</span>
      </button>

      <div className="text-muted" style={{ display: 'flex', alignItems: 'center', padding: '10px 14px 4px', fontSize: 11, letterSpacing: '.08em', textTransform: 'uppercase' }}>
        <span>{t.variants}</span>
        <div style={{ flex: 1 }} />
        {!readOnly && (
          <button type="button" className="btn btn-ghost" aria-label={t.newVariantDefault} title={t.newVariantDefault} style={{ padding: '0 4px', fontSize: 12 }} onClick={onAddVariant}>+</button>
        )}
      </div>

      {variants.map((variant) => {
        const open = variant.name === selectedVariant
        return (
          <div key={variant.name} style={{ display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', alignItems: 'center', padding: '6px 14px', gap: 6, background: open && selection.kind === 'variant' ? 'var(--color-surface)' : 'transparent' }}>
              <button type="button" aria-expanded={open} onClick={() => onPickVariant(variant.name)} style={{ ...rowButton, fontWeight: 500, padding: 0, flex: 1, display: 'flex', alignItems: 'center', gap: 6 }}>
                <span aria-hidden style={{ fontSize: 10 }}>{open ? '▾' : '▸'}</span>
                {variant.name}
              </button>
              {variant.model && <span className="text-muted" style={{ fontFamily: mono, fontSize: 11 }}>{variant.model}</span>}
              <button type="button" className="btn btn-ghost" aria-label={`${t.variantSettings}: ${variant.name}`} title={t.variantSettings} onClick={() => onOpenVariantSettings(variant.name)} style={{ padding: '0 4px', fontSize: 12 }}>⚙</button>
            </div>
            {open && variant.messages.map((message, index) => {
              const current = selection.kind === 'message' && selection.index === index
              return (
                <button
                  key={index}
                  type="button"
                  aria-current={current || undefined}
                  aria-invalid={flagged.includes(index) || undefined}
                  onClick={() => onPickMessage(index)}
                  style={{ ...rowButton, fontSize: 12, padding: '5px 14px 5px 34px', display: 'flex', gap: 6, alignItems: 'center', background: current ? 'var(--color-surface)' : 'transparent' }}
                >
                  <span className="tag tag-neutral" style={{ padding: '0 5px', fontSize: 10 }}>{message.role}</span>
                  <span style={{ fontFamily: mono, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{messageLabel(message, t.emptyMessage)}</span>
                  {flagged.includes(index) && <span aria-hidden style={{ color: '#c0392b' }}>●</span>}
                </button>
              )
            })}
            {open && !readOnly && (
              <button type="button" className="text-muted" onClick={onAddMessage} style={{ ...rowButton, fontSize: 12, padding: '4px 14px 6px 34px' }}>{t.addMessageShort}</button>
            )}
          </div>
        )
      })}

      <div style={{ flex: 1 }} />
      <div data-testid="tree-files" className="text-muted" style={{ padding: '10px 14px', borderTop: '1px solid var(--color-divider)', fontSize: 11 }}>
        {t.promptFiles}: <span style={{ fontFamily: mono }}>{files.length ? files.join(', ') : '—'}</span>
      </div>
    </nav>
  )
}
```
`aria-current` must render the string `"true"`; React renders `aria-current={true}` as `"true"`, which the test expects.

- [ ] **Step 4: Run to verify it passes**

Run: `cd frontend && npx vitest run src/components/prompt/PromptTree.test.tsx && npx tsc -b`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/prompt/PromptTree.tsx frontend/src/components/prompt/PromptTree.test.tsx
git commit -m "feat(webui): Add the prompt editor variant and message tree"
```

---

### Task 5: MessagePane (replaces MessageList)

**Files:**
- Create: `frontend/src/components/prompt/MessagePane.tsx`
- Test: `frontend/src/components/prompt/MessagePane.test.tsx`
- Delete: `frontend/src/components/MessageList.tsx`, `frontend/src/components/MessageList.test.tsx` — only after porting (Step 1). `PromptEditor.tsx` still imports `MessageList` until Task 8, so do the deletion in Task 8's Step 3, not here.

**Interfaces:**
- Consumes: `CodeEditor`, `CodeEditorHandle` (Task 2); `messagePath` (Task 1)
- Produces:
```ts
export function MessagePane(props: {
  path: string                       // messagePath(...)
  message: PromptMessageDoc
  index: number
  count: number
  readOnly: boolean
  lang?: Lang
  diagnostics?: LintError[]
  insertable: string[]               // ['agent.defect', 'vars.tone']
  editorRef: React.Ref<CodeEditorHandle>
  onRemove: () => void
  onMove: (to: number) => void
  onRole: (role: MessageRole) => void
  onContent: (content: string) => void
  onSource: (source: MessageSource) => void
  onFile: (file: string) => void
}): JSX.Element
```
Labels stay exactly as today (`t.messageRole`, `t.messageSourceLabel`, `t.messageFileLabel`, `t.moveUp`, `t.moveDown`), and the editor's accessible name stays `editorLabel(message)` (role, or `role (file)`) so existing screen tests' `getByLabelText('user')` keeps working.

- [ ] **Step 1: Write the failing test (port + new cases)**

Create `MessagePane.test.tsx` with the `CodeEditor` mock from Task 2 (path `'../CodeEditor'`). Port **every** `it` in `components/MessageList.test.tsx` that concerns one row — role change, source switch, file rename, unreadable file alert + disabled source select, read-only rendering, move up/down visibility at the ends, remove, diagnostics reaching the editor — by rendering `<MessagePane index={i} count={n} message={messages[i]} …/>` for the row under test instead of `<MessageList messages={…}/>`, and asserting the same callback arguments minus the index (e.g. `onRole('assistant')` instead of `onRole(1, 'assistant')`). Drop the list-level cases (Add message button, rendering N rows) — the tree owns those now (Task 4). Then add:

```tsx
  it('shows where the message text lives', () => {
    setup({ path: 'prompts/de/explainer/sys.jinja' })
    expect(screen.getByText('prompts/de/explainer/sys.jinja')).toBeInTheDocument()
  })

  it('inserts the chosen variable through the editor handle, then resets the picker', async () => {
    const onContent = vi.fn()
    setup({ onContent, message: inline('Hi '), insertable: ['agent.defect'] })
    await userEvent.selectOptions(screen.getByLabelText('Insert variable…'), 'agent.defect')
    expect(onContent).toHaveBeenCalledWith('Hi {{ agent.defect }}')
    expect(screen.getByLabelText('Insert variable…')).toHaveValue('')
  })

  it('offers no variable picker when read-only', () => {
    setup({ readOnly: true })
    expect(screen.queryByLabelText('Insert variable…')).not.toBeInTheDocument()
  })

  it('offers no variable picker for an unreadable file', () => {
    setup({ message: { role: 'system', source: 'file', file: 'gone.jinja', content: '', readable: false } })
    expect(screen.queryByLabelText('Insert variable…')).not.toBeInTheDocument()
  })
```
`setup()` renders `MessagePane` with a real `createRef<CodeEditorHandle>()` as `editorRef`.

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/components/prompt/MessagePane.test.tsx`
Expected: FAIL — cannot resolve `./MessagePane`.

- [ ] **Step 3: Implement**

Move `ROLES` and `editorLabel` (with its comment) from `MessageList.tsx` into `MessagePane.tsx`. The pane is a column that fills its parent:

```tsx
import type { Ref } from 'react'
import type { LintError, MessageRole, MessageSource, PromptMessageDoc } from '../../api/types'
import { useTranslations, type Lang } from '../../i18n'
import { CodeEditor, type CodeEditorHandle } from '../CodeEditor'

// ROLES + editorLabel moved verbatim from MessageList.tsx

const small = { minHeight: 26, padding: '1px 6px', fontSize: 12, width: 'auto' }

export function MessagePane({ path, message, index, count, readOnly, lang = 'de', diagnostics, insertable, editorRef, onRemove, onMove, onRole, onContent, onSource, onFile }: { /* as Interfaces */ }) {
  const t = useTranslations(lang)
  const roleId = `message-${index}-role`
  const sourceId = `message-${index}-source`
  const fileId = `message-${index}-file`
  const insertId = `message-${index}-insert`
  const unreadableId = `message-${index}-unreadable`
  const editable = !readOnly && message.readable

  return (
    <div data-testid="message-pane" style={{ flex: 1, minWidth: 0, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 12px', borderBottom: '1px solid var(--color-divider)', fontSize: 12, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: 'ui-monospace, Menlo, monospace' }}>{path}</span>
        <label htmlFor={roleId} className="sr-only">{t.messageRole}</label>
        <select className="input" id={roleId} disabled={readOnly} value={message.role} onChange={(e) => onRole(e.target.value as MessageRole)} style={small}>
          {ROLES.map((role) => <option key={role} value={role}>role: {role}</option>)}
        </select>
        {/* source select, file input, unreadable handling: carried over from MessageRow
            with the SAME ids, labels and the I3 comment -- restyled with `small`. */}
        <div style={{ flex: 1 }} />
        {editable && (
          <>
            <label htmlFor={insertId} className="sr-only">{t.insertVar}</label>
            <select
              className="input"
              id={insertId}
              value=""
              style={small}
              onChange={(event) => {
                const name = event.target.value
                if (!name) return
                const handle = typeof editorRef === 'object' && editorRef ? editorRef.current : null
                handle?.insert(`{{ ${name} }}`)
              }}
            >
              <option value="">{t.insertVar}</option>
              {insertable.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </>
        )}
        {!readOnly && index > 0 && <button type="button" className="btn btn-ghost" style={{ fontSize: 12 }} onClick={() => onMove(index - 1)}>{t.moveUp}</button>}
        {!readOnly && index < count - 1 && <button type="button" className="btn btn-ghost" style={{ fontSize: 12 }} onClick={() => onMove(index + 1)}>{t.moveDown}</button>}
        {!readOnly && <button type="button" className="btn btn-ghost" style={{ fontSize: 12, color: '#a33a2b' }} onClick={onRemove}>{t.deleteMessage}</button>}
      </div>
      {!message.readable && message.file && (
        <span id={unreadableId} role="alert" style={{ fontSize: 11, color: '#a33a2b', padding: '4px 12px' }}>
          {t.messageUnreadable} <code>{message.file}</code>
        </span>
      )}
      <div style={{ flex: 1, minHeight: 0 }}>
        <CodeEditor ref={editorRef} fill value={message.content} onChange={onContent} diagnostics={diagnostics} readOnly={readOnly} ariaLabel={editorLabel(message)} />
      </div>
    </div>
  )
}
```
Check `industry.css` for an existing visually-hidden class (`grep -n "sr-only\|visually-hidden" frontend/src/styles/*.css`); if none exists, keep the visible labels as small muted text (`<label … className="text-muted" style={{ fontSize: 11 }}>`) instead of inventing a class. "Delete message" replaces `t.remove` on this button — update the ported remove test to `getByRole('button', { name: 'Delete message' })`.

- [ ] **Step 4: Run to verify it passes**

Run: `cd frontend && npx vitest run src/components/prompt/MessagePane.test.tsx && npx tsc -b`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/prompt/MessagePane.tsx frontend/src/components/prompt/MessagePane.test.tsx
git commit -m "feat(webui): Add the single-message prompt editor pane"
```

---

### Task 6: MetaPane + VariantPane

**Files:**
- Create: `frontend/src/components/prompt/MetaPane.tsx`, `frontend/src/components/prompt/VariantPane.tsx`
- Test: `frontend/src/components/prompt/MetaPane.test.tsx`, `frontend/src/components/prompt/VariantPane.test.tsx`

**Interfaces:**
- Produces:
```ts
export function MetaPane(props: {
  draft: PromptDocument
  readOnly: boolean
  defaultVariantIssue: string | null    // saveErrorMessage when saveFieldError.kind === 'default_variant'
  lang?: Lang
  onHeader: (field: 'name' | 'summary' | 'description' | 'default_model' | 'default_variant', value: string) => void
}): JSX.Element

export function VariantPane(props: {
  variant: PromptVariantDoc
  readOnly: boolean
  lang?: Lang
  onRename: (to: string) => void
  onModel: (model: string | null) => void
  onRemove: () => void
  onAddVar: (key: string) => void
  onEditVar: (key: string, decl: PromptVarDecl) => void
  onRemoveVar: (key: string) => void
}): JSX.Element
```

- [ ] **Step 1: Write the failing tests**

`MetaPane.test.tsx`:
```tsx
// DOC: copy the `DOC` constant from screens/PromptEditor.test.tsx
it('edits every header field', async () => {
  const onHeader = vi.fn()
  render(<MetaPane draft={DOC} readOnly={false} defaultVariantIssue={null} lang="en" onHeader={onHeader} />)
  await userEvent.type(screen.getByLabelText('Summary'), '!')
  expect(onHeader).toHaveBeenLastCalledWith('summary', 'Explains defects!')
  await userEvent.selectOptions(screen.getByLabelText('Default variant'), 'Quick')
  expect(onHeader).toHaveBeenLastCalledWith('default_variant', 'Quick')
})

it('marks default_variant with the server issue', () => {
  render(<MetaPane draft={DOC} readOnly={false} defaultVariantIssue="default_variant 'X' is not a variant" lang="en" onHeader={vi.fn()} />)
  expect(screen.getByLabelText('Default variant')).toHaveAttribute('aria-invalid', 'true')
  expect(screen.getByRole('alert')).toHaveTextContent("default_variant 'X'")
})

it('is read-only for a non-admin', () => {
  render(<MetaPane draft={DOC} readOnly defaultVariantIssue={null} lang="en" onHeader={vi.fn()} />)
  expect(screen.getByLabelText('Name')).toHaveAttribute('readonly')
  expect(screen.getByLabelText('Default variant')).toBeDisabled()
})
```
`VariantPane.test.tsx`:
```tsx
const V = DOC.variants[0]
it('renames, sets the model and removes', async () => {
  const props = { onRename: vi.fn(), onModel: vi.fn(), onRemove: vi.fn(), onAddVar: vi.fn(), onEditVar: vi.fn(), onRemoveVar: vi.fn() }
  render(<VariantPane variant={V} readOnly={false} lang="en" {...props} />)
  await userEvent.type(screen.getByLabelText('Variant name'), 'X')
  expect(props.onRename).toHaveBeenLastCalledWith('ThoroughX')
  await userEvent.type(screen.getByLabelText('Variant model'), 'g')
  expect(props.onModel).toHaveBeenLastCalledWith('g')
  await userEvent.click(screen.getByRole('button', { name: /^remove$/i }))
  expect(props.onRemove).toHaveBeenCalled()
  expect(screen.getAllByTestId('var-row')).toHaveLength(1)
})

it('sends a cleared model as null', async () => {
  const onModel = vi.fn()
  render(<VariantPane variant={{ ...V, model: 'm' }} readOnly={false} lang="en" onRename={vi.fn()} onModel={onModel} onRemove={vi.fn()} onAddVar={vi.fn()} onEditVar={vi.fn()} onRemoveVar={vi.fn()} />)
  await userEvent.clear(screen.getByLabelText('Variant model'))
  expect(onModel).toHaveBeenLastCalledWith(null)
})

it('shows only the declarations for a non-admin', () => {
  render(<VariantPane variant={V} readOnly lang="en" onRename={vi.fn()} onModel={vi.fn()} onRemove={vi.fn()} onAddVar={vi.fn()} onEditVar={vi.fn()} onRemoveVar={vi.fn()} />)
  expect(screen.queryByLabelText('Variant name')).not.toBeInTheDocument()
  expect(screen.getAllByTestId('var-row')).toHaveLength(1)
})
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd frontend && npx vitest run src/components/prompt/MetaPane.test.tsx src/components/prompt/VariantPane.test.tsx`
Expected: FAIL — modules not found.

- [ ] **Step 3: Implement**

`MetaPane.tsx`: move the `Header` helper (with its `fullRow` prop) and the default-variant `<select>` block out of `PromptEditor.tsx` verbatim — same ids (`prompt-name`, `prompt-summary`, `prompt-description`, `prompt-default-model`, `prompt-default-variant`, `default-variant-issue`), same `aria-invalid`/`aria-describedby` logic, `data-testid="prompt-header"` on the root. The `setSaveFieldError(null)` side effect of the select stays in `PromptEditor` (it wraps `onHeader` for `default_variant`). Root style, per the prototype:
```ts
{ padding: '20px 24px', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '16px 24px', maxWidth: 900, alignContent: 'start', overflow: 'auto' }
```

`VariantPane.tsx`: move the `isAdmin && selectedVariantObj` "variant-actions" block (name input, model input, Remove button — same ids `variant-name`, `variant-model`, `data-testid="variant-actions"`) and render `<VarDeclTable vars={variant.vars} readOnly={readOnly} lang={lang} onAdd={onAddVar} onEdit={onEditVar} onRemove={onRemoveVar} />` under it. Root: `{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 16, overflow: 'auto' }` with an `h4` showing `t.variantSettings · {variant.name}`. The model input calls `onModel(event.target.value || null)`.

- [ ] **Step 4: Run to verify they pass**

Run: `cd frontend && npx vitest run src/components/prompt && npx tsc -b`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/prompt/MetaPane.* frontend/src/components/prompt/VariantPane.*
git commit -m "feat(webui): Add prompt.yaml and variant settings panes"
```

---

### Task 7: EditorToolbar

**Files:**
- Create: `frontend/src/components/prompt/EditorToolbar.tsx`
- Test: `frontend/src/components/prompt/EditorToolbar.test.tsx`

**Interfaces:**
- Consumes: `usePromptTree()` (existing, `api/queries.ts`); `EditorLayout` (Task 2)
- Produces:
```ts
export function EditorToolbar(props: {
  docLang: string
  agentKey: string
  path: string                  // `prompts/${draft.file}`
  variants: string[]
  selectedVariant: string
  layout: EditorLayout
  canSave: boolean
  showSave: boolean             // isAdmin
  lang?: Lang
  onVariant: (name: string) => void
  onLayout: (next: EditorLayout) => void
  onSave: () => void
}): JSX.Element
```
Language/agent selects call `useNavigate()` to `/admin/prompts/${encodeURIComponent(lang)}/${encodeURIComponent(agent)}` (D9). Their values are always the route's `docLang`/`agentKey`, so a blocked navigation leaves them unchanged. Options come from `usePromptTree()`: languages = `tree.languages.map(l => l.lang)`; agents = the current language's `prompts` where `ok` (a broken prompt cannot be opened), label `name ?? agent`. Switching language keeps the agent when that language has it, else picks that language's first `ok` prompt.

- [ ] **Step 1: Write the failing test**

`frontend/src/components/prompt/EditorToolbar.test.tsx`:
```tsx
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createMemoryRouter, RouterProvider, useParams } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { PromptTreeResponse } from '../../api/types'
import { EditorToolbar } from './EditorToolbar'

const TREE: PromptTreeResponse = { languages: [
  { lang: 'de', prompts: [
    { agent: 'explainer', file: 'de/explainer/prompt.yaml', name: 'Explainer', variants: ['Thorough', 'Quick'], ok: true, error: null, used_by: [] },
    { agent: 'broken', file: 'de/broken/prompt.yaml', name: null, variants: [], ok: false, error: 'bad yaml', used_by: [] },
  ] },
  { lang: 'en', prompts: [
    { agent: 'reviewer', file: 'en/reviewer/prompt.yaml', name: 'Reviewer', variants: ['A'], ok: true, error: null, used_by: [] },
  ] },
] }

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) =>
    url === '/admin/api/prompts'
      ? ({ ok: true, status: 200, json: async () => TREE } as Response)
      : ({ ok: false, status: 404, json: async () => ({ detail: 'no' }) } as Response)))
})
afterEach(() => vi.unstubAllGlobals())

function setup(overrides: Partial<Parameters<typeof EditorToolbar>[0]> = {}) {
  const props = {
    path: 'prompts/de/explainer/prompt.yaml', variants: ['Thorough', 'Quick'], selectedVariant: 'Thorough',
    layout: 'split' as const, canSave: true, showSave: true, lang: 'en' as const,
    onVariant: vi.fn(), onLayout: vi.fn(), onSave: vi.fn(), ...overrides,
  }
  function Screen() {
    const { lang = '', agent = '' } = useParams()
    return (
      <>
        <EditorToolbar docLang={lang} agentKey={agent} {...props} />
        <div data-testid="params">{lang}/{agent}</div>
      </>
    )
  }
  const router = createMemoryRouter([{ path: '/admin/prompts/:lang/:agent', element: <Screen /> }], {
    initialEntries: ['/admin/prompts/de/explainer'],
  })
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return props
}

describe('EditorToolbar', () => {
  it('offers only prompts that parse, with the current one selected', async () => {
    setup()
    const agent = await screen.findByLabelText('Agent')
    await within(agent).findByRole('option', { name: 'Explainer' })
    expect(within(agent).queryByRole('option', { name: 'broken' })).not.toBeInTheDocument()
    expect(agent).toHaveValue('explainer')
  })

  it('switching language falls back to that language’s first prompt', async () => {
    setup()
    const language = await screen.findByLabelText('Language')
    await within(language).findByRole('option', { name: 'en' })
    await userEvent.selectOptions(language, 'en')
    expect(await screen.findByTestId('params')).toHaveTextContent('en/reviewer')
  })

  it('steps through variants and disables the ends', async () => {
    const props = setup()
    expect(screen.getByRole('button', { name: 'Previous variant' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Next variant' }))
    expect(props.onVariant).toHaveBeenCalledWith('Quick')
  })

  it('switches layout', async () => {
    const props = setup()
    await userEvent.click(screen.getByLabelText('Tabs'))
    expect(props.onLayout).toHaveBeenCalledWith('tabs')
  })

  it('disables Save when there is nothing saveable', () => {
    setup({ canSave: false })
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
  })

  it('hides Save for a non-admin', () => {
    setup({ showSave: false })
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/components/prompt/EditorToolbar.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```tsx
import { useNavigate } from 'react-router-dom'
import { usePromptTree } from '../../api/queries'
import { useTranslations, type Lang } from '../../i18n'
import type { EditorLayout } from '../../state/editorLayout'

const compact = { width: 'auto', minHeight: 32, padding: '3px 8px', fontSize: 13 }

export function EditorToolbar({ docLang, agentKey, path, variants, selectedVariant, layout, canSave, showSave, lang = 'de', onVariant, onLayout, onSave }: { /* as Interfaces */ }) {
  const t = useTranslations(lang)
  const navigate = useNavigate()
  const tree = usePromptTree()
  const languages = tree.data?.languages ?? []
  const agentsFor = (code: string) => (languages.find((l) => l.lang === code)?.prompts ?? []).filter((p) => p.ok)
  const go = (code: string, agent: string) => navigate(`/admin/prompts/${encodeURIComponent(code)}/${encodeURIComponent(agent)}`)
  const index = variants.indexOf(selectedVariant)

  return (
    <div data-testid="editor-toolbar" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px', borderBottom: '1px solid var(--color-divider)', flexWrap: 'wrap' }}>
      <h3 style={{ margin: 0, fontSize: 22 }}>{t.prompts}</h3>
      <select className="input" aria-label={t.promptLanguage} style={compact} value={docLang}
        onChange={(e) => {
          const code = e.target.value
          const agents = agentsFor(code)
          const next = agents.some((p) => p.agent === agentKey) ? agentKey : agents[0]?.agent
          if (next) go(code, next)
        }}>
        {/* keep the current value selectable while the tree loads */}
        {(languages.length ? languages.map((l) => l.lang) : [docLang]).map((code) => <option key={code} value={code}>{code}</option>)}
      </select>
      <select className="input" aria-label={t.promptAgent} style={compact} value={agentKey} onChange={(e) => go(docLang, e.target.value)}>
        {(agentsFor(docLang).length ? agentsFor(docLang) : [{ agent: agentKey, name: null }]).map((p) => (
          <option key={p.agent} value={p.agent}>{p.name ?? p.agent}</option>
        ))}
      </select>
      <div style={{ display: 'flex', alignItems: 'center', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-sm)', overflow: 'hidden' }}>
        <button type="button" className="btn btn-ghost" aria-label={t.prevVariant} title={t.prevVariant} disabled={index <= 0} onClick={() => onVariant(variants[index - 1])} style={{ padding: '0 8px', minHeight: 30, border: 0, borderRadius: 0 }}>‹</button>
        <select className="input" aria-label={t.variants} value={selectedVariant} onChange={(e) => onVariant(e.target.value)}
          style={{ width: 'auto', minHeight: 30, border: 0, borderRadius: 0, borderLeft: '1px solid var(--color-border)', borderRight: '1px solid var(--color-border)', padding: '2px 8px', fontSize: 13, fontWeight: 600 }}>
          {variants.map((name) => <option key={name} value={name}>{name}</option>)}
        </select>
        <button type="button" className="btn btn-ghost" aria-label={t.nextVariant} title={t.nextVariant} disabled={index < 0 || index >= variants.length - 1} onClick={() => onVariant(variants[index + 1])} style={{ padding: '0 8px', minHeight: 30, border: 0, borderRadius: 0 }}>›</button>
      </div>
      <span className="text-muted" style={{ fontFamily: 'ui-monospace, Menlo, monospace', fontSize: 12 }}>{path}</span>
      <div style={{ flex: 1 }} />
      <div className="seg">
        <label className="seg-opt" style={{ padding: '4px 10px' }}>
          <input type="radio" name="prompt-layout" checked={layout === 'split'} onChange={() => onLayout('split')} />{t.layoutSplit}
        </label>
        <label className="seg-opt" style={{ padding: '4px 10px' }}>
          <input type="radio" name="prompt-layout" checked={layout === 'tabs'} onChange={() => onLayout('tabs')} />{t.layoutTabs}
        </label>
      </div>
      {showSave && <button type="button" className="btn btn-primary" disabled={!canSave} onClick={onSave}>{t.save}</button>}
    </div>
  )
}
```
Verify `--color-border` and `--radius-sm` exist: `grep -n "\-\-color-border\|\-\-radius-sm" frontend/src/styles/industry.css`. If either is missing, use `var(--color-divider)` / `0`.

- [ ] **Step 4: Run to verify it passes**

Run: `cd frontend && npx vitest run src/components/prompt/EditorToolbar.test.tsx && npx tsc -b`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/prompt/EditorToolbar.*
git commit -m "feat(webui): Add the prompt editor toolbar"
```

---

### Task 8: Assemble the Split workbench in PromptEditor

**Files:**
- Modify: `frontend/src/screens/PromptEditor.tsx` (render section, lines ~399–756; state section gains `selection`, `layout`, `editorRef`)
- Modify: `frontend/src/screens/PromptEditor.test.tsx`
- Delete: `frontend/src/components/MessageList.tsx`, `frontend/src/components/MessageList.test.tsx`

**Interfaces:**
- Consumes: everything from Tasks 1–7.

State added to `PromptEditor` (above the loading guards — hook order, see the existing comment at line ~208):
```ts
const [selection, setSelection] = useState<Selection>({ kind: 'message', index: 0 })
const [layout, setLayout] = useEditorLayout()
const editorRef = useRef<CodeEditorHandle>(null)
```
In the `reset` effect, also `setSelection({ kind: 'message', index: 0 })`.

Derived after `messages` is computed:
```ts
// A message selection that no longer points at a message (empty variant, or
// an index past the end after a remove) shows the variant settings instead --
// never an undefined message.
const current: Selection =
  selection.kind === 'message' && !messages[selection.index] ? { kind: 'variant' } : selection
const currentMessage = current.kind === 'message' ? messages[current.index] : undefined
const used = currentMessage ? usedTemplateVars(currentMessage.content) : []
const agentVars = Object.keys(original.agent_context_skeleton ?? {}).map((k) => `agent.${k}`)
const declaredVars = Object.keys(vars).map((k) => `vars.${k}`)
const undeclared = undeclaredVars(used, Object.keys(vars))
const flagged = Object.keys(diagnostics).map(Number)
```

Handlers (replace the old inline ones; keep every existing comment that explains a rule, moving it next to its new home):
- `pickVariant(name)`: `setSelectedVariant(name); clearDiagnostics(); setSelection({ kind: 'message', index: 0 })`
- `openVariantSettings(name)`: `setSelectedVariant(name); clearDiagnostics(); setSelection({ kind: 'variant' })`
- `addVariant()`: `const name = uniqueVariantName(t.newVariantDefault, draft.variants.map((v) => v.name)); dispatch({ type: 'addVariant', name }); openVariantSettings(name)`
- `addMessage()`: `dispatch({ type: 'addMessage', variant: variantName }); setSelection({ kind: 'message', index: messages.length })`
- `removeMessage(index)`: dispatch `removeMessage`; `clearDiagnostics()`; `setSelection(index > 0 ? { kind: 'message', index: index - 1 } : messages.length > 1 ? { kind: 'message', index: 0 } : { kind: 'variant' })`
- `moveMessage(from, to)`: dispatch `moveMessage`; `clearDiagnostics()`; `setSelection({ kind: 'message', index: to })` (the selection follows the moved message)
- `declareUndeclared()`: `undeclared.forEach((key) => dispatch({ type: 'addVar', variant: variantName, key }))`
- `insert(text)`: `editorRef.current?.insert(text)`
- The `newVariantName` state and its input are removed (D7).

Render (Split):
```tsx
<div data-testid="prompt-editor" style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 52px)', minHeight: 600 }}>
  <EditorToolbar docLang={docLang} agentKey={agentKey} path={`prompts/${draft.file}`}
    variants={draft.variants.map((v) => v.name)} selectedVariant={variantName}
    layout={layout} onLayout={setLayout} onVariant={pickVariant}
    showSave={isAdmin} canSave={dirty && emptyEnumVariants.length === 0} onSave={openConfirm} lang={lang} />
  {document.isError && /* existing background-refetch alert, padded 6px 16px */}
  {saveFieldError?.kind === 'emptyVariants' && saveErrorMessage && /* existing alert, padded 6px 16px */}
  {layout === 'split' ? (
    <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
      <PromptTree … flagged={flagged} selection={current} selectedVariant={variantName} readOnly={!isAdmin} />
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>
          {current.kind === 'meta' && <MetaPane … />}
          {current.kind === 'variant' && selectedVariantObj && <VariantPane … />}
          {current.kind === 'variant' && selectedVariantObj && messages.length === 0 && (
            <div className="text-muted" style={{ padding: '20px 24px', fontSize: 13 }}>{t.noMessages}</div>
          )}
          {currentMessage && current.kind === 'message' && (
            <>
              <MessagePane key={`${variantName}:${current.index}`} editorRef={editorRef}
                path={messagePath(draft.file, variantName, current.index, currentMessage)}
                message={currentMessage} index={current.index} count={messages.length}
                readOnly={!isAdmin} lang={lang} diagnostics={diagnostics[current.index]}
                insertable={[...agentVars, ...declaredVars]} … />
              <VarSidebar agentVars={agentVars} declaredVars={declaredVars} used={used} undeclared={undeclared}
                canInsert={isAdmin && currentMessage.readable} canDeclare={isAdmin}
                lint={{ running: linting, checked: lintChecked, error: lintError, errors: diagnostics[current.index] ?? [] }}
                onInsert={insert} onDeclare={declareUndeclared} onLint={() => void runLint()} lang={lang} />
            </>
          )}
        </div>
        <div data-testid="preview-pane" style={{ height: 300, flex: 'none', borderTop: '1px solid var(--color-divider)', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(420px, 100%), 1fr))', gap: 16, padding: '10px 14px', overflow: 'auto' }}>
          <RenderPreview messages={messages} vars={sampleVars(vars)} skeleton={original.agent_context_skeleton ?? {}} isAdmin={isAdmin} lang={lang} />
          <TestRunPanel messages={messages} vars={sampleVars(vars)} agentContext={original.agent_context_skeleton ?? {}} isAdmin={isAdmin} lang={lang} />
        </div>
      </div>
    </div>
  ) : (
    <TabsLayout … />   /* Task 9; until then render the split branch for both values */
  )}
  {/* SavePromptDialog + unsaved-navigation Modal: unchanged */}
</div>
```
`MessagePane` is keyed by `variant:index` so switching messages remounts `CodeEditor` cleanly (fresh undo history per message — the pane only ever holds one). `runLint` is unchanged: it still lints every message of the selected variant, which is what feeds the tree's red dots.

- [ ] **Step 1: Update the screen tests first (they fail against the old layout)**

In `PromptEditor.test.tsx`, add helpers after `renderEditor`:
```ts
const openMeta = () => userEvent.click(screen.getByRole('button', { name: /prompt\.yaml/ }))
const openVariantSettings = (name: string) => userEvent.click(screen.getByRole('button', { name: `Variant settings: ${name}` }))
const openMessage = (label: RegExp) => userEvent.click(within(screen.getByTestId('prompt-tree')).getByRole('button', { name: label }))
```
Then, mechanically:
- Before every `getByLabelText('Summary' | 'Name' | 'Description' | 'Default model' | 'Default variant')`: `await openMeta()`.
- Before every `getByLabelText('Variant name' | 'Variant model')` and `getByTestId('variant-actions')`: `await openVariantSettings('<selected variant>')`; `getByRole('button', { name: /^remove$/i })` for a variant → same.
- `getAllByTestId('message-row')` → count tree message buttons: `within(screen.getByTestId('prompt-tree')).getAllByRole('button', { name: /^(system|user|assistant)/ })`.
- A test that edits message N's text → `await openMessage(/<its label>/)` then `getByLabelText('<role>')`.
- `getByRole('button', { name: 'Thorough' | 'Quick' })` (variant chips) now hit the tree's variant buttons — unchanged.
- `'adds a variant'`: click `getByRole('button', { name: 'New variant' })`, then assert `getByLabelText('Variant name')` has value `'New variant'`.
- Lint tests: the Lint button now lives in the var sidebar (open a message first — the default selection already is message 0). Diagnostics for a message other than the open one show as `aria-invalid="true"` on its tree button, not as an alert; assert that way.
- Move tests: `getAllByRole('button', { name: /move (up|down)/i })` applies to the open message only; open the message first.

Add the Review-Focus cases. Extend the file's `fetchMock` with the tree (place it ABOVE the generic `GET /admin/api/prompts/` branch):
```ts
if (method === 'GET' && url === '/admin/api/prompts') {
  return ok({ languages: [{ lang: 'de', prompts: [
    { agent: 'explainer', file: 'de/explainer/prompt.yaml', name: 'Explainer', variants: ['Thorough', 'Quick'], ok: true, error: null, used_by: [] },
    { agent: 'other', file: 'de/other/prompt.yaml', name: 'Other', variants: ['A'], ok: true, error: null, used_by: [] },
  ] }] })
}
```
```tsx
describe('workbench navigation', () => {
  const tree = () => within(screen.getByTestId('prompt-tree'))

  it('shows the variant settings when the selected variant has no messages', async () => {
    docBody = { ...DOC, variants: [DOC.variants[0], { ...DOC.variants[1], messages: [] }] }
    renderEditor({ lang: 'en' })
    await ready()
    await userEvent.click(tree().getByRole('button', { name: 'Quick' }))
    expect(screen.getByTestId('variant-actions')).toBeInTheDocument()
    expect(screen.getByText('This variant has no messages.')).toBeInTheDocument()
  })

  it('moves the selection to the previous message after removing the open one', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    await openMessage(/Explain/)
    await userEvent.click(screen.getByRole('button', { name: 'Delete message' }))
    expect(tree().getByRole('button', { name: /sys\.jinja/ })).toHaveAttribute('aria-current', 'true')
    expect(tree().queryByRole('button', { name: /Explain/ })).not.toBeInTheDocument()
  })

  it('keeps the renamed variant selected while typing', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    await openVariantSettings('Thorough')
    await userEvent.type(screen.getByLabelText('Variant name'), 'X')
    expect(screen.getByLabelText('Variants')).toHaveValue('ThoroughX')
    expect(tree().getByRole('button', { name: 'ThoroughX' })).toHaveAttribute('aria-expanded', 'true')
  })

  it('keeps the current agent selected when a dirty navigation is cancelled', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    await openMeta()
    await userEvent.type(screen.getByLabelText('Summary'), '!')
    const agent = screen.getByLabelText('Agent')
    await within(agent).findByRole('option', { name: 'Other' })
    await userEvent.selectOptions(agent, 'other')
    expect(await screen.findByRole('heading', { name: /unsaved changes/i })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /^cancel$/i }))
    expect(screen.getByLabelText('Agent')).toHaveValue('explainer')
    expect(screen.getByLabelText('Summary')).toHaveValue('Explains defects!')
  })

  it('declares an undeclared variable from the sidebar', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    await openMessage(/Explain/)
    await userEvent.type(screen.getByLabelText('user'), ' {{{{ vars.depth }}')
    await userEvent.click(within(screen.getByTestId('var-sidebar')).getByRole('button', { name: 'declare' }))
    await openVariantSettings('Thorough')
    expect(screen.getAllByTestId('var-row')).toHaveLength(2)
  })

  it('inserts a variable at the cursor from the sidebar', async () => {
    renderEditor({ lang: 'en' })
    await ready()
    await openMessage(/Explain/)
    await userEvent.click(within(screen.getByTestId('var-sidebar')).getByRole('button', { name: /vars\.tone/ }))
    expect(screen.getByLabelText('user')).toHaveValue('Explain {{ agent.defect }}{{ vars.tone }}')
  })
})
```
(`{{{{` is `user-event`'s escape for a literal `{{`. The unsaved-changes heading is `t.unsavedNavTitle`; the existing blocker tests already match it with `/unsaved changes/i`.)

- [ ] **Step 2: Run to verify the updated tests fail**

Run: `cd frontend && npx vitest run src/screens/PromptEditor.test.tsx`
Expected: FAIL — no `prompt-tree`, no `Variant settings:` buttons.

- [ ] **Step 3: Implement**

Rewrite the render section of `PromptEditor.tsx` as above; delete `MessageList.tsx` and `MessageList.test.tsx`; delete the `Header` helper (moved to `MetaPane` in Task 6) and the `newVariantName` state.

- [ ] **Step 4: Run to verify everything passes**

Run: `cd frontend && npx vitest run && npx tsc -b`
Expected: all PASS, no type errors. Also `grep -rn "MessageList" frontend/src` → no hits.

- [ ] **Step 5: Commit**

```bash
git add -A frontend/src
git commit -m "feat(webui): Lay the prompt editor out as the prototype's workbench"
```

---

### Task 9: Tabs layout

**Files:**
- Create: `frontend/src/components/prompt/TabsLayout.tsx`
- Test: `frontend/src/components/prompt/TabsLayout.test.tsx`
- Modify: `frontend/src/screens/PromptEditor.tsx` (the `layout === 'tabs'` branch), `frontend/src/screens/PromptEditor.test.tsx`

**Interfaces:**
- Consumes: `MessagePane`, `MetaPane`, `VariantPane` elements built by `PromptEditor` (passed in as `ReactNode`s so both layouts share one wiring), `LintState`, `Selection`, `messageLabel`.
- Produces:
```ts
export type DrawerTab = 'vars' | 'preview' | 'test'
export function TabsLayout(props: {
  messages: PromptMessageDoc[]
  selection: Selection
  flagged: number[]
  readOnly: boolean
  centre: ReactNode            // MetaPane / VariantPane / MessagePane for `selection`
  variablesDrawer: ReactNode   // VarSidebar content + VarDeclTable (declarations editable here, as in the prototype)
  preview: ReactNode           // <RenderPreview …/>
  testRun: ReactNode           // <TestRunPanel …/>
  status: { lint: LintState; usedDeclared: number; declared: number; undeclared: number }
  lang?: Lang
  onOpenMeta: () => void
  onPickMessage: (index: number) => void
  onAddMessage: () => void
  onLint: () => void
}): JSX.Element
```
Drawer tab state lives inside `TabsLayout` (`useState<DrawerTab>('vars')`).

To reuse `VarSidebar` inside the drawer without its 230px column chrome, give `VarSidebar` a `variant?: 'column' | 'drawer'` prop: `'drawer'` drops `width`, `borderLeft` and `background`, and hides the lint block (the status bar shows lint in Tabs mode). Add one `VarSidebar` test: `variant="drawer"` renders no Lint button.

- [ ] **Step 1: Write the failing test**

`frontend/src/components/prompt/TabsLayout.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { PromptMessageDoc } from '../../api/types'
import { TabsLayout } from './TabsLayout'

const MESSAGES: PromptMessageDoc[] = [
  { role: 'system', source: 'file', file: 'sys.jinja', content: 'x', readable: true },
  { role: 'user', source: 'inline', file: null, content: 'Explain it', readable: true },
]
const clean = { running: false, checked: true, error: null, errors: [] }

function setup(overrides: Partial<Parameters<typeof TabsLayout>[0]> = {}) {
  const props = {
    messages: MESSAGES, selection: { kind: 'message' as const, index: 0 }, flagged: [], readOnly: false,
    centre: <div>CENTRE</div>, variablesDrawer: <div>VARIABLES</div>, preview: <div>PREVIEW</div>, testRun: <div>TESTRUN</div>,
    status: { lint: clean, usedDeclared: 1, declared: 2, undeclared: 0 }, lang: 'en' as const,
    onOpenMeta: vi.fn(), onPickMessage: vi.fn(), onAddMessage: vi.fn(), onLint: vi.fn(), ...overrides,
  }
  render(<TabsLayout {...props} />)
  return props
}

describe('TabsLayout', () => {
  it('renders prompt.yaml plus one tab per message, and picks them', async () => {
    const props = setup()
    expect(screen.getByRole('button', { name: /sys\.jinja/ })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: /Explain it/ }))
    expect(props.onPickMessage).toHaveBeenCalledWith(1)
    await userEvent.click(screen.getByRole('button', { name: 'prompt.yaml' }))
    expect(props.onOpenMeta).toHaveBeenCalled()
    expect(screen.getByText('CENTRE')).toBeInTheDocument()
  })

  it('marks a flagged message tab', () => {
    setup({ flagged: [0] })
    expect(screen.getByRole('button', { name: /sys\.jinja/ })).toHaveAttribute('aria-invalid', 'true')
  })

  it('switches the drawer between Variables, Preview and Test run', async () => {
    setup()
    expect(screen.getByText('VARIABLES')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Preview' }))
    expect(screen.getByText('PREVIEW')).toBeInTheDocument()
    expect(screen.queryByText('VARIABLES')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Test run' }))
    expect(screen.getByText('TESTRUN')).toBeInTheDocument()
  })

  it('shows lint and usage in the status bar, and runs lint', async () => {
    const props = setup()
    expect(screen.getByText(/No syntax errors\./)).toBeInTheDocument()
    expect(screen.getByText('1/2 declared vars used · 0 undeclared')).toBeInTheDocument()
    expect(screen.getByText('jinja · UTF-8')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /^lint$/i }))
    expect(props.onLint).toHaveBeenCalled()
  })

  it('shows lint errors by line in the status bar', () => {
    setup({ status: { lint: { ...clean, errors: [{ line: 2, column: 1, message: 'bad' }] }, usedDeclared: 0, declared: 0, undeclared: 0 } })
    expect(screen.getByText('Line 2: bad')).toBeInTheDocument()
  })

  it('hides + message in a read-only session', () => {
    setup({ readOnly: true })
    expect(screen.queryByRole('button', { name: '+ message' })).not.toBeInTheDocument()
  })
})
```
Render the usage note as ONE text node — `` {`${usedDeclared}/${declared} ${t.varsUsed} · ${undeclared} ${t.undeclaredCount}`} `` — and each lint error as one node — `` {`${t.lintLine} ${e.line}: ${e.message}`} `` — so the exact-text assertions match.

Screen-level (`PromptEditor.test.tsx`): one test that clicks the `Tabs` radio, expects `queryByTestId('prompt-tree')` to be absent and a `prompt.yaml` tab present, then reloads (unmount + `renderEditor` again) and expects Tabs to persist.

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/components/prompt/TabsLayout.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Structure (styles from the prototype's Tabs branch, "Prototype reference" §3):
```tsx
<div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
  <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
    <div role="tablist"-free strip style={{ display: 'flex', alignItems: 'flex-end', gap: 2, padding: '8px 16px 0', borderBottom: '1px solid var(--color-divider)', flexWrap: 'wrap' }}>
      {/* prompt.yaml tab, then per message: <span className="text-muted">{i + 1}</span> role tag, monospace messageLabel, red ● when flagged;
          each a <button aria-pressed={current}> — plain toggle buttons, NOT role="tab", for the same reason
          the old variant chips' comment gives (no roving focus / tabpanel wiring). Active tab:
          background var(--color-bg), border-bottom 1px solid var(--color-bg), margin-bottom -1px;
          inactive: background var(--color-surface). */}
      {!readOnly && <button className="btn btn-ghost" style={{ fontSize: 12, marginBottom: 2 }} onClick={onAddMessage}>{t.addMessageShort}</button>}
    </div>
    <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>{centre}</div>
    <div style={{ display: 'flex', gap: 16, alignItems: 'center', padding: '5px 12px', borderTop: '1px solid var(--color-divider)', background: 'var(--color-surface)', fontSize: 12 }}>
      {/* ✓ lintClean (green) | "Line n: msg" (red) | lint.error (red, role=alert) */}
      <span className="text-muted">{usedDeclared}/{declared} {t.varsUsed} · {undeclared} {t.undeclaredCount}</span>
      <div style={{ flex: 1 }} />
      <span className="text-muted">jinja · UTF-8</span>
    </div>
  </div>
  <aside style={{ width: 340, flex: 'none', borderLeft: '1px solid var(--color-divider)', background: 'var(--color-surface)', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
    <div style={{ display: 'flex', borderBottom: '1px solid var(--color-divider)', fontSize: 12 }}>
      {/* three buttons (t.drawerVariables, t.previewPane, t.testRun), flex 1, padding 9px 0,
          borderBottom 2px solid (active ? var(--color-accent) : transparent), opacity active ? 1 : .7, aria-pressed */}
    </div>
    <div style={{ padding: 12, overflow: 'auto', flex: 1 }}>{tab === 'vars' ? variablesDrawer : tab === 'preview' ? preview : testRun}</div>
  </aside>
</div>
```
In `PromptEditor`, build `centre`, `preview`, `testRun` once and hand them to whichever layout is active; the Lint button in Tabs mode is the status bar's first item (`<button type="button" className="btn btn-ghost" style={{ fontSize: 12, padding: '0 6px' }} disabled={status.lint.running} onClick={onLint}>{t.lint}</button>`), wired to `runLint`.

- [ ] **Step 4: Run to verify**

Run: `cd frontend && npx vitest run && npx tsc -b`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/prompt frontend/src/screens/PromptEditor.*
git commit -m "feat(webui): Add the prompt editor's Tabs layout"
```

---

### Task 10: Preview fixtures and side-by-side visual check

**Files:**
- Modify: `frontend/src/dev/preview.tsx` (`FIXTURES`)

- [ ] **Step 1: Add fixtures**

Add to `FIXTURES`:
- `'/admin/api/prompts'`: the tree from Task 7's test (languages `de` with `test_case_set_reviewer` ok, `en` with one ok prompt).
- `'/admin/api/prompts/de/test_case_set_reviewer'`: a `PromptDocument` with two variants ("Gründlich" with a file-backed system message `gruendlich_system.jinja` and an inline user message `Prüfe {{ agent.test_case_set }} im Ton {{ vars.tone }}`, declaring `tone`; "Kompakt" with one inline message), `agent_context_skeleton: { test_case_set: '', test_cases: [], project_name: '' }`.
Confirm the exact document URL by reading `usePromptDocument` in `frontend/src/api/queries.ts` first.

- [ ] **Step 2: Run the preview and compare**

Run: `cd frontend && npx vite --open /admin/preview.html` (check `preview.html`'s script path if the URL differs), navigate to `/admin/prompts/de/test_case_set_reviewer`.
Compare against the prototype at 1440×900 and 1280×800, both layouts, light and dark theme: toolbar row, 250px tree, message toolbar, 230px var sidebar, bottom pane, Tabs drawer. Note any mismatch not listed under "Deviations" and fix it in the owning component.

- [ ] **Step 3: Full verification**

Run: `cd frontend && npx tsc -b && npx vitest run && npm run build`
Expected: all pass; build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/dev/preview.tsx
git commit -m "chore(webui): Add prompt editor fixtures to the preview harness"
```
