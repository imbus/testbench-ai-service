import { useEffect, useRef, useState } from 'react'
import { DefaultValueControl } from './VarDeclTable'
import { useRenderPrompt } from '../api/mutations'
import { mergeContext } from '../api/prompts'
import type { PromptMessageDoc, PromptVarDecl } from '../api/types'
import { useTranslations, type Lang } from '../i18n'

/** `null` on anything that is not a JSON object -- an array or a scalar is
 * not a context, and treating it as one would crash `mergeContext`. */
function parseContext(text: string): Record<string, unknown> | null {
  try {
    const parsed: unknown = JSON.parse(text)
    if (parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>
    }
    return null
  } catch {
    return null
  }
}

/**
 * The vars a render sends: the sample defaults, overlaid with what the
 * operator typed into the variables section.
 *
 * A cleared field (`null` from `DefaultValueControl`) follows the same rule
 * as `sampleVars`: a required var is OMITTED so `StrictUndefined` names it,
 * an optional one is sent as its lenient-runtime value (`false` / `""`) --
 * a `null` would 422 the whole request. Edits for keys the variant no longer
 * declares are dropped rather than sent as stray vars.
 */
function effectiveVars(
  vars: Record<string, unknown>,
  decls: Record<string, PromptVarDecl>,
  edits: Record<string, unknown>,
): Record<string, unknown> {
  const out: Record<string, unknown> = { ...vars }
  for (const [key, value] of Object.entries(edits)) {
    const decl = decls[key]
    if (!decl) continue
    if (value !== null && value !== undefined) {
      out[key] = value
    } else if (decl.required) {
      delete out[key]
    } else {
      out[key] = decl.value_type === 'boolean' ? false : ''
    }
  }
  return out
}

/**
 * Renders a draft variant's messages against sample vars and an editable
 * `agent_context` (design §5.6).
 *
 * Admin-only: `POST /prompts/render` evaluates operator-supplied Jinja
 * server-side, and the route is admin-gated to match -- offering the button
 * to a non-admin would just spend a click on a 403.
 */
export function RenderPreview({
  messages,
  vars,
  decls = {},
  skeleton,
  isAdmin,
  lang = 'de',
}: {
  messages: PromptMessageDoc[]
  vars: Record<string, unknown>
  /** The variant's declared vars, one sample-value control each. */
  decls?: Record<string, PromptVarDecl>
  skeleton: Record<string, unknown>
  isAdmin: boolean
  lang?: Lang
}) {
  const t = useTranslations(lang)
  const render = useRenderPrompt()
  const [contextText, setContextText] = useState(() => JSON.stringify(skeleton, null, 2))
  const [parseError, setParseError] = useState(false)
  // Only what the operator changed, keyed by var name. The sample defaults
  // stay live underneath, so editing a declared default in the variant pane
  // still shows here for every var the operator has not touched.
  const [varEdits, setVarEdits] = useState<Record<string, unknown>>({})
  const sending = effectiveVars(vars, decls, varEdits)
  const declEntries = Object.entries(decls)
  // Tracks the skeleton this pane was last reconciled against, so the merge
  // below runs only when the skeleton itself actually changes (a different
  // variant, or its Jinja edited) -- not on every keystroke in the textarea.
  const previousSkeleton = useRef(skeleton)

  useEffect(() => {
    if (previousSkeleton.current === skeleton) return
    previousSkeleton.current = skeleton
    setContextText((current) => {
      const typed = parseContext(current) ?? {}
      return JSON.stringify(mergeContext(skeleton, typed), null, 2)
    })
  }, [skeleton])

  // Design D3: not merely hidden -- absent. A disabled button would still
  // announce a feature that 403s the moment it is clicked.
  if (!isAdmin) return null

  const handleRender = () => {
    const context = parseContext(contextText)
    if (!context) {
      setParseError(true)
      return
    }
    setParseError(false)
    render.mutate({ messages, vars: sending, agent_context: context })
  }

  return (
    <div data-testid="render-preview" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <fieldset
        data-testid="render-vars"
        style={{ border: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 8 }}
      >
        <legend
          style={{ fontSize: 12, padding: 0, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 8, width: '100%' }}
        >
          <span>{t.renderVars}</span>
          {Object.keys(varEdits).length > 0 && (
            <button
              type="button"
              className="btn btn-ghost"
              style={{ marginLeft: 'auto', fontSize: 11 }}
              onClick={() => setVarEdits({})}
            >
              {t.renderVarsReset}
            </button>
          )}
        </legend>
        {declEntries.length === 0 && (
          <span className="text-muted" style={{ fontSize: 12 }}>
            {t.renderVarsEmpty}
          </span>
        )}
        {declEntries.map(([key, decl]) => {
          const id = `render-var-${encodeURIComponent(key)}`
          const labelId = `${id}-label`
          return (
            <div key={key} className="field">
              <label id={labelId} htmlFor={id} title={decl.description ?? undefined}>
                <code>{key}</code>
                {decl.required && <span aria-hidden="true"> *</span>}
              </label>
              <DefaultValueControl
                id={id}
                labelId={labelId}
                decl={{ ...decl, default_value: key in sending ? sending[key] : null }}
                onChange={(value) => setVarEdits((current) => ({ ...current, [key]: value }))}
              />
            </div>
          )
        })}
      </fieldset>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <label htmlFor="render-context" style={{ fontSize: 12 }}>
          {t.renderContext}
        </label>
        {/* The wire field name the mutation actually sends -- supplementary,
            not the accessible label: an ordinary UI word ("context") has an
            unambiguous German translation, unlike a literal TOML path such as
            `Field.tsx`'s `spec.key`. */}
        <span
          className="text-muted"
          style={{ fontSize: 11, fontFamily: 'ui-monospace, Menlo, monospace' }}
        >
          agent_context
        </span>
        <textarea
          id="render-context"
          className="input"
          rows={8}
          style={{
            width: '100%',
            fontFamily: 'ui-monospace, Menlo, monospace',
            fontSize: 12,
            resize: 'vertical',
          }}
          value={contextText}
          onChange={(event) => setContextText(event.target.value)}
        />
      </div>

      <div>
        <button
          type="button"
          className="btn btn-ghost"
          disabled={render.isPending}
          onClick={handleRender}
        >
          {render.isPending ? t.rendering : t.render}
        </button>
      </div>

      {parseError && (
        <div role="alert" style={{ fontSize: 12, color: '#a33a2b' }}>
          {t.renderInvalidJson}
        </div>
      )}

      {render.isError && (
        <div role="alert" style={{ fontSize: 12, color: '#a33a2b' }}>
          {(render.error as Error)?.message}
        </div>
      )}

      {render.data && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {render.data.messages.map((message, index) => (
            <div
              key={index}
              data-testid="render-message"
              style={{ borderTop: '1px solid var(--color-divider)', paddingTop: 8 }}
            >
              {/* The message role, straight from the wire -- not translated. */}
              <div
                className="text-muted"
                style={{ fontSize: 11, fontFamily: 'ui-monospace, Menlo, monospace' }}
              >
                {message.role}
              </div>
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontSize: 12 }}>
                {message.content}
              </pre>
              {message.error && (
                <div role="alert" style={{ fontSize: 11, color: '#a33a2b' }}>
                  {message.error}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
