import { Message } from 'primereact/message'
import { useTranslation } from 'react-i18next'

/**
 * "Restart needed", and what for.
 *
 * Deliberately has no action: re-execing the process only works under a
 * supervisor (Windows service, systemd) and would kill a bare terminal process
 * outright, so the console tells the operator rather than doing it (spec 7).
 */
export function RestartBanner({ fields }: { fields: string[] }) {
  const { t } = useTranslation()
  if (fields.length === 0) return null

  return (
    // A PrimeReact `Message` stretched into a full-width strip, with the
    // restart glyph as its icon. It keeps the bar's `status` role rather than
    // Message's own `alert`: nothing here demands the operator's attention now.
    <Message
      severity="info"
      role="status"
      className="banner"
      style={{ gap: 12, borderColor: 'var(--color-divider)', padding: '6px 16px' }}
      icon={
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
      }
      text={
        <>
          {t('restartNeeded')} {t('restartWhich')}{' '}
          <code style={{ fontFamily: 'var(--font-code)' }}>{fields.join(', ')}</code>
        </>
      }
    />
  )
}
