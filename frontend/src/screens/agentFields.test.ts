/**
 * `AGENT_FIELDS`, `AGENT_READONLY_FIELDS`, `PROJECT_FIELDS` and the dynamic
 * prompt-variable specs (design §5.4).
 *
 * These are functions, not constants, because the path a control writes to
 * depends on scope: the same "enabled" switch addresses
 * `agents.<key>.enabled` globally and
 * `projects."<name>".agents.<key>.enabled` in a project.
 */
import { describe, expect, it } from 'vitest'
import type { PromptVarDefinition } from '../api/types'
import {
  AGENT_FIELDS,
  AGENT_READONLY_FIELDS,
  PROJECT_FIELDS,
  promptVarField,
  varDefault,
} from './agentFields'

const GLOBAL = { kind: 'global' as const }
const PROJECT = { kind: 'project' as const, project: 'Release 2.0' }

function def(overrides: Partial<PromptVarDefinition> = {}): PromptVarDefinition {
  return {
    name: 'Max findings',
    description: 'How many to report',
    value_type: 'number',
    choices: null,
    default_value: 10,
    required: false,
    ...overrides,
  }
}

// --- AGENT_FIELDS -------------------------------------------------------

describe('AGENT_FIELDS', () => {
  it('addresses the global agent table in global scope', () => {
    const keys = AGENT_FIELDS(GLOBAL, 'reviewer').map((f) => f.key)
    expect(keys).toEqual([
      'agents.reviewer.enabled',
      'agents.reviewer.prompt.file',
      'agents.reviewer.prompt.variant',
    ])
  })

  it('addresses the project override table in project scope, quoting the name', () => {
    const keys = AGENT_FIELDS(PROJECT, 'reviewer').map((f) => f.key)
    expect(keys).toEqual([
      'projects."Release 2.0".agents.reviewer.enabled',
      'projects."Release 2.0".agents.reviewer.prompt.file',
      'projects."Release 2.0".agents.reviewer.prompt.variant',
    ])
  })

  it('offers no create or delete of the agent itself', () => {
    // D6: defining an agent means shipping a Python class -- a deploy, not a
    // config change. So `endpoint_path` and `class_path` are not editable
    // here, and neither is the agent key.
    const keys = AGENT_FIELDS(GLOBAL, 'reviewer').map((f) => f.key)
    expect(keys.some((key) => key.endsWith('endpoint_path'))).toBe(false)
    expect(keys.some((key) => key.endsWith('class_path'))).toBe(false)
  })

  it('types enabled as a switch', () => {
    const enabled = AGENT_FIELDS(GLOBAL, 'reviewer')[0]
    expect(enabled.type).toBe('bool')
    expect(enabled.hint).not.toBe('')
  })

  it('makes the variant a select when metadata names the variants', () => {
    const fields = AGENT_FIELDS(GLOBAL, 'reviewer', ['Thorough', 'Quick'])
    const variant = fields.find((f) => f.key.endsWith('prompt.variant'))
    expect(variant?.type).toBe('select')
    expect(variant?.options).toEqual(['Thorough', 'Quick'])
  })

  it('falls back to free text when the prompt metadata could not be read', () => {
    // A 404 on the metadata endpoint (a prompt file that moved) must still
    // leave the field editable, or the operator cannot fix the path that
    // caused the 404 in the first place.
    const variant = AGENT_FIELDS(GLOBAL, 'reviewer').find((f) =>
      f.key.endsWith('prompt.variant'),
    )
    expect(variant?.type).toBe('text')
    expect(variant?.options).toBeUndefined()
  })

  it('keeps the variant a select when the configured value is not among the variants', () => {
    // A stale variant name must still be selectable, or the form would
    // silently rewrite it to the first option on the operator's behalf.
    const variant = AGENT_FIELDS(GLOBAL, 'reviewer', ['Thorough'], 'Gone').find((f) =>
      f.key.endsWith('prompt.variant'),
    )
    expect(variant?.options).toEqual(['Gone', 'Thorough'])
  })

  it('does not duplicate a configured variant that is already declared', () => {
    const variant = AGENT_FIELDS(GLOBAL, 'reviewer', ['Thorough', 'Quick'], 'Quick').find(
      (f) => f.key.endsWith('prompt.variant'),
    )
    expect(variant?.options).toEqual(['Thorough', 'Quick'])
  })
})

// --- AGENT_READONLY_FIELDS ---------------------------------------------

describe('AGENT_READONLY_FIELDS', () => {
  it('names the two fields a restart would be needed for', () => {
    expect(AGENT_READONLY_FIELDS('reviewer').map((f) => f.key)).toEqual([
      'agents.reviewer.endpoint_path',
      'agents.reviewer.class_path',
    ])
  })

  it('says in the hint that these are edited in config.toml', () => {
    for (const field of AGENT_READONLY_FIELDS('reviewer')) {
      expect(field.hint).toMatch(/config\.toml/)
    }
  })

  it('always addresses the global table, whatever the scope', () => {
    // A project cannot override either one: the router table is built once at
    // startup from the global agents, so a per-project endpoint_path would be
    // a value that never takes effect.
    expect(AGENT_READONLY_FIELDS('reviewer')[0].key).toBe('agents.reviewer.endpoint_path')
  })
})

// --- PROJECT_FIELDS -----------------------------------------------------

describe('PROJECT_FIELDS', () => {
  it('offers the language override, keyed by the raw project name', () => {
    expect(PROJECT_FIELDS('Release 2.0').map((f) => f.key)).toEqual([
      'projects."Release 2.0".language',
    ])
  })

  it('types language as a select over the supported languages', () => {
    const language = PROJECT_FIELDS('Alpha')[0]
    expect(language.type).toBe('select')
    expect(language.options).toEqual(['de', 'en'])
  })

  it('offers no llm_config — D8 keeps the per-project surface to language and agents', () => {
    expect(PROJECT_FIELDS('Alpha').some((f) => f.key.includes('llm_config'))).toBe(false)
  })
})

// --- promptVarField ----------------------------------------------------

describe('promptVarField', () => {
  it('addresses the variable under the scope prompt vars table', () => {
    const field = promptVarField(PROJECT, 'reviewer', 'max_findings', def())
    expect(field.key).toBe(
      'projects."Release 2.0".agents.reviewer.prompt.vars.max_findings',
    )
  })

  it('quotes a variable name that contains a dot', () => {
    const field = promptVarField(GLOBAL, 'reviewer', 'a.b', def())
    expect(field.key).toBe('agents.reviewer.prompt.vars."a.b"')
  })

  it('renders a number variable as a number input', () => {
    expect(promptVarField(GLOBAL, 'r', 'v', def({ value_type: 'number' })).type).toBe('number')
  })

  it('renders a boolean variable as a switch', () => {
    expect(promptVarField(GLOBAL, 'r', 'v', def({ value_type: 'boolean' })).type).toBe('bool')
  })

  it('renders an enum variable as a select over its declared choices', () => {
    const field = promptVarField(
      GLOBAL,
      'r',
      'v',
      def({ value_type: 'enum', choices: ['formal', 'casual'] }),
    )
    expect(field.type).toBe('select')
    expect(field.options).toEqual(['formal', 'casual'])
  })

  it('renders a string variable as a text input', () => {
    expect(promptVarField(GLOBAL, 'r', 'v', def({ value_type: 'string' })).type).toBe('text')
  })

  it('renders a text variable as a textarea', () => {
    expect(promptVarField(GLOBAL, 'r', 'v', def({ value_type: 'text' })).type).toBe('textarea')
  })

  it('uses the declared name and description as the label and hint', () => {
    const field = promptVarField(
      GLOBAL,
      'r',
      'v',
      def({ name: 'Tone of voice', description: 'How formal to be' }),
    )
    expect(field.label).toBe('Tone of voice')
    expect(field.hint).toBe('How formal to be')
  })

  it('falls back to the variable key as a label when the prompt declares no name', () => {
    const field = promptVarField(GLOBAL, 'r', 'max_findings', def({ name: '' }))
    expect(field.label).toBe('max_findings')
  })

  it('marks a required variable in the hint', () => {
    const field = promptVarField(GLOBAL, 'r', 'v', def({ required: true, description: null }))
    expect(field.hint).toMatch(/required/i)
  })

  it('survives an enum that declares no choices', () => {
    // The server model forbids it, but this renders whatever a prompt file
    // actually contains; an empty select beats a crashed screen.
    const field = promptVarField(GLOBAL, 'r', 'v', def({ value_type: 'enum', choices: null }))
    expect(field.options).toEqual([])
  })
})

// --- varDefault --------------------------------------------------------

describe('varDefault', () => {
  it('reports the declared default as what an unset variable inherits', () => {
    expect(varDefault(def({ default_value: 10 }))).toBe(10)
  })

  it('reports undefined when the prompt declares no default', () => {
    expect(varDefault(def({ default_value: null }))).toBeUndefined()
  })
})
