import { useNavigate } from 'react-router-dom'
import { Button } from 'primereact/button'
import { Dropdown } from 'primereact/dropdown'
import { usePromptTree } from '../../api/queries'
import { useTranslation } from 'react-i18next'

const compact = { minHeight: 32, fontSize: 13 }

export function EditorToolbar({ docLang, agentKey, path, variants, selectedVariant, canSave, showSave, onVariant, onSave }: {
  docLang: string
  agentKey: string
  path: string
  variants: string[]
  selectedVariant: string
  canSave: boolean
  showSave: boolean
  onVariant: (name: string) => void
  onSave: () => void
}): JSX.Element {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const tree = usePromptTree()
  const languages = tree.data?.languages ?? []
  const agentsFor = (code: string) => (languages.find((l) => l.lang === code)?.prompts ?? []).filter((p) => p.ok)
  const go = (code: string, agent: string) => navigate(`/admin/prompts/${encodeURIComponent(code)}/${encodeURIComponent(agent)}`)
  const index = variants.indexOf(selectedVariant)

  // keep the current value selectable while the tree loads
  const languageOptions = (languages.length ? languages.map((l) => l.lang) : [docLang]).map((code) => ({ label: code, value: code }))
  const agentOptions = (agentsFor(docLang).length ? agentsFor(docLang) : [{ agent: agentKey, name: null }]).map((p) => ({ label: p.name ?? p.agent, value: p.agent }))
  const stepper = { padding: '0 8px', minHeight: 30, border: 0, borderRadius: 0 }

  return (
    <div data-testid="editor-toolbar" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px', borderBottom: '1px solid var(--color-divider)', flexWrap: 'wrap' }}>
      <h3 className="page-title" style={{ margin: 0, fontSize: 22 }}>{t('prompts')}</h3>
      <Dropdown aria-label={t('promptLanguage')} style={compact} value={docLang} options={languageOptions}
        onChange={(e) => {
          const code = e.value as string
          const agents = agentsFor(code)
          const next = agents.some((p) => p.agent === agentKey) ? agentKey : agents[0]?.agent
          if (next) go(code, next)
        }} />
      <Dropdown aria-label={t('promptAgent')} style={compact} value={agentKey} options={agentOptions} onChange={(e) => go(docLang, e.value as string)} />
      <div style={{ display: 'flex', alignItems: 'center', border: '1px solid var(--color-divider)', borderRadius: 'var(--radius-sm)', overflow: 'hidden' }}>
        <Button type="button" text label="‹" aria-label={t('prevVariant')} title={t('prevVariant')} disabled={index <= 0} onClick={() => onVariant(variants[index - 1])} style={stepper} />
        <Dropdown aria-label={t('variants')} value={selectedVariant} options={variants.map((name) => ({ label: name, value: name }))} onChange={(e) => onVariant(e.value as string)}
          style={{ minHeight: 30, border: 0, borderRadius: 0, borderLeft: '1px solid var(--color-divider)', borderRight: '1px solid var(--color-divider)', fontSize: 13, fontWeight: 600 }} />
        <Button type="button" text label="›" aria-label={t('nextVariant')} title={t('nextVariant')} disabled={index < 0 || index >= variants.length - 1} onClick={() => onVariant(variants[index + 1])} style={stepper} />
      </div>
      <span className="text-muted" style={{ fontFamily: 'var(--font-code)', fontSize: 12 }}>{path}</span>
      <div style={{ flex: 1 }} />
      {showSave && <Button type="button" label={t('save')} disabled={!canSave} onClick={onSave} />}
    </div>
  )
}
