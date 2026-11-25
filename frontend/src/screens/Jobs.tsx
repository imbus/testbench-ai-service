import { ApiError } from '../api/client'
import { useState } from 'react'
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
  Duration,
  JobDetailView,
  LOCALES,
  Progress,
  STATUS_COLORS,
  STATUS_ICONS,
  STATUS_LABELS,
  StatusLabel,
} from './jobs/JobDetailView'

const STATUSES: JobStatus[] = ['running', 'succeeded', 'failed']
/** How many jobs one step of the list adds, and the most one request may ask for. */
const JOBS_PAGE = 50
const JOBS_MAX = 200

/**
 * The item a job is for: the unique ID of its tree root. Jobs from before the
 * UID was kept fall back to the root key, else the first item.
 */
function itemLabel(job: JobSummary): string | null {
  return job.root_uid ?? job.root_key ?? job.item_ids[0] ?? null
}

function JobPane({ jobId }: { jobId: string }) {
  const { t } = useTranslation()
  const job = useJob(jobId)
  // "Not there" is not "could not load": an unknown id, or a job of somebody
  // else, is answered with 404 either way, and the list itself is fine.
  if (job.isError) {
    const missing = job.error instanceof ApiError && job.error.status === 404
    return (
      <Message
        severity={missing ? 'info' : 'error'}
        text={t(missing ? 'jobNotFound' : 'jobsError')}
        style={{ justifyContent: 'flex-start' }}
      />
    )
  }
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
  // The server hands out the newest jobs first, a page at a time; the page
  // grows on request up to what one request may ask for.
  const [limit, setLimit] = useState(JOBS_PAGE)
  const jobs = useJobs({ agent, status }, limit)
  const search = params.size > 0 ? `?${params}` : ''

  const setFilter = (key: 'agent' | 'status', value: string | undefined) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  return (
    <div
      style={{
        padding: 'var(--space-4, 16px)',
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
      }}
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
          limit={limit}
          onMore={() => setLimit((current) => Math.min(current + JOBS_PAGE, JOBS_MAX))}
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
  limit,
  onMore,
}: {
  jobs: ReturnType<typeof useJobs>
  agent: string | undefined
  status: JobStatus | undefined
  search: string
  setFilter: (key: 'agent' | 'status', value: string | undefined) => void
  limit: number
  onMore: () => void
}) {
  const { t } = useTranslation()
  const lang = useLang()
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
      <div
        style={{
          display: 'flex',
          gap: 12,
          flexWrap: 'wrap',
          alignItems: 'center',
        }}
      >
        <Dropdown
          ariaLabel={t('jobFilterAgent')}
          placeholder={t('jobFilterAgent')}
          value={agent ?? null}
          options={agents}
          showClear
          onChange={(event) => setFilter('agent', (event.value as string | null) ?? undefined)}
        />
        <StatusChips value={status} onChange={(value) => setFilter('status', value)} />
      </div>
      {jobs.isError && <Message severity="error" text={t('jobsError')} />}
      {jobs.isSuccess && rows.length === 0 && (
        <div className="text-muted">
          {t(session?.has_user_key === false ? 'jobsNoUserKey' : 'jobsEmpty')}
        </div>
      )}
      {rows.length > 0 && (
        <DataTable value={rows} dataKey="job_id" size="small" rowClassName={() => 'tb-link-row'}>
          {/* A real link, stretched over the row by .tb-row-link, so the row
              opens like any link: middle-click, Ctrl-click, copy link. */}
          <Column
            header={t('jobFilterAgent')}
            body={(job: JobSummary) => (
              <Link className="tb-row-link" to={`/admin/jobs/${job.job_id}${search}`}>
                {job.agent_key}
              </Link>
            )}
          />
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
          <Column
            header={t('jobDuration')}
            align="right"
            style={{ fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}
            body={(job: JobSummary) => <Duration job={job} />}
          />
        </DataTable>
      )}
      {/* A full page means there may be more: say so, instead of ending the
          list as if these were all. */}
      {rows.length >= limit && (
        <div
          data-testid="jobs-more"
          className="text-muted"
          style={{ display: 'flex', gap: 12, alignItems: 'center', fontSize: 13 }}
        >
          <span>{t('jobsShowingNewest', { count: rows.length })}</span>
          {limit < JOBS_MAX ? (
            <Button
              type="button"
              outlined
              size="small"
              label={t('jobsShowMore')}
              loading={jobs.isFetching}
              onClick={onMore}
            />
          ) : (
            <span>{t('jobsNarrowDown')}</span>
          )}
        </div>
      )}
    </>
  )
}

/**
 * The status filter as a row of toggle chips: All plus one per status. Each
 * chip carries its status's icon and color, like the pills in the table.
 */
function StatusChips({
  value,
  onChange,
}: {
  value: JobStatus | undefined
  onChange: (value: JobStatus | undefined) => void
}) {
  const { t } = useTranslation()
  const chips: { status: JobStatus | undefined; label: string }[] = [
    { status: undefined, label: t('jobFilterAll') },
    ...STATUSES.map((s) => ({ status: s, label: t(STATUS_LABELS[s]) })),
  ]
  return (
    <div
      role="group"
      aria-label={t('jobFilterStatus')}
      style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}
    >
      {chips.map(({ status, label }) => (
        <button
          key={status ?? 'all'}
          type="button"
          className="tb-chip"
          aria-pressed={value === status}
          data-status={status}
          style={status ? { ['--chip-color' as string]: STATUS_COLORS[status] } : undefined}
          onClick={() => onChange(status)}
        >
          {status && <span aria-hidden="true">{STATUS_ICONS[status]}</span>}
          {label}
        </button>
      ))}
    </div>
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
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 12,
        }}
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
