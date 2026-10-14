import { useState, type ReactNode } from 'react'
import { Button } from 'primereact/button'
import { Message } from 'primereact/message'
import { TabPanel, TabView } from 'primereact/tabview'
import { Tag } from 'primereact/tag'
import type { PromptMessageDoc } from '../../api/types'
import { useTranslation } from 'react-i18next'
import { messageLabel, type Selection } from './selection'
import type { LintState } from './VarSidebar'

export type DrawerTab = 'vars' | 'preview' | 'test'

const mono = 'ui-monospace, Menlo, monospace'
const DRAWER_TABS: DrawerTab[] = ['vars', 'preview', 'test']

/**
 * The Tabs layout: a tab strip (prompt.yaml + one tab per message of the
 * selected variant) over the centre pane and a status bar, beside a 340px
 * drawer holding Variables | Preview | Test run.
 *
 * The centre and drawer contents are built by `PromptEditor` and passed in,
 * so both layouts share one wiring.
 */
export function TabsLayout({ messages, selection, flagged, readOnly, centre, variablesDrawer, preview, testRun, status, variantName, onOpenMeta, onOpenVariantSettings, onPickMessage, onAddMessage, onLint }: {
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
  onOpenMeta: () => void
  onOpenVariantSettings: () => void
  onPickMessage: (index: number) => void
  onAddMessage: () => void
  onLint: () => void
}) {
  const { t } = useTranslation()
  const [tab, setTab] = useState<DrawerTab>('vars')
  const { lint, usedDeclared, declared, undeclared } = status

  const drawerLabels: Record<DrawerTab, string> = {
    vars: t('drawerVariables'),
    preview: t('previewPane'),
    test: t('testRun'),
  }
  // Tab 0 is prompt.yaml, tab 1 the variant's settings, then one per message.
  const activeIndex = selection.kind === 'meta' ? 0 : selection.kind === 'variant' ? 1 : selection.index + 2
  const pick = (index: number) => {
    if (index === 0) onOpenMeta()
    else if (index === 1) onOpenVariantSettings()
    else onPickMessage(index - 2)
  }

  return (
    <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8, padding: '8px 16px 0', borderBottom: '1px solid var(--color-divider)' }}>
          {/* Header-only: the centre pane renders below, outside the tab
              view, so every panel is empty and the selection is fully
              controlled by `selection`. */}
          <TabView
            activeIndex={activeIndex}
            onTabChange={(event) => pick(event.index)}
            style={{ flex: '1 1 auto', minWidth: 0 }}
          >
            <TabPanel header={<span style={{ fontFamily: mono }}>prompt.yaml</span>} />
            {/* The selected variant's settings (rename, model, remove,
                declarations) -- Tabs has no tree to reach them from. Named like
                PromptTree's gear button. */}
            <TabPanel
              header={
                <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span aria-hidden>⚙</span>
                  <span>{variantName}</span>
                </span>
              }
              pt={{ headerAction: { 'aria-label': `${t('variantSettings')}: ${variantName}` } }}
            />
            {messages.map((message, index) => {
              const isFlagged = flagged.includes(index)
              return (
                <TabPanel
                  key={index}
                  header={
                    <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span className="text-muted">{index + 1}</span>
                      <Tag severity="secondary" value={message.role} style={{ padding: '0 5px', fontSize: 10 }} />
                      <span style={{ fontFamily: mono }}>{messageLabel(message, t('emptyMessage'))}</span>
                      {isFlagged && <span aria-hidden style={{ color: '#c0392b' }}>●</span>}
                    </span>
                  }
                  pt={{ headerAction: { 'aria-invalid': isFlagged || undefined } }}
                />
              )
            })}
          </TabView>
          {!readOnly && (
            <Button type="button" text label={t('addMessageShort')} style={{ fontSize: 12, marginBottom: 6, flex: 'none' }} onClick={onAddMessage} />
          )}
        </div>

        <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>{centre}</div>

        <div style={{ display: 'flex', gap: 16, alignItems: 'center', padding: '5px 12px', borderTop: '1px solid var(--color-divider)', background: 'var(--color-surface)', fontSize: 12, flexWrap: 'wrap' }}>
          <Button type="button" text label={lint.running ? t('linting') : t('lint')} style={{ fontSize: 12, padding: '0 6px' }} disabled={lint.running} onClick={onLint} />
          {lint.checking && !lint.running && <span className="text-muted">{t('lintChecking')}</span>}
          {lint.error && <Message severity="error" text={lint.error} style={{ padding: '2px 8px', fontSize: 12 }} />}
          {lint.errors.map((error, index) => (
            <span key={index} style={{ color: '#a33a2b' }}>{t('lintLine', { line: error.line, message: error.message })}</span>
          ))}
          {lint.clean && !lint.error && <span style={{ color: '#2e8b5e' }}>✓ {t('lintClean')}</span>}
          <span className="text-muted">{t('varsStatus', { used: usedDeclared, declared, undeclared })}</span>
          <div style={{ flex: 1 }} />
          <span className="text-muted">jinja · UTF-8</span>
        </div>
      </div>

      <aside style={{ width: 340, flex: 'none', borderLeft: '1px solid var(--color-divider)', background: 'var(--color-surface)', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        {/* Only the active panel is mounted (Prime's default), so a drawer
            never runs a hidden Preview or Test run. */}
        <TabView
          activeIndex={DRAWER_TABS.indexOf(tab)}
          onTabChange={(event) => setTab(DRAWER_TABS[event.index])}
          style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, fontSize: 12 }}
          pt={{
            panelContainer: { style: { padding: 12, overflow: 'auto', flex: 1 } },
          }}
        >
          {DRAWER_TABS.map((id) => (
            <TabPanel key={id} header={drawerLabels[id]} headerStyle={{ flex: 1 }}>
              {id === 'vars' ? variablesDrawer : id === 'preview' ? preview : testRun}
            </TabPanel>
          ))}
        </TabView>
      </aside>
    </div>
  )
}
