import { describe, expect, it } from 'vitest'

import type { PromptDocument } from '../api/types'
import { changedFiles, isDirty, promptDraftReducer as reduce } from './promptDraft'

const base: PromptDocument = {
  lang: 'de', agent: 'explainer', file: 'de/explainer/prompt.yaml',
  name: 'E', summary: null, description: null,
  default_model: 'm', default_variant: 'A',
  variants: [
    {
      name: 'A', description: null, model: null, vars: {},
      messages: [
        { role: 'system', source: 'file', file: 'sys.jinja', content: 'S', readable: true },
        { role: 'user', source: 'inline', file: null, content: 'U', readable: true },
      ],
    },
  ],
  agent_context_skeleton: {},
}

describe('header', () => {
  it('sets a header field', () => {
    expect(reduce(base, { type: 'setHeader', field: 'name', value: 'Neu' }).name).toBe('Neu')
  })
  it('does not mutate the input', () => {
    reduce(base, { type: 'setHeader', field: 'name', value: 'Neu' })
    expect(base.name).toBe('E')
  })
})

describe('variants', () => {
  it('adds a variant', () => {
    const next = reduce(base, { type: 'addVariant', name: 'B' })
    expect(next.variants.map((v) => v.name)).toEqual(['A', 'B'])
  })
  it('renames a variant', () => {
    expect(reduce(base, { type: 'renameVariant', from: 'A', to: 'Z' }).variants[0].name).toBe('Z')
  })
  it('repoints default_variant when the default is renamed', () => {
    expect(reduce(base, { type: 'renameVariant', from: 'A', to: 'Z' }).default_variant).toBe('Z')
  })
  it('removes a variant', () => {
    const two = reduce(base, { type: 'addVariant', name: 'B' })
    expect(reduce(two, { type: 'removeVariant', name: 'A' }).variants.map((v) => v.name)).toEqual(['B'])
  })
  it('refuses to remove the last variant', () => {
    // PromptDefinition requires at least one; the UI must not build an invalid doc.
    expect(reduce(base, { type: 'removeVariant', name: 'A' }).variants).toHaveLength(1)
  })
  it('repoints default_variant to the first remaining variant when the default is removed', () => {
    const two = reduce(base, { type: 'addVariant', name: 'B' })
    expect(two.default_variant).toBe('A')
    const next = reduce(two, { type: 'removeVariant', name: 'A' })
    expect(next.variants.map((v) => v.name)).toEqual(['B'])
    expect(next.default_variant).toBe('B')
  })
})

describe('variables', () => {
  it('adds a declaration with a usable default type', () => {
    const next = reduce(base, { type: 'addVar', variant: 'A', key: 'tone' })
    expect(next.variants[0].vars.tone.value_type).toBe('string')
  })
  it('removes a declaration', () => {
    const added = reduce(base, { type: 'addVar', variant: 'A', key: 'tone' })
    expect(reduce(added, { type: 'removeVar', variant: 'A', key: 'tone' }).variants[0].vars).toEqual({})
  })
  it('clears choices when the type stops being enum', () => {
    let next = reduce(base, { type: 'addVar', variant: 'A', key: 'tone' })
    next = reduce(next, {
      type: 'editVar', variant: 'A', key: 'tone',
      decl: { ...next.variants[0].vars.tone, value_type: 'enum', choices: ['a'] },
    })
    next = reduce(next, {
      type: 'editVar', variant: 'A', key: 'tone',
      decl: { ...next.variants[0].vars.tone, value_type: 'string' },
    })
    // PromptVariableDefinition rejects choices on a non-enum type.
    expect(next.variants[0].vars.tone.choices).toBeNull()
  })
  it('normalises a null choices to an empty array when the type becomes enum', () => {
    let next = reduce(base, { type: 'addVar', variant: 'A', key: 'tone' })
    // addVar's default decl has value_type 'string' and choices null.
    next = reduce(next, {
      type: 'editVar', variant: 'A', key: 'tone',
      decl: { ...next.variants[0].vars.tone, value_type: 'enum' },
    })
    // PromptVariableDefinition.validate_choices requires non-empty choices on
    // 'enum'; null would 422 the save, so the reducer must not pass it through.
    expect(next.variants[0].vars.tone.choices).toEqual([])
  })
})

describe('messages', () => {
  it('adds an inline message', () => {
    const next = reduce(base, { type: 'addMessage', variant: 'A' })
    expect(next.variants[0].messages).toHaveLength(3)
    expect(next.variants[0].messages[2].source).toBe('inline')
  })
  it('sets content', () => {
    const next = reduce(base, { type: 'setMessageContent', variant: 'A', index: 1, content: 'X' })
    expect(next.variants[0].messages[1].content).toBe('X')
  })
  it('sets a role', () => {
    const next = reduce(base, { type: 'setMessageRole', variant: 'A', index: 1, role: 'assistant' })
    expect(next.variants[0].messages[1].role).toBe('assistant')
  })
  it('moves a message', () => {
    const next = reduce(base, { type: 'moveMessage', variant: 'A', index: 0, to: 1 })
    expect(next.variants[0].messages.map((m) => m.role)).toEqual(['user', 'system'])
  })
  it('ignores a move off either end', () => {
    expect(reduce(base, { type: 'moveMessage', variant: 'A', index: 0, to: -1 })).toEqual(base)
    expect(reduce(base, { type: 'moveMessage', variant: 'A', index: 1, to: 2 })).toEqual(base)
  })
  it('ignores a move whose source index is out of range, without corrupting the array', () => {
    const next = reduce(base, { type: 'moveMessage', variant: 'A', index: 5, to: 0 })
    expect(next).toEqual(base)
    expect(next.variants[0].messages).toHaveLength(2)
    expect(next.variants[0].messages.every((m) => m !== undefined)).toBe(true)
  })
  it('ignores a move whose source index is negative', () => {
    // A negative index would otherwise hit JS's negative-splice semantics and
    // silently move the last message instead of being a no-op.
    expect(reduce(base, { type: 'moveMessage', variant: 'A', index: -1, to: 0 })).toEqual(base)
  })
  it('removes a message', () => {
    expect(reduce(base, { type: 'removeMessage', variant: 'A', index: 0 }).variants[0].messages).toHaveLength(1)
  })
  it('refuses to remove the last message', () => {
    const one = reduce(base, { type: 'removeMessage', variant: 'A', index: 0 })
    expect(reduce(one, { type: 'removeMessage', variant: 'A', index: 0 }).variants[0].messages).toHaveLength(1)
  })
})

describe('shared template files', () => {
  // build_write_set guarantees two messages naming the same `file` start out
  // identical, and 409s otherwise -- so editing one must edit both, or the
  // draft drifts into a state the backend will refuse to save.
  const shared: PromptDocument = {
    ...base,
    variants: [
      base.variants[0],
      {
        name: 'B', description: null, model: null, vars: {},
        messages: [
          { role: 'system', source: 'file', file: 'sys.jinja', content: 'S', readable: true },
        ],
      },
    ],
  }

  it('editing a file-backed message updates a message in another variant sharing the same file', () => {
    const next = reduce(shared, { type: 'setMessageContent', variant: 'A', index: 0, content: 'S2' })
    expect(next.variants[0].messages[0].content).toBe('S2')
    expect(next.variants[1].messages[0].content).toBe('S2')
  })

  it('editing an inline message does not touch any other message', () => {
    const next = reduce(shared, { type: 'setMessageContent', variant: 'A', index: 1, content: 'U2' })
    expect(next.variants[0].messages[1].content).toBe('U2')
    expect(next.variants[0].messages[0].content).toBe('S')
    expect(next.variants[1].messages[0].content).toBe('S')
  })

  it('names the shared template exactly once after such an edit', () => {
    const next = reduce(shared, { type: 'setMessageContent', variant: 'B', index: 0, content: 'S3' })
    expect(changedFiles(shared, next)).toEqual(['sys.jinja'])
  })

  it('leaves no divergence between the two messages sharing a file after an edit', () => {
    const next = reduce(shared, { type: 'setMessageContent', variant: 'A', index: 0, content: 'S4' })
    const contents = next.variants.flatMap((v) =>
      v.messages.filter((m) => m.source === 'file' && m.file === 'sys.jinja').map((m) => m.content),
    )
    expect(contents).toEqual(['S4', 'S4'])
  })
})

describe('isDirty and changedFiles', () => {
  it('is clean against itself', () => expect(isDirty(base, base)).toBe(false))
  it('is dirty after an edit', () => {
    expect(isDirty(base, reduce(base, { type: 'setHeader', field: 'name', value: 'N' }))).toBe(true)
  })
  it('names the yaml when the header changed', () => {
    const next = reduce(base, { type: 'setHeader', field: 'name', value: 'N' })
    expect(changedFiles(base, next)).toEqual(['de/explainer/prompt.yaml'])
  })
  it('names a template when only its body changed', () => {
    const next = reduce(base, { type: 'setMessageContent', variant: 'A', index: 0, content: 'S2' })
    expect(changedFiles(base, next)).toEqual(['sys.jinja'])
  })
  it('names both when the yaml and a template changed', () => {
    let next = reduce(base, { type: 'setMessageContent', variant: 'A', index: 0, content: 'S2' })
    next = reduce(next, { type: 'setHeader', field: 'name', value: 'N' })
    expect(changedFiles(base, next).sort()).toEqual(['de/explainer/prompt.yaml', 'sys.jinja'])
  })
  it('names nothing when nothing changed', () => expect(changedFiles(base, base)).toEqual([]))
})
