import logoUrl from '../assets/logo.svg'

/**
 * The console's identity: the TestBench logo (assets/logo.svg) and the
 * wordmark whose "Bench" carries the TestBench orange (`--tb-orange`,
 * defined in brand.css).
 *
 * Two sizes, both the artboard's: 36px mark over a 24px wordmark on the login
 * card, 26px over 20px in the top bar. The mark is decorative — the wordmark
 * beside it already says the name — so it is hidden from assistive tech.
 */
export function BrandMark({ size, subtitle }: { size: 'login' | 'header'; subtitle?: string }) {
  const login = size === 'login'
  const mark = login ? 36 : 26
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <img src={logoUrl} width={mark} height={mark} alt="" style={{ flex: 'none' }} />
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <div
          style={{
            fontFamily: 'var(--font-heading)',
            fontWeight: 600,
            fontSize: login ? 24 : 20,
            lineHeight: 1.1,
            letterSpacing: login ? undefined : '-0.01em',
            whiteSpace: 'nowrap',
          }}
        >
          <span>Test</span>
          <span style={{ color: 'var(--tb-orange)' }}>Bench</span>{' '}
          <span style={{ fontWeight: 400 }}>AI Service</span>
        </div>
        {subtitle && (
          <div className="text-muted" style={{ fontSize: 12 }}>
            {subtitle}
          </div>
        )}
      </div>
    </div>
  )
}
