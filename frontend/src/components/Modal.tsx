import type { CSSProperties, ReactNode } from 'react'

/**
 * The shell every console dialog shares.
 *
 * Extracted because three dialogs had copied the same overlay and card markup
 * verbatim. Behaviour is deliberately identical to what they each had — no
 * focus trap, no Escape handling, no autofocus. Those are real accessibility
 * work and they are not in this increment; adding them here would change three
 * dialogs at once under cover of a refactor.
 *
 * `maxHeight` is optional and unset by default: only `DiffDialog` capped its
 * card's height (to keep long diffs scrolling inside the dialog rather than
 * growing it past the viewport) — the other two callers never had it, and
 * must not gain it here.
 */
export function Modal({
  label,
  width = 560,
  maxHeight,
  children,
}: {
  label: string
  width?: number
  maxHeight?: CSSProperties['maxHeight']
  children: ReactNode
}) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={label}
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
          width: `min(${width}px, 100%)`,
          ...(maxHeight !== undefined ? { maxHeight } : {}),
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
          padding: 20,
        }}
      >
        {children}
      </div>
    </div>
  )
}
