import { useTranslations, type Lang } from '../i18n'

/**
 * "Restart needed", and what for.
 *
 * Deliberately has no action: re-execing the process only works under a
 * supervisor (Windows service, systemd) and would kill a bare terminal process
 * outright, so the console tells the operator rather than doing it (spec 7).
 */
export function RestartBanner({ lang, fields }: { lang: Lang; fields: string[] }) {
  const t = useTranslations(lang)
  if (fields.length === 0) return null

  return (
    <div
      role="status"
      style={{
        background: 'var(--color-surface)',
        borderBottom: '1px solid var(--color-divider)',
        padding: '6px 16px',
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        fontSize: 13,
      }}
    >
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        aria-hidden="true"
      >
        <path d="M21 12a9 9 0 1 1-3-6.7" />
        <path d="M21 3v6h-6" />
      </svg>
      <span>
        {t.restartNeeded} {t.restartWhich}{' '}
        <code style={{ fontFamily: 'ui-monospace, Menlo, monospace' }}>{fields.join(', ')}</code>
      </span>
    </div>
  )
}
