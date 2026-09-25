import { useNavigate } from 'react-router-dom'
import { usePromptTree } from '../../api/queries'
import { useTranslations, type Lang } from '../../i18n'
import type { EditorLayout } from '../../state/editorLayout'

const compact = { width: 'auto', minHeight: 32, padding: '3px 8px', fontSize: 13 }

export function EditorToolbar({ docLang, agentKey, path, variants, selectedVariant, layout, canSave, showSave, lang = 'de', onVariant, onLayout, onSave }: {
  docLang: string
  agentKey: string
  path: string
  variants: string[]
  selectedVariant: string
  layout: EditorLayout
  canSave: boolean
  showSave: boolean
  lang?: Lang
  onVariant: (name: string) => void
  onLayout: (next: EditorLayout) => void
  onSave: () => void
}): JSX.Element {
  const t = useTranslations(lang)
  const navigate = useNavigate()
  const tree = usePromptTree()
  const languages = tree.data?.languages ?? []
  const agentsFor = (code: string) => (languages.find((l) => l.lang === code)?.prompts ?? []).filter((p) => p.ok)
  const go = (code: string, agent: string) => navigate(`/admin/prompts/${encodeURIComponent(code)}/${encodeURIComponent(agent)}`)
  const index = variants.indexOf(selectedVariant)

  return (
    <div data-testid="editor-toolbar" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px', borderBottom: '1px solid var(--color-divider)', flexWrap: 'wrap' }}>
      <h3 style={{ margin: 0, fontSize: 22 }}>{t.prompts}</h3>
      <select className="input" aria-label={t.promptLanguage} style={compact} value={docLang}
        onChange={(e) => {
          const code = e.target.value
          const agents = agentsFor(code)
          const next = agents.some((p) => p.agent === agentKey) ? agentKey : agents[0]?.agent
          if (next) go(code, next)
        }}>
        {/* keep the current value selectable while the tree loads */}
        {(languages.length ? languages.map((l) => l.lang) : [docLang]).map((code) => <option key={code} value={code}>{code}</option>)}
      </select>
      <select className="input" aria-label={t.promptAgent} style={compact} value={agentKey} onChange={(e) => go(docLang, e.target.value)}>
        {(agentsFor(docLang).length ? agentsFor(docLang) : [{ agent: agentKey, name: null }]).map((p) => (
          <option key={p.agent} value={p.agent}>{p.name ?? p.agent}</option>
        ))}
      </select>
      <div style={{ display: 'flex', alignItems: 'center', border: '1px solid var(--color-divider)', borderRadius: 'var(--radius-sm)', overflow: 'hidden' }}>
        <button type="button" className="btn btn-ghost" aria-label={t.prevVariant} title={t.prevVariant} disabled={index <= 0} onClick={() => onVariant(variants[index - 1])} style={{ padding: '0 8px', minHeight: 30, border: 0, borderRadius: 0 }}>‹</button>
        <select className="input" aria-label={t.variants} value={selectedVariant} onChange={(e) => onVariant(e.target.value)}
          style={{ width: 'auto', minHeight: 30, border: 0, borderRadius: 0, borderLeft: '1px solid var(--color-divider)', borderRight: '1px solid var(--color-divider)', padding: '2px 8px', fontSize: 13, fontWeight: 600 }}>
          {variants.map((name) => <option key={name} value={name}>{name}</option>)}
        </select>
        <button type="button" className="btn btn-ghost" aria-label={t.nextVariant} title={t.nextVariant} disabled={index < 0 || index >= variants.length - 1} onClick={() => onVariant(variants[index + 1])} style={{ padding: '0 8px', minHeight: 30, border: 0, borderRadius: 0 }}>›</button>
      </div>
      <span className="text-muted" style={{ fontFamily: 'ui-monospace, Menlo, monospace', fontSize: 12 }}>{path}</span>
      <div style={{ flex: 1 }} />
      <div className="seg">
        <label className="seg-opt" style={{ padding: '4px 10px' }}>
          <input type="radio" name="prompt-layout" checked={layout === 'split'} onChange={() => onLayout('split')} />{t.layoutSplit}
        </label>
        <label className="seg-opt" style={{ padding: '4px 10px' }}>
          <input type="radio" name="prompt-layout" checked={layout === 'tabs'} onChange={() => onLayout('tabs')} />{t.layoutTabs}
        </label>
      </div>
      {showSave && <button type="button" className="btn btn-primary" disabled={!canSave} onClick={onSave}>{t.save}</button>}
    </div>
  )
}
