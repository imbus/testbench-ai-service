import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { Translations } from '../../i18n'
import type {
  AspectCoverage,
  CoverageResult,
  CoverageStatus,
  NoEvidenceReason,
  WeakReason,
} from '../../api/types'

const STATUS_COLORS: Record<CoverageStatus, string> = {
  covered: '#2e9e6b',
  weak: '#b8860b',
  missing: '#c0392b',
}

const STATUS_LABELS: Record<CoverageStatus, keyof Translations> = {
  covered: 'coverageCovered',
  weak: 'coverageWeak',
  missing: 'coverageMissing',
}

const NO_EVIDENCE_LABELS: Record<NoEvidenceReason, keyof Translations> = {
  no_test_cases: 'coverageNoTestCases',
  no_matching_aspect: 'coverageNoMatchingAspect',
  interpretation_failed: 'coverageInterpretationFailed',
}

const WEAK_LABELS: Record<WeakReason, keyof Translations> = {
  only_partial: 'coverageOnlyPartial',
  set_not_released: 'coverageSetNotReleased',
}

/** Open marker, statement, status and evidence count, as one table row. */
const ROW_COLUMNS = '14px minmax(0, 1fr) 170px 60px'

/** The report of the coverage checker, rendered from the stored JSON. */
export function CoverageReport({ report }: { report: CoverageResult }) {
  const { t } = useTranslation()
  const count = (status: CoverageStatus) =>
    report.aspects.filter((entry) => entry.status === status).length
  // The path reads on its own; the key is all there is for a set the run never saw.
  const setName = (key: string) => report.set_paths[key] ?? key

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <Summary report={report} count={count} />
      {report.incomplete && (
        <div role="status" style={{ color: STATUS_COLORS.weak }}>
          {t('coverageIncomplete')}
        </div>
      )}
      {report.reduced_mode && (
        <div role="status" style={{ color: STATUS_COLORS.weak }}>
          {t('coverageReduced')}
        </div>
      )}
      <div style={{ borderTop: '1px solid var(--color-divider)' }}>
        <div
          className="text-muted"
          style={{
            display: 'grid',
            gridTemplateColumns: ROW_COLUMNS,
            gap: 12,
            padding: '6px 8px',
            fontSize: 12,
            fontWeight: 600,
            borderBottom: '1px solid var(--color-divider)',
          }}
        >
          <span />
          <span>{t('coverageAspect')}</span>
          <span>{t('jobFilterStatus')}</span>
          <span style={{ textAlign: 'right' }}>{t('coverageEvidence')}</span>
        </div>
        {report.aspects.map((entry) => (
          <AspectRow key={entry.aspect.id} entry={entry} setName={setName} />
        ))}
      </div>
      {report.sets_without_evidence.length > 0 && (
        <div>
          <div className="card-kicker">{t('coverageSetsWithoutEvidence')}</div>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {report.sets_without_evidence.map((entry) => (
              <li key={entry.set_key}>
                {setName(entry.set_key)}{' '}
                <span className="text-muted">({t(NO_EVIDENCE_LABELS[entry.reason])})</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {report.skipped_comments.length > 0 && (
        <div className="text-muted">
          {t('coverageSkippedComments')}: {report.skipped_comments.map(setName).join(', ')}
        </div>
      )}
    </div>
  )
}

/** The counts per status as numbers and as one bar split in their proportions. */
function Summary({
  report,
  count,
}: {
  report: CoverageResult
  count: (status: CoverageStatus) => number
}) {
  const { t } = useTranslation()
  const statuses: CoverageStatus[] = ['covered', 'weak', 'missing']
  return (
    <div
      data-testid="coverage-summary"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        padding: '10px 12px',
        border: '1px solid var(--color-divider)',
        borderRadius: 'var(--radius-md)',
      }}
    >
      <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', alignItems: 'baseline' }}>
        {statuses.map((status) => (
          <span key={status}>
            <strong
              style={{
                color: STATUS_COLORS[status],
                fontFamily: 'var(--font-heading)',
                fontSize: 22,
                fontVariantNumeric: 'tabular-nums',
              }}
            >
              {count(status)}
            </strong>{' '}
            {t(STATUS_LABELS[status])}
          </span>
        ))}
        <span className="text-muted">
          {report.requirement_key} · {t('coverageAspectCount', { count: report.aspects.length })}
        </span>
      </div>
      {report.aspects.length > 0 && (
        <div
          aria-hidden
          style={{ display: 'flex', gap: 2, height: 8, borderRadius: 4, overflow: 'hidden' }}
        >
          {statuses.map(
            (status) =>
              count(status) > 0 && (
                <span
                  key={status}
                  style={{ flex: count(status), background: STATUS_COLORS[status] }}
                />
              ),
          )}
        </div>
      )}
    </div>
  )
}

function AspectRow({
  entry,
  setName,
}: {
  entry: AspectCoverage
  setName: (key: string) => string
}) {
  const { t } = useTranslation()
  // A gap is what the reader came for, so a missing aspect starts open.
  const [open, setOpen] = useState(entry.status === 'missing')
  return (
    <details
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
      style={{ borderBottom: '1px solid var(--color-divider)' }}
    >
      <summary
        style={{
          display: 'grid',
          gridTemplateColumns: ROW_COLUMNS,
          gap: 12,
          padding: '7px 8px',
          cursor: 'pointer',
          alignItems: 'baseline',
          borderLeft: `3px solid ${STATUS_COLORS[entry.status]}`,
        }}
      >
        {/* A grid summary drops the browser's own marker, so it draws one. */}
        <span aria-hidden className="text-muted">
          {open ? '▾' : '▸'}
        </span>
        <span>{entry.aspect.statement}</span>
        <span>
          <span style={{ color: STATUS_COLORS[entry.status], fontWeight: 600 }}>
            {t(STATUS_LABELS[entry.status])}
          </span>
          {entry.weak_reason && (
            <span className="text-muted"> ({t(WEAK_LABELS[entry.weak_reason])})</span>
          )}
        </span>
        <span style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
          {entry.evidence.length}
        </span>
      </summary>
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 6,
          padding: '4px 8px 12px 34px',
          borderLeft: `3px solid ${STATUS_COLORS[entry.status]}`,
        }}
      >
        {entry.evidence.length === 0 && (
          <div className="text-muted" style={{ fontSize: 13 }}>
            {t('coverageNoEvidence')}
          </div>
        )}
        {entry.evidence.map((item) => (
          <div
            key={`${item.set_key}-${item.test_case_key}`}
            className="text-muted"
            style={{ fontSize: 13 }}
          >
            {setName(item.set_key)} · {item.test_case_key}: {item.evidence}
          </div>
        ))}
        {entry.gap_reason && (
          <div>
            <span className="text-muted">{t('coverageGap')}: </span>
            <span>{entry.gap_reason}</span>
          </div>
        )}
        {entry.suggested_test && (
          <div>
            <span className="text-muted">{t('coverageSuggestedTest')}: </span>
            <strong>{entry.suggested_test.title}</strong>
            <div className="text-muted" style={{ fontSize: 13 }}>
              {entry.suggested_test.description}
            </div>
          </div>
        )}
      </div>
    </details>
  )
}
