import { useEffect, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from 'react'
import { createPortal } from 'react-dom'

/** Gap between the trigger and the popup, and the popup's margin to the window edge. */
const GAP = 4
const EDGE = 8

/**
 * The popup of a searchable pick list: a search field with focus, the list,
 * an optional footer.
 *
 * Rendered into `document.body` and placed below `anchor`, so a table row or
 * card that clips its overflow cannot cut it off. A mouse press outside both
 * the anchor and the popup calls `onDismiss`; `anchor` should hold the
 * trigger, or pressing the trigger would close and reopen. Escape calls
 * `onEscape`, Enter in the search field calls `onEnter`.
 *
 * Arrow Down and Arrow Up walk the entries: from the search field into the
 * list, through its buttons, and back up into the field. The entry that has
 * focus is the one Enter picks, as for any button.
 */
export function SearchPopover({
  anchor,
  label,
  searchLabel,
  query,
  onQuery,
  onEnter,
  onEscape,
  onDismiss,
  width = 260,
  footer,
  children,
}: {
  anchor: RefObject<HTMLElement | null>
  /** Names the popup for assistive technology. */
  label: string
  searchLabel: string
  query: string
  onQuery: (query: string) => void
  onEnter: () => void
  onEscape: () => void
  onDismiss: () => void
  width?: number
  footer?: ReactNode
  /** The `<li>` entries of the list. */
  children: ReactNode
}) {
  const popup = useRef<HTMLDivElement>(null)
  const [place, setPlace] = useState<{ top: number; left: number } | null>(null)

  useLayoutEffect(() => {
    const update = () => {
      const box = anchor.current?.getBoundingClientRect()
      if (!box) return
      const room = window.innerWidth - width - EDGE
      setPlace({ top: box.bottom + GAP, left: Math.max(EDGE, Math.min(box.left, room)) })
    }
    update()
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    return () => {
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update, true)
    }
  }, [anchor, width])

  const dismiss = useRef(onDismiss)
  dismiss.current = onDismiss
  useEffect(() => {
    const onDown = (event: MouseEvent) => {
      const target = event.target as Node
      if (anchor.current?.contains(target) || popup.current?.contains(target)) return
      dismiss.current()
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [anchor])

  return createPortal(
    <div
      ref={popup}
      role="dialog"
      aria-label={label}
      className="tb-popover"
      style={{ width, top: place?.top ?? 0, left: place?.left ?? 0 }}
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          event.stopPropagation()
          onEscape()
          return
        }
        if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
        const root = popup.current
        if (!root) return
        const search = root.querySelector<HTMLInputElement>('input[type="search"]')
        const entries = Array.from(
          root.querySelectorAll<HTMLButtonElement>('ul button:not([disabled])'),
        )
        if (entries.length === 0) return
        event.preventDefault()
        const at = entries.indexOf(document.activeElement as HTMLButtonElement)
        if (event.key === 'ArrowDown') {
          entries[Math.min(at + 1, entries.length - 1)].focus()
        } else if (at <= 0) {
          search?.focus()
        } else {
          entries[at - 1].focus()
        }
      }}
    >
      <input
        type="search"
        autoFocus
        aria-label={searchLabel}
        placeholder={searchLabel}
        value={query}
        onChange={(event) => onQuery(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault()
            onEnter()
          }
        }}
      />
      <ul>{children}</ul>
      {footer && <div className="tb-popover-foot text-muted">{footer}</div>}
    </div>,
    document.body,
  )
}
