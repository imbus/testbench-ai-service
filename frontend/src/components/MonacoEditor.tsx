import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'

import type { CodeEditorHandle, CodeEditorProps } from './CodeEditor'
import { LANGUAGE, THEME, monaco, observeTheme, setCompletionContext } from './monaco'

const LINT_OWNER = 'jinja-lint'

type Cached = { model: monaco.editor.ITextModel; view: monaco.editor.ICodeEditorViewState | null }

/**
 * Models by `modelKey`, module-level so a tab's undo history and view state
 * outlive the editor itself (the pane unmounts while prompt.yaml or the
 * variant settings are open). Disposed through `keepModels`.
 */
const cache = new Map<string, Cached>()
const ANONYMOUS = 'anonymous:'
let anonymousCount = 0

function cachedModel(key: string, value: string): Cached {
  let entry = cache.get(key)
  if (!entry) {
    entry = { model: monaco.editor.createModel(value, LANGUAGE), view: null }
    cache.set(key, entry)
  }
  return entry
}

function dropModel(key: string): void {
  cache.get(key)?.model.dispose()
  cache.delete(key)
}

/**
 * A Monaco editor for one Jinja template. Loaded lazily through `CodeEditor`.
 *
 * Deliberately free of app logic: screen tests mock this component out to a
 * plain textarea, because Monaco needs DOM APIs jsdom does not implement.
 * Logic put here would be logic nothing covers -- the completion rules live
 * in `prompt/templateCompletion.ts`, which is tested on its own. The model
 * cache and its lifecycle below are the exception, deliberately untested
 * under jsdom and checked by hand.
 * The `insert` handle is the one imperative entry point, used by the variable sidebar.
 *
 * With a `modelKey`, models live in a module-level cache and the editor
 * swaps between them, so each keeps its undo history, cursor and scroll.
 * `keepModels` names the keys still in use; the rest are disposed. Without
 * a key the editor owns one private model, as before.
 *
 * The editor is built once per mount; `readOnly` and `ariaLabel` are applied
 * in place, so neither discards undo history, cursor or scroll.
 */
const MonacoEditor = forwardRef<CodeEditorHandle, CodeEditorProps>(function MonacoEditor(
  { value, onChange, diagnostics, readOnly, ariaLabel, fill, completion, modelKey, keepModels },
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
  // An editor without a key owns one private model, as before.
  const anonymousKey = useRef<string | null>(null)
  if (!modelKey && !anonymousKey.current) anonymousKey.current = `${ANONYMOUS}${++anonymousCount}`
  const key = modelKey ?? (anonymousKey.current as string)
  const keyRef = useRef(key)
  const valueRef = useRef(value)
  valueRef.current = value

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
    const entry = cachedModel(keyRef.current, valueRef.current)
    const editor = monaco.editor.create(host.current, {
      model: entry.model,
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
    if (entry.view) editor.restoreViewState(entry.view)
    view.current = editor

    // Completion is looked up by model, so it follows whichever model is shown.
    let unregister = setCompletionContext(entry.model, () => completionRef.current)
    const modelChanged = editor.onDidChangeModel(() => {
      unregister()
      const model = editor.getModel()
      unregister = model ? setCompletionContext(model, () => completionRef.current) : () => {}
    })
    // Editor-level, so only the shown model reports edits.
    const changes = editor.onDidChangeModelContent(() => onChangeRef.current(editor.getValue()))

    // Without `fill`, the editor grows with its content like a textarea.
    const resize = () => {
      if (fill || !host.current) return
      host.current.style.height = `${Math.max(editor.getContentHeight(), 80)}px`
    }
    const sizes = editor.onDidContentSizeChange(resize)
    resize()

    return () => {
      const shown = cache.get(keyRef.current)
      if (shown) shown.view = editor.saveViewState()
      sizes.dispose()
      changes.dispose()
      modelChanged.dispose()
      unregister()
      editor.dispose()
      if (keyRef.current.startsWith(ANONYMOUS)) dropModel(keyRef.current)
      view.current = null
    }
    // Built once; the effects below sync `value`, `readOnly` and `ariaLabel`
    // in place, so remounting on every keystroke never happens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fill])

  // Declared before the value sync, so a switch and a value change in one
  // render apply in that order.
  useEffect(() => {
    const editor = view.current
    if (!editor || keyRef.current === key) return
    const previous = cache.get(keyRef.current)
    if (previous) previous.view = editor.saveViewState()
    keyRef.current = key
    const entry = cachedModel(key, valueRef.current)
    editor.setModel(entry.model)
    if (entry.view) editor.restoreViewState(entry.view)
  }, [key])

  const keep = keepModels?.join('\n')
  useEffect(() => {
    if (keepModels === undefined) return
    for (const cached of [...cache.keys()]) {
      if (cached.startsWith(ANONYMOUS) || cached === keyRef.current) continue
      if (!keepModels.includes(cached)) dropModel(cached)
    }
    // `keep` is the list's content; the array itself is new every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [keep])

  useEffect(() => {
    view.current?.updateOptions({ readOnly: Boolean(readOnly), ariaLabel })
  }, [readOnly, ariaLabel])

  // Also on a model switch: a cached model can be stale (another message on
  // the same file was edited meanwhile) even when `value` itself is unchanged
  // from the previous tab's.
  useEffect(() => {
    const model = view.current?.getModel()
    if (!model) return
    if (model.getValue() !== value) {
      // An edit, not setValue, so an outside change (revert, insert) stays
      // undoable. On the model rather than the editor: the editor's
      // `executeEdits` is a no-op while read-only, which would leave a
      // viewer's cached model stale for good.
      model.pushEditOperations([], [{ range: model.getFullModelRange(), text: value }], () => null)
    }
  }, [value, key])

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
  }, [diagnostics, key])

  return <div ref={host} data-testid="code-editor" style={fill ? { height: '100%' } : undefined} />
})

export default MonacoEditor
