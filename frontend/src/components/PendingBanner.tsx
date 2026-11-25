import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from 'primereact/button'
import { Message } from 'primereact/message'
import type { ConfigIssue } from '../api/types'
import { useTranslation } from 'react-i18next'
import { useDraft } from '../state/draft'
import { DiffDialog } from './DiffDialog'

/** How long the "changes applied" strip stays. */
const APPLIED_NOTICE_MS = 6000

type Section = 'service' | 'llm' | 'logging' | 'agents' | 'projects'

/** Nav order, so the chips read in the same order as the rail. */
const SECTIONS: { key: Section; path: string }[] = [
  { key: 'service', path: '/admin/service' },
  { key: 'llm', path: '/admin/llm' },
  { key: 'logging', path: '/admin/logging' },
  { key: 'agents', path: '/admin/agents' },
  { key: 'projects', path: '/admin/projects' },
]

/**
 * Which screen edits a dotted config path, judged by the path alone.
 *
 * The fallback for an edit whose origin is not known (see `originOf` on the
 * draft). It follows where a setting is edited, not which table it is stored
 * in: an agent's model lives under `llm_config.agent_models` but is picked on
 * the Agents screen, and a project's prompt settings for an agent are edited
 * on that agent's detail screen. Anything outside the named tables is a
 * top-level service setting.
 */
export function sectionOf(path: string): Section {
  const segments = path.split('.')
  const head = segments[0]
  if (head === 'llm_config') return segments[1] === 'agent_models' ? 'agents' : 'llm'
  if (head === 'projects') {
    if (segments.includes('agent_models') || segments.includes('prompt')) return 'agents'
    if (segments.includes('llm_config')) return 'llm'
    return 'projects'
  }
  if (head === 'logging' || head === 'agents') return head
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

  // An apply empties the draft, but the dialog may have to stay: when the reload
  // did not go cleanly it shows the reason, which is written nowhere else. The
  // dialog keeps its place in the tree below, so it is not remounted then.
  const hasChanges = draft.changeCount > 0

  // A clean apply empties the draft and closes the dialog, which used to leave
  // no trace that anything had happened. This strip says so for a few seconds.
  const [applied, setApplied] = useState(false)
  useEffect(() => {
    if (!applied) return
    const timer = window.setTimeout(() => setApplied(false), APPLIED_NOTICE_MS)
    return () => window.clearTimeout(timer)
  }, [applied])

  if (!hasChanges && !showDiff && !applied) return null

  const perSection = new Map<Section, number>()
  for (const path of Object.keys(draft.edits)) {
    // Where the change was made, when the draft remembers; else where it is edited.
    const section = draft.originOf?.(path) ?? sectionOf(path)
    perSection.set(section, (perSection.get(section) ?? 0) + 1)
  }

  return (
    <>
      {hasChanges && (
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
                      <b>{draft.changeCount}</b> {t('unapplied', { count: draft.changeCount })}
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
        </>
      )}
      {!hasChanges && applied && (
        <Message
          severity="success"
          role="status"
          className="banner"
          style={{ padding: '7px 16px', justifyContent: 'flex-start' }}
          text={t('appliedNotice')}
        />
      )}
      {showDiff && (
        <DiffDialog
          onClose={() => setShowDiff(false)}
          onIssues={onIssues}
          onApplied={() => setApplied(true)}
        />
      )}
    </>
  )
}
