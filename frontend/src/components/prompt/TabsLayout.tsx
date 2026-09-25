import { useState, type ReactNode } from 'react'
import type { PromptMessageDoc } from '../../api/types'
import { useTranslations, type Lang } from '../../i18n'
import { messageLabel, type Selection } from './selection'
import type { LintState } from './VarSidebar'

export type DrawerTab = 'vars' | 'preview' | 'test'

const mono = 'ui-monospace, Menlo, monospace'

function tabStyle(active: boolean) {
  return {
    border: '1px solid var(--color-divider)',
    borderBottom: active ? '1px solid var(--color-bg)' : '1px solid var(--color-divider)',
    marginBottom: active ? -1 : 0,
    background: active ? 'var(--color-bg)' : 'var(--color-surface)',
    color: 'inherit',
    font: 'inherit',
    fontSize: 12,
    padding: '6px 12px',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    gap: 6,
  }
}

/**
 * The Tabs layout: a tab strip (prompt.yaml + one tab per message of the
 * selected variant) over the centre pane and a status bar, beside a 340px
 * drawer holding Variables | Preview | Test run.
 *
 * The centre and drawer contents are built by `PromptEditor` and passed in,
 * so both layouts share one wiring.
 */
export function TabsLayout({ messages, selection, flagged, readOnly, centre, variablesDrawer, preview, testRun, status, variantName, lang = 'de', onOpenMeta, onOpenVariantSettings, onPickMessage, onAddMessage, onLint }: {
  messages: PromptMessageDoc[]
  selection: Selection
  flagged: number[]
  readOnly: boolean
  centre: ReactNode
  variablesDrawer: ReactNode
  preview: ReactNode
  testRun: ReactNode
  status: { lint: LintState; usedDeclared: number; declared: number; undeclared: number }
  variantName: string
  lang?: Lang
  onOpenMeta: () => void
  onOpenVariantSettings: () => void
  onPickMessage: (index: number) => void
  onAddMessage: () => void
  onLint: () => void
}) {
  const t = useTranslations(lang)
  const [tab, setTab] = useState<DrawerTab>('vars')
  const { lint, usedDeclared, declared, undeclared } = status

  const drawerTabs: { id: DrawerTab; label: string }[] = [
    { id: 'vars', label: t.drawerVariables },
    { id: 'preview', label: t.previewPane },
    { id: 'test', label: t.testRun },
  ]

  return (
    <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        {/* Plain toggle buttons (aria-pressed), not role="tab": there is no
            roving focus or tabpanel wiring behind them, and a tablist
            without those is a worse announcement than honest buttons. */}
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, padding: '8px 16px 0', borderBottom: '1px solid var(--color-divider)', flexWrap: 'wrap' }}>
          <button type="button" aria-pressed={selection.kind === 'meta'} onClick={onOpenMeta} style={{ ...tabStyle(selection.kind === 'meta'), fontFamily: mono }}>
            prompt.yaml
          </button>
          {/* The selected variant's settings (rename, model, remove,
              declarations) -- Tabs has no tree to reach them from. Named like
              PromptTree's gear button. */}
          <button
            type="button"
            aria-pressed={selection.kind === 'variant'}
            aria-label={`${t.variantSettings}: ${variantName}`}
            onClick={onOpenVariantSettings}
            style={tabStyle(selection.kind === 'variant')}
          >
            <span aria-hidden>⚙</span>
            <span>{variantName}</span>
          </button>
          {messages.map((message, index) => {
            const current = selection.kind === 'message' && selection.index === index
            const isFlagged = flagged.includes(index)
            return (
              <button
                key={index}
                type="button"
                aria-pressed={current}
                aria-invalid={isFlagged || undefined}
                onClick={() => onPickMessage(index)}
                style={tabStyle(current)}
              >
                <span className="text-muted">{index + 1}</span>
                <span className="tag tag-neutral" style={{ padding: '0 5px', fontSize: 10 }}>{message.role}</span>
                <span style={{ fontFamily: mono }}>{messageLabel(message, t.emptyMessage)}</span>
                {isFlagged && <span aria-hidden style={{ color: '#c0392b' }}>●</span>}
              </button>
            )
          })}
          {!readOnly && (
            <button type="button" className="btn btn-ghost" style={{ fontSize: 12, marginBottom: 2 }} onClick={onAddMessage}>
              {t.addMessageShort}
            </button>
          )}
        </div>

        <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>{centre}</div>

        <div style={{ display: 'flex', gap: 16, alignItems: 'center', padding: '5px 12px', borderTop: '1px solid var(--color-divider)', background: 'var(--color-surface)', fontSize: 12, flexWrap: 'wrap' }}>
          <button type="button" className="btn btn-ghost" style={{ fontSize: 12, padding: '0 6px' }} disabled={lint.running} onClick={onLint}>
            {t.lint}
          </button>
          {lint.error && <span role="alert" style={{ color: '#a33a2b' }}>{lint.error}</span>}
          {lint.errors.map((error, index) => (
            <span key={index} style={{ color: '#a33a2b' }}>{`${t.lintLine} ${error.line}: ${error.message}`}</span>
          ))}
          {lint.checked && !lint.error && lint.errors.length === 0 && <span style={{ color: '#2e8b5e' }}>✓ {t.lintClean}</span>}
          <span className="text-muted">{`${usedDeclared}/${declared} ${t.varsUsed} · ${undeclared} ${t.undeclaredCount}`}</span>
          <div style={{ flex: 1 }} />
          <span className="text-muted">jinja · UTF-8</span>
        </div>
      </div>

      <aside style={{ width: 340, flex: 'none', borderLeft: '1px solid var(--color-divider)', background: 'var(--color-surface)', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <div style={{ display: 'flex', borderBottom: '1px solid var(--color-divider)', fontSize: 12 }}>
          {drawerTabs.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              aria-pressed={tab === id}
              onClick={() => setTab(id)}
              style={{ flex: 1, padding: '9px 0', border: 0, borderBottom: `2px solid ${tab === id ? 'var(--color-accent)' : 'transparent'}`, background: 'transparent', color: 'inherit', font: 'inherit', cursor: 'pointer', opacity: tab === id ? 1 : 0.7 }}
            >
              {label}
            </button>
          ))}
        </div>
        <div style={{ padding: 12, overflow: 'auto', flex: 1 }}>
          {tab === 'vars' ? variablesDrawer : tab === 'preview' ? preview : testRun}
        </div>
      </aside>
    </div>
  )
}
