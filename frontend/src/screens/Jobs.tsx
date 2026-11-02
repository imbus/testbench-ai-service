import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Button } from 'primereact/button'
import { Column } from 'primereact/column'
import { DataTable } from 'primereact/datatable'
import { Dropdown } from 'primereact/dropdown'
import { Message } from 'primereact/message'
import { useTranslation } from 'react-i18next'
import { useJob, useJobs } from '../api/queries'
import type { JobStatus, JobSummary } from '../api/types'
import { useLang } from '../i18n'
import { useSession } from '../state/session'
import { formatActivityTime } from './Status'
import {
  JobDetailView,
  LOCALES,
  Progress,
  STATUS_LABELS,
  StatusLabel,
} from './jobs/JobDetailView'

const STATUSES: JobStatus[] = ['running', 'succeeded', 'failed']

/** The requirement or item a job is for: its root key, else the first item. */
function itemLabel(job: JobSummary): string | null {
  return job.root_key ?? job.item_ids[0] ?? null
}

function JobPane({ jobId }: { jobId: string }) {
  const { t } = useTranslation()
  const job = useJob(jobId)
  if (job.isError) return <Message severity="error" text={t('jobsError')} />
  return job.data ? <JobDetailView job={job.data} /> : null
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
