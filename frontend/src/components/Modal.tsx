import type { CSSProperties, ReactNode } from 'react'
import { Dialog } from 'primereact/dialog'

/**
 * The shell every console dialog shares -- PrimeReact's `Dialog` since the
 * PrimeReact pilot.
 *
 * Callers still mount it only while it is open and draw their own title and
 * buttons, so the dialog is always `visible`, has no header bar and no close
 * icon. What Prime adds for free is a focus trap and focus-on-show.
 *
 * Escape closes the dialog when the caller passes `onClose` -- the same
 * handler its Cancel button calls, so the caller always knows the dialog is
 * gone and no stale state is left behind. Without `onClose` Escape is inert.
 *
 * Prime labels the dialog through `aria-labelledby` pointing at its header;
 * with the header hidden that id resolves to nothing, so the root takes the
 * caller's `label` as `aria-label` instead.
 *
 * `maxHeight` is optional and unset by default: only `DiffDialog` caps its
 * card's height (to keep long diffs scrolling inside the dialog rather than
 * growing it past the viewport).
 */
export function Modal({
  label,
  width = 560,
  maxHeight,
  onClose,
  children,
}: {
  label: string
  width?: number
  maxHeight?: CSSProperties['maxHeight']
  /** What Cancel does. Given, Escape does the same. */
  onClose?: () => void
  children: ReactNode
}) {
  return (
    <Dialog
      visible
      modal
      onHide={() => onClose?.()}
      showHeader={false}
      closable={onClose !== undefined}
      closeOnEscape={onClose !== undefined}
      draggable={false}
      resizable={false}
      style={{ width: `min(${width}px, calc(100vw - 48px))` }}
      contentStyle={{
        ...(maxHeight !== undefined ? { maxHeight } : {}),
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
      }}
      pt={{ root: { 'aria-label': label, 'aria-labelledby': undefined } }}
    >
      {children}
    </Dialog>
  )
}
