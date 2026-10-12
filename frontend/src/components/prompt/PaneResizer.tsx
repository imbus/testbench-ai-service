import { useRef, type KeyboardEvent, type PointerEvent } from 'react'

const KEY_STEP = 16

/**
 * A horizontal splitter sitting on the top edge of a bottom pane: dragging
 * it up grows the pane, down shrinks it. Arrow keys do the same in 16px
 * steps, so the handle is a real `separator` rather than a mouse-only strip.
 *
 * `max` is read at the start of each drag / key press rather than passed as
 * a number, because it depends on the surrounding column's live height.
 */
export function PaneResizer({ height, min, max, label, onResize }: {
  height: number
  min: number
  max: () => number
  label: string
  onResize: (next: number) => void
}) {
  const drag = useRef<{ startY: number; startHeight: number; max: number } | null>(null)

  const clamp = (value: number, upper: number) => Math.min(Math.max(value, min), Math.max(upper, min))

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return
    event.preventDefault()
    event.currentTarget.setPointerCapture(event.pointerId)
    const upper = max()
    drag.current = { startY: event.clientY, startHeight: clamp(height, upper), max: upper }
  }

  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const current = drag.current
    if (!current) return
    onResize(clamp(current.startHeight + (current.startY - event.clientY), current.max))
  }

  const endDrag = (event: PointerEvent<HTMLDivElement>) => {
    if (!drag.current) return
    drag.current = null
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const delta = event.key === 'ArrowUp' ? KEY_STEP : event.key === 'ArrowDown' ? -KEY_STEP : 0
    if (!delta) return
    event.preventDefault()
    onResize(clamp(height + delta, max()))
  }

  return (
    <div
      role="separator"
      aria-orientation="horizontal"
      aria-label={label}
      aria-valuenow={Math.round(height)}
      aria-valuemin={min}
      tabIndex={0}
      className="pane-resizer"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onKeyDown={onKeyDown}
      style={{
        height: 6,
        flex: 'none',
        cursor: 'row-resize',
        touchAction: 'none',
        borderTop: '1px solid var(--color-divider)',
        background: 'var(--color-surface)',
      }}
    />
  )
}
