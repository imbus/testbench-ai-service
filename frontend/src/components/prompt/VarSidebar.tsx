import type { LintError } from '../../api/types'
import { useTranslations, type Lang } from '../../i18n'

export type LintState = { running: boolean; checked: boolean; error: string | null; errors: LintError[] }

const caps = { fontSize: 11, letterSpacing: '.08em', textTransform: 'uppercase' as const }
const mono = 'ui-monospace, Menlo, monospace'

function VarButton({ name, used, disabled, onInsert }: { name: string; used: boolean; disabled: boolean; onInsert: () => void }) {
  return (
    <button
      type="button"
      data-used={used}
      disabled={disabled}
      onClick={onInsert}
      style={{ textAlign: 'left', border: 0, background: 'transparent', color: 'inherit', fontFamily: mono, fontSize: 12, padding: '2px 0', cursor: disabled ? 'default' : 'pointer', display: 'flex', justifyContent: 'space-between' }}
    >
      <span>{name}</span>
      {used && <span aria-hidden style={{ color: 'var(--color-accent)' }}>●</span>}
    </button>
  )
}

/** The Split layout's right column: insertable variables and the syntax check. */
export function VarSidebar({ agentVars, declaredVars, used, undeclared, canInsert, canDeclare, lint, lang = 'de', onInsert, onDeclare, onLint }: {
  agentVars: string[]
  declaredVars: string[]
  used: string[]
  undeclared: string[]
  canInsert: boolean
  canDeclare: boolean
  lint: LintState
  lang?: Lang
  onInsert: (name: string) => void
  onDeclare: () => void
  onLint: () => void
}) {
  const t = useTranslations(lang)
  const list = (names: string[]) =>
    names.map((name) => (
      <VarButton key={name} name={name} used={used.includes(name)} disabled={!canInsert} onInsert={() => onInsert(`{{ ${name} }}`)} />
    ))

  return (
    <aside
      data-testid="var-sidebar"
      style={{ width: 230, flex: 'none', borderLeft: '1px solid var(--color-divider)', background: 'var(--color-surface)', padding: 12, display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12, overflow: 'auto' }}
    >
      <div className="text-muted" style={caps}>agent.*</div>
      {list(agentVars)}
      <div className="text-muted" style={{ ...caps, marginTop: 8 }}>vars.* ({t.varsVariantScope})</div>
      {list(declaredVars)}
      {undeclared.length > 0 && (
        <div style={{ border: '1px solid #c9a227', padding: 6, color: '#7a5a00', background: 'color-mix(in srgb, #c9a227 12%, transparent)' }}>
          {t.undeclaredVars} <span style={{ fontFamily: mono }}>{undeclared.join(', ')}</span>{' '}
          {canDeclare && (
            <button type="button" className="btn btn-ghost" style={{ fontSize: 11, padding: '0 4px' }} onClick={onDeclare}>
              {t.declareVars}
            </button>
          )}
        </div>
      )}
      <div style={{ flex: 1 }} />
      <button type="button" className="btn btn-ghost" disabled={lint.running} onClick={onLint} style={{ alignSelf: 'flex-start', fontSize: 12 }}>
        {lint.running ? t.linting : t.lint}
      </button>
      {lint.error && <div role="alert" style={{ color: '#a33a2b' }}>{lint.error}</div>}
      {lint.errors.map((error, index) => (
        <div key={index} style={{ border: '1px solid #c0392b', background: 'color-mix(in srgb, #c0392b 10%, transparent)', padding: '6px 8px', color: '#a33a2b' }}>
          {`${t.lintLine} ${error.line}: ${error.message}`}
        </div>
      ))}
      {lint.checked && !lint.error && lint.errors.length === 0 && <div style={{ color: '#2e8b5e' }}>✓ {t.lintClean}</div>}
    </aside>
  )
}
