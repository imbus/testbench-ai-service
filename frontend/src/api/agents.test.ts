/**
 * The inherit/override model the Agents and Projects screens are built on.
 *
 * `config.toml` carries a global `[agents.<key>]` table and, per project, a
 * sparse `[projects."<name>".agents.<key>"]` override. Every screen in phase 3
 * shows one of three states for a given setting, and the whole point of these
 * helpers is that the three states stay distinguishable: a project that says
 * nothing is NOT the same as a project that says `false`.
 */
import { describe, expect, it } from 'vitest'
import {
  agentPath,
  effectiveAgent,
  overridingProjects,
  projectAgentPath,
  projectPath,
} from './agents'

const CONFIG = {
  agents: {
    test_case_set_reviewer: {
      enabled: true,
      endpoint_path: '/test-case-set-reviews',
      class_path: 'a.b.Reviewer',
      prompt: { file: 'test_case_set_reviewer/prompt.yaml', variant: 'Thorough' },
    },
    defect_explainer: {
      enabled: false,
      endpoint_path: '/defect-explanations',
      class_path: 'a.b.Explainer',
      prompt: { file: 'defect_explainer/prompt.yaml' },
    },
  },
  projects: {
    Alpha: {
      language: 'en',
      agents: {
        test_case_set_reviewer: { enabled: false },
      },
    },
    'Release 2.0': {
      agents: {
        test_case_set_reviewer: { prompt: { variant: 'Quick' } },
      },
    },
    Empty: {},
  },
}

// --- path building -------------------------------------------------------

describe('path building', () => {
  it('addresses a global agent setting', () => {
    expect(agentPath('test_case_set_reviewer', 'enabled')).toBe(
      'agents.test_case_set_reviewer.enabled',
    )
  })

  it('addresses a nested global agent setting', () => {
    expect(agentPath('defect_explainer', 'prompt.variant')).toBe(
      'agents.defect_explainer.prompt.variant',
    )
  })

  it('addresses a project table', () => {
    expect(projectPath('Alpha')).toBe('projects.Alpha')
  })

  it('quotes a project name that contains a dot', () => {
    // The whole reason the tokenizer exists: an unquoted `Release 2.0` splits
    // into two segments and addresses nothing the server would recognise.
    expect(projectPath('Release 2.0')).toBe('projects."Release 2.0"')
  })

  it('addresses a per-project agent override with a dotted project name', () => {
    expect(projectAgentPath('Release 2.0', 'test_case_set_reviewer', 'enabled')).toBe(
      'projects."Release 2.0".agents.test_case_set_reviewer.enabled',
    )
  })

  it('quotes a project name containing a quote', () => {
    expect(projectPath('He said "no"')).toBe('projects."He said \\"no\\""')
  })

  it('leaves a project name with a space unquoted', () => {
    // A space is not a delimiter and is not ambiguous, so quoting it would be
    // a gratuitous change to a path phase 2 already produced.
    expect(projectPath('My Project')).toBe('projects.My Project')
  })

  it('addresses a project language override', () => {
    expect(projectPath('Alpha', 'language')).toBe('projects.Alpha.language')
  })
})

// --- effectiveAgent -----------------------------------------------------

describe('effectiveAgent', () => {
  it('returns the global settings in global scope', () => {
    const agent = effectiveAgent(CONFIG, 'test_case_set_reviewer', null)
    expect(agent.enabled).toBe(true)
    expect(agent.prompt?.variant).toBe('Thorough')
  })

  it('applies a project override on top of the global value', () => {
    const agent = effectiveAgent(CONFIG, 'test_case_set_reviewer', 'Alpha')
    expect(agent.enabled).toBe(false)
  })

  it('keeps global settings the project does not mention', () => {
    // The override is sparse -- Alpha says only `enabled = false`, so the
    // endpoint, class and prompt all still come from the global table.
    const agent = effectiveAgent(CONFIG, 'test_case_set_reviewer', 'Alpha')
    expect(agent.endpoint_path).toBe('/test-case-set-reviews')
    expect(agent.prompt?.file).toBe('test_case_set_reviewer/prompt.yaml')
  })

  it('merges a nested prompt override without dropping its siblings', () => {
    const agent = effectiveAgent(CONFIG, 'test_case_set_reviewer', 'Release 2.0')
    expect(agent.prompt?.variant).toBe('Quick')
    expect(agent.prompt?.file).toBe('test_case_set_reviewer/prompt.yaml')
  })

  it('falls back to the global value for a project with no agents table', () => {
    const agent = effectiveAgent(CONFIG, 'test_case_set_reviewer', 'Empty')
    expect(agent.enabled).toBe(true)
  })

  it('falls back to the global value for a project absent from the config', () => {
    const agent = effectiveAgent(CONFIG, 'test_case_set_reviewer', 'Not In Config')
    expect(agent.enabled).toBe(true)
  })

  it('is empty for an agent key the config does not declare', () => {
    expect(effectiveAgent(CONFIG, 'no_such_agent', null)).toEqual({})
  })

  it('tolerates a config with no agents table at all', () => {
    expect(effectiveAgent({}, 'test_case_set_reviewer', null)).toEqual({})
  })

  it('tolerates malformed branches instead of throwing', () => {
    // `disk` is unvalidated TOML: every level of it can be the wrong type, and
    // a render must not crash on a config the operator can still fix.
    for (const config of [
      { agents: 'nonsense' },
      { agents: { test_case_set_reviewer: 5 } },
      { projects: 'nonsense' },
      { agents: { a: { enabled: true } }, projects: { Alpha: { agents: 'nonsense' } } },
    ]) {
      expect(() => effectiveAgent(config, 'a', 'Alpha')).not.toThrow()
    }
  })
})

// --- overridingProjects -------------------------------------------------

describe('overridingProjects', () => {
  it('names the projects that override a given agent', () => {
    expect(overridingProjects(CONFIG, 'test_case_set_reviewer')).toEqual([
      'Alpha',
      'Release 2.0',
    ])
  })

  it('excludes a project that overrides only its language', () => {
    const config = { projects: { Alpha: { language: 'en' } } }
    expect(overridingProjects(config, 'test_case_set_reviewer')).toEqual([])
  })

  it('excludes a project that overrides a different agent', () => {
    expect(overridingProjects(CONFIG, 'defect_explainer')).toEqual([])
  })

  it('is empty for a config with no projects', () => {
    expect(overridingProjects({}, 'test_case_set_reviewer')).toEqual([])
  })

  it('counts an empty override table as an override', () => {
    // `[projects.Alpha.agents.x]` with nothing in it is still a block the
    // operator wrote, and the Agents list must show it rather than hide it.
    const config = { projects: { Alpha: { agents: { x: {} } } } }
    expect(overridingProjects(config, 'x')).toEqual(['Alpha'])
  })
})
