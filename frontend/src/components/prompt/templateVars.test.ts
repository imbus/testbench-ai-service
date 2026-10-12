import { describe, expect, it } from 'vitest'
import { undeclaredVars, usedTemplateVars } from './templateVars'

describe('usedTemplateVars', () => {
  it('finds agent.* and vars.* inside expressions and statements', () => {
    const text = 'Hi {{ agent.defect }}\n{% for c in agent.test_cases %}{{ c }}{% endfor %}{{ vars.tone | upper }}'
    expect(usedTemplateVars(text)).toEqual(['agent.defect', 'agent.test_cases', 'vars.tone'])
  })

  it('ignores names outside template tags', () => {
    expect(usedTemplateVars('see agent.defect in the docs')).toEqual([])
  })

  it('returns each name once, in first-appearance order', () => {
    expect(usedTemplateVars('{{ vars.b }}{{ vars.a }}{{ vars.b }}')).toEqual(['vars.b', 'vars.a'])
  })

  it('handles an unterminated tag without throwing', () => {
    expect(usedTemplateVars('{{ agent.defect ')).toEqual([])
  })
})

describe('undeclaredVars', () => {
  it('returns bare keys of used vars.* not declared on the variant', () => {
    expect(undeclaredVars(['agent.defect', 'vars.tone', 'vars.depth'], ['depth'])).toEqual(['tone'])
  })
})
