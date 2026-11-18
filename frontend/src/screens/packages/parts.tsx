/** Pieces the agent package screen and its dialogs share. */
import { Message } from 'primereact/message'
import { useTranslation } from 'react-i18next'
import { issuesOf, packageErrorKey } from '../../api/packages'
import type { PackageReport } from '../../api/types'

const LIST = { margin: '2px 0 0', paddingLeft: 18, fontSize: 12 } as const

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
        <li key={`w-${warning}`} className="text-muted">
          {t('packagesWarning')}: {warning}
        </li>
      ))}
    </ul>
  )
}

/**
 * A version's check report: the package-level findings, then one line per
 * agent entry point. `registered` maps agent keys to entry points, so a line
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
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <Findings errors={report.errors} warnings={report.warnings} />
      {agents.length === 0 && (
        <div className="text-muted" style={{ fontSize: 13 }}>
          {t('packagesNoAgents')}
        </div>
      )}
      {agents.map(([entryPoint, agent]) => {
        const keys = Object.keys(registered).filter((key) => registered[key] === entryPoint)
        return (
          <div key={entryPoint} data-testid={`package-agent-${entryPoint}`}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', fontSize: 13 }}>
              <span
                aria-label={agent.ok ? 'ok' : t('packagesCheckFailed')}
                style={{ color: agent.ok ? 'var(--color-success)' : 'var(--color-danger)' }}
              >
                {agent.ok ? '✔' : '✖'}
              </span>
              <code>{entryPoint}</code>
              {keys.length > 0 && (
                <span className="text-muted">
                  {t('packagesRegisteredAs')} <code>{keys.join(', ')}</code>
                </span>
              )}
              <span
                className="text-muted"
                style={{ fontSize: 11, fontFamily: 'var(--font-code)', marginLeft: 'auto' }}
              >
                {agent.class_path}
              </span>
            </div>
            <Findings errors={agent.errors} warnings={agent.warnings} />
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
