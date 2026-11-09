import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { Translations } from '../../i18n'
import type { Confidence, LinkCandidate, LinkFinderResult } from '../../api/types'

const CONFIDENCE_COLORS: Record<Confidence, string> = {
  high: 'var(--color-success)',
  medium: 'var(--color-warning)',
  low: 'var(--color-muted)',
}

const CONFIDENCE_LABELS: Record<Confidence, keyof Translations> = {
  high: 'linkHigh',
  medium: 'linkMedium',
  low: 'linkLow',
}

const CONFIDENCES: Confidence[] = ['high', 'medium', 'low']

/** Open marker, set path, confidence and aspects touched, as one table row. */
const ROW_COLUMNS = '14px minmax(0, 1fr) 120px 70px'

/** The report of the link finder, rendered from the stored JSON. */
export function LinkFinderReport({ report }: { report: LinkFinderResult }) {
  const { t } = useTranslation()
  // The path reads on its own; the key is all there is for a set the run never saw.
  const setName = (key: string) => report.set_paths[key] ?? key

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <Summary report={report} />
      {report.incomplete && (
        <div role="status" style={{ color: CONFIDENCE_COLORS.medium }}>
          {t('linkIncomplete')}
        </div>
      )}
      {report.reduced_mode && (
        <div role="status" style={{ color: CONFIDENCE_COLORS.medium }}>
          {t('linkReduced')}
        </div>
      )}
      {report.candidates.length === 0 ? (
        <div className="text-muted">{t('linkNoCandidates')}</div>
      ) : (
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
            <span>{t('linkCandidate')}</span>
            <span>{t('linkConfidence')}</span>
            <span style={{ textAlign: 'right' }}>{t('linkAspects')}</span>
          </div>
          {report.candidates.map((candidate) => (
            <CandidateRow key={candidate.set_key} candidate={candidate} aspects={report.aspects} />
          ))}
        </div>
      )}
      <SetList label={t('linkEmptySets')} keys={report.empty_sets} setName={setName} />
      <SetList label={t('linkFailedSets')} keys={report.failed_sets} setName={setName} />
      {report.skipped_comments.length > 0 && (
        <div className="text-muted">
          {t('linkSkippedComments')}: {report.skipped_comments.map(setName).join(', ')}
        </div>
      )}
    </div>
  )
}

/** The counts per confidence, and how much of the search space was read. */
function Summary({ report }: { report: LinkFinderResult }) {
  const { t } = useTranslation()
  const count = (confidence: Confidence) =>
    report.candidates.filter((candidate) => candidate.confidence === confidence).length
  return (
    <div
      data-testid="link-summary"
      style={{
        display: 'flex',
        gap: 18,
        flexWrap: 'wrap',
        alignItems: 'baseline',
        padding: '10px 12px',
        border: '1px solid var(--color-divider)',
        borderRadius: 'var(--radius-md)',
      }}
    >
      {CONFIDENCES.map((confidence) => (
        <span key={confidence}>
          <strong
            style={{
              color: CONFIDENCE_COLORS[confidence],
              fontFamily: 'var(--font-heading)',
              fontSize: 22,
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {count(confidence)}
          </strong>{' '}
          {t(CONFIDENCE_LABELS[confidence])}
        </span>
      ))}
      <span className="text-muted">
        {report.requirement_key} ·{' '}
        {t('linkSetsRead', { detailed: report.sets_detailed, screened: report.sets_screened })}
      </span>
    </div>
  )
}

function CandidateRow({
  candidate,
  aspects,
}: {
  candidate: LinkCandidate
  aspects: Record<string, string>
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const color = CONFIDENCE_COLORS[candidate.confidence]
  const total = Object.keys(aspects).length
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
          borderLeft: `3px solid ${color}`,
        }}
      >
        {/* A grid summary drops the browser's own marker, so it draws one. */}
        <span aria-hidden className="text-muted">
          {open ? '▾' : '▸'}
        </span>
        <span>
          {candidate.set_unique_id && (
            <>
              <span style={{ fontFamily: 'var(--font-code)', fontSize: 12 }}>
                {candidate.set_unique_id}
              </span>{' '}
            </>
          )}
          <span>{candidate.path}</span>
          <span className="text-muted" style={{ fontSize: 12 }}>
            {' '}
            ({candidate.spec_status})
          </span>
        </span>
        <span style={{ color, fontWeight: 600 }}>{t(CONFIDENCE_LABELS[candidate.confidence])}</span>
        <span style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
          {`${candidate.covered_aspect_ids.length}/${total}`}
        </span>
      </summary>
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 6,
          padding: '4px 8px 12px 34px',
          borderLeft: `3px solid ${color}`,
        }}
      >
        {candidate.evidence.map((item) => (
          <div
            key={`${item.aspect_id}-${item.test_case_key}`}
            className="text-muted"
            style={{ fontSize: 13 }}
          >
            {aspects[item.aspect_id] ?? item.aspect_id} · {item.test_case_key}
            {item.strength === 'partial' && ` (${t('linkPartial')})`}: {item.evidence}
          </div>
        ))}
        {candidate.already_linked_to.length > 0 && (
          <div>
            <span className="text-muted">{t('linkAlreadyLinkedTo')}: </span>
            <span>{candidate.already_linked_to.join(', ')}</span>
          </div>
        )}
      </div>
    </details>
  )
}

function SetList({
  label,
  keys,
  setName,
}: {
  label: string
  keys: string[]
  setName: (key: string) => string
}) {
  if (keys.length === 0) return null
  return (
    <div>
      <div className="card-kicker">{label}</div>
      <ul style={{ margin: 0, paddingLeft: 18 }}>
        {keys.map((key) => (
          <li key={key}>{setName(key)}</li>
        ))}
      </ul>
    </div>
  )
}
