import { useState } from 'react'
import { Button } from 'primereact/button'
import { Message } from 'primereact/message'
import type { ConfigIssue } from '../api/types'
import { useTranslation } from 'react-i18next'
import { useDraft } from '../state/draft'
import { DiffDialog } from './DiffDialog'

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

  if (draft.changeCount === 0) return null

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
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flex: 1, minWidth: 0 }}>
            <span
              style={{
                width: 8,
                height: 8,
                flex: 'none',
                borderRadius: '50%',
                background: 'var(--color-accent)',
              }}
            />
            <span
              style={{
                minWidth: 0,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              <b>{draft.changeCount}</b> {t('unapplied')} ·{' '}
              <span style={{ fontFamily: 'var(--font-code)', fontSize: 12 }}>
                {Object.keys(draft.edits).join(', ')}
              </span>
            </span>
            <div style={{ flex: 1 }} />
            <Button
              type="button"
              outlined
              size="small"
              label={t('viewDiff')}
              onClick={() => setShowDiff(true)}
            />
            <Button
              type="button"
              outlined
              size="small"
              label={t('discard')}
              onClick={() => {
                draft.discardAll()
                // A validation marker must not outlive the draft that caused it.
                onIssues?.([])
              }}
            />
            {/* The artboard's primary verb, and it does what the artboard's does:
                opens the diff. Applying still happens in one place, behind the
                operator's approval of the exact text that will be written. */}
            <Button
              type="button"
              size="small"
              label={t('apply')}
              onClick={() => setShowDiff(true)}
            />
          </div>
        }
      />
      {showDiff && (
        <DiffDialog onClose={() => setShowDiff(false)} onIssues={onIssues} />
      )}
    </>
  )
}
