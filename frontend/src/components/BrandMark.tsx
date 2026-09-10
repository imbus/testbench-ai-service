/**
 * The console's identity, taken from the artboard: a dashed ring around a
 * solid core, and the wordmark whose "Bench" carries the TestBench orange
 * (`--tb-orange`, defined in brand.css).
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
      <svg width={mark} height={mark} viewBox="0 0 32 32" fill="none" aria-hidden="true">
        <circle
          cx="16"
          cy="16"
          r="11"
          stroke="var(--color-accent)"
          strokeWidth="3.5"
          strokeDasharray="9 5"
          strokeLinecap="round"
        />
        <circle cx="16" cy="16" r="4" fill="var(--color-accent)" />
      </svg>
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
