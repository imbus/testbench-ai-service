import { useEffect, useRef, useState } from 'react'
import { Button } from 'primereact/button'
import { InputTextarea } from 'primereact/inputtextarea'
import { Message } from 'primereact/message'
import { DefaultValueControl } from './VarDeclTable'
import { MarkdownView } from './MarkdownView'
import { useRenderPrompt } from '../api/mutations'
import { mergeContext } from '../api/prompts'
import type { PromptMessageDoc, PromptVarDecl, RenderResponse } from '../api/types'
import { useTranslation } from 'react-i18next'

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

/** How long the operator must pause before the Render tab re-renders. */
export const RENDER_DELAY_MS = 500

/** Matches the variables sidebar on the message tabs (`VarSidebar`). */
const column = {
  width: 230,
  flex: 'none',
  borderLeft: '1px solid var(--color-divider)',
  background: 'var(--color-surface)',
  padding: 12,
  overflow: 'auto',
} as const

/**
 * Renders a draft variant's messages against sample vars and an editable
 * `agent_context` (design §5.6): the rendered text in the middle, the
 * inputs in a right-hand column.
 *
 * Live while `active` (its tab is the open one): once on becoming active,
 * then `RENDER_DELAY_MS` after the last change of any input. Never while
 * inactive -- the pane stays mounted behind other tabs, and a hidden render
 * per keystroke in a message would only spend server time.
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
  active,
}: {
  messages: PromptMessageDoc[]
  vars: Record<string, unknown>
  /** The variant's declared vars, one sample-value control each. */
  decls?: Record<string, PromptVarDecl>
  skeleton: Record<string, unknown>
  isAdmin: boolean
  /** Whether the Render tab is the open one; renders live only then. */
  active: boolean
}) {
  const { t } = useTranslation()
  const render = useRenderPrompt()
  const [contextText, setContextText] = useState(() => JSON.stringify(skeleton, null, 2))
  const [parseError, setParseError] = useState(false)
  // The result shown, kept apart from the mutation's own state so a
  // response is applied only while it is still the latest request's.
  const [result, setResult] = useState<RenderResponse | null>(null)
  const [requestError, setRequestError] = useState<Error | null>(null)
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
  // Every input of a render, serialised: the props are new objects on every
  // parent render, so only their content says whether anything changed.
  const inputKey = JSON.stringify([messages, sending, contextText])
  // The inputs the last render was attempted for (sent, or refused as
  // invalid JSON). Recorded when attempted, not when the effect runs, so
  // StrictMode's mount-unmount-mount does not send twice.
  const attemptedKey = useRef<string | null>(null)
  // Numbers each request; only the newest one may land on screen.
  const sequence = useRef(0)
  // True from (re)activation until the first attempt after it: that one
  // goes out at once, every later change waits for a pause.
  const fresh = useRef(true)

  useEffect(() => {
    if (previousSkeleton.current === skeleton) return
    previousSkeleton.current = skeleton
    setContextText((current) => {
      const typed = parseContext(current) ?? {}
      return JSON.stringify(mergeContext(skeleton, typed), null, 2)
    })
  }, [skeleton])

  // Read by the effect below through a ref, so the effect depends on the
  // serialised inputs alone and not on a new closure every render.
  const attemptRef = useRef<() => void>(() => {})
  attemptRef.current = () => {
    attemptedKey.current = inputKey
    fresh.current = false
    const context = parseContext(contextText)
    if (!context) {
      // Nothing is sent, and the last good result stays on screen.
      setParseError(true)
      return
    }
    setParseError(false)
    const id = ++sequence.current
    render.mutateAsync({ messages, vars: sending, agent_context: context }).then(
      (data) => {
        if (id !== sequence.current) return
        setResult(data)
        setRequestError(null)
      },
      (error: unknown) => {
        if (id !== sequence.current) return
        setRequestError(error instanceof Error ? error : new Error(String(error)))
      },
    )
  }

  useEffect(() => {
    if (!isAdmin) return
    if (!active) {
      fresh.current = true
      return
    }
    if (attemptedKey.current === inputKey) return
    if (fresh.current) {
      attemptRef.current()
      return
    }
    // Rechecked when it fires: ↻ Render may have rendered these very
    // inputs during the pause.
    const timer = setTimeout(() => {
      if (attemptedKey.current !== inputKey) attemptRef.current()
    }, RENDER_DELAY_MS)
    return () => clearTimeout(timer)
  }, [isAdmin, active, inputKey])

  // Design D3: not merely hidden -- absent. A disabled button would still
  // announce a feature that 403s the moment it is clicked.
  if (!isAdmin) return null

  return (
    <div data-testid="render-preview" style={{ flex: 1, minWidth: 0, minHeight: 0, height: '100%', display: 'flex' }}>
      <div
        data-testid="render-output"
        style={{ flex: 1, minWidth: 0, overflow: 'auto', padding: '14px 24px', display: 'flex', flexDirection: 'column', gap: 10 }}
      >
        {requestError && (
          <Message severity="error" text={requestError.message} style={{ fontSize: 12, justifyContent: 'flex-start' }} />
        )}
        {!result && !requestError && (
          <span className="text-muted" style={{ fontSize: 12 }}>
            {t('rendering')}
          </span>
        )}
        {result?.messages.map((message, index) => (
          <div
            key={index}
            data-testid="render-message"
            style={{ borderTop: index > 0 ? '1px solid var(--color-divider)' : undefined, paddingTop: index > 0 ? 8 : 0 }}
          >
            {/* The message role, straight from the wire -- not translated. */}
            <div className="text-muted" style={{ fontSize: 11, fontFamily: 'ui-monospace, Menlo, monospace' }}>
              {message.role}
            </div>
            {message.content && <MarkdownView text={message.content} />}
            {message.error && (
              <Message severity="error" text={message.error} style={{ fontSize: 11, justifyContent: 'flex-start' }} />
            )}
          </div>
        ))}
      </div>

      <aside
        data-testid="render-inputs"
        style={{ ...column, display: 'flex', flexDirection: 'column', gap: 12, fontSize: 12 }}
      >
        <fieldset
          data-testid="render-vars"
          style={{ border: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 8 }}
        >
          <legend
            style={{ fontSize: 12, padding: 0, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 8, width: '100%' }}
          >
            <span>{t('renderVars')}</span>
            {Object.keys(varEdits).length > 0 && (
              <Button
                type="button"
                text
                label={t('renderVarsReset')}
                style={{ marginLeft: 'auto', fontSize: 11 }}
                onClick={() => setVarEdits({})}
              />
            )}
          </legend>
          {declEntries.length === 0 && (
            <span className="text-muted" style={{ fontSize: 12 }}>
              {t('renderVarsEmpty')}
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
            {t('renderContext')}
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
          <InputTextarea
            id="render-context"
            rows={12}
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

        {parseError && (
          <Message severity="error" text={t('renderInvalidJson')} style={{ fontSize: 12, justifyContent: 'flex-start' }} />
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {/* Renders now, skipping the pause: the attempt records the
              current inputs, so the pending delayed one finds nothing new.
              The aria-label keeps the name "Render" without the glyph. */}
          <Button
            type="button"
            text
            label={`↻ ${t('render')}`}
            aria-label={t('render')}
            style={{ fontSize: 12, alignSelf: 'flex-start' }}
            onClick={() => attemptRef.current()}
          />
          {render.isPending && <span className="text-muted">{t('rendering')}</span>}
        </div>
      </aside>
    </div>
  )
}
