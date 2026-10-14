import { useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { useBlocker, useParams } from 'react-router-dom'
import { Button } from 'primereact/button'
import { Message } from 'primereact/message'
import type { Scope } from '../api/agents'
import { ApiError } from '../api/client'
import { useLintTemplate, usePlanPrompt, useSavePrompt } from '../api/mutations'
import { agentContextOf, agentsUsingVariant, emptyMessage } from '../api/prompts'
import { useConfig, usePromptDocument } from '../api/queries'
import type { LintError, PromptDocument, PromptMessageDoc, PromptVarDecl } from '../api/types'
import type { CodeEditorHandle } from '../components/CodeEditor'
import { Modal } from '../components/Modal'
import { EditorTabs, type EditorTab } from '../components/prompt/EditorTabs'
import { EditorToolbar } from '../components/prompt/EditorToolbar'
import { MessagePane } from '../components/prompt/MessagePane'
import { MetaPane } from '../components/prompt/MetaPane'
import { PaneResizer } from '../components/prompt/PaneResizer'
import { PromptTree } from '../components/prompt/PromptTree'
import { useLiveLint } from '../components/prompt/liveLint'
import { messageLabel, messagePath, uniqueVariantName, type Selection } from '../components/prompt/selection'
import { undeclaredVars, usedTemplateVars } from '../components/prompt/templateVars'
import { VariantPane } from '../components/prompt/VariantPane'
import { VarSidebar, type LintState } from '../components/prompt/VarSidebar'
import { RenderPreview } from '../components/RenderPreview'
import { SavePromptDialog } from '../components/SavePromptDialog'
import { TestRunPanel } from '../components/TestRunPanel'
import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'
import { MIN_PANE_HEIGHT, usePaneHeight } from '../state/editorLayout'
import { closeTab, messageTabOf, openTab, pinTab, useEditorTabs, type TabId } from '../state/editorTabs'
import {
  isDirty,
  isMessageDirty,
  isMetaDirty,
  isVariantDirty,
  newMessageUid,
  promptDraftReducer,
  withMessageUids,
  withoutMessageUids,
} from '../state/promptDraft'

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
    agent_context_sample: doc.agent_context_sample ?? {},
  }
}

/**
 * Sample values a render preview can send: each declared default.
 *
 * A var with no `default_value` is never sent as `null`.
 * `RenderRequest.vars` is `dict[str, PromptVarValue]` (`str | bool | int |
 * float`), so a single `null` 422s the whole request -- and FastAPI's 422
 * `detail` is a list, which `apiFetch` cannot render, so the operator would
 * see only "Request failed with status 422" for four of this repo's eight
 * prompts.
 *
 * An OPTIONAL var with no default is sent as the value it effectively has at
 * runtime: `build_prompt_utils` renders with a lenient `Environment`, where a
 * missing var is falsy and renders empty, so `false` for a boolean and `""`
 * otherwise. Without this, the preview's `StrictUndefined` fails a plain
 * `{% if vars.validate_output %}` that the agent renders fine.
 *
 * A REQUIRED var with no default is OMITTED, so `StrictUndefined` reports it
 * against the one message that actually uses it, which is the useful feedback.
 */
function sampleVars(vars: Record<string, PromptVarDecl>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [key, decl] of Object.entries(vars)) {
    if (decl.default_value !== null && decl.default_value !== undefined) {
      out[key] = decl.default_value
    } else if (!decl.required) {
      out[key] = decl.value_type === 'boolean' ? false : ''
    }
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
    variants: withoutMessageUids(doc.variants),
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
 * variant with no messages (its tree row). Not reachable by removing messages
 * -- the reducer keeps a variant's last one and Delete message is hidden there
 * -- and a newly added variant starts with one (`emptyVariant`); only a
 * variant that LOADED with zero messages (`PromptTree`/this screen's own test
 * suite exercise that) can still be saved empty.
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
function referenceLabel(t: TFunction, scope: Scope): string {
  return scope.kind === 'global' ? t('orphanGlobalTable') : t('orphanProject', { project: scope.project })
}

/** The variant the centre pane works on. Never `variants[0]` unguarded: an
 * empty list (or a stale selection after a rename) falls back to
 * `undefined`, not a throw. */
function selectedVariantOf(draft: PromptDocument, selected: string | null) {
  const name = selected ?? draft.default_variant
  return draft.variants.find((v) => v.name === name) ?? draft.variants[0]
}

function withoutIndex(set: ReadonlySet<number>, index: number): ReadonlySet<number> {
  if (!set.has(index)) return set
  const next = new Set(set)
  next.delete(index)
  return next
}

export function PromptEditor({ isAdmin }: { isAdmin: boolean }) {
  const { t } = useTranslation()
  // The route's own `:lang` names the PROMPT FILE's language (which
  // `prompts_dir/<lang>/` a save reads and writes) -- unrelated to the
  // console's own display language, which i18next holds.
  const { lang: docLang = '', agent: agentKey = '' } = useParams()

  const document = usePromptDocument(docLang || undefined, agentKey || undefined)
  const config = useConfig()
  const save = useSavePrompt(docLang, agentKey)
  const plan = usePlanPrompt(docLang, agentKey)
  const lint = useLintTemplate()

  const [draft, dispatch] = useReducer(promptDraftReducer, undefined, () =>
    emptyDocument(docLang, agentKey),
  )
  const draftRef = useRef(draft)
  draftRef.current = draft
  const [selectedVariant, setSelectedVariant] = useState<string | null>(null)
  // The open editor tabs, per variant. The active one is what the centre
  // pane shows (`current` below).
  const tabsState = useEditorTabs()
  const [paneHeight, setPaneHeight] = usePaneHeight()
  const splitColumnRef = useRef<HTMLDivElement>(null)
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
  // Which message indices `diagnostics` holds a current result for, clean or
  // not -- by the button (every message) or the live check (the open one).
  // "No syntax errors" is only ever claimed for text in here.
  const [checked, setChecked] = useState<ReadonlySet<number>>(new Set())
  // Bumped by every wholesale invalidation, so the live check re-runs on the
  // open message even when neither its text nor its index changed (a save's
  // reload, a reorder that kept it in place).
  const [lintEpoch, setLintEpoch] = useState(0)
  // Why the last lint run produced no results: a 403, a 500, a dropped
  // connection. Without it a failed request just stopped the spinner and said
  // nothing, unlike every other action on this screen.
  const [lintError, setLintError] = useState<string | null>(null)

  /** Every prior lint result is invalid: a variant switch, a document reset,
   * a removed message, or a reordering (`diagnostics` is keyed by index, so
   * a shifted index would otherwise annotate a message that never produced
   * that error -- worse than no marker at all). `checked` goes with it,
   * so a stale "no syntax errors" cannot survive either. */
  const clearDiagnostics = () => {
    setDiagnosticsMap({})
    setChecked(new Set())
    setLintError(null)
    setLintEpoch((epoch) => epoch + 1)
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
    setChecked((current) => withoutIndex(current, index))
  }

  /** The live check's verdict on message `index`; `null` is a failed request,
   * which leaves that message unchecked rather than clean. */
  const applyLiveResult = (index: number, errors: LintError[] | null) => {
    setDiagnosticsMap((current) => {
      const next = { ...current }
      if (errors && errors.length > 0) next[index] = errors
      else delete next[index]
      return next
    })
    setChecked((current) => (errors ? new Set(current).add(index) : withoutIndex(current, index)))
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
  // Which route `originalRef` was seeded for. The route reset below clears
  // `originalRef` only AFTER the first render on the new route; when that
  // render already has the new route's document (react-query cache), this is
  // what keeps the previous agent's draft from painting under it.
  const originalRouteRef = useRef<string | null>(null)

  // Every hook above this line runs on every render of this instance,
  // including the loading -> loaded transition below: this screen stays
  // mounted across it, and a hook called only on some renders of the same
  // instance corrupts React's hook order -- a hard crash ("Rendered more
  // hooks than during the previous render"), not a lint nit. That is exactly
  // what phase 3's AgentDetail hit. So the reducer is seeded from an effect
  // rather than a hook moved below the guards, and every value the JSX below
  // needs is derived from `document.data ?? undefined`, never assumed present.
  //
  // Two resets, not one, because two different things change:
  //
  // A ROUTE change (the toolbar's language/agent selects navigate within this
  // same mounted screen) is a different document altogether, so everything
  // about "where the operator is" starts over: the variant selection returns
  // to the new document's `default_variant` (a name kept from the previous
  // agent would otherwise stay selected whenever the new one happens to share
  // it), every variant's open tabs are dropped, and the previous agent's
  // `originalRef` is dropped so the `!original` guard below covers the load.
  // Declared BEFORE the document reset: when both fire in one commit (a
  // cached document for the new route), the document reset's `originalRef`
  // must be the one that sticks.
  useEffect(() => {
    originalRef.current = null
    setSelectedVariant(null)
    tabsState.reset()
    clearDiagnostics()
  }, [docLang, agentKey])

  // A new `document.data` for the SAME route -- the first load, or the
  // refetch this screen's own successful save triggers -- re-seeds the draft
  // and invalidates every lint result (they describe the old text), but
  // leaves the open tabs alone: saving must not close what the operator had
  // open. A tab that no longer resolves simply drops out (`visibleTabs`).
  useEffect(() => {
    if (!document.data) return
    // Same route: the reload after a save. Its draft donates its uids by
    // position, so the open tabs keep pointing at the same messages.
    const sameRoute = originalRouteRef.current === `${docLang}/${agentKey}`
    const normalized = withMessageUids(
      normalizeDocument(document.data, docLang, agentKey),
      sameRoute ? draftRef.current : null,
    )
    originalRef.current = normalized
    originalRouteRef.current = `${docLang}/${agentKey}`
    dispatch({ type: 'reset', document: normalized })
    clearDiagnostics()
  }, [document.data, docLang, agentKey])

  const original =
    originalRouteRef.current === `${docLang}/${agentKey}` ? originalRef.current : null
  const dirty = original ? isDirty(original, draft) : false
  // What the agent provides plus what the templates reference -- the variable
  // tree and the render/test context both work from this one object, and the
  // render pane re-merges only when its identity changes.
  const agentContext = useMemo(
    () => agentContextOf(original?.agent_context_sample ?? {}, original?.agent_context_skeleton ?? {}),
    [original],
  )

  // Warns on a tab close or refresh. `useBlocker` below covers an IN-APP
  // navigation instead -- neither is a router navigation, so this effect is
  // still needed alongside it, not superseded by it.
  useEffect(() => {
    if (!dirty) return
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = t('unsavedChangesWarning')
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [dirty, t('unsavedChangesWarning')])

  // Blocks an IN-APP navigation (a `<Link>`/`NavLink` click elsewhere in the
  // console) the same way the effect above blocks a tab close or refresh.
  // Needs a data router -- see main.tsx and dev/preview.tsx, both switched to
  // `createBrowserRouter`/`RouterProvider` for this. `beforeunload` above is
  // kept alongside this, not replaced by it: `useBlocker` has no say over a
  // tab close or a refresh, since neither is a router navigation.
  const blocker = useBlocker(dirty)

  // The live check is a hook, so it runs above the loading guards below and
  // derives the open message itself -- only once `original` says the draft
  // belongs to this route, never from a previous agent's leftover draft.
  const liveVariant = original ? selectedVariantOf(draft, selectedVariant) : undefined
  const liveActive = tabsState.tabsFor(liveVariant).active
  const liveIndex = liveVariant ? liveVariant.messages.findIndex((m, i) => messageTabOf(m, i) === liveActive) : -1
  const liveMessage = liveVariant?.messages[liveIndex]
  const liveLint = useLintTemplate()
  const live = useLiveLint(
    liveVariant && liveMessage
      ? { key: `${liveVariant.name}:${liveIndex}:${lintEpoch}`, content: liveMessage.content }
      : null,
    async (content) => (await liveLint.mutateAsync(content)).errors,
    (errors) => applyLiveResult(liveIndex, errors),
  )

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
      <div style={{ padding: 28 }}>
        <Message
          severity="error"
          style={{ justifyContent: 'flex-start' }}
          text={
            <>
              <div>{t('promptDocError')}</div>
              {detail && (
                <div className="text-muted" style={{ fontSize: 12, marginTop: 4 }}>
                  {detail}
                </div>
              )}
            </>
          }
        />
      </div>
    )
  }
  // A document loaded, but the document reset above has not yet run against
  // it (see `originalRef`'s own comment) -- without this guard, this render
  // would paint the OLD draft (the initial empty document, or a previous
  // agent's) under the NEW document's header for exactly one frame. A
  // previous agent's `originalRef` never counts: `original` above is null
  // unless it was seeded for the current route.
  if (!original) return <div style={{ padding: 28 }}>…</div>

  const disk = config.data?.disk ?? {}

  const selectedVariantObj = selectedVariantOf(draft, selectedVariant)
  const variantName = selectedVariantObj?.name ?? ''
  const vars = selectedVariantObj?.vars ?? {}
  const messages = selectedVariantObj?.messages ?? []

  // What the centre pane shows: the active tab. Null when every tab is closed.
  const tabs = tabsState.tabsFor(selectedVariantObj)
  const activeIndex = messages.findIndex((m, i) => messageTabOf(m, i) === tabs.active)
  const current: Selection | null =
    tabs.active === 'meta' ? { kind: 'meta' }
      : tabs.active === 'variant' && selectedVariantObj ? { kind: 'variant' }
      : activeIndex >= 0 ? { kind: 'message', index: activeIndex }
      : null
  const currentMessage = current?.kind === 'message' ? messages[current.index] : undefined
  const used = currentMessage ? usedTemplateVars(currentMessage.content) : []
  const agentVars = Object.keys(agentContext).map((k) => `agent.${k}`)
  const declaredVars = Object.keys(vars).map((k) => `vars.${k}`)
  // Read through a ref by CodeEditor, so a fresh object per render costs nothing.
  const completion = { agent: agentContext, vars }
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
  // Messages of the selected variant with a current syntax error. Save stays
  // disabled while any is flagged; a broken message in a variant the
  // operator never opened is not known here, and the server's own Jinja
  // check refuses that save instead (named in the confirm dialog).
  const invalidJinja = flagged
    .filter((index) => messages[index])
    .sort((a, b) => a - b)
    .map((index) => ({ index, message: messages[index], error: diagnostics[index][0] }))

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
   * The open message is already checked live (`useLiveLint`, above): once
   * when it opens, then after each pause in the typing -- the parse is cheap
   * enough server-side for that round trip. This button covers what the live
   * check does not: every OTHER message of the variant, in one action, and
   * it is the one place a failed request is reported aloud (the live check
   * stays quiet rather than alerting on every pause). Open to a non-admin:
   * `POST /prompts/lint` is session-gated, not admin-gated (unlike render),
   * so a read-only operator must still be able to run it.
   */
  const runLint = async () => {
    setLinting(true)
    setChecked(new Set())
    setLintError(null)
    try {
      const results = await Promise.all(messages.map((message) => lint.mutateAsync(message.content)))
      const next: Record<number, LintError[]> = {}
      results.forEach((result, index) => {
        if (result.errors.length > 0) next[index] = result.errors
      })
      setDiagnosticsMap(next)
      setChecked(new Set(messages.map((_, index) => index)))
    } catch (error) {
      // A 403, a 500 or a dropped connection. Surfaced the way
      // `RenderPreview` surfaces its own mutation error -- the message from
      // the failure itself, not a generic one. Any partial result is dropped:
      // `Promise.all` rejects on the first failure, so the results that did
      // arrive cover an unknown subset of the messages, and a diagnostics map
      // missing entries reads exactly like "these messages are clean".
      setDiagnosticsMap({})
      setLintError((error as Error)?.message || t('lintFailed'))
    } finally {
      setLinting(false)
    }
  }

  /** What `useEditorTabs` resolves a variant's tabs against; `extra` is a
   * message the draft adds in the same event, before the reducer has run. */
  const variantTabs = (name: string, extra: PromptMessageDoc[] = []) => {
    const variant = draft.variants.find((v) => v.name === name)
    return { name, messages: [...(variant?.messages ?? []), ...extra] }
  }
  const open = (tab: TabId, pin: boolean) => tabsState.update(variantTabs(variantName), (prev) => openTab(prev, tab, pin))
  /** The first edit in a preview tab keeps it, as in VS Code. */
  const pinActive = () => {
    if (tabs.active && tabs.preview === tabs.active) tabsState.update(variantTabs(variantName), (prev) => pinTab(prev, tabs.active as TabId))
  }

  const pickVariant = (name: string) => {
    if (name === variantName) return
    setSelectedVariant(name)
    // A message index means something different in a different variant's
    // own message list. The variant's own tabs come back with it.
    clearDiagnostics()
  }

  const openVariantSettings = (name: string, pin = false) => {
    if (name !== variantName) {
      setSelectedVariant(name)
      clearDiagnostics()
    }
    tabsState.update(variantTabs(name), (prev) => openTab(prev, 'variant', pin))
  }

  const addVariant = () => {
    const name = uniqueVariantName(t('newVariantDefault'), draft.variants.map((v) => v.name))
    const uid = newMessageUid()
    dispatch({ type: 'addVariant', name, uid })
    setSelectedVariant(name)
    clearDiagnostics()
    // The reducer has not run yet, so the new variant is described by hand.
    // Its first message opens as the preview tab (as for any variant), and
    // the settings open beside it, pinned and active.
    tabsState.update({ name, messages: [{ ...emptyMessage(), uid }] }, (prev) => openTab(prev, 'variant', true))
  }

  const addMessage = () => {
    const uid = newMessageUid()
    dispatch({ type: 'addMessage', variant: variantName, uid })
    tabsState.update(variantTabs(variantName, [{ ...emptyMessage(), uid }]), (prev) => openTab(prev, `msg:${uid}`, true))
  }

  const removeMessage = (index: number) => {
    dispatch({ type: 'removeMessage', variant: variantName, index })
    // Every remaining entry's index now names a different message than the
    // one it was computed for -- clearing is honest; remapping would be
    // guessing which message shifted where. The message's tab closes by
    // itself: its uid no longer resolves (`visibleTabs`).
    clearDiagnostics()
  }

  const moveMessage = (from: number, to: number) => {
    dispatch({ type: 'moveMessage', variant: variantName, index: from, to })
    // The open tab follows the moved message by its uid; the index-keyed
    // diagnostics cannot.
    clearDiagnostics()
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
    pinActive()
    if (field === 'default_variant') {
      setSaveFieldError(null)
      // Until the operator picks a variant, the one worked on is the default
      // one -- changing the default must not swap the open variant (and with
      // it the open tabs) out from under the prompt.yaml pane.
      if (selectedVariant === null) setSelectedVariant(variantName)
    }
    dispatch({ type: 'setHeader', field, value })
  }

  const alertStyle = { fontSize: 12, margin: '6px 16px', justifyContent: 'flex-start' }

  // The lint result for the open message -- the sidebar's lint block
  // shows exactly this. "Clean" needs the open message checked (or, on the
  // prompt.yaml / settings pane, every message) AND nothing flagged anywhere:
  // a clean open message says nothing while any other message is still
  // flagged.
  const lintState: LintState = {
    running: linting,
    checking: live.checking,
    clean:
      flagged.length === 0 &&
      (current?.kind === 'message'
        ? checked.has(current.index)
        : messages.length > 0 && messages.every((_, index) => checked.has(index))),
    error: lintError,
    errors: current?.kind === 'message' ? (diagnostics[current.index] ?? []) : [],
  }

  const varSidebarProps = {
    agentVars,
    agentContext,
    declaredVars,
    used,
    undeclared,
    canInsert: isAdmin && !!currentMessage?.readable,
    canDeclare: isAdmin,
    lint: lintState,
    onInsert: insert,
    onDeclare: declareUndeclared,
    onLint: () => void runLint(),
  }

  // A message's editor model is named after its tab, so the key the pane
  // shows and the keys kept alive below can never disagree.
  const modelKeyOf = (tab: `msg:${string}`) => `${docLang}/${agentKey}/${tab.slice(4)}`
  // Every open message tab of every variant keeps its editor model (undo,
  // cursor, scroll). Resolved per variant: a deleted message's tab drops out
  // at once, and a variant never touched still has its implicit first tab.
  const modelKeys = draft.variants
    .flatMap((variant) => tabsState.tabsFor(variant).open)
    .filter((id): id is `msg:${string}` => id.startsWith('msg:'))
    .map(modelKeyOf)

  // Built once: the centre pane for `current`, the preview, the test run.
  const centre = (
    <>
      {!current && (
        <div className="text-muted" style={{ flex: 1, display: 'grid', placeItems: 'center', fontSize: 13, padding: 24 }}>
          {t('noOpenEditor')}
        </div>
      )}
      {current?.kind === 'meta' && (
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
          onHeader={setHeader}
        />
      )}
      {current?.kind === 'variant' && selectedVariantObj && (
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', overflow: 'auto' }}>
          {messages.length === 0 && (
            <div className="text-muted" style={{ padding: '20px 24px 0', fontSize: 13 }}>
              {t('noMessages')}
            </div>
          )}
          <VariantPane
            variant={selectedVariantObj}
            readOnly={!isAdmin}
            canRemove={draft.variants.length > 1}
            onRename={(to) => {
              pinActive()
              dispatch({ type: 'renameVariant', from: selectedVariantObj.name, to })
              // The selection is resolved BY NAME, so it has to follow the
              // rename. Without this, the first keystroke makes the old
              // name unresolvable, the selection falls through to
              // `variants[0]`, and every later keystroke renames THAT
              // variant instead -- leaving the intended one named after
              // whatever the field held when the fall-through happened.
              // The open tabs are kept by name too.
              setSelectedVariant(to)
              tabsState.renameVariant(selectedVariantObj.name, to)
            }}
            onModel={(model) => {
              pinActive()
              dispatch({ type: 'setVariantModel', variant: selectedVariantObj.name, model })
            }}
            onRemove={() => {
              dispatch({ type: 'removeVariant', name: selectedVariantObj.name })
              tabsState.removeVariant(selectedVariantObj.name)
              // The selection falls through to another variant, whose
              // message indices the old diagnostics do not describe.
              clearDiagnostics()
            }}
            onAddVar={(key) => {
              pinActive()
              dispatch({ type: 'addVar', variant: variantName, key })
            }}
            onEditVar={(key, decl) => {
              pinActive()
              dispatch({ type: 'editVar', variant: variantName, key, decl })
            }}
            onRemoveVar={(key) => {
              pinActive()
              dispatch({ type: 'removeVar', variant: variantName, key })
            }}
          />
        </div>
      )}
      {currentMessage && current?.kind === 'message' && (
        // Not keyed by message: the editor survives a tab switch and swaps
        // in that message's own model (`modelKey`), undo history included.
        // A different document still starts a fresh editor.
        <MessagePane
          key={`${docLang}/${agentKey}`}
          editorRef={editorRef}
          path={messagePath(draft.file, variantName, current.index, currentMessage)}
          message={currentMessage}
          index={current.index}
          count={messages.length}
          readOnly={!isAdmin}
          diagnostics={diagnostics[current.index]}
          insertable={[...agentVars, ...declaredVars]}
          completion={completion}
          modelKey={modelKeyOf(messageTabOf(currentMessage, current.index))}
          keepModels={modelKeys}
          onRemove={() => removeMessage(current.index)}
          onMove={(to) => moveMessage(current.index, to)}
          onRole={(role) => {
            pinActive()
            dispatch({ type: 'setMessageRole', variant: variantName, index: current.index, role })
          }}
          onContent={(content) => {
            // The value sync after a tab switch re-sends the same text;
            // only a real edit pins the tab and drops the lint result.
            if (content === currentMessage.content) return
            pinActive()
            dispatch({ type: 'setMessageContent', variant: variantName, index: current.index, content })
            // Only THIS message's own result is invalid -- it changed no
            // index, so every other message's result still points correctly.
            dropDiagnostic(current.index)
          }}
          onSource={(source) => {
            pinActive()
            dispatch({ type: 'setMessageSource', variant: variantName, index: current.index, source })
          }}
          onFile={(file) => {
            pinActive()
            dispatch({ type: 'setMessageFile', variant: variantName, index: current.index, file })
          }}
        />
      )}
    </>
  )

  // The render and test-run requests post these; the uids are client-only.
  const [requestVariant] = selectedVariantObj ? withoutMessageUids([selectedVariantObj]) : []
  const requestMessages = requestVariant?.messages ?? []

  const preview = (
    <RenderPreview
      messages={requestMessages}
      vars={sampleVars(vars)}
      decls={vars}
      skeleton={agentContext}
      isAdmin={isAdmin}
    />
  )

  const testRun = (
    <TestRunPanel
      messages={requestMessages}
      vars={sampleVars(vars)}
      agentContext={agentContext}
      isAdmin={isAdmin}
    />
  )

  // `tabs.open` only holds ids that resolve (`visibleTabs`), so a message
  // tab always finds its message.
  const editorTabs: EditorTab[] = tabs.open.map((id) => {
    const isPreview = tabs.preview === id
    if (id === 'meta') return { id, label: 'prompt.yaml', dirty: isMetaDirty(original, draft), flagged: false, preview: isPreview }
    if (id === 'variant') {
      return { id, label: variantName, prefix: '⚙', dirty: selectedVariantObj ? isVariantDirty(original, selectedVariantObj) : false, flagged: false, preview: isPreview }
    }
    const index = messages.findIndex((m, i) => messageTabOf(m, i) === id)
    const message = messages[index]
    return { id, label: messageLabel(message, t('emptyMessage')), prefix: message.role, dirty: isMessageDirty(original, message), flagged: index in diagnostics, preview: isPreview }
  })

  const split = (
    <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
      <PromptTree
        variants={draft.variants}
        selectedVariant={variantName}
        activeTab={tabs.active}
        flagged={flagged}
        invalidVariants={saveFieldError?.kind === 'emptyVariants' ? saveFieldError.names : []}
        readOnly={!isAdmin}
        onOpenMeta={(pin) => open('meta', pin)}
        onPickVariant={pickVariant}
        onOpenVariantSettings={openVariantSettings}
        onPickMessage={(index, pin) => open(messageTabOf(messages[index], index), pin)}
        onAddVariant={addVariant}
        onAddMessage={addMessage}
      />
      <div ref={splitColumnRef} style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <EditorTabs
          tabs={editorTabs}
          active={tabs.active}
          onActivate={(id) => open(id, false)}
          onPin={(id) => tabsState.update(variantTabs(variantName), (prev) => pinTab(prev, id))}
          onClose={(id) => tabsState.update(variantTabs(variantName), (prev) => closeTab(prev, id))}
        />
        <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>
          {centre}
          {currentMessage && <VarSidebar {...varSidebarProps} />}
        </div>
        {/* The editor above keeps at least 160px; the rest is the viewer's
            to hand to Preview / Test run. */}
        <PaneResizer
          height={paneHeight}
          min={MIN_PANE_HEIGHT}
          max={() => (splitColumnRef.current?.clientHeight ?? 0) - 160}
          label={t('resizePreviewPane')}
          onResize={setPaneHeight}
        />
        <div
          data-testid="preview-pane"
          style={{
            height: paneHeight,
            // A height remembered from a taller window must not crush the editor.
            maxHeight: 'calc(100% - 160px)',
            flex: 'none',
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(min(420px, 100%), 1fr))',
            gap: 16,
            padding: '10px 14px',
            overflow: 'auto',
          }}
        >
          {preview}
          {testRun}
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
        onVariant={pickVariant}
        showSave={isAdmin}
        canSave={dirty && emptyEnumVariants.length === 0 && invalidJinja.length === 0}
        onSave={openConfirm}
      />

      {/* A background refetch failure (e.g. the tree/document invalidation
          this screen's own successful save triggers) -- NOT the fatal
          load-failure guard above, which only fires when no document has
          ever loaded. The draft stays exactly as it was. */}
      {document.isError && (
        <Message severity="error" style={alertStyle} text={t('promptDocError')} />
      )}
      {isAdmin && invalidJinja.length > 0 && (
        // `status`, not `alert`: the error itself is already the alert (the
        // editor's marker, the sidebar's line) -- this says what it blocks.
        <Message
          severity="error"
          role="status"
          data-testid="save-blocked-jinja"
          style={alertStyle}
          text={
            <>
              {t('saveBlockedJinja')}{' '}
              {invalidJinja
                .map(({ index, message, error }) =>
                  `${index + 1} (${message.role}${message.source === 'file' && message.file ? `, ${message.file}` : ''}), ${t('lintLine', { line: error.line, message: error.message })}`,
                )
                .join(' · ')}
            </>
          }
        />
      )}
      {saveFieldError?.kind === 'emptyVariants' && saveErrorMessage && (
        <Message severity="error" style={alertStyle} text={saveErrorMessage} />
      )}

      {split}

      {confirmOpen && (
        <SavePromptDialog
          plan={plan.data ?? null}
          error={planErrorMessage ?? saveErrorMessage}
          pending={save.isPending || plan.isPending}
          onCancel={closeConfirm}
          onConfirm={confirmSave}
        >
          {orphanWarnings.length > 0 && (
            <Message
              severity="error"
              style={{ fontSize: 12, justifyContent: 'flex-start' }}
              content={
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {orphanWarnings.map((entry) => (
                    <div key={entry.name} data-testid={`orphan-${entry.name}`}>
                      {t('confirmSaveOrphanWarning')} {entry.name} —{' '}
                      {entry.referencedBy.map((scope) => referenceLabel(t, scope)).join(', ')}
                    </div>
                  ))}
                </div>
              }
            />
          )}
        </SavePromptDialog>
      )}

      {blocker.state === 'blocked' && (
        <Modal label={t('unsavedNavTitle')} width={480}>
          <h3 style={{ margin: 0 }}>{t('unsavedNavTitle')}</h3>
          <div style={{ fontSize: 13 }}>{t('unsavedNavBody')}</div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <Button type="button" outlined label={t('cancel')} onClick={() => blocker.reset?.()} />
            <Button type="button" label={t('leaveAnyway')} onClick={() => blocker.proceed?.()} />
          </div>
        </Modal>
      )}
    </div>
  )
}
