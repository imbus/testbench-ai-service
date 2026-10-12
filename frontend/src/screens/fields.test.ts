import { LLM_FIELDS, LOGGING_FIELDS, SERVICE_TABS, llmFields, valueAt } from './fields'

const CONFIG = {
  host: '127.0.0.1',
  port: 8010,
  debug: false,
  tb_ssl_verify: true,
  llm_config: { provider: 'openai', model: null },
  logging: { console: { log_level: 'INFO' }, file: { file_name: 'svc.log' } },
}

test('reads a top-level value', () => {
  expect(valueAt(CONFIG, 'host')).toBe('127.0.0.1')
})

test('reads a nested value', () => {
  expect(valueAt(CONFIG, 'logging.console.log_level')).toBe('INFO')
})

test('missing paths read as undefined, not a crash', () => {
  expect(valueAt(CONFIG, 'llm_config.azure_endpoint')).toBeUndefined()
  expect(valueAt(CONFIG, 'nope.nested.deep')).toBeUndefined()
})

test('null is preserved so the UI can show "no override"', () => {
  expect(valueAt(CONFIG, 'llm_config.model')).toBeNull()
})

test('the service tabs match the source design', () => {
  expect(SERVICE_TABS.map((tab) => tab.key)).toEqual(['general', 'tb', 'tls', 'proxy'])
})

test('general tab covers the documented service fields', () => {
  const keys = SERVICE_TABS[0].fields.map((field) => field.key)
  expect(keys).toContain('tb_server_url')
  expect(keys).toContain('host')
  expect(keys).toContain('port')
  expect(keys).toContain('language')
  expect(keys).toContain('prompts_dir')
  // templates_dir is in AppConfig but was missing from the prototype (spec 11.4).
  expect(keys).toContain('templates_dir')
})

test('deployment_mapping is deliberately absent from the LLM fields', () => {
  /** Spec 11.3: the backend has no notion of it, so no control pretends to. */
  expect(LLM_FIELDS.map((field) => field.key)).not.toContain(
    'llm_config.deployment_mapping',
  )
})

test('logging covers both sinks', () => {
  const keys = LOGGING_FIELDS.map((field) => field.key)
  expect(keys).toContain('logging.console.log_level')
  expect(keys).toContain('logging.file.file_name')
})

test('offers the declared LLM timeout and retry options', () => {
  const keys = LLM_FIELDS.map((spec) => spec.key)

  expect(keys).toContain('llm_config.timeout')
  expect(keys).toContain('llm_config.max_retries')
})

// Phase 3: a config path can address a TestBench project by name, and those
// names are arbitrary strings.

const PROJECT_CONFIG = {
  projects: {
    'Release 2.0': { language: 'en' },
    'My Project': { language: 'de' },
  },
}

test('reads through a project name containing a dot', () => {
  expect(valueAt(PROJECT_CONFIG, 'projects."Release 2.0".language')).toBe('en')
})

test('reads through a project name containing a space, unquoted', () => {
  // Unchanged from phase 2: a space is not a delimiter, so it needs no quoting.
  expect(valueAt(PROJECT_CONFIG, 'projects.My Project.language')).toBe('de')
})

test('a dotted project name is not read as nested tables', () => {
  expect(valueAt({ projects: { a: { b: 'wrong' } } }, 'projects."a.b"')).toBeUndefined()
})

describe('llmFields', () => {
  test('global scope keeps the existing top-level keys', () => {
    const keys = llmFields({ kind: 'global' }).map((field) => field.key)
    expect(keys).toEqual([
      'llm_config.provider',
      'llm_config.model',
      'llm_config.auth_method',
      'llm_config.azure_endpoint',
      'llm_config.api_version',
      'llm_config.class_path',
      'llm_config.timeout',
      'llm_config.max_retries',
    ])
  })

  test('LLM_FIELDS stays the global list, so existing callers are unchanged', () => {
    expect(LLM_FIELDS).toEqual(llmFields({ kind: 'global' }))
  })

  test('project scope addresses the project table', () => {
    const keys = llmFields({ kind: 'project', project: 'Alpha' }).map((field) => field.key)
    expect(keys[0]).toBe('projects.Alpha.llm_config.provider')
    expect(keys[7]).toBe('projects.Alpha.llm_config.max_retries')
  })

  test('a dotted project name is quoted', () => {
    const keys = llmFields({ kind: 'project', project: 'Release 2.0' }).map((field) => field.key)
    expect(keys[0]).toBe('projects."Release 2.0".llm_config.provider')
  })

  test('selects gain a way back to inheriting in project scope', () => {
    // Without allowEmpty a select can only move between its options, so an
    // override could be set and never taken back off.
    const provider = llmFields({ kind: 'project', project: 'Alpha' }).find(
      (field) => field.setting === 'provider',
    )
    expect(provider?.type).toBe('select')
    expect(provider?.allowEmpty).toBe(true)
  })

  test('selects have no blank option globally', () => {
    // The service always has a provider; offering "none" there would be a
    // setting that cannot boot.
    const provider = llmFields({ kind: 'global' }).find((field) => field.setting === 'provider')
    expect(provider?.allowEmpty).toBeUndefined()
  })

  test('every field carries the setting it edits', () => {
    for (const field of llmFields({ kind: 'project', project: 'Alpha' })) {
      expect(field.setting, `no setting on ${field.key}`).toBeTruthy()
      expect(field.key.endsWith(field.setting as string)).toBe(true)
    }
  })

  test('options and hints survive the scoping', () => {
    const provider = llmFields({ kind: 'project', project: 'Alpha' }).find(
      (field) => field.setting === 'provider',
    )
    expect(provider?.options).toEqual(['openai', 'azure_openai', 'anthropic', 'custom'])
    expect(provider?.hint).toBeTruthy()
  })
})
