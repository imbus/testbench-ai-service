import { useNavigate, useParams } from 'react-router-dom'
import { Column } from 'primereact/column'
import { DataTable } from 'primereact/datatable'
import { Dropdown } from 'primereact/dropdown'
import { Message } from 'primereact/message'
import { ProgressBar } from 'primereact/progressbar'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useJob, useJobs } from '../api/queries'
import type { CoverageResult, JobDetail, JobStatus, JobSummary } from '../api/types'
import { type Lang, type Translations, useLang } from '../i18n'
import { formatActivityTime } from './Status'
import { CoverageReport } from './jobs/CoverageReport'

const STATUS_COLORS: Record<JobStatus, string> = {
  succeeded: '#2e9e6b',
  running: '#b8860b',
  failed: '#c0392b',
}

const STATUS_LABELS: Record<JobStatus, keyof Translations> = {
  running: 'jobStatusRunning',
  succeeded: 'jobStatusSucceeded',
  failed: 'jobStatusFailed',
}

const STATUSES: JobStatus[] = ['running', 'succeeded', 'failed']
const LOCALES: Record<Lang, string> = { de: 'de-DE', en: 'en-GB' }

function StatusLabel({ job }: { job: JobSummary }) {
  const { t } = useTranslation()
  return (
    <span style={{ color: STATUS_COLORS[job.status], fontWeight: 500 }}>
      {t(STATUS_LABELS[job.status])}
    </span>
  )
}

function Progress({ job }: { job: JobSummary }) {
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

function JobPane({ jobId }: { jobId: string }) {
  const { t } = useTranslation()
  const lang = useLang()
  const job = useJob(jobId)
  if (job.isError) return <Message severity="error" text={t('jobsError')} />
  const data = job.data
  if (!data) return null
  const when = (iso: string) => formatActivityTime(iso, undefined, LOCALES[lang])
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div>
        <h3 style={{ margin: 0 }}>{data.agent_key}</h3>
        <div className="text-muted">
          {t('jobProject')}: {data.project_name} ({data.project_key})
          {data.item_ids.length > 0 && ` · ${data.item_ids.join(', ')}`}
        </div>
        <div className="text-muted" style={{ fontSize: 13 }}>
          {t('jobStarted')}: {when(data.created_at)}
          {data.finished_at && ` · ${t('jobFinished')}: ${when(data.finished_at)}`}
        </div>
      </div>
      <div>
        <StatusLabel job={data} />
        <Progress job={data} />
      </div>
      {data.error && (
        <div style={{ color: STATUS_COLORS.failed }}>
          <span className="card-kicker">{t('jobError')}</span>
          <div>{data.error}</div>
        </div>
      )}
      {data.warnings.length > 0 && (
        <div>
          <div className="card-kicker">{t('jobWarnings')}</div>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {data.warnings.map((warning, i) => (
              <li key={i}>{warning}</li>
            ))}
          </ul>
        </div>
      )}
      <Report job={data} />
    </div>
  )
}

/** The signed-in user's agent jobs: the list on the left, the picked job on the right. */
export function Jobs() {
  const { t } = useTranslation()
  const lang = useLang()
  const navigate = useNavigate()
  const { jobId } = useParams()
  const [agent, setAgent] = useState<string | undefined>()
  const [status, setStatus] = useState<JobStatus | undefined>()
  const jobs = useJobs({ agent, status })
  const rows = jobs.data ?? []
  // Only the agents seen so far can be offered; keep the chosen one selectable
  // even when the filtered list no longer shows it.
  const agents = [...new Set([...rows.map((job) => job.agent_key), ...(agent ? [agent] : [])])]

  return (
    <div
      style={{ padding: 'var(--space-4, 16px)', display: 'flex', flexDirection: 'column', gap: 12 }}
    >
      <div>
        <h2 style={{ margin: 0 }}>{t('jobs')}</h2>
        <div className="text-muted">{t('jobsSub')}</div>
      </div>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <Dropdown
          ariaLabel={t('jobFilterAgent')}
          placeholder={t('jobFilterAgent')}
          value={agent ?? null}
          options={agents}
          showClear
          onChange={(event) => setAgent((event.value as string | null) ?? undefined)}
        />
        <Dropdown
          ariaLabel={t('jobFilterStatus')}
          placeholder={t('jobFilterStatus')}
          value={status ?? null}
          options={STATUSES.map((s) => ({ label: t(STATUS_LABELS[s]), value: s }))}
          showClear
          onChange={(event) => setStatus((event.value as JobStatus | null) ?? undefined)}
        />
      </div>
      {jobs.isError && <Message severity="error" text={t('jobsError')} />}
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'flex-start' }}>
        <div style={{ flex: '2 1 320px', minWidth: 0 }}>
          {jobs.isSuccess && rows.length === 0 && (
            <div className="text-muted">{t('jobsEmpty')}</div>
          )}
          {rows.length > 0 && (
            <DataTable
              value={rows}
              dataKey="job_id"
              selectionMode="single"
              metaKeySelection={false}
              selection={rows.find((job) => job.job_id === jobId) ?? null}
              onSelectionChange={(event) => {
                const picked = event.value as JobSummary | null
                if (picked) navigate(`/admin/jobs/${picked.job_id}`)
              }}
              size="small"
            >
              <Column
                header={t('jobFilterAgent')}
                body={(job: JobSummary) => (
                  <div>
                    <div>{job.agent_key}</div>
                    <div className="text-muted" style={{ fontSize: 12 }}>
                      {job.project_name} ·{' '}
                      {formatActivityTime(job.created_at, undefined, LOCALES[lang])}
                    </div>
                  </div>
                )}
              />
              <Column
                header={t('jobFilterStatus')}
                body={(job: JobSummary) => (
                  <div>
                    <StatusLabel job={job} />
                    <Progress job={job} />
                  </div>
                )}
              />
            </DataTable>
          )}
        </div>
        <div data-testid="job-detail" style={{ flex: '3 1 420px', minWidth: 0 }}>
          {jobId ? <JobPane jobId={jobId} /> : <div className="text-muted">{t('jobSelect')}</div>}
        </div>
      </div>
    </div>
  )
}
