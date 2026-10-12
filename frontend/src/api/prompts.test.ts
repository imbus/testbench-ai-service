import { describe, expect, it } from 'vitest'

import { agentContextOf, agentsUsingVariant, emptyMessage, emptyVariant, mergeContext } from './prompts'

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

describe('agentContextOf', () => {
  it('keeps every typed field the agent provides', () => {
    expect(agentContextOf({ a: '<str>', o: { x: '<int>' } }, {})).toEqual({ a: '<str>', o: { x: '<int>' } })
  })
  it("the typed placeholder wins over the skeleton's empty string", () => {
    expect(agentContextOf({ a: '<str>' }, { a: '' })).toEqual({ a: '<str>' })
  })
  it('keeps a referenced path the agent does not provide', () => {
    expect(agentContextOf({ o: { x: '<int>' } }, { o: { typo: '' }, b: '' })).toEqual({
      o: { x: '<int>', typo: '' },
      b: '',
    })
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
    expect(agentsUsingVariant(disk, 'explainer', 'A')).toEqual([{ kind: 'global' }])
  })
  it('finds a project override', () => {
    const disk = { projects: { Alpha: { agents: { explainer: { prompt: { variant: 'A' } } } } } }
    expect(agentsUsingVariant(disk, 'explainer', 'A')).toEqual([
      { kind: 'project', project: 'Alpha' },
    ])
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
