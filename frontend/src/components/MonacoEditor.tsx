import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'

import type { CodeEditorHandle, CodeEditorProps } from './CodeEditor'
import { LANGUAGE, THEME, monaco, observeTheme, setCompletionContext } from './monaco'

const LINT_OWNER = 'jinja-lint'

/**
 * A Monaco editor for one Jinja template. Loaded lazily through `CodeEditor`.
 *
 * Deliberately free of behaviour: screen tests mock this component out to a
 * plain textarea, because Monaco needs DOM APIs jsdom does not implement.
 * Logic put here would be logic nothing covers -- the completion rules live
 * in `prompt/templateCompletion.ts`, which is tested on its own.
 * The `insert` handle is the one imperative entry point, used by the variable sidebar.
 *
 * The editor is built once per mount; `readOnly` and `ariaLabel` are applied
 * in place, so neither discards undo history, cursor or scroll.
 */
const MonacoEditor = forwardRef<CodeEditorHandle, CodeEditorProps>(function MonacoEditor(
  { value, onChange, diagnostics, readOnly, ariaLabel, fill, completion },
  ref,
) {
  const host = useRef<HTMLDivElement>(null)
  const view = useRef<monaco.editor.IStandaloneCodeEditor | null>(null)
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange
  const completionRef = useRef(completion)
  completionRef.current = completion
  const readOnlyRef = useRef(readOnly)
  readOnlyRef.current = readOnly

  useImperativeHandle(
    ref,
    () => ({
      insert(text: string) {
        const editor = view.current
        if (!editor || readOnlyRef.current) return
        const selection = editor.getSelection()
        if (!selection) return
        editor.executeEdits('insert-variable', [{ range: selection, text, forceMoveMarkers: true }])
        editor.focus()
      },
    }),
    [],
  )

  useEffect(() => {
    if (!host.current) return
    observeTheme()
    const model = monaco.editor.createModel(value, LANGUAGE)
    const editor = monaco.editor.create(host.current, {
      model,
      theme: THEME,
      ariaLabel,
      readOnly: Boolean(readOnly),
      automaticLayout: true,
      minimap: { enabled: false },
      wordWrap: 'on',
      scrollBeyondLastLine: false,
      fontSize: 13,
      fontFamily: 'ui-monospace, Menlo, Consolas, monospace',
      lineNumbersMinChars: 3,
      renderLineHighlight: 'line',
      // Only the template's own names, never words picked up from the text.
      wordBasedSuggestions: 'off',
      quickSuggestions: { other: true, comments: false, strings: false },
      suggest: { showWords: false },
      fixedOverflowWidgets: true,
    })
    view.current = editor

    const unregister = setCompletionContext(model, () => completionRef.current)
    const changes = model.onDidChangeContent(() => onChangeRef.current(model.getValue()))

    // Without `fill`, the editor grows with its content like a textarea.
    const resize = () => {
      if (fill || !host.current) return
      host.current.style.height = `${Math.max(editor.getContentHeight(), 80)}px`
    }
    const sizes = editor.onDidContentSizeChange(resize)
    resize()

    return () => {
      sizes.dispose()
      changes.dispose()
      unregister()
      editor.dispose()
      model.dispose()
      view.current = null
    }
    // Built once; the effects below sync `value`, `readOnly` and `ariaLabel`
    // in place, so remounting on every keystroke never happens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fill])

  useEffect(() => {
    view.current?.updateOptions({ readOnly: Boolean(readOnly), ariaLabel })
  }, [readOnly, ariaLabel])

  useEffect(() => {
    const editor = view.current
    const model = editor?.getModel()
    if (!editor || !model) return
    if (model.getValue() !== value) {
      // An edit, not setValue, so an outside change (revert, insert) stays undoable.
      editor.executeEdits('sync', [{ range: model.getFullModelRange(), text: value }])
    }
  }, [value])

  useEffect(() => {
    const model = view.current?.getModel()
    if (!model) return
    const markers = (diagnostics ?? []).map((error): monaco.editor.IMarkerData => {
      const line = Math.min(Math.max(error.line, 1), model.getLineCount())
      return {
        severity: monaco.MarkerSeverity.Error,
        message: error.message,
        startLineNumber: line,
        startColumn: 1,
        endLineNumber: line,
        endColumn: model.getLineMaxColumn(line),
      }
    })
    monaco.editor.setModelMarkers(model, LINT_OWNER, markers)
  }, [diagnostics])

  return <div ref={host} data-testid="code-editor" style={fill ? { height: '100%' } : undefined} />
})

export default MonacoEditor
