import type { PromptVarDecl } from '../../api/types'
import { templateCompletions } from './templateCompletion'

const agent = {
  name: '<str>',
  language: '<str | None>',
  project: { key: '<str>', title: '<str>' },
  test_cases: [{ uid: '<str>' }],
  settings: { '<key>': '<str>' },
}

function decl(name: string, extra: Partial<PromptVarDecl> = {}): PromptVarDecl {
  return { name, description: null, value_type: 'string', choices: null, default_value: null, required: false, ...extra }
}

const vars = {
  tone: decl('tone', { value_type: 'enum', choices: ['formal', 'casual'], description: 'Answer style' }),
  max_items: decl('max_items', { value_type: 'number', default_value: 5 }),
}

const ctx = { agent, vars }
const labels = (text: string) => templateCompletions(text, ctx)?.items.map((item) => item.label) ?? null

describe('templateCompletions', () => {
  it('offers nothing outside a Jinja tag', () => {
    expect(labels('Hello agent.')).toBeNull()
    expect(labels('{{ agent.name }} and agent.')).toBeNull()
  })

  it('offers nothing inside a comment', () => {
    expect(labels('{# agent.')).toBeNull()
  })

  it('offers the two roots inside an expression', () => {
    expect(labels('{{ ')).toEqual(['agent', 'vars'])
    expect(labels('{{ ag')).toEqual(['agent', 'vars'])
  })

  it('offers the agent fields with their sampled type', () => {
    const result = templateCompletions('{{ agent.', ctx)
    expect(result?.items.map((item) => [item.label, item.detail])).toEqual([
      ['name', 'str'],
      ['language', 'str | None'],
      ['project', 'object'],
      ['test_cases', 'list'],
      ['settings', 'dict'],
    ])
    expect(result?.replaceLength).toBe(0)
  })

  it('walks nested agent objects', () => {
    expect(labels('{{ agent.project.')).toEqual(['key', 'title'])
  })

  it('reports how much of the word the completion replaces', () => {
    expect(templateCompletions('{{ agent.project.ti', ctx)?.replaceLength).toBe(2)
  })

  it('stops below a list or a dict, where the path is no longer one expression', () => {
    expect(labels('{{ agent.test_cases.')).toBeNull()
    expect(labels('{{ agent.settings.')).toBeNull()
    expect(labels('{{ agent.nope.')).toBeNull()
  })

  it('offers the variant variables with their declaration', () => {
    const result = templateCompletions('{% if vars.', ctx)
    expect(result?.items.map((item) => item.label)).toEqual(['tone', 'max_items'])
    expect(result?.items[0]).toMatchObject({ detail: 'enum', documentation: 'Answer style\n\nChoices: formal, casual' })
    expect(result?.items[1]).toMatchObject({ detail: 'number', documentation: 'Default: 5' })
  })

  it('has no children below a variant variable', () => {
    expect(labels('{{ vars.tone.')).toBeNull()
  })

  it('does not complete a chain hanging off a subscript or call', () => {
    expect(labels('{{ items[0].')).toBeNull()
    expect(labels('{{ f().')).toBeNull()
  })

  it('offers statement keywords at the start of a block tag', () => {
    expect(labels('{% ')).toContain('for')
    expect(labels('{%- en')).toContain('endif')
    expect(labels('{% ')).not.toContain('agent')
  })

  it('offers roots after the keyword of a block tag', () => {
    expect(labels('{% for item in ')).toEqual(['agent', 'vars'])
  })

  it('uses the latest tag when several are open in the text', () => {
    expect(labels('{{ agent.name }}\n{% if vars.tone %}\n{{ agent.')).toContain('project')
  })
})
