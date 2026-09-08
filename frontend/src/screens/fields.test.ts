import { LLM_FIELDS, LOGGING_FIELDS, SERVICE_TABS, valueAt } from './fields'

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
