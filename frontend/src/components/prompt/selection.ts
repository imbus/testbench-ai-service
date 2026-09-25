import type { PromptMessageDoc } from '../../api/types'

/** What the editor's centre pane shows. `message.index` is into the SELECTED variant. */
export type Selection = { kind: 'meta' } | { kind: 'variant' } | { kind: 'message'; index: number }

/** The tree/tab label: a file-backed message by its file, an inline one by its first line. */
export function messageLabel(message: PromptMessageDoc, empty: string): string {
  if (message.source === 'file' && message.file) return message.file
  return message.content.split('\n')[0].slice(0, 28) || empty
}

/**
 * Where a message's text lives on disk, for the message toolbar.
 *
 * `docFile` is the document's own `file` (`de/explainer/prompt.yaml`, relative
 * to `prompts_dir`); a template sits next to it.
 */
export function messagePath(docFile: string, variant: string, index: number, message: PromptMessageDoc): string {
  if (message.source === 'file' && message.file) {
    const dir = docFile.includes('/') ? docFile.slice(0, docFile.lastIndexOf('/')) : ''
    return `prompts/${dir ? `${dir}/` : ''}${message.file}`
  }
  return `prompt.yaml › ${variant} › messages[${index}]`
}

export function uniqueVariantName(base: string, existing: string[]): string {
  if (!existing.includes(base)) return base
  let n = 2
  while (existing.includes(`${base} ${n}`)) n += 1
  return `${base} ${n}`
}
