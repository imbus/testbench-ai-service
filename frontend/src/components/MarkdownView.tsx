import { useState } from 'react'
import { SelectButton } from 'primereact/selectbutton'
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

  return (
    <div className="markdown-view">
      {/* A pair of toggle buttons, the current mode the pressed one;
          `allowEmpty` off so a click on it cannot leave neither view. */}
      <SelectButton
        aria-label={t('markdownViewMode')}
        className="markdown-view-modes"
        value={mode}
        allowEmpty={false}
        options={[
          { label: t('markdownViewRendered'), value: 'markdown' },
          { label: t('markdownViewPlain'), value: 'plain' },
        ]}
        onChange={(event) => {
          if (event.value) setMode(event.value as MarkdownMode)
        }}
        pt={{ button: { style: { padding: '2px 8px', fontSize: 11 } } }}
      />
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
