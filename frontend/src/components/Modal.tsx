import type { CSSProperties, ReactNode } from 'react'
import { Dialog } from 'primereact/dialog'

/**
 * The shell every console dialog shares -- PrimeReact's `Dialog` since the
 * PrimeReact pilot.
 *
 * Callers still mount it only while it is open and draw their own title and
 * buttons, so the dialog is always `visible`, has no header bar and no close
 * icon. Escape stays inert as before: `onHide` has nobody to tell, and a
 * dialog that vanished without its caller knowing would leave stale state
 * behind. What Prime adds for free is a focus trap and focus-on-show.
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
  children,
}: {
  label: string
  width?: number
  maxHeight?: CSSProperties['maxHeight']
  children: ReactNode
}) {
  return (
    <Dialog
      visible
      modal
      onHide={() => {}}
      showHeader={false}
      closable={false}
      closeOnEscape={false}
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
