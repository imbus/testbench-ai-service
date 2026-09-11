import { describe, expect, it } from 'vitest'

import { agentsUsingVariant, emptyMessage, emptyVariant, mergeContext, variantByName } from './prompts'
import type { PromptDocument } from './types'

const doc = {
  lang: 'de', agent: 'explainer', file: 'de/explainer/prompt.yaml',
  name: 'E', summary: null, description: null,
  default_model: 'm', default_variant: 'A',
  variants: [
    { name: 'A', description: null, model: null, vars: {}, messages: [] },
    { name: 'B', description: null, model: null, vars: {}, messages: [] },
  ],
  agent_context_skeleton: {},
} satisfies PromptDocument

describe('variantByName', () => {
  it('finds a variant', () => expect(variantByName(doc, 'B')?.name).toBe('B'))
  it('returns undefined for an unknown name', () =>
    expect(variantByName(doc, 'Z')).toBeUndefined())
})

describe('emptyVariant / emptyMessage', () => {
  it('makes a variant with one user message', () => {
    const v = emptyVariant('New')
    expect(v.name).toBe('New')
    expect(v.messages).toHaveLength(1)
    expect(v.messages[0].role).toBe('user')
  })
  it('makes an inline message, never a file one', () => {
    // Phase 4a never creates a file, so a new message must be inline.
    expect(emptyMessage().source).toBe('inline')
    expect(emptyMessage().file).toBeNull()
  })
})

describe('mergeContext', () => {
  it('keeps values the operator already typed', () => {
    expect(mergeContext({ a: '', b: '' }, { a: 'typed' })).toEqual({ a: 'typed', b: '' })
  })
  it('adds keys the skeleton gained', () => {
    expect(mergeContext({ a: '', b: '' }, {})).toEqual({ a: '', b: '' })
  })
  it('drops keys the skeleton no longer has', () => {
    expect(mergeContext({ a: '' }, { a: 'x', gone: 'y' })).toEqual({ a: 'x' })
  })
  it('merges nested objects', () => {
    expect(mergeContext({ r: { t: '', u: '' } }, { r: { t: 'kept' } })).toEqual({
      r: { t: 'kept', u: '' },
    })
  })
  it('replaces a scalar where the skeleton wants an object', () => {
    expect(mergeContext({ r: { t: '' } }, { r: 'scalar' })).toEqual({ r: { t: '' } })
  })
})

describe('agentsUsingVariant', () => {
  it('finds a global reference', () => {
    const disk = { agents: { explainer: { prompt: { variant: 'A' } } } }
    expect(agentsUsingVariant(disk, 'explainer', 'A')).toEqual(['the global agents table'])
  })
  it('finds a project override', () => {
    const disk = { projects: { Alpha: { agents: { explainer: { prompt: { variant: 'A' } } } } } }
    expect(agentsUsingVariant(disk, 'explainer', 'A')).toEqual(["project 'Alpha'"])
  })
  it('ignores a different variant', () => {
    const disk = { agents: { explainer: { prompt: { variant: 'B' } } } }
    expect(agentsUsingVariant(disk, 'explainer', 'A')).toEqual([])
  })
  it('survives unvalidated TOML shapes', () => {
    for (const disk of [{}, { agents: 'x' }, { agents: { explainer: 3 } }, { projects: 7 }]) {
      expect(agentsUsingVariant(disk as never, 'explainer', 'A')).toEqual([])
    }
  })
})
