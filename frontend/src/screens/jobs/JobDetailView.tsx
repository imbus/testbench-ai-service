import { useEffect, useState } from 'react'
import { ProgressBar } from 'primereact/progressbar'
import { useTranslation } from 'react-i18next'
import type {
  CoverageResult,
  JobDetail,
  JobStatus,
  JobSummary,
  LinkFinderResult,
} from '../../api/types'
import { type Lang, type Translations, useLang } from '../../i18n'
import { formatActivityTime } from '../Status'
import { CoverageReport } from './CoverageReport'
import { LinkFinderReport } from './LinkFinderReport'

const STATUS_COLORS: Record<JobStatus, string> = {
  succeeded: '#2e9e6b',
  running: '#b8860b',
  failed: '#c0392b',
}

export const STATUS_LABELS: Record<JobStatus, keyof Translations> = {
  running: 'jobStatusRunning',
  succeeded: 'jobStatusSucceeded',
  failed: 'jobStatusFailed',
}

export const LOCALES: Record<Lang, string> = { de: 'de-DE', en: 'en-GB' }

/** Shape as well as color, so the status reads without telling red from green. */
const STATUS_ICONS: Record<JobStatus, string> = {
  running: '●',
  succeeded: '✓',
  failed: '✕',
}

export function StatusLabel({ job }: { job: JobSummary }) {
  const { t } = useTranslation()
  const color = STATUS_COLORS[job.status]
  return (
    <span
      data-status={job.status}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        // Wide enough for the longest label in either language, so the pills
        // line up down the column.
        minWidth: '9.5em',
        padding: '2px 8px',
        fontSize: 12,
        fontWeight: 600,
        color,
        background: `color-mix(in srgb, ${color} 12%, transparent)`,
        border: `1px solid color-mix(in srgb, ${color} 35%, transparent)`,
        whiteSpace: 'nowrap',
      }}
    >
      <span aria-hidden="true" style={{ width: '1em', textAlign: 'center' }}>
        {STATUS_ICONS[job.status]}
      </span>
      {t(STATUS_LABELS[job.status])}
    </span>
  )
}

/** "42s", "1m 38s", "1h 05m": the smaller unit is padded so a column lines up. */
export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60
  if (hours) return `${hours}h ${String(minutes).padStart(2, '0')}m`
  if (minutes) return `${minutes}m ${String(secs).padStart(2, '0')}s`
  return `${secs}s`
}

/** How long a job ran: to its finish, or up to `now` while it is still running. */
export function jobSeconds(job: JobSummary, now: Date): number {
  const end = job.finished_at ? new Date(job.finished_at) : now
  return (end.getTime() - new Date(job.created_at).getTime()) / 1000
}

/** A job's duration, ticking once a second while the job is running. */
export function Duration({ job }: { job: JobSummary }) {
  const running = job.status === 'running' && !job.finished_at
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    if (!running) return
    const timer = window.setInterval(() => setNow(new Date()), 1000)
    return () => window.clearInterval(timer)
  }, [running])
  return <>{formatDuration(jobSeconds(job, now))}</>
}

export function Progress({ job }: { job: JobSummary }) {
  if (job.status !== 'running' || !job.progress) return null
  const { done, total, text } = job.progress
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <ProgressBar
        value={total > 0 ? Math.round((done / total) * 100) : 0}
        showValue={false}
        style={{ height: 6 }}
      />
      <span className="text-muted" style={{ fontSize: 12 }}>
        <span>{`${done}/${total}`}</span>
        {text ? ` · ${text}` : ''}
      </span>
    </div>
  )
}

function Report({ job }: { job: JobDetail }) {
  if (job.report_type === 'coverage_checker' && job.report) {
    return <CoverageReport report={job.report as CoverageResult} />
  }
  if (job.report_type === 'link_finder' && job.report) {
    return <LinkFinderReport report={job.report as LinkFinderResult} />
  }
  // A report type this UI does not know is still shown, as the stored JSON.
  if (job.report) {
    return (
      <pre style={{ margin: 0, overflowX: 'auto', fontFamily: 'var(--font-code)', fontSize: 12 }}>
        {JSON.stringify(job.report, null, 2)}
      </pre>
    )
  }
  return null
}

/**
 * One job with its report, as the console's job page and the browser page the
 * TestBench client opens (`/jobs/{id}/view`) both show it.
 */
export function JobDetailView({ job }: { job: JobDetail }) {
  const { t } = useTranslation()
  const lang = useLang()
  // The root key leads; the items follow without repeating it.
  const items = [...new Set([job.root_key, ...job.item_ids].filter((id): id is string => !!id))]
  const when = (iso: string) => formatActivityTime(iso, undefined, LOCALES[lang])
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div>
        <h2 style={{ margin: 0 }}>{job.agent_key}</h2>
        <div className="text-muted">
          {t('jobProject')}: {job.project_name} ({job.project_key})
          {items.length > 0 && ` · ${items.join(', ')}`}
        </div>
        <div className="text-muted" style={{ fontSize: 13 }}>
          {t('jobStarted')}: {when(job.created_at)}
          {job.finished_at && ` · ${t('jobFinished')}: ${when(job.finished_at)}`}
        </div>
      </div>
      <div>
        <StatusLabel job={job} />
        <Progress job={job} />
      </div>
      {job.error && (
        <div style={{ color: STATUS_COLORS.failed }}>
          <span className="card-kicker">{t('jobError')}</span>
          <div>{job.error}</div>
        </div>
      )}
      {job.warnings.length > 0 && (
        <div>
          <div className="card-kicker">{t('jobWarnings')}</div>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {job.warnings.map((warning, i) => (
              <li key={i}>{warning}</li>
            ))}
          </ul>
        </div>
      )}
      <Report job={job} />
    </div>
  )
}
