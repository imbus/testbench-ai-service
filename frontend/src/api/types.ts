export interface SessionInfo {
  username: string
  roles: string[]
  is_admin: boolean
  tb_server_url: string
  has_user_key: boolean
}

export interface ServiceStatus {
  version: string
  host: string
  port: number
  debug: boolean
  uptime_seconds: number
  language: string
  /** When this run of the service started; a restart changes it. */
  started_at: string
  /** Whether the console can restart the service in its process. */
  can_restart: boolean
}

/** Where the service will listen once the restart it accepted is done. */
export interface RestartResponse {
  host: string
  port: number
  tls: boolean
  in_flight_tasks: number
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
  /** Agent package name -> why it is not in use (failed, or waits for a restart). */
  unloaded_packages?: Record<string, string>
  /** Agent key -> why its class failed to import at startup (it has no route). */
  failed_agents?: Record<string, string>
}

export interface ModelUsageEntry {
  provider: string
  model: string
  calls: number
  input_tokens: number
  output_tokens: number
  /** Part of `output_tokens`, not on top of it. */
  reasoning_tokens: number
  last_used: string
}

/** Token totals per model since the usage file was created. */
export interface UsageSummary {
  /** `false` when the usage file could not be read -- `models` is then empty for that reason. */
  available: boolean
  models: ModelUsageEntry[]
}

export interface StatusResponse {
  service: ServiceStatus
  testbench: TestBenchStatus
  api_keys: ApiKeyStatus[]
  agents: AgentSummary
  in_flight_tasks: number
  restart_required: string[]
  token_usage: UsageSummary
  /** Why the LLM client an uploaded package provides is not in use, if it is not. */
  llm_client_error?: string | null
}

export type ActivityScope = 'mine' | 'service' | 'all'

export interface ActivityEntry {
  timestamp: string
  level: string
  source: string
  message: string
  scope: 'user' | 'service'
  agent: string | null
  project_key: string | null
  run_id: string | null
  exc: string | null
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
  /** Client-only identity for editor tabs; assigned on load, stripped before saving. */
  uid?: string
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
  /** Named message lists of a multi-step agent. Read-only in the console. */
  steps?: Record<string, PromptMessageDoc[]>
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

/** Token counts as the provider reported them for one test run. */
export interface TokenUsage {
  /** Every prompt token, cached ones included. */
  input_tokens: number
  output_tokens: number
  /** Part of `output_tokens`, not on top of it; `null` when not reported. */
  reasoning_tokens: number | null
}

export interface PromptTestResult {
  text: string
  latency_ms: number
  /** `null` when the provider (or a custom client) reported no usage. */
  usage?: TokenUsage | null
  resolved: ResolvedRoute
}

/** One `llm_config.extra_models` entry as the LLM view edits it. */
export interface ExtraModelEntry {
  provider: string
  routing: RoutingFamily
}

export type JobStatus = 'running' | 'succeeded' | 'failed'

export interface JobProgress {
  done: number
  total: number
  text: string | null
}

/** A job without its report, as `GET /jobs` lists it. Datetimes are ISO strings. */
export interface JobSummary {
  job_id: string
  agent_key: string
  project_key: string
  project_name: string
  root_key: string | null
  /** Unique ID of the tree root the job was started on; null for jobs from before it was kept. */
  root_uid: string | null
  item_ids: string[]
  status: JobStatus
  progress: JobProgress | null
  error: string | null
  warnings: string[]
  report_type: string | null
  created_at: string
  updated_at: string
  finished_at: string | null
}

/** `report` is stored as the agent returned it; its shape depends on `report_type`. */
export interface JobDetail extends JobSummary {
  report: unknown
}

export type AspectKind = 'happy_path' | 'negative' | 'boundary' | 'non_functional'
export type EvidenceStrength = 'full' | 'partial'
export type CoverageStatus = 'covered' | 'weak' | 'missing'
export type WeakReason = 'only_partial' | 'set_not_released'
export type NoEvidenceReason = 'no_test_cases' | 'no_matching_aspect' | 'interpretation_failed'

export interface Aspect {
  id: string
  statement: string
  kind: AspectKind
  source_quote: string
}

export interface CoverageEvidence {
  set_key: string
  test_case_key: string
  strength: EvidenceStrength
  evidence: string
}

export interface SuggestedTest {
  title: string
  description: string
}

export interface AspectCoverage {
  aspect: Aspect
  status: CoverageStatus
  weak_reason: WeakReason | null
  evidence: CoverageEvidence[]
  gap_reason: string | null
  suggested_test: SuggestedTest | null
}

export interface SetWithoutEvidence {
  set_key: string
  reason: NoEvidenceReason
}

/** Report of the `coverage_checker` agent (`report_type === 'coverage_checker'`). */
export interface CoverageResult {
  requirement_key: string
  aspects: AspectCoverage[]
  sets_without_evidence: SetWithoutEvidence[]
  skipped_comments: string[]
  reduced_mode: boolean
  incomplete: boolean
  no_linked_tests?: boolean
  set_paths: Record<string, string>
}

export type Confidence = 'high' | 'medium' | 'low'

export interface AspectEvidence {
  aspect_id: string
  test_case_key: string
  strength: EvidenceStrength
  evidence: string
}

export interface LinkCandidate {
  set_key: string
  /** Missing in reports stored before it was added. */
  set_unique_id?: string
  set_title: string
  path: string
  spec_status: string
  confidence: Confidence
  covered_aspect_ids: string[]
  evidence: AspectEvidence[]
  already_linked_to: string[]
}

/** Report of the `link_finder` agent (`report_type === 'link_finder'`). */
export interface LinkFinderResult {
  requirement_key: string
  aspects: Record<string, string>
  candidates: LinkCandidate[]
  sets_screened: number
  sets_detailed: number
  empty_sets: string[]
  failed_sets: string[]
  skipped_comments: string[]
  reduced_mode: boolean
  incomplete: boolean
  set_paths: Record<string, string>
}

/** Inspection result for one agent entry point of an uploaded package. */
export interface PackageAgentReport {
  entry_point: string
  class_path: string
  ok: boolean
  errors: string[]
  warnings: string[]
  uses_llm: boolean
  default_endpoint_path: string | null
}

/** Inspection result for a whole package version. */
export interface PackageReport {
  ok: boolean
  errors: string[]
  warnings: string[]
  /** Entry point -> its report. */
  agents: Record<string, PackageAgentReport>
  /** Entry point -> its report; absent in reports written before LLM clients were checked. */
  llm_clients?: Record<string, PackageLlmClientReport>
}

/** Inspection result for one LLM client entry point of an uploaded package. */
export interface PackageLlmClientReport {
  entry_point: string
  class_path: string
  ok: boolean
  errors: string[]
  warnings: string[]
}

/** One uploaded wheel. */
export interface PackageVersion {
  name: string
  version: string
  filename: string
  sha256: string
  size: number
  uploaded_at: string
  uploaded_by: string | null
  active: boolean
  report: PackageReport
}

export interface AgentPackage {
  name: string
  /** Newest upload first. */
  versions: PackageVersion[]
  /** Agent key -> entry point, for the agents of this package in config.toml. */
  registered: Record<string, string>
  /** Entry point of the LLM client config.toml takes from this package, if it does. */
  llm_client?: string | null
  loaded: boolean
  load_error: string | null
}

export interface PackagesResponse {
  allow_upload: boolean
  /** The shipped prompt or template directory is in use: registering is refused. */
  default_dirs: boolean
  packages: AgentPackage[]
}

export interface RegisterAgentRequest {
  entry_point: string
  agent_key: string
  endpoint_path: string
  enabled: boolean
}

export interface RegisterResult {
  written: string[]
  backup: string | null
  restart_required: string[]
}

/** A prompt or template file that exists with other content than the package's. */
export interface FileConflict {
  path: string
  current: string
  incoming: string
}
