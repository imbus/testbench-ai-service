import { useEffect } from 'react'
import type { ApiError } from '../api/client'
import { useApply, usePreview } from '../api/mutations'
import type { ConfigIssue } from '../api/types'
import { useTranslations, type Lang } from '../i18n'
import { useDraft } from '../state/draft'

/** What IssueList needs — a preview's `ConfigIssue` and a validated apply-rejection entry both satisfy this. */
interface RenderableIssue {
  path?: string
  toml_section?: string
  message: string
}

/**
 * True for an entry that can be labeled and shown: a non-null object with a
 * string `message` and at least one of a string `path` or `toml_section`
 * (the renderer falls back from `path` to `toml_section`, so either is
 * enough).
 */
function isRenderableIssue(entry: unknown): entry is RenderableIssue {
  if (entry === null || typeof entry !== 'object') return false
  const candidate = entry as Record<string, unknown>
  if (typeof candidate.message !== 'string') return false
  return typeof candidate.path === 'string' || typeof candidate.toml_section === 'string'
}

/**
 * A structured `{message, issues}` apply-rejection detail, as opposed to a
 * bare string.
 *
 * Validated entry by entry, not just at the container: a `null` entry, or
 * one missing both `path` and `toml_section`, would otherwise throw at
 * `key={...issue.path...}` or render an unlabeled row. Malformed entries are
 * dropped rather than rendered; if none survive, this returns `null` — the
 * same as "no issues" at all — so the dialog falls back to just the summary
 * message instead of an empty list.
 */
function issuesOf(detail: unknown): RenderableIssue[] | null {
  if (detail === null || typeof detail !== 'object') return null
  const raw = (detail as { issues?: unknown }).issues
  if (!Array.isArray(raw)) return null
  const wellFormed = raw.filter(isRenderableIssue)
  return wellFormed.length > 0 ? wellFormed : null
}

/**
 * Narrow a `RenderableIssue` list down to the subset `ConfigSection` can
 * address to a field: a `toml_section`-only entry (no `path`) has nothing for
 * `issueMatchesField` to compare against, so it is dropped here rather than
 * forwarded as a field marker with an empty path.
 */
function toFieldIssues(issues: RenderableIssue[] | null): ConfigIssue[] {
  if (!issues) return []
  return issues
    .filter((issue): issue is RenderableIssue & { path: string } => typeof issue.path === 'string')
    .map((issue) => ({
      path: issue.path,
      message: issue.message,
      toml_section: issue.toml_section ?? '',
    }))
}

function IssueList({ issues }: { issues: RenderableIssue[] }) {
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
export function DiffDialog({
  lang,
  onClose,
  onIssues,
}: {
  lang: Lang
  onClose: () => void
  /** Field-addressed validation failures, forwarded up to `App` so the config
   * screens can mark the offending inputs. Optional so callers that don't
   * care about issue markers (and existing tests) need not supply it. */
  onIssues?: (issues: ConfigIssue[]) => void
}) {
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

  useEffect(() => {
    if (!onIssues) return
    if (!data) return
    // Report a clean marker set on a VALID preview too, not just an invalid
    // one: an operator who fixes the field and reopens the dialog must see
    // the marker clear here, rather than only on discard/apply/sign-out.
    onIssues(data.valid ? [] : data.issues)
  }, [data, onIssues])

  // HAZARD -- infinite render loop: this effect must be keyed on `apply.error`
  // (a stable object identity for a given failed mutation), NEVER on a value
  // derived fresh each render such as `applyIssues` above. `applyIssues` is
  // recomputed by `issuesOf(...).filter(...)` on every render, so a dependency
  // array containing it receives a new array identity every time; the effect
  // then fires on every render, calls `onIssues`, which sets state in `App`,
  // which re-renders this component, which produces yet another new
  // `applyIssues` array -- forever ("Maximum update depth exceeded"). The
  // preview effect above is safe only because react-query's `data` identity is
  // stable across renders; nothing derived from `apply.error` may be trusted
  // the same way, so the issues are computed INSIDE the effect body instead.
  useEffect(() => {
    if (!onIssues || !apply.error) return
    const issues = issuesOf((apply.error as ApiError).detail)
    if (issues) onIssues(toFieldIssues(issues))
  }, [apply.error, onIssues])

  const onApply = () => {
    apply.mutate(draft.edits, {
      onSuccess: (response) => {
        // The edits are on disk now, so the overlay has nothing left to say.
        draft.discardAll()
        onIssues?.([])
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
