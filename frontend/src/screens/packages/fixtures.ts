/** Test data for the agent package screens. */
import type { AgentPackage, PackagesResponse, PackageVersion } from '../../api/types'

export function version(overrides: Partial<PackageVersion> = {}): PackageVersion {
  return {
    name: 'acme-tb-agents',
    version: '1.2.0',
    filename: 'acme_tb_agents-1.2.0-py3-none-any.whl',
    sha256: '3f9a0c1d2e3f4a5b6c7d8e9f',
    size: 2048,
    uploaded_at: '2026-11-17T09:00:00Z',
    uploaded_by: 'admin',
    active: true,
    report: {
      ok: false,
      errors: [],
      warnings: ['Package warning: no README'],
      agents: {
        risk_rater: {
          entry_point: 'risk_rater',
          class_path: 'acme.risk:RiskRater',
          ok: true,
          errors: [],
          warnings: [],
          uses_llm: true,
          default_endpoint_path: '/acme-risk-rater',
        },
        dup_finder: {
          entry_point: 'dup_finder',
          class_path: 'acme.dup:DupFinder',
          ok: false,
          errors: ['prompts/de/prompt.yaml is missing'],
          warnings: [],
          uses_llm: true,
          default_endpoint_path: null,
        },
      },
    },
    ...overrides,
  }
}

export function pkg(overrides: Partial<AgentPackage> = {}): AgentPackage {
  return {
    name: 'acme-tb-agents',
    versions: [version(), version({ version: '1.1.0', active: false })],
    registered: { acme_risk_rater: 'risk_rater' },
    loaded: true,
    load_error: null,
    ...overrides,
  }
}

export function packages(overrides: Partial<PackagesResponse> = {}): PackagesResponse {
  return { allow_upload: true, default_dirs: false, packages: [pkg()], ...overrides }
}

export function ok(body: unknown, status = 200): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}
