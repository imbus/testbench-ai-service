import { describe, expect, it } from 'vitest'
import type { PromptMessageDoc } from '../../api/types'
import { messageLabel, messagePath, uniqueVariantName } from './selection'

const inline = (content: string): PromptMessageDoc => ({ role: 'user', source: 'inline', file: null, content, readable: true })
const file: PromptMessageDoc = { role: 'system', source: 'file', file: 'sys.jinja', content: 'x', readable: true }

describe('messageLabel', () => {
  it('uses the file name for a file-backed message', () => {
    expect(messageLabel(file, '(empty)')).toBe('sys.jinja')
  })
  it('uses the first line, cut to 28 characters, for inline text', () => {
    expect(messageLabel(inline('A very long first line that keeps going\nsecond'), '(empty)')).toBe('A very long first line that ')
  })
  it('falls back to the empty label', () => {
    expect(messageLabel(inline(''), '(empty)')).toBe('(empty)')
  })
})

describe('messagePath', () => {
  it('points a file-backed message at its template next to prompt.yaml', () => {
    expect(messagePath('de/explainer/prompt.yaml', 'Thorough', 0, file)).toBe('prompts/de/explainer/sys.jinja')
  })
  it('points an inline message into prompt.yaml', () => {
    expect(messagePath('de/explainer/prompt.yaml', 'Thorough', 1, inline('x'))).toBe('prompt.yaml › Thorough › messages[1]')
  })
})

describe('uniqueVariantName', () => {
  it('returns the base when free, else the first free numbered name', () => {
    expect(uniqueVariantName('New variant', ['A'])).toBe('New variant')
    expect(uniqueVariantName('New variant', ['New variant', 'New variant 2'])).toBe('New variant 3')
  })
})
