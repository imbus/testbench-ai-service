import { useEffect } from 'react'
import type { ApiError } from '../api/client'
import { useApply, usePreview } from '../api/mutations'
import type { ConfigIssue } from '../api/types'
import { useTranslations, type Lang } from '../i18n'
import { useDraft } from '../state/draft'

/** A structured `{message, issues}` apply-rejection detail, as opposed to a bare string. */
function issuesOf(detail: unknown): ConfigIssue[] | null {
  if (
    detail !== null &&
    typeof detail === 'object' &&
    Array.isArray((detail as { issues?: unknown }).issues)
  ) {
    return (detail as { issues: ConfigIssue[] }).issues
  }
  return null
}

function IssueList({ issues }: { issues: ConfigIssue[] }) {
  return (
    <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
      {issues.map((issue) => (
        <li key={`${issue.path}-${issue.message}`}>
          <code>{issue.path || issue.toml_section}</code> — {issue.message}
        </li>
      ))}
    </ul>
  )
}

/**
 * The gate between a draft and the filesystem.
 *
 * Previews on open rather than on every keystroke: the preview reads the file
 * off disk and constructs an AppConfig (which imports agent classes), so it is
 * not something to run per character.
 */
export function DiffDialog({ lang, onClose }: { lang: Lang; onClose: () => void }) {
  const t = useTranslations(lang)
  const draft = useDraft()
  const preview = usePreview()
  const apply = useApply()

  useEffect(() => {
    preview.mutate(draft.edits)
    // Deliberately on mount only: re-previewing as the draft changes underneath
    // an open dialog would show the operator a diff they did not ask to approve.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const data = preview.data
  const applyIssues = apply.isError ? issuesOf((apply.error as ApiError).detail) : null

  const onApply = () => {
    apply.mutate(draft.edits, {
      onSuccess: (response) => {
        // The edits are on disk now, so the overlay has nothing left to say.
        draft.discardAll()
        // A populated reload_detail means the reload failed for a reason other
        // than a required restart (e.g. the log file could not be opened) — in
        // that exact case the reason cannot be written to the log, so this
        // dialog is the operator's only channel for it. Stay open to show it
        // instead of closing out from under the message.
        if (!response.reload_detail) onClose()
      },
    })
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t.viewDiff}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,.45)',
        display: 'grid',
        placeItems: 'center',
        padding: 24,
        zIndex: 20,
      }}
    >
      <div
        className="card"
        style={{
          background: 'var(--color-bg)',
          width: 'min(900px, 100%)',
          maxHeight: '85vh',
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
          padding: 20,
        }}
      >
        <h3 style={{ margin: 0 }}>{t.viewDiff}</h3>

        {preview.isPending && <div>…</div>}

        {preview.isError && (
          <div role="alert" style={{ color: '#a33a2b' }}>
            {(preview.error as Error).message}
          </div>
        )}

        {data && !data.valid && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ color: '#a33a2b' }}>{t.invalidDraft}</div>
            <IssueList issues={data.issues} />
          </div>
        )}

        {data?.valid && data.diffs.length === 0 && <div>{t.noChanges}</div>}

        {data?.valid &&
          data.diffs.map((entry) => (
            <div key={entry.path} style={{ display: 'flex', flexDirection: 'column', gap: 4, minHeight: 0 }}>
              <div
                className="text-muted"
                title={entry.path}
                style={{ fontSize: 12, fontFamily: 'ui-monospace, Menlo, monospace' }}
              >
                {/* The basename, not the full path: the diff body below already
                    shows the full path in its own "--- / +++" headers, and
                    repeating it here as bare text would make every text query
                    for it ambiguous between this line and the diff. The full
                    path is still available on hover via the title attribute. */}
                {t.writesTo} <code>{entry.path.split(/[/\\]/).pop()}</code> · +{entry.added} −
                {entry.removed}
              </div>
              <pre
                style={{
                  margin: 0,
                  padding: 12,
                  overflow: 'auto',
                  maxHeight: '45vh',
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-divider)',
                  fontSize: 12.5,
                  lineHeight: 1.5,
                  fontFamily: 'ui-monospace, Menlo, monospace',
                }}
              >
                {entry.diff}
              </pre>
            </div>
          ))}

        {data && data.restart_required.length > 0 && (
          <div style={{ fontSize: 13 }}>
            {t.restartWhich} <code>{data.restart_required.join(', ')}</code>
          </div>
        )}

        {data && data.in_flight_tasks > 0 && (
          <div style={{ fontSize: 13 }}>
            {data.in_flight_tasks} {t.inFlight}
          </div>
        )}

        {apply.isSuccess && apply.data.reload_detail && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <div>{t.applied}</div>
            <div role="alert" style={{ color: '#a33a2b' }}>
              {apply.data.reload_detail}
            </div>
            {/* This is exactly the moment the operator wants to know a backup
                exists: the dialog is staying open specifically because the
                reload didn't go cleanly, and a clean apply never renders this
                (it auto-closes, discarding the draft — see onApply above). */}
            {apply.data.backup && (
              <div className="text-muted" style={{ fontSize: 12 }}>
                {t.backupKept} <code>{apply.data.backup}</code>
              </div>
            )}
          </div>
        )}

        {apply.isError && (
          <div role="alert" style={{ color: '#a33a2b' }}>
            <div>{(apply.error as Error).message}</div>
            {applyIssues && <IssueList issues={applyIssues} />}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            {t.close}
          </button>
          {data?.valid && data.diffs.length > 0 && !apply.isSuccess && (
            <button
              type="button"
              className="btn btn-primary"
              onClick={onApply}
              disabled={apply.isPending}
            >
              {apply.isPending ? t.applying : t.apply}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
