import { useEffect, useReducer, useRef, useState } from 'react'
import { useBlocker, useParams } from 'react-router-dom'
import type { Scope } from '../api/agents'
import { ApiError } from '../api/client'
import { useLintTemplate, usePlanPrompt, useSavePrompt } from '../api/mutations'
import { agentsUsingVariant } from '../api/prompts'
import { useConfig, usePromptDocument } from '../api/queries'
import type { LintError, PromptDocument, PromptVarDecl } from '../api/types'
import type { CodeEditorHandle } from '../components/CodeEditor'
import { Modal } from '../components/Modal'
import { EditorToolbar } from '../components/prompt/EditorToolbar'
import { MessagePane } from '../components/prompt/MessagePane'
import { MetaPane } from '../components/prompt/MetaPane'
import { PromptTree } from '../components/prompt/PromptTree'
import { messagePath, uniqueVariantName, type Selection } from '../components/prompt/selection'
import { undeclaredVars, usedTemplateVars } from '../components/prompt/templateVars'
import { VariantPane } from '../components/prompt/VariantPane'
import { VarSidebar } from '../components/prompt/VarSidebar'
import { RenderPreview } from '../components/RenderPreview'
import { SavePromptDialog } from '../components/SavePromptDialog'
import { TestRunPanel } from '../components/TestRunPanel'
import { useTranslations, type Lang, type Translations } from '../i18n'
import { useEditorLayout } from '../state/editorLayout'
import { isDirty, promptDraftReducer } from '../state/promptDraft'

function emptyDocument(lang: string, agent: string): PromptDocument {
  return {
    lang,
    agent,
    file: '',
    name: '',
    summary: null,
    description: null,
    default_model: '',
    default_variant: '',
    variants: [],
    agent_context_skeleton: {},
  }
}

/**
 * A loaded document, defensively defaulted field by field.
 *
 * A 200 response is not the same guarantee as one shaped the way
 * `PromptDocument` says -- the same lesson Task 14 relearned for the prompt
 * tree. This is dispatched into the reducer as the `reset` document, so it
 * also protects every reducer branch (`removeVariant` assumes at least one
 * survives, `renameVariant` walks `variants`, ...) from ever seeing a
 * missing field, not only the render below.
 */
function normalizeDocument(doc: PromptDocument, lang: string, agent: string): PromptDocument {
  return {
    lang: doc.lang ?? lang,
    agent: doc.agent ?? agent,
    file: doc.file ?? '',
    name: doc.name ?? '',
    summary: doc.summary ?? null,
    description: doc.description ?? null,
    default_model: doc.default_model ?? '',
    default_variant: doc.default_variant ?? '',
    variants: doc.variants ?? [],
    agent_context_skeleton: doc.agent_context_skeleton ?? {},
  }
}

/**
 * Sample values a render preview can send: each declared default.
 *
 * A var with no `default_value` is OMITTED, never sent as `null`.
 * `RenderRequest.vars` is `dict[str, PromptVarValue]` (`str | bool | int |
 * float`), so a single `null` 422s the whole request -- and FastAPI's 422
 * `detail` is a list, which `apiFetch` cannot render, so the operator would
 * see only "Request failed with status 422" for four of this repo's eight
 * prompts. Left out, `StrictUndefined` reports the missing variable against
 * the one message that actually uses it, which is the useful feedback.
 */
function sampleVars(vars: Record<string, PromptVarDecl>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [key, decl] of Object.entries(vars)) {
    if (decl.default_value === null || decl.default_value === undefined) continue
    out[key] = decl.default_value
  }
  return out
}

/**
 * Every variant holding an enum var with no `choices`, by name.
 *
 * `PromptVariableDefinition.validate_choices` refuses an empty `choices` on an
 * enum, so such a document round-trips to a 422. Design §6 says the form
 * "enforces both edges": `VarDeclTable` already shows the row-level alert, and
 * this is what stops Save from firing a request that cannot succeed. Walks
 * EVERY variant, not just the selected one -- the save sends all of them.
 */
function variantsWithEmptyEnum(doc: PromptDocument): string[] {
  return doc.variants
    .filter((variant) =>
      Object.values(variant.vars ?? {}).some(
        (decl) => decl.value_type === 'enum' && (decl.choices ?? []).length === 0,
      ),
    )
    .map((variant) => variant.name)
}

/** What `PUT /prompts/{lang}/{agent}` actually accepts -- the draft minus its read-only metadata. */
function toSaveRequest(doc: PromptDocument) {
  return {
    name: doc.name,
    summary: doc.summary,
    description: doc.description,
    default_model: doc.default_model,
    default_variant: doc.default_variant,
    variants: doc.variants,
  }
}

type SaveFieldError = { kind: 'default_variant' } | { kind: 'emptyVariants'; names: string[] }

/**
 * Which control a 422's message names, so the form can mark it.
 *
 * `build_write_set`'s validation errors are prose, not field-addressed JSON
 * (unlike `config/apply`'s `ConfigIssue` list). This recognizes the two cases
 * that both name something concrete AND correspond to a single control on
 * this screen: an out-of-range `default_variant` (the header select), and a
 * variant with no messages (its tree row) -- reachable because this screen lets
 * a variant's last message be removed, and `PromptTree`/this screen's own test
 * suite exercise a variant that loads with zero messages already.
 *
 * Deliberately not a general parser: matching English server prose is
 * brittle by construction. Any 422 this does not recognize still surfaces
 * verbatim in the confirm dialog -- it is simply not pinned to one control.
 */
function fieldFromSaveError(message: string): SaveFieldError | null {
  if (message.startsWith('default_variant')) return { kind: 'default_variant' }
  const empty = /^Every variant needs at least one message\. Empty: (.+)$/.exec(message)
  if (empty) return { kind: 'emptyVariants', names: empty[1].split(', ').map((s) => s.trim()) }
  return null
}

/** Localizes one `agentsUsingVariant` scope. Only the project name (a wire
 * token, like an agent key) stays untranslated. */
function referenceLabel(t: Translations, scope: Scope): string {
  return scope.kind === 'global' ? t.orphanGlobalTable : `${t.orphanProjectPrefix} '${scope.project}'`
}

export function PromptEditor({ lang = 'de', isAdmin }: { lang?: Lang; isAdmin: boolean }) {
  const t = useTranslations(lang)
  // The route's own `:lang` names the PROMPT FILE's language (which
  // `prompts_dir/<lang>/` a save reads and writes) -- unrelated to the `lang`
  // prop above, which is the console's own display language.
  const { lang: docLang = '', agent: agentKey = '' } = useParams()

  const document = usePromptDocument(docLang || undefined, agentKey || undefined)
  const config = useConfig()
  const save = useSavePrompt(docLang, agentKey)
  const plan = usePlanPrompt(docLang, agentKey)
  const lint = useLintTemplate()

  const [draft, dispatch] = useReducer(promptDraftReducer, undefined, () =>
    emptyDocument(docLang, agentKey),
  )
  const [selectedVariant, setSelectedVariant] = useState<string | null>(null)
  // What the centre pane shows. A message index is into the SELECTED
  // variant's own message list, like `diagnostics` below.
  const [selection, setSelection] = useState<Selection>({ kind: 'message', index: 0 })
  const [layout, setLayout] = useEditorLayout()
  // The one open message's editor -- the sidebar inserts at its cursor.
  const editorRef = useRef<CodeEditorHandle>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [saveFieldError, setSaveFieldError] = useState<SaveFieldError | null>(null)
  // Per-message lint results for the CURRENTLY SELECTED variant, keyed by
  // that variant's own message index -- what feeds the tree's red dots and
  // the open message's editor. Cleared on a variant switch (an index means
  // something different in a different variant's message list) and on a
  // document reset, so
  // nothing here ever survives being stale or belonging to the wrong variant.
  const [diagnostics, setDiagnosticsMap] = useState<Record<number, LintError[]>>({})
  const [linting, setLinting] = useState(false)
  const [lintChecked, setLintChecked] = useState(false)
  // Why the last lint run produced no results: a 403, a 500, a dropped
  // connection. Without it a failed request just stopped the spinner and said
  // nothing, unlike every other action on this screen.
  const [lintError, setLintError] = useState<string | null>(null)

  /** Every prior lint result is invalid: a variant switch, a document reset,
   * a removed message, or a reordering (`diagnostics` is keyed by index, so
   * a shifted index would otherwise annotate a message that never produced
   * that error -- worse than no marker at all). `lintChecked` goes with it,
   * so a stale "no syntax errors" cannot survive either. */
  const clearDiagnostics = () => {
    setDiagnosticsMap({})
    setLintChecked(false)
    setLintError(null)
  }

  /** Only the edited message's own result is invalid -- the operator changed
   * exactly that text, so every OTHER message's still-correct result (and
   * still points at the right message, since editing content changes no
   * index) is worth keeping rather than discarding wholesale. */
  const dropDiagnostic = (index: number) => {
    setDiagnosticsMap((current) => {
      if (!(index in current)) return current
      const next = { ...current }
      delete next[index]
      return next
    })
    setLintChecked(false)
  }
  // The normalized document the reducer was last `reset` from -- what the
  // draft is diffed against. NOT `document.data` directly: on the very render
  // where the query first resolves, `document.data` is already the loaded
  // document but `draft` is still whatever `useReducer` held before (the
  // initial empty document, or a previous agent's), because the `reset`
  // dispatch below only takes effect one render later. Diffing against
  // `document.data` in that single transient render reads as "dirty" against
  // a draft that has not actually been touched -- long enough to spuriously
  // arm the unsaved-changes warning. This ref is set in the SAME effect that
  // dispatches `reset`, so it and `draft` always change together.
  const originalRef = useRef<PromptDocument | null>(null)

  // Every hook above this line runs on every render of this instance,
  // including the loading -> loaded transition below: this screen stays
  // mounted across it, and a hook called only on some renders of the same
  // instance corrupts React's hook order -- a hard crash ("Rendered more
  // hooks than during the previous render"), not a lint nit. That is exactly
  // what phase 3's AgentDetail hit. So the reducer is seeded from an effect
  // rather than a hook moved below the guards, and every value the JSX below
  // needs is derived from `document.data ?? undefined`, never assumed present.
  useEffect(() => {
    if (!document.data) return
    const normalized = normalizeDocument(document.data, docLang, agentKey)
    originalRef.current = normalized
    dispatch({ type: 'reset', document: normalized })
    setSelection({ kind: 'message', index: 0 })
    clearDiagnostics()
  }, [document.data, docLang, agentKey])

  const original = originalRef.current
  const dirty = original ? isDirty(original, draft) : false

  // Warns on a tab close or refresh. `useBlocker` below covers an IN-APP
  // navigation instead -- neither is a router navigation, so this effect is
  // still needed alongside it, not superseded by it.
  useEffect(() => {
    if (!dirty) return
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = t.unsavedChangesWarning
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [dirty, t.unsavedChangesWarning])

  // Blocks an IN-APP navigation (a `<Link>`/`NavLink` click elsewhere in the
  // console) the same way the effect above blocks a tab close or refresh.
  // Needs a data router -- see main.tsx and dev/preview.tsx, both switched to
  // `createBrowserRouter`/`RouterProvider` for this. `beforeunload` above is
  // kept alongside this, not replaced by it: `useBlocker` has no say over a
  // tab close or a refresh, since neither is a router navigation.
  const blocker = useBlocker(dirty)

  // `document.isLoading` is only true on the FIRST load. A failed refetch
  // after this screen's own successful save (`useSavePrompt`'s
  // `invalidateQueries`) sets `document.isError` while `document.data` still
  // holds the last good document -- react-query does not clear `data` just
  // because a background refetch failed. Treating `isError` as fatal here
  // would replace the whole editor, unsaved edits included, with an error
  // page over a refetch the operator never asked for. Only the absence of any
  // successfully loaded document is fatal.
  if (document.isLoading) return <div style={{ padding: 28 }}>…</div>
  if (!document.data) {
    const detail = (document.error as Error)?.message
    return (
      <div role="alert" style={{ padding: 28 }}>
        <div>{t.promptDocError}</div>
        {detail && (
          <div className="text-muted" style={{ fontSize: 12, marginTop: 4 }}>
            {detail}
          </div>
        )}
      </div>
    )
  }
  // A document loaded, but the `reset` effect above has not yet run against
  // it (see `originalRef`'s own comment) -- without this guard, this render
  // would paint the OLD draft (the initial empty document, or a previous
  // agent's) under the NEW document's header for exactly one frame.
  if (!original) return <div style={{ padding: 28 }}>…</div>

  const disk = config.data?.disk ?? {}

  const selectedName = selectedVariant ?? draft.default_variant
  // Never `variants[0]` unguarded: an empty list (or a stale selection after
  // a rename) must fall back to `undefined`, not throw.
  const selectedVariantObj = draft.variants.find((v) => v.name === selectedName) ?? draft.variants[0]
  const variantName = selectedVariantObj?.name ?? ''
  const vars = selectedVariantObj?.vars ?? {}
  const messages = selectedVariantObj?.messages ?? []

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

  // Names the draft dropped since the load -- renamed away or removed
  // outright -- mirrored against `config.disk` exactly as the server's own
  // guard (§5.5) will, so the operator sees the same refusal *before*
  // confirming rather than only after a 409.
  //
  // Narrower than the server's own check, by construction: this only walks
  // variant names that were present in the LOADED document, so a
  // `config.toml` entry pointing at a variant this document never contained
  // (a stale reference, or a typo) gets no client-side warning here -- only
  // the server's 409 catches that case. Acceptable: it is the server that is
  // authoritative, and this is a best-effort warning ahead of it, not a
  // replacement for it.
  const orphanWarnings = original.variants
    .map((v) => v.name)
    .filter((name) => !draft.variants.some((v) => v.name === name))
    .map((name) => ({ name, referencedBy: agentsUsingVariant(disk, agentKey, name) }))
    .filter((entry) => entry.referencedBy.length > 0)

  const saveErrorMessage =
    save.isError && save.error instanceof ApiError ? save.error.message : null
  const planErrorMessage =
    plan.isError && plan.error instanceof ApiError ? plan.error.message : null

  // Any variant -- not only the selected one -- holding an enum var with no
  // choices. The save sends every variant, so any one of them 422s it.
  const emptyEnumVariants = variantsWithEmptyEnum(draft)

  /**
   * Which control a 422 names, whichever of the two requests it came from.
   *
   * A plan refusal and a save refusal both run `build_write_set`'s
   * validation, so both 422 with the same prose -- routing them through the
   * same marker keeps the form's field-level feedback identical regardless
   * of which request happened to fail.
   */
  const markSaveError = (error: unknown) => {
    if (error instanceof ApiError && error.status === 422) {
      setSaveFieldError(fieldFromSaveError(error.message))
    } else {
      setSaveFieldError(null)
    }
  }

  // Save no longer opens the dialog on the strength of the browser's own
  // guess at what will change -- it asks the server what saving WOULD do,
  // and the dialog renders that answer once it arrives (D8: only the server
  // can name a deletion).
  const openConfirm = () => {
    setConfirmOpen(true)
    plan.mutate(toSaveRequest(draft), {
      onSuccess: () => setSaveFieldError(null),
      onError: markSaveError,
    })
  }

  const confirmSave = () => {
    save.mutate(toSaveRequest(draft), {
      onSuccess: () => {
        setConfirmOpen(false)
        setSaveFieldError(null)
      },
      onError: markSaveError,
    })
  }

  const closeConfirm = () => {
    setConfirmOpen(false)
    // A stale 422 marker must not survive past the dialog the operator saw
    // it in -- reopening Save on an unrelated later edit would otherwise
    // still show the old server text and an invalid `default_variant`.
    setSaveFieldError(null)
  }

  /**
   * Lints every message of the SELECTED variant, on demand.
   *
   * Not per-keystroke and not on blur: `POST /prompts/lint` is a real
   * network round trip, and `CodeEditor` is deliberately free of behaviour
   * (Task 10's ruling) -- it exposes no blur hook to drive lint-on-blur from
   * without giving that finished, tested component a new job. A single
   * button lints the whole variant in one action, matching how Save and
   * Render are already the screen's other on-demand actions. Open to a
   * non-admin: `POST /prompts/lint` is session-gated, not admin-gated
   * (unlike render), so a read-only operator must still be able to run it.
   */
  const runLint = async () => {
    setLinting(true)
    setLintChecked(false)
    setLintError(null)
    try {
      const results = await Promise.all(messages.map((message) => lint.mutateAsync(message.content)))
      const next: Record<number, LintError[]> = {}
      results.forEach((result, index) => {
        if (result.errors.length > 0) next[index] = result.errors
      })
      setDiagnosticsMap(next)
      setLintChecked(true)
    } catch (error) {
      // A 403, a 500 or a dropped connection. Surfaced the way
      // `RenderPreview` surfaces its own mutation error -- the message from
      // the failure itself, not a generic one. Any partial result is dropped:
      // `Promise.all` rejects on the first failure, so the results that did
      // arrive cover an unknown subset of the messages, and a diagnostics map
      // missing entries reads exactly like "these messages are clean".
      setDiagnosticsMap({})
      setLintError((error as Error)?.message || t.lintFailed)
    } finally {
      setLinting(false)
    }
  }

  const pickVariant = (name: string) => {
    setSelectedVariant(name)
    // A message index means something different in a different variant's
    // own message list.
    clearDiagnostics()
    setSelection({ kind: 'message', index: 0 })
  }

  const openVariantSettings = (name: string) => {
    setSelectedVariant(name)
    clearDiagnostics()
    setSelection({ kind: 'variant' })
  }

  const addVariant = () => {
    const name = uniqueVariantName(t.newVariantDefault, draft.variants.map((v) => v.name))
    dispatch({ type: 'addVariant', name })
    openVariantSettings(name)
  }

  const addMessage = () => {
    dispatch({ type: 'addMessage', variant: variantName })
    setSelection({ kind: 'message', index: messages.length })
  }

  const removeMessage = (index: number) => {
    dispatch({ type: 'removeMessage', variant: variantName, index })
    // Every remaining entry's index now names a different message than the
    // one it was computed for -- clearing is honest; remapping would be
    // guessing which message shifted where.
    clearDiagnostics()
    setSelection(
      index > 0
        ? { kind: 'message', index: index - 1 }
        : messages.length > 1
          ? { kind: 'message', index: 0 }
          : { kind: 'variant' },
    )
  }

  const moveMessage = (from: number, to: number) => {
    dispatch({ type: 'moveMessage', variant: variantName, index: from, to })
    clearDiagnostics()
    // The selection follows the moved message.
    setSelection({ kind: 'message', index: to })
  }

  const declareUndeclared = () => {
    undeclared.forEach((key) => dispatch({ type: 'addVar', variant: variantName, key }))
  }

  const insert = (text: string) => {
    editorRef.current?.insert(text)
  }

  // Kept here rather than inline in `MetaPane`: only this screen owns the
  // 422 marker it clears.
  const setHeader = (
    field: 'name' | 'summary' | 'description' | 'default_model' | 'default_variant',
    value: string,
  ) => {
    // Clears a stale 422 marker the moment the operator actually edits the
    // field it was marking -- otherwise it would persist (with the old server
    // text) past a fix that has already made it wrong.
    if (field === 'default_variant') setSaveFieldError(null)
    dispatch({ type: 'setHeader', field, value })
  }

  const alertStyle = { fontSize: 12, color: '#a33a2b', padding: '6px 16px' }

  // Task 9 adds the Tabs layout; until then both `layout` values render Split.
  const split = (
    <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
      <PromptTree
        variants={draft.variants}
        selectedVariant={variantName}
        selection={current}
        flagged={flagged}
        invalidVariants={saveFieldError?.kind === 'emptyVariants' ? saveFieldError.names : []}
        readOnly={!isAdmin}
        lang={lang}
        onOpenMeta={() => setSelection({ kind: 'meta' })}
        onPickVariant={pickVariant}
        onOpenVariantSettings={openVariantSettings}
        onPickMessage={(index) => setSelection({ kind: 'message', index })}
        onAddVariant={addVariant}
        onAddMessage={addMessage}
      />
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>
          {current.kind === 'meta' && (
            <MetaPane
              draft={draft}
              readOnly={!isAdmin}
              // A plan 422 marks the field too (both requests funnel through
              // `markSaveError`), so fall back to the plan's own message --
              // `MetaPane` only sets `aria-invalid` when it has text to show.
              defaultVariantIssue={
                saveFieldError?.kind === 'default_variant'
                  ? (saveErrorMessage ?? planErrorMessage)
                  : null
              }
              lang={lang}
              onHeader={setHeader}
            />
          )}
          {current.kind === 'variant' && selectedVariantObj && (
            <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', overflow: 'auto' }}>
              {messages.length === 0 && (
                <div className="text-muted" style={{ padding: '20px 24px 0', fontSize: 13 }}>
                  {t.noMessages}
                </div>
              )}
              <VariantPane
                variant={selectedVariantObj}
                readOnly={!isAdmin}
                lang={lang}
                onRename={(to) => {
                  dispatch({ type: 'renameVariant', from: selectedVariantObj.name, to })
                  // The selection is resolved BY NAME, so it has to follow the
                  // rename. Without this, the first keystroke makes the old
                  // name unresolvable, the selection falls through to
                  // `variants[0]`, and every later keystroke renames THAT
                  // variant instead -- leaving the intended one named after
                  // whatever the field held when the fall-through happened.
                  setSelectedVariant(to)
                }}
                onModel={(model) =>
                  dispatch({ type: 'setVariantModel', variant: selectedVariantObj.name, model })
                }
                onRemove={() => dispatch({ type: 'removeVariant', name: selectedVariantObj.name })}
                onAddVar={(key) => dispatch({ type: 'addVar', variant: variantName, key })}
                onEditVar={(key, decl) => dispatch({ type: 'editVar', variant: variantName, key, decl })}
                onRemoveVar={(key) => dispatch({ type: 'removeVar', variant: variantName, key })}
              />
            </div>
          )}
          {currentMessage && current.kind === 'message' && (
            <>
              {/* Keyed by variant and index so switching messages remounts
                  `CodeEditor` cleanly -- a fresh undo history per message,
                  since the pane only ever holds one. */}
              <MessagePane
                key={`${variantName}:${current.index}`}
                editorRef={editorRef}
                path={messagePath(draft.file, variantName, current.index, currentMessage)}
                message={currentMessage}
                index={current.index}
                count={messages.length}
                readOnly={!isAdmin}
                lang={lang}
                diagnostics={diagnostics[current.index]}
                insertable={[...agentVars, ...declaredVars]}
                onRemove={() => removeMessage(current.index)}
                onMove={(to) => moveMessage(current.index, to)}
                onRole={(role) =>
                  dispatch({ type: 'setMessageRole', variant: variantName, index: current.index, role })
                }
                onContent={(content) => {
                  dispatch({ type: 'setMessageContent', variant: variantName, index: current.index, content })
                  // Only THIS message's own result is invalid -- it changed no
                  // index, so every other message's result still points correctly.
                  dropDiagnostic(current.index)
                }}
                onSource={(source) =>
                  dispatch({ type: 'setMessageSource', variant: variantName, index: current.index, source })
                }
                onFile={(file) =>
                  dispatch({ type: 'setMessageFile', variant: variantName, index: current.index, file })
                }
              />
              <VarSidebar
                agentVars={agentVars}
                declaredVars={declaredVars}
                used={used}
                undeclared={undeclared}
                canInsert={isAdmin && currentMessage.readable}
                canDeclare={isAdmin}
                lint={{
                  running: linting,
                  checked: lintChecked,
                  error: lintError,
                  errors: diagnostics[current.index] ?? [],
                }}
                onInsert={insert}
                onDeclare={declareUndeclared}
                onLint={() => void runLint()}
                lang={lang}
              />
            </>
          )}
        </div>
        <div
          data-testid="preview-pane"
          style={{
            height: 300,
            flex: 'none',
            borderTop: '1px solid var(--color-divider)',
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(min(420px, 100%), 1fr))',
            gap: 16,
            padding: '10px 14px',
            overflow: 'auto',
          }}
        >
          <RenderPreview
            messages={messages}
            vars={sampleVars(vars)}
            skeleton={original.agent_context_skeleton ?? {}}
            isAdmin={isAdmin}
            lang={lang}
          />
          <TestRunPanel
            messages={messages}
            vars={sampleVars(vars)}
            agentContext={original.agent_context_skeleton ?? {}}
            isAdmin={isAdmin}
            lang={lang}
          />
        </div>
      </div>
    </div>
  )

  return (
    <div
      data-testid="prompt-editor"
      style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 52px)', minHeight: 600 }}
    >
      {/* Blocked, not merely flagged: design §6 has the form enforce both
          edges, and an enum with no `choices` is refused by
          `PromptVariableDefinition.validate_choices`, so Save could only
          ever produce a 422. `VarDeclTable` already renders the row-level
          alert that says why. */}
      <EditorToolbar
        docLang={docLang}
        agentKey={agentKey}
        path={`prompts/${draft.file}`}
        variants={draft.variants.map((v) => v.name)}
        selectedVariant={variantName}
        layout={layout}
        onLayout={setLayout}
        onVariant={pickVariant}
        showSave={isAdmin}
        canSave={dirty && emptyEnumVariants.length === 0}
        onSave={openConfirm}
        lang={lang}
      />

      {/* A background refetch failure (e.g. the tree/document invalidation
          this screen's own successful save triggers) -- NOT the fatal
          load-failure guard above, which only fires when no document has
          ever loaded. The draft stays exactly as it was. */}
      {document.isError && (
        <div role="alert" style={alertStyle}>
          {t.promptDocError}
        </div>
      )}
      {saveFieldError?.kind === 'emptyVariants' && saveErrorMessage && (
        <div role="alert" style={alertStyle}>
          {saveErrorMessage}
        </div>
      )}

      {split}

      {confirmOpen && (
        <SavePromptDialog
          plan={plan.data ?? null}
          error={planErrorMessage ?? saveErrorMessage}
          pending={save.isPending || plan.isPending}
          onCancel={closeConfirm}
          onConfirm={confirmSave}
          lang={lang}
        >
          {orphanWarnings.length > 0 && (
            <div role="alert" style={{ fontSize: 12, color: '#a33a2b', display: 'flex', flexDirection: 'column', gap: 4 }}>
              {orphanWarnings.map((entry) => (
                <div key={entry.name} data-testid={`orphan-${entry.name}`}>
                  {t.confirmSaveOrphanWarning} {entry.name} —{' '}
                  {entry.referencedBy.map((scope) => referenceLabel(t, scope)).join(', ')}
                </div>
              ))}
            </div>
          )}
        </SavePromptDialog>
      )}

      {blocker.state === 'blocked' && (
        <Modal label={t.unsavedNavTitle} width={480}>
          <h3 style={{ margin: 0 }}>{t.unsavedNavTitle}</h3>
          <div style={{ fontSize: 13 }}>{t.unsavedNavBody}</div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button type="button" className="btn btn-secondary" onClick={() => blocker.reset?.()}>
              {t.cancel}
            </button>
            <button type="button" className="btn btn-primary" onClick={() => blocker.proceed?.()}>
              {t.leaveAnyway}
            </button>
          </div>
        </Modal>
      )}
    </div>
  )
}
