import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import Markdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'

export type MarkdownMode = 'markdown' | 'plain'

// A link in a preview must never navigate the console itself away from an
// unsaved prompt draft.
const COMPONENTS: Components = {
  a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
}

/**
 * Text that is usually Markdown -- a rendered prompt, a model's answer --
 * shown formatted, with a switch back to the exact characters.
 *
 * The plain view matters: the model receives the raw text, not the
 * formatting, so a stray `*` or a missing blank line before a list is only
 * visible there.
 *
 * Raw HTML in the text is never turned into elements (react-markdown escapes
 * it unless a raw-HTML plugin is added, and none is). Rendered prompts carry
 * TestBench data, which must not become markup in the console.
 */
export function MarkdownView({ text, defaultMode = 'markdown' }: { text: string; defaultMode?: MarkdownMode }) {
  const { t } = useTranslation()
  const [mode, setMode] = useState<MarkdownMode>(defaultMode)
  const name = useId()

  return (
    <div className="markdown-view">
      <div role="radiogroup" aria-label={t('markdownViewMode')} className="markdown-view-modes">
        {(['markdown', 'plain'] as const).map((value) => (
          <label key={value} className={mode === value ? 'is-active' : undefined}>
            <input
              type="radio"
              name={name}
              value={value}
              checked={mode === value}
              onChange={() => setMode(value)}
            />
            {value === 'markdown' ? t('markdownViewRendered') : t('markdownViewPlain')}
          </label>
        ))}
      </div>
      {mode === 'markdown' ? (
        <div className="markdown-body" data-testid="markdown-rendered">
          <Markdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>{text}</Markdown>
        </div>
      ) : (
        <pre className="markdown-plain" data-testid="markdown-plain">
          {text}
        </pre>
      )}
    </div>
  )
}
