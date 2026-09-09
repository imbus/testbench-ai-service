import { useEffect, useRef, useState } from 'react'
import { usePreview } from '../api/mutations'
import { useTranslations, type Lang } from '../i18n'
import { useDraft } from '../state/draft'

/**
 * The `config.toml` the current draft would write.
 *
 * It comes from `POST /config/preview` rather than being rendered in the
 * browser: the artboard hand-rolled a `toToml`, and two serializers for one
 * file is two chances to disagree about what is actually on disk.
 */
export function Raw({ lang }: { lang: Lang }) {
  const t = useTranslations(lang)
  const draft = useDraft()
  const preview = usePreview()
  const [copied, setCopied] = useState(false)
  const timerRef = useRef<NodeJS.Timeout | number>()

  const edits = JSON.stringify(draft.edits)
  useEffect(() => {
    preview.mutate(draft.edits)
    // Keyed on the serialized edits: the object identity changes on every
    // render, and re-previewing per render would hammer the endpoint.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [edits])

  useEffect(() => {
    // Clear any pending timer on unmount to avoid setState on an unmounted component.
    return () => {
      if (timerRef.current) {
        window.clearTimeout(timerRef.current)
      }
    }
  }, [])

  const onCopy = () => {
    void navigator.clipboard.writeText(preview.data?.toml ?? '').then(() => {
      // Clear any existing timer before starting a new one, so rapid clicks
      // do not leave the label stuck or double-flip.
      if (timerRef.current) {
        window.clearTimeout(timerRef.current)
      }
      setCopied(true)
      timerRef.current = window.setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div
      style={{
        padding: '28px 32px',
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
        maxWidth: 1000,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <h2 style={{ margin: 0, fontSize: 30 }}>config.toml</h2>
        <span className="text-muted" style={{ fontSize: 12 }}>
          {t.rawSub}
        </span>
        <div style={{ flex: 1 }} />
        {preview.data && !preview.isError && (
          <button type="button" className="btn btn-secondary" onClick={onCopy}>
            {copied ? t.copied : t.copy}
          </button>
        )}
      </div>

      {preview.isError && (
        <div role="alert" style={{ color: '#a33a2b' }}>
          {(preview.error as Error).message}
        </div>
      )}

      {preview.data && !preview.isError && (
        <pre
          style={{
            margin: 0,
            padding: '16px 20px',
            fontSize: 12.5,
            lineHeight: 1.55,
            background: 'var(--color-surface)',
            border: '1px solid var(--color-divider)',
            overflow: 'auto',
            fontFamily: 'ui-monospace, Menlo, monospace',
          }}
        >
          {preview.data.toml}
        </pre>
      )}
      {/* React Query retains the last successful data even after a failed
        re-preview. We deliberately do not render it here: showing an older
        TOML beside a current error breaks the contract "this is exactly what
        an apply would write", and the operator cannot tell which text is
        current. An honest gap is better than a document that looks
        authoritative and is stale. */}
    </div>
  )
}
