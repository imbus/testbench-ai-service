import { useState } from 'react'
import { useTranslations, type Lang } from '../i18n'
import { useDraft } from '../state/draft'
import { DiffDialog } from './DiffDialog'

/** The artboard's top strip: how many changes are queued, and what to do with them. */
export function PendingBanner({ lang }: { lang: Lang }) {
  const t = useTranslations(lang)
  const draft = useDraft()
  const [showDiff, setShowDiff] = useState(false)

  if (draft.changeCount === 0) return null

  return (
    <>
      <div
        role="status"
        style={{
          background: 'var(--color-accent-100)',
          borderBottom: '1px solid var(--color-accent-300)',
          padding: '7px 16px',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          fontSize: 13,
          color: 'var(--color-accent-900)',
        }}
      >
        <span
          style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--color-accent)' }}
        />
        <span
          style={{
            minWidth: 0,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          <b>{draft.changeCount}</b> {t.unapplied} ·{' '}
          <span style={{ fontFamily: 'ui-monospace, Menlo, monospace', fontSize: 12 }}>
            {Object.keys(draft.edits).join(', ')}
          </span>
        </span>
        <div style={{ flex: 1 }} />
        <button
          type="button"
          className="btn btn-secondary"
          style={{ padding: '4px 10px', fontSize: 13 }}
          onClick={() => setShowDiff(true)}
        >
          {t.viewDiff}
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          style={{ padding: '4px 10px', fontSize: 13 }}
          onClick={() => draft.discardAll()}
        >
          {t.discard}
        </button>
      </div>
      {showDiff && <DiffDialog lang={lang} onClose={() => setShowDiff(false)} />}
    </>
  )
}
