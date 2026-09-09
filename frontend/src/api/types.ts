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
