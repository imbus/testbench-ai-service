import { useEffect, useRef, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import type { TabId } from '../../state/editorTabs'
import './EditorTabs.css'

const mono = 'ui-monospace, Menlo, monospace'

export type EditorTab = {
  id: TabId
  label: string
  /** Muted prefix: the message role, or the ⚙ glyph for the variant settings. */
  prefix?: string
  dirty: boolean
  flagged: boolean
  preview: boolean
}

/**
 * The open editors above the template editor, VS Code style.
 *
 * Plain buttons rather than PrimeReact's `TabView`: a tab here carries its own
 * close button and reacts to double and middle click, which `TabView`'s header
 * cannot host cleanly. Purely presentational -- which tabs exist, which is
 * active and which is the preview all come from `state/editorTabs`.
 */
export function EditorTabs({ tabs, active, onActivate, onPin, onClose }: {
  tabs: EditorTab[]
  active: TabId | null
  onActivate: (id: TabId) => void
  onPin: (id: TabId) => void
  onClose: (id: TabId) => void
}) {
  const { t } = useTranslation()
  const refs = useRef(new Map<TabId, HTMLButtonElement>())

  useEffect(() => {
    // jsdom has no scrollIntoView.
    if (active) refs.current.get(active)?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
  }, [active])

  const onKey = (event: KeyboardEvent, index: number) => {
    // The close button stays out of the tab order, so Delete is the
    // keyboard's way to close a tab.
    if (event.key === 'Delete') {
      event.preventDefault()
      onClose(tabs[index].id)
      return
    }
    const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0
    if (!step) return
    event.preventDefault()
    const next = tabs[(index + step + tabs.length) % tabs.length]
    refs.current.get(next.id)?.focus()
    onActivate(next.id)
  }

  return (
    <div
      role="tablist"
      aria-label={t('openEditors')}
      className="editor-tabs"
      style={{ display: 'flex', overflowX: 'auto', overflowY: 'hidden', flex: 'none', background: 'var(--color-surface)', borderBottom: '1px solid var(--color-divider)' }}
    >
      {tabs.map((tab, index) => {
        const isActive = tab.id === active
        return (
          <div
            key={tab.id}
            // Only a wrapper: the tablist's children are the buttons inside.
            role="presentation"
            className="editor-tab"
            data-active={isActive}
            data-dirty={tab.dirty}
            onMouseDown={(event) => {
              // Stops the browser's middle-click autoscroll.
              if (event.button === 1) event.preventDefault()
            }}
            onAuxClick={(event) => {
              if (event.button === 1) onClose(tab.id)
            }}
            style={{
              display: 'flex', alignItems: 'center', gap: 2, flex: 'none', height: 34, paddingRight: 4,
              borderRight: '1px solid var(--color-divider)',
              // The active tab merges into the editor below it; the bar on top marks it.
              background: isActive ? 'var(--color-bg)' : 'var(--color-surface)',
              boxShadow: isActive ? 'inset 0 2px 0 var(--color-accent)' : undefined,
              marginBottom: isActive ? -1 : 0,
            }}
          >
            <button
              ref={(el) => {
                if (el) refs.current.set(tab.id, el)
                else refs.current.delete(tab.id)
              }}
              type="button"
              role="tab"
              aria-selected={isActive}
              aria-invalid={tab.flagged || undefined}
              tabIndex={isActive ? 0 : -1}
              onClick={() => onActivate(tab.id)}
              onDoubleClick={() => onPin(tab.id)}
              onKeyDown={(event) => onKey(event, index)}
              style={{
                border: 0, background: 'transparent', color: isActive ? 'var(--color-text)' : 'inherit', cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: 6, padding: '0 6px 0 12px', height: '100%',
                fontFamily: mono, fontSize: 12, whiteSpace: 'nowrap', opacity: isActive ? 1 : 0.75,
              }}
            >
              {tab.prefix && <span className="text-muted" style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '.04em' }}>{tab.prefix}</span>}
              <span style={{ fontStyle: tab.preview ? 'italic' : 'normal', maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis' }}>{tab.label}</span>
              {tab.flagged && <span aria-hidden style={{ color: '#c0392b' }}>●</span>}
            </button>
            <button
              type="button"
              className="editor-tab-close"
              tabIndex={-1}
              data-dirty={tab.dirty}
              aria-label={tab.dirty ? t('closeTabUnsaved', { name: tab.label }) : t('closeTab', { name: tab.label })}
              title={tab.dirty ? t('closeTabUnsaved', { name: tab.label }) : t('closeTab', { name: tab.label })}
              onClick={() => onClose(tab.id)}
              style={{ border: 0, background: 'transparent', color: 'inherit', cursor: 'pointer', width: 20, height: 20, padding: 0, borderRadius: 3, fontSize: 14, lineHeight: '20px' }}
            >
              <span className="editor-tab-dirty" aria-hidden>●</span>
              <span className="editor-tab-x" aria-hidden>×</span>
            </button>
          </div>
        )
      })}
    </div>
  )
}
