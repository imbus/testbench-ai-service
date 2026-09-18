import { splitPath } from '../api/paths'
import { scopedLlmPath } from '../api/agents'
import type { Scope } from '../api/agents'

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
  /**
   * A select that may also be set to nothing.
   *
   * Without it a select can only ever move between its options: a variant
   * written into `config.toml` could be changed but never taken back out,
   * and "no variant" is what makes the prompt's own `default_variant` apply.
   */
  allowEmpty?: boolean
  /**
   * Which setting of an agent this field edits (`enabled`, `prompt.file`,
   * `prompt.variant`), independent of the scope its `key` addresses.
   *
   * Only the agent screens set it, and only so they can read the same setting
   * out of another scope without having to recognise it from the path.
   */
  setting?: string
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

/** The `llm_config` settings, independent of the scope that holds them. */
const LLM_SETTINGS: Omit<FieldSpec, 'key'>[] = [
  {
    setting: 'provider',
    type: 'select',
    options: ['openai', 'azure_openai', 'anthropic', 'custom'],
    hint: 'gpt-*/o-series route to OpenAI, claude-* to Anthropic, regardless of this setting',
  },
  {
    setting: 'model',
    type: 'text',
    hint: "Global override. When empty, each prompt variant's model is used.",
  },
  { setting: 'auth_method', type: 'text', hint: 'Azure only: api_key or entra_id' },
  { setting: 'azure_endpoint', type: 'text', hint: 'Required for Azure' },
  { setting: 'api_version', type: 'text', hint: 'Required for Azure' },
  { setting: 'class_path', type: 'text', hint: 'Custom LLMClient subclass' },
  {
    setting: 'timeout',
    type: 'number',
    hint: "Seconds to wait for an LLM response. Empty uses the provider SDK's default.",
  },
  {
    setting: 'max_retries',
    type: 'number',
    hint: "Retries after a failed LLM request. Empty uses the provider SDK's default.",
  },
]

/**
 * The LLM fields, addressed at one scope.
 *
 * In project scope every control must be removable, so selects gain the blank
 * option that is the only thing wired to `draft.unsetValue`. Globally they
 * must not: the service always has a provider, and offering "none" there is a
 * setting that cannot boot.
 */
export function llmFields(scope: Scope): FieldSpec[] {
  const project = scope.kind === 'project'
  return LLM_SETTINGS.map((spec) => ({
    ...spec,
    key: scopedLlmPath(scope, spec.setting),
    ...(project && spec.type === 'select' ? { allowEmpty: true } : {}),
  }))
}

export const LLM_FIELDS: FieldSpec[] = llmFields({ kind: 'global' })

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
