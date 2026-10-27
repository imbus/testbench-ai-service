import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Button } from 'primereact/button'
import { Column } from 'primereact/column'
import { DataTable } from 'primereact/datatable'
import { Dropdown } from 'primereact/dropdown'
import { Message } from 'primereact/message'
import { ProgressBar } from 'primereact/progressbar'
import { useTranslation } from 'react-i18next'
import { useJob, useJobs } from '../api/queries'
import type {
  CoverageResult,
  JobDetail,
  JobStatus,
  JobSummary,
  LinkFinderResult,
} from '../api/types'
import { type Lang, type Translations, useLang } from '../i18n'
import { useSession } from '../state/session'
import { formatActivityTime } from './Status'
import { CoverageReport } from './jobs/CoverageReport'
import { LinkFinderReport } from './jobs/LinkFinderReport'

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

/** The requirement or item a job is for: its root key, else the first item. */
function itemLabel(job: JobSummary): string | null {
  return job.root_key ?? job.item_ids[0] ?? null
}

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

function JobPane({ jobId }: { jobId: string }) {
  const { t } = useTranslation()
  const lang = useLang()
  const job = useJob(jobId)
  if (job.isError) return <Message severity="error" text={t('jobsError')} />
  const data = job.data
  if (!data) return null
  // The root key leads; the items follow without repeating it.
  const items = [...new Set([data.root_key, ...data.item_ids].filter((id): id is string => !!id))]
  const when = (iso: string) => formatActivityTime(iso, undefined, LOCALES[lang])
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div>
        <h2 style={{ margin: 0 }}>{data.agent_key}</h2>
        <div className="text-muted">
          {t('jobProject')}: {data.project_name} ({data.project_key})
          {items.length > 0 && ` · ${items.join(', ')}`}
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

/**
 * The signed-in user's agent jobs: the list on `/admin/jobs`, one job with its
 * report on `/admin/jobs/:jobId`. The filters live in the query string, so
 * opening a job and coming back keeps them, and newer/older step through the
 * same filtered list.
 */
export function Jobs() {
  const { jobId } = useParams()
  const [params, setParams] = useSearchParams()
  const agent = params.get('agent') ?? undefined
  const rawStatus = params.get('status')
  const status = STATUSES.find((s) => s === rawStatus)
  const jobs = useJobs({ agent, status })
  const search = params.size > 0 ? `?${params}` : ''

  const setFilter = (key: 'agent' | 'status', value: string | undefined) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  return (
    <div
      style={{ padding: 'var(--space-4, 16px)', display: 'flex', flexDirection: 'column', gap: 12 }}
    >
      {jobId ? (
        <JobPage jobId={jobId} rows={jobs.data ?? []} search={search} />
      ) : (
        <JobList
          jobs={jobs}
          agent={agent}
          status={status}
          search={search}
          setFilter={setFilter}
        />
      )}
    </div>
  )
}

function JobList({
  jobs,
  agent,
  status,
  search,
  setFilter,
}: {
  jobs: ReturnType<typeof useJobs>
  agent: string | undefined
  status: JobStatus | undefined
  search: string
  setFilter: (key: 'agent' | 'status', value: string | undefined) => void
}) {
  const { t } = useTranslation()
  const lang = useLang()
  const navigate = useNavigate()
  const { session } = useSession()
  const rows = jobs.data ?? []
  // Only the agents seen so far can be offered; keep the chosen one selectable
  // even when the filtered list no longer shows it.
  const agents = [...new Set([...rows.map((job) => job.agent_key), ...(agent ? [agent] : [])])]

  return (
    <>
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
          onChange={(event) => setFilter('agent', (event.value as string | null) ?? undefined)}
        />
        <Dropdown
          ariaLabel={t('jobFilterStatus')}
          placeholder={t('jobFilterStatus')}
          value={status ?? null}
          options={STATUSES.map((s) => ({ label: t(STATUS_LABELS[s]), value: s }))}
          showClear
          onChange={(event) => setFilter('status', (event.value as JobStatus | null) ?? undefined)}
        />
      </div>
      {jobs.isError && <Message severity="error" text={t('jobsError')} />}
      {jobs.isSuccess && rows.length === 0 && (
        <div className="text-muted">
          {t(session?.has_user_key === false ? 'jobsNoUserKey' : 'jobsEmpty')}
        </div>
      )}
      {rows.length > 0 && (
        <DataTable
          value={rows}
          dataKey="job_id"
          selectionMode="single"
          metaKeySelection={false}
          selection={null}
          onSelectionChange={(event) => {
            const picked = event.value as JobSummary | null
            if (picked) navigate(`/admin/jobs/${picked.job_id}${search}`)
          }}
          size="small"
        >
          <Column header={t('jobFilterAgent')} field="agent_key" />
          <Column header={t('jobItem')} body={(job: JobSummary) => itemLabel(job) ?? ''} />
          <Column header={t('jobProject')} field="project_name" />
          <Column
            header={t('jobStarted')}
            body={(job: JobSummary) => formatActivityTime(job.created_at, undefined, LOCALES[lang])}
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
    </>
  )
}

/** One job on a page of its own, with the way back and to its neighbours in the list. */
function JobPage({ jobId, rows, search }: { jobId: string; rows: JobSummary[]; search: string }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  // The list is newest first; a job the list does not show has no neighbours.
  const index = rows.findIndex((job) => job.job_id === jobId)
  const newer = index > 0 ? rows[index - 1] : undefined
  const older = index >= 0 ? rows[index + 1] : undefined
  const open = (job: JobSummary) => navigate(`/admin/jobs/${job.job_id}${search}`)

  return (
    <>
      <div
        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}
      >
        <Link to={`/admin/jobs${search}`}>← {t('jobsBack')}</Link>
        <div style={{ display: 'flex', gap: 4 }}>
          <Button
            type="button"
            text
            label={`‹ ${t('jobNewer')}`}
            disabled={!newer}
            onClick={() => newer && open(newer)}
            style={{ fontSize: 13 }}
          />
          <Button
            type="button"
            text
            label={`${t('jobOlder')} ›`}
            disabled={!older}
            onClick={() => older && open(older)}
            style={{ fontSize: 13 }}
          />
        </div>
      </div>
      <div data-testid="job-detail">
        <JobPane jobId={jobId} />
      </div>
    </>
  )
}
