import { defaultKeymap, history, historyKeymap } from '@codemirror/commands'
import { StreamLanguage } from '@codemirror/language'
import { jinja2 } from '@codemirror/legacy-modes/mode/jinja2'
import { type Diagnostic, setDiagnostics } from '@codemirror/lint'
import { EditorState } from '@codemirror/state'
import { EditorView, keymap, lineNumbers } from '@codemirror/view'
import { useEffect, useRef } from 'react'

import type { LintError } from '../api/types'

// The editor's colours come from the app's own CSS variables (defined in
// styles/industry.css and styles/brand.css), so it follows data-theme like
// every other surface. No CM6 theme package is installed. The mapping
// mirrors the app's existing (CodeMirror 5) editor rules in brand.css:
// content uses --color-bg/--color-text, gutters use --color-surface, and
// the cursor/focus ring use --color-accent.
const theme = EditorView.theme({
  '&': { backgroundColor: 'var(--color-bg)', color: 'var(--color-text)', fontSize: '13px' },
  '.cm-gutters': {
    backgroundColor: 'var(--color-surface)',
    color: 'color-mix(in srgb, var(--color-text) 40%, transparent)',
    border: 'none',
  },
  '.cm-content': { fontFamily: 'ui-monospace, Menlo, Consolas, monospace' },
  '&.cm-focused': { outline: '2px solid var(--color-accent)' },
})

type Props = {
  value: string
  onChange: (value: string) => void
  diagnostics?: LintError[]
  readOnly?: boolean
  ariaLabel: string
}

/**
 * A CodeMirror 6 view for one Jinja template.
 *
 * Deliberately free of behaviour: screen tests mock this component out to a
 * plain textarea, because CM6 needs DOM APIs jsdom does not implement. Logic
 * put here would be logic nothing covers.
 */
export function CodeEditor({ value, onChange, diagnostics, readOnly, ariaLabel }: Props) {
  const host = useRef<HTMLDivElement>(null)
  const view = useRef<EditorView | null>(null)
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange

  useEffect(() => {
    if (!host.current) return
    const editor = new EditorView({
      parent: host.current,
      state: EditorState.create({
        doc: value,
        extensions: [
          lineNumbers(),
          history(),
          keymap.of([...defaultKeymap, ...historyKeymap]),
          StreamLanguage.define(jinja2),
          theme,
          EditorView.lineWrapping,
          EditorState.readOnly.of(Boolean(readOnly)),
          EditorView.contentAttributes.of({ 'aria-label': ariaLabel }),
          EditorView.updateListener.of((update) => {
            if (update.docChanged) onChangeRef.current(update.state.doc.toString())
          }),
        ],
      }),
    })
    view.current = editor
    return () => {
      editor.destroy()
      view.current = null
    }
    // Built once; `value` is synced by the effect below so remounting on every
    // keystroke never happens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readOnly, ariaLabel])

  useEffect(() => {
    const editor = view.current
    if (!editor) return
    const current = editor.state.doc.toString()
    if (current !== value) {
      editor.dispatch({ changes: { from: 0, to: current.length, insert: value } })
    }
  }, [value])

  useEffect(() => {
    const editor = view.current
    if (!editor) return
    const mapped: Diagnostic[] = (diagnostics ?? []).map((error) => {
      const line = editor.state.doc.line(Math.min(Math.max(error.line, 1), editor.state.doc.lines))
      return { from: line.from, to: line.to, severity: 'error', message: error.message }
    })
    editor.dispatch(setDiagnostics(editor.state, mapped))
  }, [diagnostics])

  return <div ref={host} data-testid="code-editor" />
}
