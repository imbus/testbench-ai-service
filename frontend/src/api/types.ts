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

/** One config key pointing at a prompt file. Localized by the caller. */
export type PromptUsage = { agent: string; project: string | null }

export type PromptTreeEntry = {
  agent: string
  file: string
  name: string | null
  variants: string[]
  ok: boolean
  error: string | null
  used_by: PromptUsage[]
}
export type PromptTreeLanguage = { lang: string; prompts: PromptTreeEntry[] }
export type PromptTreeResponse = { languages: PromptTreeLanguage[] }

export type MessageRole = 'system' | 'user' | 'assistant'
export type MessageSource = 'inline' | 'file'
export type PromptMessageDoc = {
  role: MessageRole
  source: MessageSource
  file: string | null
  content: string
  readable: boolean
}

export type VarValueType = 'string' | 'text' | 'boolean' | 'number' | 'enum'
export type PromptVarDecl = {
  name: string
  description: string | null
  value_type: VarValueType
  choices: string[] | null
  default_value: unknown
  required: boolean
}

export type PromptVariantDoc = {
  name: string
  description: string | null
  model: string | null
  vars: Record<string, PromptVarDecl>
  messages: PromptMessageDoc[]
}

export type PromptDocument = {
  lang: string
  agent: string
  file: string
  name: string
  summary: string | null
  description: string | null
  default_model: string
  default_variant: string
  variants: PromptVariantDoc[]
  agent_context_skeleton: Record<string, unknown>
  /** Typed sample of every agent.* field the agent provides (`"<str>"` leaves). */
  agent_context_sample?: Record<string, unknown>
}

export type LintError = { line: number; column: number; message: string }
export type LintResponse = { ok: boolean; errors: LintError[] }
export type RenderedMessage = { role: string; content: string; error: string | null }
export type RenderResponse = { messages: RenderedMessage[] }
export type PromptSaveResponse = {
  written: string[]
  created: string[]
  deleted: string[]
  deletions_skipped: string | null
  backups: string[]
}

export type PromptPlanResponse = {
  created: string[]
  updated: string[]
  deleted: string[]
  deletions_skipped: string | null
}

export type PromptForkResponse = {
  lang: string
  agent: string
  file: string
  created: string[]
  config_backup: string | null
  reloaded: boolean
  reload_detail: string | null
}

export type RoutingFamily = 'chat' | 'reasoning' | 'adaptive' | 'budget' | 'fallback'

export interface CatalogueModel {
  id: string
  routing: RoutingFamily
  /** `builtin` comes from a client's routing set; only `config` is removable. */
  source: 'builtin' | 'config'
}

export interface CatalogueProvider {
  provider: string
  /** Whether a credential exists. Presence only — never a value. */
  key_present: boolean
  models: CatalogueModel[]
}

export interface ModelCatalogue {
  providers: CatalogueProvider[]
}

export interface ResolvedRoute {
  provider: string
  model: string
  /** Which credential the run actually used; `global` means the fallback hit. */
  credential_scope: 'project' | 'global'
}

export interface PromptTestResult {
  text: string
  latency_ms: number
  resolved: ResolvedRoute
}

/** One `llm_config.extra_models` entry as the LLM view edits it. */
export interface ExtraModelEntry {
  provider: string
  routing: RoutingFamily
}
