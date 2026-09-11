import { useEffect, useReducer, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useSavePrompt } from '../api/mutations'
import { agentsUsingVariant } from '../api/prompts'
import { useConfig, usePromptDocument } from '../api/queries'
import type { MessageRole, PromptDocument, PromptVarDecl } from '../api/types'
import { MessageList } from '../components/MessageList'
import { RenderPreview } from '../components/RenderPreview'
import { VarDeclTable } from '../components/VarDeclTable'
import { useTranslations, type Lang } from '../i18n'
import { changedFiles, isDirty, promptDraftReducer } from '../state/promptDraft'

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

/** Sample values a render preview can send: each declared default, or `null`. */
function sampleVars(vars: Record<string, PromptVarDecl>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [key, decl] of Object.entries(vars)) out[key] = decl.default_value ?? null
  return out
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

/**
 * Which field a 422's message names, so the form can mark it.
 *
 * `build_write_set`'s validation errors are prose, not field-addressed JSON
 * (unlike `config/apply`'s `ConfigIssue` list) -- this is the client's own
 * mirror of the one case the editor can act on: an out-of-range
 * `default_variant`, which is a field this screen renders as a single select.
 */
function fieldFromSaveError(message: string): 'default_variant' | null {
  return message.startsWith('default_variant') ? 'default_variant' : null
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

  const [draft, dispatch] = useReducer(promptDraftReducer, undefined, () =>
    emptyDocument(docLang, agentKey),
  )
  const [selectedVariant, setSelectedVariant] = useState<string | null>(null)
  const [newVariantName, setNewVariantName] = useState('')
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [saveFieldError, setSaveFieldError] = useState<string | null>(null)
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
  }, [document.data, docLang, agentKey])

  const original = originalRef.current
  const dirty = original ? isDirty(original, draft) : false

  // Warns on an actual tab close/refresh/navigation away from the origin.
  // react-router v7's `useBlocker` needs a data router (this app renders
  // through a plain `<BrowserRouter>`, see main.tsx), so an in-app Link click
  // is not interceptable here without a larger routing change; this covers
  // the same real data-loss risk `beforeunload` is meant for.
  useEffect(() => {
    if (!dirty) return
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = t.unsavedChangesWarning
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [dirty, t.unsavedChangesWarning])

  if (document.isLoading) return <div style={{ padding: 28 }}>…</div>
  if (document.isError || !document.data) {
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

  const disk = config.data?.disk ?? {}

  const selectedName = selectedVariant ?? draft.default_variant
  // Never `variants[0]` unguarded: an empty list (or a stale selection after
  // a rename) must fall back to `undefined`, not throw.
  const selectedVariantObj = draft.variants.find((v) => v.name === selectedName) ?? draft.variants[0]
  const variantName = selectedVariantObj?.name ?? ''
  const vars = selectedVariantObj?.vars ?? {}
  const messages = selectedVariantObj?.messages ?? []

  const files = original ? changedFiles(original, draft) : []

  // Names the draft dropped since the load -- renamed away or removed
  // outright -- mirrored against `config.disk` exactly as the server's own
  // guard (§5.5) will, so the operator sees the same refusal *before*
  // confirming rather than only after a 409. Guarded against `original` (the
  // reducer's own reset document, always field-defaulted -- see
  // `normalizeDocument`) rather than the raw `document.data`, which a 200 with
  // a missing `variants` field would otherwise crash `.map` on.
  const orphanWarnings = (original?.variants ?? [])
    .map((v) => v.name)
    .filter((name) => !draft.variants.some((v) => v.name === name))
    .map((name) => ({ name, referencedBy: agentsUsingVariant(disk, agentKey, name) }))
    .filter((entry) => entry.referencedBy.length > 0)

  const saveErrorMessage =
    save.isError && save.error instanceof ApiError ? save.error.message : null

  const confirmSave = () => {
    save.mutate(toSaveRequest(draft), {
      onSuccess: () => {
        setConfirmOpen(false)
        setSaveFieldError(null)
      },
      onError: (error) => {
        if (error instanceof ApiError && error.status === 422) {
          setSaveFieldError(fieldFromSaveError(error.message))
        } else {
          setSaveFieldError(null)
        }
      },
    })
  }

  const headerReadOnly = !isAdmin

  return (
    <div
      data-testid="prompt-editor"
      style={{ padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: 18, maxWidth: 900 }}
    >
      <div>
        <h2 style={{ margin: 0, fontSize: 30 }}>{draft.name || agentKey}</h2>
        <div
          className="text-muted"
          style={{ fontSize: 12, fontFamily: 'ui-monospace, Menlo, monospace' }}
        >
          {agentKey} · {docLang} · {draft.file}
        </div>
      </div>

      <section
        className="blueprint"
        data-testid="prompt-header"
        style={{ padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}
      >
        <Header
          label={t.promptName}
          id="prompt-name"
          value={draft.name}
          readOnly={headerReadOnly}
          onChange={(value) => dispatch({ type: 'setHeader', field: 'name', value })}
        />
        <Header
          label={t.promptSummary}
          id="prompt-summary"
          value={draft.summary ?? ''}
          readOnly={headerReadOnly}
          onChange={(value) => dispatch({ type: 'setHeader', field: 'summary', value })}
        />
        <Header
          label={t.promptDescription}
          id="prompt-description"
          value={draft.description ?? ''}
          readOnly={headerReadOnly}
          multiline
          onChange={(value) => dispatch({ type: 'setHeader', field: 'description', value })}
        />
        <Header
          label={t.defaultModel}
          id="prompt-default-model"
          value={draft.default_model}
          readOnly={headerReadOnly}
          onChange={(value) => dispatch({ type: 'setHeader', field: 'default_model', value })}
        />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <label htmlFor="prompt-default-variant" style={{ fontSize: 12 }}>
            {t.defaultVariant}
          </label>
          <select
            className="input"
            id="prompt-default-variant"
            disabled={headerReadOnly}
            aria-invalid={saveFieldError === 'default_variant' || undefined}
            aria-describedby={saveFieldError === 'default_variant' ? 'default-variant-issue' : undefined}
            value={draft.default_variant}
            onChange={(event) =>
              dispatch({ type: 'setHeader', field: 'default_variant', value: event.target.value })
            }
            style={{ maxWidth: 260 }}
          >
            {draft.variants.map((v) => (
              <option key={v.name} value={v.name}>
                {v.name}
              </option>
            ))}
          </select>
          {saveFieldError === 'default_variant' && saveErrorMessage && (
            <span id="default-variant-issue" role="alert" style={{ fontSize: 11, color: '#a33a2b' }}>
              {saveErrorMessage}
            </span>
          )}
        </div>
      </section>

      <section className="blueprint" style={{ padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div role="tablist" aria-label={t.variants} style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          {draft.variants.map((v) => (
            <button
              key={v.name}
              type="button"
              role="tab"
              className="tb-chip"
              aria-selected={v.name === variantName}
              onClick={() => setSelectedVariant(v.name)}
              style={{
                border: '1px solid var(--color-divider)',
                padding: '4px 12px',
                font: 'inherit',
                fontSize: 13,
                background: v.name === variantName ? 'var(--color-accent)' : 'transparent',
                color: v.name === variantName ? 'var(--color-bg)' : 'inherit',
                cursor: 'pointer',
              }}
            >
              {v.name}
            </button>
          ))}
        </div>

        {isAdmin && selectedVariantObj && (
          <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <label htmlFor="variant-name" style={{ fontSize: 12 }}>
                {t.variantName}
              </label>
              <input
                className="input"
                id="variant-name"
                value={selectedVariantObj.name}
                onChange={(event) =>
                  dispatch({ type: 'renameVariant', from: selectedVariantObj.name, to: event.target.value })
                }
              />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <label htmlFor="variant-model" style={{ fontSize: 12 }}>
                {t.variantModel}
              </label>
              <input
                className="input"
                id="variant-model"
                value={selectedVariantObj.model ?? ''}
                onChange={(event) =>
                  dispatch({
                    type: 'setVariantModel',
                    variant: selectedVariantObj.name,
                    model: event.target.value || null,
                  })
                }
              />
            </div>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => dispatch({ type: 'removeVariant', name: selectedVariantObj.name })}
            >
              {t.remove}
            </button>
          </div>
        )}

        {isAdmin && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              className="input"
              aria-label={t.newVariantName}
              placeholder={t.newVariantName}
              value={newVariantName}
              onChange={(event) => setNewVariantName(event.target.value)}
            />
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => {
                const name = newVariantName.trim()
                if (!name) return
                dispatch({ type: 'addVariant', name })
                setNewVariantName('')
              }}
            >
              {t.addVariant}
            </button>
          </div>
        )}

        <VarDeclTable
          vars={vars}
          readOnly={!isAdmin}
          lang={lang}
          onAdd={(key) => dispatch({ type: 'addVar', variant: variantName, key })}
          onEdit={(key, decl) => dispatch({ type: 'editVar', variant: variantName, key, decl })}
          onRemove={(key) => dispatch({ type: 'removeVar', variant: variantName, key })}
        />

        <MessageList
          messages={messages}
          readOnly={!isAdmin}
          lang={lang}
          onAdd={() => dispatch({ type: 'addMessage', variant: variantName })}
          onRemove={(index) => dispatch({ type: 'removeMessage', variant: variantName, index })}
          onMove={(from, to) => dispatch({ type: 'moveMessage', variant: variantName, index: from, to })}
          onRole={(index, role: MessageRole) =>
            dispatch({ type: 'setMessageRole', variant: variantName, index, role })
          }
          onContent={(index, content) =>
            dispatch({ type: 'setMessageContent', variant: variantName, index, content })
          }
        />
      </section>

      <RenderPreview
        messages={messages}
        vars={sampleVars(vars)}
        skeleton={original?.agent_context_skeleton ?? {}}
        isAdmin={isAdmin}
        lang={lang}
      />

      {isAdmin && (
        <div>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!dirty}
            onClick={() => setConfirmOpen(true)}
          >
            {t.save}
          </button>
        </div>
      )}

      {confirmOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={t.confirmSaveTitle}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,.45)',
            display: 'grid',
            placeItems: 'center',
            padding: 24,
            zIndex: 20,
          }}
        >
          <div
            className="card"
            style={{
              background: 'var(--color-bg)',
              width: 'min(560px, 100%)',
              display: 'flex',
              flexDirection: 'column',
              gap: 12,
              padding: 20,
            }}
          >
            <h3 style={{ margin: 0 }}>{t.confirmSaveTitle}</h3>
            <div style={{ fontSize: 13 }}>{t.confirmSaveFiles}</div>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, fontFamily: 'ui-monospace, Menlo, monospace' }}>
              {files.map((file) => (
                <li key={file} data-testid="confirm-file">
                  {file}
                </li>
              ))}
            </ul>

            {orphanWarnings.length > 0 && (
              <div role="alert" style={{ fontSize: 12, color: '#a33a2b', display: 'flex', flexDirection: 'column', gap: 4 }}>
                {orphanWarnings.map((entry) => (
                  <div key={entry.name} data-testid={`orphan-${entry.name}`}>
                    {t.confirmSaveOrphanWarning} {entry.name} — {entry.referencedBy.join(', ')}
                  </div>
                ))}
              </div>
            )}

            {/* A field-specific 422 is already shown beside that field; a
                generic failure (409, or anything not field-addressed) is
                shown here instead of a duplicate. */}
            {saveErrorMessage && !saveFieldError && (
              <div role="alert" style={{ fontSize: 12, color: '#a33a2b' }}>
                {saveErrorMessage}
              </div>
            )}

            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button type="button" className="btn btn-secondary" onClick={() => setConfirmOpen(false)}>
                {t.cancel}
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={confirmSave}
                disabled={save.isPending}
              >
                {save.isPending ? t.saving : t.confirm}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function Header({
  label,
  id,
  value,
  readOnly,
  multiline,
  onChange,
}: {
  label: string
  id: string
  value: string
  readOnly?: boolean
  multiline?: boolean
  onChange: (value: string) => void
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <label htmlFor={id} style={{ fontSize: 12 }}>
        {label}
      </label>
      {multiline ? (
        <textarea
          className="input"
          id={id}
          readOnly={readOnly}
          value={value}
          rows={3}
          onChange={(event) => onChange(event.target.value)}
        />
      ) : (
        <input
          className="input"
          id={id}
          type="text"
          readOnly={readOnly}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
    </div>
  )
}
