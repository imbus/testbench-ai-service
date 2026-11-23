import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from 'primereact/button'
import { Message } from 'primereact/message'
import type { ConfigIssue } from '../api/types'
import { useTranslation } from 'react-i18next'
import { useDraft } from '../state/draft'
import { DiffDialog } from './DiffDialog'

type Section = 'service' | 'llm' | 'logging' | 'agents' | 'projects'

/** Nav order, so the chips read in the same order as the rail. */
const SECTIONS: { key: Section; path: string }[] = [
  { key: 'service', path: '/admin/service' },
  { key: 'llm', path: '/admin/llm' },
  { key: 'logging', path: '/admin/logging' },
  { key: 'agents', path: '/admin/agents' },
  { key: 'projects', path: '/admin/projects' },
]

/** Which screen edits a dotted config path. Anything outside the named
 * tables is a top-level service setting. */
export function sectionOf(path: string): Section {
  const head = path.split('.', 1)[0]
  if (head === 'llm_config') return 'llm'
  if (head === 'logging' || head === 'agents' || head === 'projects') return head
  return 'service'
}

/** The artboard's top strip: how many changes are queued, and what to do with them. */
export function PendingBanner({
  onIssues,
}: {
  /** Forwarded to the diff dialog so a preview or apply rejection's
   * field-addressed issues can reach the config screens. Optional so callers
   * that don't track issues (and existing tests) need not supply it. */
  onIssues?: (issues: ConfigIssue[]) => void
}) {
  const { t } = useTranslation()
  const draft = useDraft()
  const [showDiff, setShowDiff] = useState(false)
  const [confirming, setConfirming] = useState(false)

  if (draft.changeCount === 0) return null

  const perSection = new Map<Section, number>()
  for (const path of Object.keys(draft.edits)) {
    const section = sectionOf(path)
    perSection.set(section, (perSection.get(section) ?? 0) + 1)
  }

  return (
    <>
      {/* A PrimeReact `Message` stretched into a full-width strip. Its own
          role is `alert`; this is a standing summary rather than an
          interruption, so it keeps the bar's `status` role. */}
      <Message
        severity="warn"
        role="status"
        className="banner"
        style={{
          borderColor: 'var(--color-accent-300)',
          padding: '7px 16px',
          color: 'var(--color-accent-900)',
        }}
        content={
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              flex: 1,
              minWidth: 0,
              flexWrap: 'wrap',
            }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                flex: 'none',
                borderRadius: '50%',
                background: 'var(--color-accent)',
              }}
            />
            {confirming ? (
              <span>{t('discardConfirm', { count: draft.changeCount })}</span>
            ) : (
              <>
                <span>
                  <b>{draft.changeCount}</b> {t('unapplied')}
                </span>
                {/* Where the changes are, not what they are: the exact paths
                    and values are the diff dialog's job. */}
                <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {SECTIONS.filter(({ key }) => perSection.has(key)).map(({ key, path }) => (
                    <Link
                      key={key}
                      to={path}
                      style={{
                        fontSize: 12,
                        padding: '1px 8px',
                        border: '1px solid var(--color-accent-300)',
                        color: 'inherit',
                        textDecoration: 'none',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {t(key)} <b>{perSection.get(key)}</b>
                    </Link>
                  ))}
                </span>
              </>
            )}
            <div style={{ flex: 1 }} />
            {confirming ? (
              <>
                <Button
                  type="button"
                  text
                  size="small"
                  label={t('cancel')}
                  onClick={() => setConfirming(false)}
                />
                <Button
                  type="button"
                  size="small"
                  severity="danger"
                  label={t('discard')}
                  onClick={() => {
                    setConfirming(false)
                    draft.discardAll()
                    onIssues?.([])
                  }}
                />
              </>
            ) : (
              <>
                {/* The queued draft survives reloads and may span several
                    screens, so throwing it away takes a second click. */}
                <Button
                  type="button"
                  text
                  size="small"
                  label={t('discardAsk')}
                  onClick={() => setConfirming(true)}
                />
                {/* One primary verb. It opens the diff; applying happens there,
                    behind the operator's approval of the exact text that will
                    be written. */}
                <Button
                  type="button"
                  size="small"
                  label={t('reviewApply')}
                  onClick={() => setShowDiff(true)}
                />
              </>
            )}
          </div>
        }
      />
      {showDiff && <DiffDialog onClose={() => setShowDiff(false)} onIssues={onIssues} />}
    </>
  )
}
