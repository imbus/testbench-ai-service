import { useEffect, useRef, useState } from 'react'
import { useRenderPrompt } from '../api/mutations'
import { mergeContext } from '../api/prompts'
import type { PromptMessageDoc } from '../api/types'
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
  skeleton,
  isAdmin,
  lang = 'de',
}: {
  messages: PromptMessageDoc[]
  vars: Record<string, unknown>
  skeleton: Record<string, unknown>
  isAdmin: boolean
  lang?: Lang
}) {
  const t = useTranslations(lang)
  const render = useRenderPrompt()
  const [contextText, setContextText] = useState(() => JSON.stringify(skeleton, null, 2))
  const [parseError, setParseError] = useState(false)
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
    render.mutate({ messages, vars, agent_context: context })
  }

  return (
    <div data-testid="render-preview" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {/* A wire token (the `agent_context` field of the render request), not
            prose -- kept as-is regardless of `lang`, matching Field.tsx's own
            treatment of spec.key. */}
        <label
          htmlFor="render-context"
          style={{ fontSize: 11, fontFamily: 'ui-monospace, Menlo, monospace' }}
        >
          agent_context
        </label>
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
