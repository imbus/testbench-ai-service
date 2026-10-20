import { forwardRef, lazy, Suspense } from 'react'

import type { LintError } from '../api/types'
import type { CompletionContext } from './prompt/templateCompletion'

export type CodeEditorProps = {
  value: string
  onChange: (value: string) => void
  diagnostics?: LintError[]
  readOnly?: boolean
  ariaLabel: string
  fill?: boolean
  /** The names `agent.` / `vars.` complete to; no completion when absent. */
  completion?: CompletionContext
  /** Which cached model the editor shows; switching keeps each model's undo history and view state. */
  modelKey?: string
  /** Every model key still in use; cached models not listed are disposed. */
  keepModels?: string[]
}

export type CodeEditorHandle = {
  /** Replaces the selection (or inserts at the cursor) and focuses the editor. No-op when read-only. */
  insert: (text: string) => void
}

// Monaco is several MB; only the prompt editor needs it, so it is split into
// its own chunk and fetched the first time an editor is shown.
const MonacoEditor = lazy(() => import('./MonacoEditor'))

/** A Jinja template editor. See `MonacoEditor` for the editor itself. */
export const CodeEditor = forwardRef<CodeEditorHandle, CodeEditorProps>(function CodeEditor(props, ref) {
  return (
    <Suspense fallback={<div data-testid="code-editor" style={props.fill ? { height: '100%' } : { minHeight: 80 }} />}>
      <MonacoEditor ref={ref} {...props} />
    </Suspense>
  )
})
