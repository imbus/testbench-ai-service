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

export function StatusLabel({ job }: { job: JobSummary }) {
  const { t } = useTranslation()
  return (
    <span style={{ color: STATUS_COLORS[job.status], fontWeight: 500 }}>
      {t(STATUS_LABELS[job.status])}
    </span>
  )
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
