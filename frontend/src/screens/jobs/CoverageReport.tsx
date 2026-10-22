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

/** The report of the coverage checker, rendered from the stored JSON. */
export function CoverageReport({ report }: { report: CoverageResult }) {
  const { t } = useTranslation()
  const count = (status: CoverageStatus) =>
    report.aspects.filter((entry) => entry.status === status).length
  // The path reads on its own; the key is all there is for a set the run never saw.
  const setName = (key: string) => report.set_paths[key] ?? key

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div>
        <strong style={{ fontSize: 18 }}>
          {`${count('covered')} / ${count('weak')} / ${count('missing')}`}
        </strong>{' '}
        <span className="text-muted">
          {t('coverageCovered')} / {t('coverageWeak')} / {t('coverageMissing')}
        </span>
        <span className="text-muted"> · {report.requirement_key}</span>
      </div>
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
      {report.aspects.map((entry) => (
        <AspectRow key={entry.aspect.id} entry={entry} setName={setName} />
      ))}
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

function AspectRow({
  entry,
  setName,
}: {
  entry: AspectCoverage
  setName: (key: string) => string
}) {
  const { t } = useTranslation()
  return (
    <div
      style={{
        borderLeft: `3px solid ${STATUS_COLORS[entry.status]}`,
        paddingLeft: 10,
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
      }}
    >
      <div>
        <span style={{ color: STATUS_COLORS[entry.status], fontWeight: 600 }}>
          {t(STATUS_LABELS[entry.status])}
        </span>{' '}
        {entry.aspect.statement}
        {entry.weak_reason && (
          <span className="text-muted"> ({t(WEAK_LABELS[entry.weak_reason])})</span>
        )}
      </div>
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
  )
}
