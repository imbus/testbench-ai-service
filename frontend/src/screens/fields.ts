import { splitPath } from '../api/paths'

export type FieldType = 'text' | 'textarea' | 'number' | 'bool' | 'select' | 'list'

export interface FieldSpec {
  /** Dotted path into the config object returned by GET /config. */
  key: string
  type: FieldType
  hint: string
  options?: string[]
  /**
   * Label to show instead of the path's last segment.
   *
   * Only prompt variables use it: their key is `max_findings` but the prompt
   * author named them "Maximum findings", and that declared name is what the
   * operator should read.
   */
  label?: string
}

export interface ServiceTab {
  key: string
  /** Translation key for the tab label. */
  labelKey: 'general' | 'tbConn' | 'tls' | 'proxy'
  fields: FieldSpec[]
}

const LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

export const SERVICE_TABS: ServiceTab[] = [
  {
    key: 'general',
    labelKey: 'general',
    fields: [
      { key: 'tb_server_url', type: 'text', hint: 'Base URL of the TestBench REST API' },
      { key: 'host', type: 'text', hint: 'Bind address' },
      { key: 'port', type: 'number', hint: 'Port to listen on' },
      { key: 'debug', type: 'bool', hint: 'Verbose logging, auto-reload' },
      {
        key: 'language',
        type: 'select',
        options: ['de', 'en'],
        hint: 'Default language for prompt resolution and localization',
      },
      { key: 'prompts_dir', type: 'text', hint: 'Directory with prompt YAML files' },
      { key: 'templates_dir', type: 'text', hint: 'Directory with output templates' },
    ],
  },
  {
    key: 'tb',
    labelKey: 'tbConn',
    fields: [
      { key: 'tb_ssl_verify', type: 'bool', hint: 'Verify the TestBench TLS certificate' },
      { key: 'tb_ssl_ca_bundle', type: 'text', hint: 'Path to a CA bundle' },
      { key: 'tb_connect_timeout', type: 'number', hint: 'Seconds to wait while connecting' },
      { key: 'tb_read_timeout', type: 'number', hint: 'Seconds to wait for data' },
      {
        key: 'tb_max_retries',
        type: 'number',
        hint: 'Retries after connection errors — idempotent methods only',
      },
    ],
  },
  {
    key: 'tls',
    labelKey: 'tls',
    fields: [
      { key: 'ssl_cert', type: 'text', hint: 'Certificate file' },
      { key: 'ssl_key', type: 'text', hint: 'Private key file' },
      {
        key: 'ssl_ca_cert',
        type: 'text',
        hint: 'CA certificate — when set, client certificates are required (mTLS)',
      },
    ],
  },
  {
    key: 'proxy',
    labelKey: 'proxy',
    fields: [
      { key: 'trusted_proxies', type: 'list', hint: 'Trusted proxy IP addresses' },
    ],
  },
]

export const LLM_FIELDS: FieldSpec[] = [
  {
    key: 'llm_config.provider',
    type: 'select',
    options: ['openai', 'azure_openai', 'anthropic', 'custom'],
    hint: 'gpt-*/o-series route to OpenAI, claude-* to Anthropic, regardless of this setting',
  },
  {
    key: 'llm_config.model',
    type: 'text',
    hint: "Global override. When empty, each prompt variant's model is used.",
  },
  { key: 'llm_config.auth_method', type: 'text', hint: 'Azure only: api_key or entra_id' },
  { key: 'llm_config.azure_endpoint', type: 'text', hint: 'Required for Azure' },
  { key: 'llm_config.api_version', type: 'text', hint: 'Required for Azure' },
  { key: 'llm_config.class_path', type: 'text', hint: 'Custom LLMClient subclass' },
  {
    key: 'llm_config.timeout',
    type: 'number',
    hint: "Seconds to wait for an LLM response. Empty uses the provider SDK's default.",
  },
  {
    key: 'llm_config.max_retries',
    type: 'number',
    hint: "Retries after a failed LLM request. Empty uses the provider SDK's default.",
  },
]

export const LOGGING_FIELDS: FieldSpec[] = [
  { key: 'logging.console.log_level', type: 'select', options: LOG_LEVELS, hint: 'Console' },
  { key: 'logging.console.log_format', type: 'text', hint: 'Python logging format string' },
  { key: 'logging.file.file_name', type: 'text', hint: 'Relative paths resolve from the CWD' },
  { key: 'logging.file.log_level', type: 'select', options: LOG_LEVELS, hint: 'File' },
  { key: 'logging.file.log_format', type: 'text', hint: 'Python logging format string' },
]

/** Read a dotted path out of the config object, tolerating absent branches. */
export function valueAt(config: Record<string, unknown>, path: string): unknown {
  // Tokenized, not split on '.': a segment can be a TestBench project name,
  // and those may contain dots. A malformed path addresses nothing rather
  // than throwing -- `prune` calls this for every stored edit, including one
  // left behind by an older console.
  let segments: string[]
  try {
    segments = splitPath(path)
  } catch {
    return undefined
  }
  return segments.reduce<unknown>((node, key) => {
    if (node === null || typeof node !== 'object') return undefined
    return (node as Record<string, unknown>)[key]
  }, config)
}
