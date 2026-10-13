/**
 * The one place Monaco is loaded and configured.
 *
 * Bundled from node_modules, never from a CDN: the console ships inside the
 * Python package and the PyInstaller binary, and must work on networks
 * without internet access.
 *
 * `editor.api` alone is the bare editor; every contribution below is opted
 * into by hand. `editor.main` would pull ~80 languages plus the TS/JSON/CSS/
 * HTML language services (and their workers), none of which a Jinja prompt
 * needs.
 */
import * as monaco from 'monaco-editor/editor/editor.api'
import 'monaco-editor/editor/browser/coreCommands'
import 'monaco-editor/editor/browser/widget/codeEditor/codeEditorWidget'
import 'monaco-editor/editor/contrib/bracketMatching/browser/bracketMatching'
import 'monaco-editor/editor/contrib/clipboard/browser/clipboard'
import 'monaco-editor/editor/contrib/contextmenu/browser/contextmenu'
import 'monaco-editor/editor/contrib/cursorUndo/browser/cursorUndo'
import 'monaco-editor/editor/contrib/find/browser/findController'
import 'monaco-editor/editor/contrib/hover/browser/hoverContribution'
import 'monaco-editor/editor/contrib/linesOperations/browser/linesOperations'
import 'monaco-editor/editor/contrib/multicursor/browser/multicursor'
import 'monaco-editor/editor/contrib/snippet/browser/snippetController2'
import 'monaco-editor/editor/contrib/suggest/browser/suggestController'
import 'monaco-editor/editor/contrib/wordOperations/browser/wordOperations'
import 'monaco-editor/editor/standalone/browser/quickAccess/standaloneCommandsQuickAccess'
import 'monaco-editor/editor/common/standaloneStrings'
import 'monaco-editor/features/codicon/register'
import EditorWorker from 'monaco-editor/editor/editor.worker?worker'

import { type CompletionContext, type TemplateCompletion, templateCompletions } from './prompt/templateCompletion'

export { monaco }

export const LANGUAGE = 'jinja2'
export const THEME = 'tbai'

// Only the base editor worker (diffing, word ranges) -- Jinja has no
// language service of its own.
self.MonacoEnvironment = { getWorker: () => new EditorWorker() }

monaco.languages.register({ id: LANGUAGE })

monaco.languages.setLanguageConfiguration(LANGUAGE, {
  brackets: [['{{', '}}'], ['{%', '%}'], ['(', ')'], ['[', ']']],
  autoClosingPairs: [
    { open: '{{', close: ' }}' },
    { open: '{%', close: ' %}' },
    { open: '{#', close: ' #}' },
    { open: '(', close: ')' },
    { open: '[', close: ']' },
    { open: '"', close: '"', notIn: ['string'] },
    { open: "'", close: "'", notIn: ['string'] },
  ],
  // `.` is a word separator here, so completing `agent.pro|` replaces only `pro`.
  wordPattern: /[A-Za-z_]\w*/,
})

// Prompts are Markdown with Jinja in it, so the grammar is both: Markdown
// for the text, and the Jinja tags (a port of the legacy CodeMirror jinja2
// mode) wherever they appear -- including inside headings, emphasis and code
// blocks, since Jinja renders before anyone reads the Markdown. Markdown
// spans therefore stop at a `{`, letting the tag take over.
monaco.languages.setMonarchTokensProvider(LANGUAGE, {
  keywords: [
    'if', 'elif', 'else', 'endif', 'for', 'endfor', 'in', 'not', 'and', 'or', 'is',
    'set', 'endset', 'macro', 'endmacro', 'call', 'endcall', 'filter', 'endfilter',
    'raw', 'endraw', 'with', 'endwith', 'block', 'endblock', 'include', 'import',
    'from', 'as', 'true', 'false', 'none', 'True', 'False', 'None',
  ],
  roots: ['agent', 'vars'],
  tokenizer: {
    root: [
      { include: '@jinja' },
      [/^\s*```.*$/, 'markup.codeblock', '@codeblock'],
      [/^#{1,6}\s[^{]*/, 'markup.heading'],
      [/^\s*(---|\*\*\*|___)\s*$/, 'markup.hr'],
      [/^\s*>/, 'markup.quote'],
      [/^\s*([-*+]|\d+\.)\s/, 'markup.list'],
      [/\*\*[^*{]+\*\*|__[^_{]+__/, 'markup.bold'],
      [/\*[^*\s{][^*{]*\*/, 'markup.italic'],
      [/`[^`{]+`/, 'markup.code'],
      [/\[[^\]{]*\]\([^){]*\)/, 'markup.link'],
      [/[^{*`[_]+/, ''],
      [/./, ''],
    ],
    jinja: [
      [/\{#/, 'comment', '@comment'],
      [/\{\{-?/, 'delimiter.bracket', '@tag.}}'],
      [/\{%-?/, 'delimiter.bracket', '@tag.%}'],
    ],
    codeblock: [
      [/^\s*```\s*$/, 'markup.codeblock', '@pop'],
      { include: '@jinja' },
      [/[^{]+/, 'markup.codeblock'],
      [/\{/, 'markup.codeblock'],
    ],
    comment: [
      [/#\}/, 'comment', '@pop'],
      [/[^#]+/, 'comment'],
      [/#/, 'comment'],
    ],
    tag: [
      [/-?(\}\}|%\})/, { cases: { '$1==$S2': { token: 'delimiter.bracket', next: '@pop' }, '@default': 'invalid' } }],
      [/"([^"\\]|\\.)*"/, 'string'],
      [/'([^'\\]|\\.)*'/, 'string'],
      [/\d+(\.\d+)?/, 'number'],
      [/\|\s*[A-Za-z_]\w*/, 'type'],
      [/\.[A-Za-z_]\w*/, 'variable.property'],
      [/[A-Za-z_]\w*/, { cases: { '@keywords': 'keyword', '@roots': 'variable.predefined', '@default': 'identifier' } }],
      [/[=<>!+\-*/%~]+/, 'operator'],
      [/\s+/, ''],
      [/./, ''],
    ],
  },
})

/** A CSS custom property from the root element, if it is a colour Monaco accepts. */
function cssColor(name: string): string | undefined {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return /^#[0-9a-f]{3,8}$/i.test(value) ? value : undefined
}

/**
 * Defines (or redefines) the editor theme from the app's own CSS variables,
 * so it follows data-theme/data-brand like every other surface. Monaco only
 * takes literal hex colours, so the variables are read, not referenced.
 */
export function applyEditorTheme(): void {
  const dark = document.documentElement.dataset.theme === 'dark'
  const colors: Record<string, string> = {}
  const set = (key: string, value: string | undefined) => {
    if (value) colors[key] = value
  }
  const bg = cssColor('--color-bg')
  const surface = cssColor('--color-surface')
  const text = cssColor('--color-text')
  const accent = cssColor('--color-accent')
  set('editor.background', bg)
  set('editor.foreground', text)
  set('editorGutter.background', surface)
  set('editorLineNumber.foreground', text && `${text}66`)
  set('editorLineNumber.activeForeground', text)
  set('editorCursor.foreground', accent)
  set('focusBorder', accent)
  set('editorSuggestWidget.background', surface)
  set('editorSuggestWidget.selectedBackground', accent && `${accent}33`)
  set('editorHoverWidget.background', surface)
  set('editorWidget.background', surface)
  monaco.editor.defineTheme(THEME, {
    base: dark ? 'vs-dark' : 'vs',
    inherit: true,
    rules: [
      { token: 'comment', foreground: dark ? '8b949e' : '6a737d', fontStyle: 'italic' },
      { token: 'delimiter.bracket', foreground: dark ? '6fd3a8' : '416180' },
      { token: 'keyword', foreground: dark ? '6fd3a8' : '416180', fontStyle: 'bold' },
      { token: 'variable.predefined', foreground: dark ? '9fe0c2' : '597ea3' },
      { token: 'variable.property', foreground: dark ? '9fe0c2' : '597ea3' },
      { token: 'string', foreground: dark ? 'd9b07a' : '7a5a2a' },
      { token: 'markup.heading', foreground: dark ? 'e7e9ec' : '1d2d3d', fontStyle: 'bold' },
      { token: 'markup.bold', fontStyle: 'bold' },
      { token: 'markup.italic', fontStyle: 'italic' },
      { token: 'markup.code', foreground: dark ? 'd9b07a' : '7a5a2a' },
      { token: 'markup.codeblock', foreground: dark ? 'd9b07a' : '7a5a2a' },
      { token: 'markup.link', foreground: dark ? '94bce3' : '416180', fontStyle: 'underline' },
      { token: 'markup.list', foreground: dark ? '6fd3a8' : '597ea3', fontStyle: 'bold' },
      { token: 'markup.quote', foreground: dark ? '8b949e' : '6a737d' },
      { token: 'markup.hr', foreground: dark ? '8b949e' : '6a737d' },
    ],
    colors,
  })
  monaco.editor.setTheme(THEME)
}

// Monaco's theme is global, so one observer serves every editor.
let themeObserved = false
export function observeTheme(): void {
  if (themeObserved) return
  themeObserved = true
  applyEditorTheme()
  new MutationObserver(applyEditorTheme).observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['data-theme', 'data-brand'],
  })
}

/**
 * Completion contexts by model URI. A Monaco provider is registered per
 * language, not per editor, so each editor files its own context here and the
 * single provider looks it up by the model it is asked about.
 */
const contexts = new Map<string, () => CompletionContext | undefined>()

export function setCompletionContext(model: monaco.editor.ITextModel, get: () => CompletionContext | undefined): () => void {
  const key = model.uri.toString()
  contexts.set(key, get)
  return () => {
    contexts.delete(key)
  }
}

const KIND: Record<TemplateCompletion['kind'], monaco.languages.CompletionItemKind> = {
  root: monaco.languages.CompletionItemKind.Module,
  field: monaco.languages.CompletionItemKind.Field,
  variable: monaco.languages.CompletionItemKind.Variable,
  keyword: monaco.languages.CompletionItemKind.Keyword,
}

monaco.languages.registerCompletionItemProvider(LANGUAGE, {
  triggerCharacters: ['.'],
  provideCompletionItems(model, position) {
    const ctx = contexts.get(model.uri.toString())?.()
    if (!ctx) return { suggestions: [] }
    const textBefore = model.getValueInRange({
      startLineNumber: 1,
      startColumn: 1,
      endLineNumber: position.lineNumber,
      endColumn: position.column,
    })
    const result = templateCompletions(textBefore, ctx)
    if (!result) return { suggestions: [] }
    const range = new monaco.Range(
      position.lineNumber,
      position.column - result.replaceLength,
      position.lineNumber,
      position.column,
    )
    return {
      suggestions: result.items.map((item, i) => ({
        label: item.label,
        kind: KIND[item.kind],
        detail: item.detail,
        documentation: item.documentation,
        insertText: item.label,
        // Keep the server's order (declaration order) rather than alphabetical.
        sortText: String(i).padStart(4, '0'),
        range,
      })),
    }
  },
})
