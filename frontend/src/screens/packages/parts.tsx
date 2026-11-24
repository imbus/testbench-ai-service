/** Pieces the agent package screen and its dialogs share. */
import { Message } from 'primereact/message'
import { useTranslation } from 'react-i18next'
import { issuesOf, packageErrorKey } from '../../api/packages'
import type { PackageReport } from '../../api/types'

const LIST = { margin: '2px 0 0', paddingLeft: 18, fontSize: 12 } as const

/** A stroke icon in the style of the nav rail's; `d` is the SVG path. */
export function Icon({ d, size = 16, color }: { d: string; size?: number; color?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color ?? 'currentColor'}
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      style={{ flex: 'none' }}
    >
      <path d={d} />
    </svg>
  )
}

export const ICONS = {
  upload: 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12',
  file: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6',
  close: 'M18 6 6 18M6 6l12 12',
  box: 'M21 16V8a2 2 0 0 0-1-1.7l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.7l7 4a2 2 0 0 0 2 0l7-4a2 2 0 0 0 1-1.7zM3.3 7 12 12l8.7-5M12 22V12',
  check: 'M20 6 9 17l-5-5',
  warn: 'M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01',
}

/** A bordered list whose rows are divided by hairlines, as in the cards. */
export const LIST_GROUP = {
  border: '1px solid var(--color-divider)',
  borderRadius: 8,
  overflow: 'hidden',
} as const
export const LIST_ROW = {
  padding: '9px 14px',
  borderTop: '1px solid var(--color-divider)',
} as const

/** Errors and warnings as two short lists, nothing when both are empty. */
function Findings({ errors, warnings }: { errors: string[]; warnings: string[] }) {
  const { t } = useTranslation()
  if (errors.length === 0 && warnings.length === 0) return null
  return (
    <ul style={LIST}>
      {errors.map((error) => (
        <li key={`e-${error}`} style={{ color: 'var(--color-danger)' }}>
          {t('packagesError')}: {error}
        </li>
      ))}
      {warnings.map((warning) => (
        <li key={`w-${warning}`} style={{ color: 'var(--color-warning)' }}>
          {t('packagesWarning')}: {warning}
        </li>
      ))}
    </ul>
  )
}

/**
 * A version's check report: the package-level findings, then one row per
 * agent entry point. `registered` maps agent keys to entry points, so a row
 * can say which key an entry point is configured under.
 */
export function ReportView({
  report,
  registered = {},
}: {
  report: PackageReport
  registered?: Record<string, string>
}) {
  const { t } = useTranslation()
  const agents = Object.entries(report.agents)
  // A package with LLM clients only has no agents to list, and says so nowhere.
  const hasClients = Object.keys(report.llm_clients ?? {}).length > 0
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {(report.errors.length > 0 || report.warnings.length > 0) && (
        <Message
          severity={report.errors.length > 0 ? 'error' : 'warn'}
          style={{ justifyContent: 'flex-start' }}
          content={<Findings errors={report.errors} warnings={report.warnings} />}
        />
      )}
      {agents.length === 0 ? (
        !hasClients && (
          <div className="text-muted" style={{ fontSize: 13 }}>
            {t('packagesNoAgents')}
          </div>
        )
      ) : (
        <div style={LIST_GROUP}>
          {agents.map(([entryPoint, agent], index) => {
            const keys = Object.keys(registered).filter((key) => registered[key] === entryPoint)
            const color = agent.ok ? 'var(--color-success)' : 'var(--color-danger)'
            return (
              <div
                key={entryPoint}
                data-testid={`package-agent-${entryPoint}`}
                style={{ ...LIST_ROW, ...(index === 0 ? { borderTop: 'none' } : {}) }}
              >
                <div style={{ display: 'flex', gap: 10, alignItems: 'center', fontSize: 13 }}>
                  <span
                    role="img"
                    aria-label={agent.ok ? 'ok' : t('packagesCheckFailed')}
                    style={{ display: 'flex' }}
                  >
                    <Icon d={agent.ok ? ICONS.check : ICONS.close} color={color} />
                  </span>
                  <code style={{ fontWeight: 600 }}>{entryPoint}</code>
                  {keys.length > 0 && (
                    <span
                      style={{
                        fontSize: 12,
                        padding: '1px 8px',
                        borderRadius: 999,
                        background: 'var(--color-success-soft)',
                      }}
                    >
                      {t('packagesRegisteredAs')}{' '}
                      <code style={{ fontSize: 12 }}>{keys.join(', ')}</code>
                    </span>
                  )}
                  <span
                    className="text-muted"
                    style={{
                      fontSize: 11,
                      fontFamily: 'var(--font-code)',
                      marginLeft: 'auto',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      minWidth: 0,
                    }}
                  >
                    {agent.class_path}
                  </span>
                </div>
                <div style={{ paddingLeft: 26 }}>
                  <Findings errors={agent.errors} warnings={agent.warnings} />
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

/**
 * What a wheel is installed for. Agents and the LLM provider are two things,
 * each with a screen: a screen shows a package's side that belongs to it and
 * leaves the other side to the other screen.
 */
export type PackageKind = 'agents' | 'provider'

/**
 * The LLM clients of a version's check report, one row each. `inUse` is the
 * entry point the service's configuration takes its custom provider from.
 */
export function LlmClientsView({
  report,
  inUse,
}: {
  report: PackageReport
  inUse?: string | null
}) {
  const { t } = useTranslation()
  const clients = Object.entries(report.llm_clients ?? {})
  if (clients.length === 0) return null
  return (
    <div style={LIST_GROUP}>
      {clients.map(([entryPoint, client], index) => {
        const color = client.ok ? 'var(--color-success)' : 'var(--color-danger)'
        return (
          <div
            key={entryPoint}
            data-testid={`package-llm-client-${entryPoint}`}
            style={{ ...LIST_ROW, ...(index === 0 ? { borderTop: 'none' } : {}) }}
          >
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', fontSize: 13 }}>
              <span
                role="img"
                aria-label={client.ok ? 'ok' : t('packagesCheckFailed')}
                style={{ display: 'flex' }}
              >
                <Icon d={client.ok ? ICONS.check : ICONS.close} color={color} />
              </span>
              <code style={{ fontWeight: 600 }}>{entryPoint}</code>
              {inUse === entryPoint && (
                <span
                  style={{
                    fontSize: 12,
                    padding: '1px 8px',
                    borderRadius: 999,
                    background: 'var(--color-success-soft)',
                  }}
                >
                  {t('packagesProviderInUse')}
                </span>
              )}
              <span
                className="text-muted"
                style={{
                  fontSize: 11,
                  fontFamily: 'var(--font-code)',
                  marginLeft: 'auto',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  minWidth: 0,
                }}
              >
                {client.class_path}
              </span>
            </div>
            <div style={{ paddingLeft: 26 }}>
              <Findings errors={client.errors} warnings={client.warnings} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

/**
 * A failed package call: the translated case first, the backend's English
 * detail and any issues below it as secondary information.
 */
export function PackageError({ error, upload }: { error: unknown; upload?: boolean }) {
  const { t } = useTranslation()
  const detail = error instanceof Error ? error.message : undefined
  const issues = issuesOf(error)
  return (
    <Message
      severity="error"
      role="alert"
      style={{ justifyContent: 'flex-start' }}
      content={
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <div>{t(packageErrorKey(error, { upload }))}</div>
          {detail && (
            <div className="text-muted" style={{ fontSize: 12 }}>
              {detail}
            </div>
          )}
          {issues.length > 0 && (
            <ul style={LIST}>
              {issues.map((issue) => (
                <li key={issue}>{issue}</li>
              ))}
            </ul>
          )}
        </div>
      }
    />
  )
}
