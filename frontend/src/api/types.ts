export interface SessionInfo {
  username: string
  roles: string[]
  is_admin: boolean
  tb_server_url: string
}

export interface ServiceStatus {
  version: string
  host: string
  port: number
  debug: boolean
  uptime_seconds: number
  language: string
}

export interface TestBenchStatus {
  url: string
  reachable: boolean
  detail: string | null
}

export interface ApiKeyStatus {
  name: string
  present: boolean
}

export interface AgentSummary {
  total: number
  enabled: number
  project_overrides: number
  projects: number
}

export interface StatusResponse {
  service: ServiceStatus
  testbench: TestBenchStatus
  api_keys: ApiKeyStatus[]
  agents: AgentSummary
  log_file: string
  in_flight_tasks: number
  restart_required: string[]
}

export interface LogLine {
  raw: string
  timestamp: string | null
  level: string | null
  source: string | null
  message: string
}

export interface ConfigResponse {
  running: Record<string, unknown>
  disk: Record<string, unknown>
  config_path: string
}

export interface MetaResponse {
  tb_server_url: string
}

export interface ConfigIssue {
  path: string
  message: string
  toml_section: string
}

export interface FileDiff {
  path: string
  diff: string
  added: number
  removed: number
}

export interface PreviewResponse {
  valid: boolean
  issues: ConfigIssue[]
  diffs: FileDiff[]
  restart_required: string[]
  in_flight_tasks: number
  toml: string
}

export interface ApplyResponse {
  written: string[]
  backup: string | null
  restart_required: string[]
  reloaded: boolean
  in_flight_tasks: number
  reload_detail: string | null
}

/** One TestBench project, named the way a `[projects."<name>"]` block keys it. */
export interface ProjectRef {
  name: string
  key: string
}

export interface ProjectsResponse {
  projects: ProjectRef[]
  fetched_at: string | null
  /**
   * `'unavailable'` means the server could not ask TestBench — either the
   * login-time fetch failed or none has happened. An empty list is then an
   * absence of information, not an answer, which is what unlocks the Projects
   * screen's free-text "add project by name" field.
   */
  source: 'testbench' | 'unavailable'
  error: string | null
}

/** Declared type of one prompt variable, straight from the prompt YAML. */
export type PromptVarType = 'string' | 'text' | 'boolean' | 'number' | 'enum'

export interface PromptVarDefinition {
  name: string
  description: string | null
  value_type: PromptVarType
  choices: string[] | null
  default_value: unknown
  required: boolean
}

export interface PromptVariantMeta {
  name: string
  description: string | null
  /** As the variant declares it. `null` means "fall back to default_model". */
  model: string | null
  vars: Record<string, PromptVarDefinition>
}

/**
 * Read-only prompt metadata. Carries no message bodies — the variant list and
 * the variable declarations are all the agent form needs.
 */
export interface PromptMeta {
  name: string
  summary: string | null
  description: string | null
  default_model: string
  default_variant: string
  variants: PromptVariantMeta[]
}
