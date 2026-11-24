import type { ReactNode } from 'react'

/**
 * One section of a screen that has several: a tinted header bar with the
 * title, and the content in a thin frame below it. Sections drawn alike read
 * as peers, where a bare heading under a table reads as a part of that table.
 */
export function SectionPanel({
  title,
  hint,
  action,
  children,
}: {
  title: string
  /** One line under the title saying what the section is for. */
  hint?: string
  /** The section's main control, at the right end of the header bar. */
  action?: ReactNode
  children: ReactNode
}) {
  return (
    <section
      aria-label={title}
      style={{
        border: '1px solid var(--color-divider)',
        borderRadius: 10,
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 14,
          flexWrap: 'wrap',
          padding: '10px 18px',
          background: 'var(--color-surface)',
          borderBottom: '1px solid var(--color-divider)',
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <h3 style={{ margin: 0, fontSize: 20 }}>{title}</h3>
          {hint && (
            <div className="text-muted" style={{ fontSize: 12 }}>
              {hint}
            </div>
          )}
        </div>
        {action}
      </div>
      <div style={{ padding: '14px 18px 18px', display: 'flex', flexDirection: 'column', gap: 14 }}>
        {children}
      </div>
    </section>
  )
}
