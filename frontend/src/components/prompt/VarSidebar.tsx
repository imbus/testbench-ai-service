import { useState } from 'react'
import type { LintError } from '../../api/types'
import { useTranslations, type Lang } from '../../i18n'

/**
 * What the lint block shows. `errors` are the OPEN message's own results;
 * `clean` means the open message (or, on a non-message pane, every message)
 * has a current clean result AND no message of the variant is flagged -- so
 * "no syntax errors" never appears on a clean message while another message
 * is flagged. `checking` is the live check's request in flight, shown apart
 * from `running` (the Lint button's own run).
 */
export type LintState = { running: boolean; checking?: boolean; clean: boolean; error: string | null; errors: LintError[] }

const caps = { fontSize: 11, letterSpacing: '.08em', textTransform: 'uppercase' as const }
const mono = 'ui-monospace, Menlo, monospace'

function VarButton({ name, label, type, used, disabled, onInsert }: { name: string; label?: string; type?: string; used: boolean; disabled: boolean; onInsert: () => void }) {
  return (
    <button
      type="button"
      data-used={used}
      disabled={disabled}
      onClick={onInsert}
      title={name}
      style={{ flex: 1, minWidth: 0, textAlign: 'left', border: 0, background: 'transparent', color: 'inherit', fontFamily: mono, fontSize: 12, padding: '2px 0', cursor: disabled ? 'default' : 'pointer', display: 'flex', justifyContent: 'space-between', gap: 6 }}
    >
      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{label ?? name}</span>
      <span style={{ display: 'flex', gap: 4, flex: 'none' }}>
        {type && <span className="text-muted">{type}</span>}
        {used && <span aria-hidden style={{ color: 'var(--color-accent)' }}>●</span>}
      </span>
    </button>
  )
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** The type a sample value stands for: `"<str | None>"` -> `str | None`. */
export function sampleType(value: unknown): string | undefined {
  if (Array.isArray(value)) return 'list'
  if (isRecord(value)) return DICT_KEY in value ? 'dict' : 'object'
  if (typeof value === 'string') {
    const match = /^<(.+)>$/.exec(value)
    return match ? match[1] : undefined
  }
  return undefined
}

/** The placeholder key the server samples a `dict[str, T]` under. */
const DICT_KEY = '<key>'

/** The fields under a container sample: an object's own, a list's item's, a dict's value's. */
function childrenOf(value: unknown): [string, unknown][] {
  if (Array.isArray(value)) return childrenOf(value[0])
  if (!isRecord(value)) return []
  if (DICT_KEY in value) return childrenOf(value[DICT_KEY])
  return Object.entries(value)
}

/**
 * One `agent.*` field and, folded, what it contains.
 *
 * Attribute chains are insertable all the way down. Below a list or a dict
 * the path stops being one expression (`agent.x[0].y`, `agent.x['k'].y`),
 * so those fields are shown as a hint of the item's shape, not inserted --
 * the template reaches them through a `{% for %}` loop.
 */
function AgentField({ name, path, value, depth, insertable, used, disabled, onInsert }: {
  name: string
  path: string
  value: unknown
  depth: number
  insertable: boolean
  used: string[]
  disabled: boolean
  onInsert: (name: string) => void
}) {
  const [open, setOpen] = useState(false)
  const type = sampleType(value)
  const children = childrenOf(value)
  const container = Array.isArray(value) || (isRecord(value) && DICT_KEY in value)
  const label = depth === 0 ? path : name
  const item = container ? (Array.isArray(value) ? '[]' : `[${DICT_KEY}]`) : ''

  return (
    <div data-testid="agent-field" data-path={path}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
        {children.length > 0 ? (
          <button
            type="button"
            aria-expanded={open}
            aria-label={`${open ? '▾' : '▸'} ${path}`}
            onClick={() => setOpen(!open)}
            style={{ border: 0, background: 'transparent', color: 'inherit', padding: 0, width: 12, cursor: 'pointer', fontSize: 10, flex: 'none' }}
          >
            {open ? '▾' : '▸'}
          </button>
        ) : (
          <span style={{ width: 12, flex: 'none' }} />
        )}
        {insertable ? (
          <VarButton name={path} label={label} type={type} used={used.includes(path)} disabled={disabled} onInsert={() => onInsert(`{{ ${path} }}`)} />
        ) : (
          <span title={path} style={{ flex: 1, minWidth: 0, display: 'flex', justifyContent: 'space-between', gap: 6, fontFamily: mono, padding: '2px 0' }}>
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</span>
            {type && <span className="text-muted">{type}</span>}
          </span>
        )}
      </div>
      {open && (
        <div style={{ marginLeft: 6, paddingLeft: 6, borderLeft: '1px solid var(--color-divider)' }}>
          {children.map(([key, child]) => (
            <AgentField
              key={key}
              name={`${item}.${key}`}
              path={`${path}${item}.${key}`}
              value={child}
              depth={depth + 1}
              insertable={insertable && !container}
              used={used}
              disabled={disabled}
              onInsert={onInsert}
            />
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * The Split layout's right column: insertable variables and the syntax check.
 *
 * `variant="drawer"` is the Tabs layout's Variables drawer: no column chrome
 * (the drawer supplies its own) and no lint block (the status bar shows lint).
 */
export function VarSidebar({ agentVars, agentContext, declaredVars, used, undeclared, canInsert, canDeclare, lint, variant = 'column', lang = 'de', onInsert, onDeclare, onLint }: {
  agentVars: string[]
  /** Typed sample of the agent.* namespace; shown as a foldable field tree. */
  agentContext?: Record<string, unknown>
  declaredVars: string[]
  used: string[]
  undeclared: string[]
  canInsert: boolean
  canDeclare: boolean
  lint: LintState
  variant?: 'column' | 'drawer'
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

  const column = variant === 'column'
  const chrome = column
    ? { width: 230, borderLeft: '1px solid var(--color-divider)', background: 'var(--color-surface)', padding: 12, overflow: 'auto' }
    : {}

  return (
    <aside
      data-testid="var-sidebar"
      style={{ ...chrome, flex: 'none', display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12 }}
    >
      <div className="text-muted" style={caps}>agent.*</div>
      {agentContext
        ? Object.entries(agentContext).map(([key, value]) => (
            <AgentField
              key={key}
              name={key}
              path={`agent.${key}`}
              value={value}
              depth={0}
              insertable
              used={used}
              disabled={!canInsert}
              onInsert={onInsert}
            />
          ))
        : list(agentVars)}
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
      {column && (
        <>
          <div style={{ flex: 1 }} />
          <button type="button" className="btn btn-ghost" disabled={lint.running} onClick={onLint} style={{ alignSelf: 'flex-start', fontSize: 12 }}>
            {lint.running ? t.linting : t.lint}
          </button>
          {lint.checking && !lint.running && <div className="text-muted">{t.lintChecking}</div>}
          {lint.error && <div role="alert" style={{ color: '#a33a2b' }}>{lint.error}</div>}
          {lint.errors.map((error, index) => (
            <div key={index} style={{ border: '1px solid #c0392b', background: 'color-mix(in srgb, #c0392b 10%, transparent)', padding: '6px 8px', color: '#a33a2b' }}>
              {`${t.lintLine} ${error.line}: ${error.message}`}
            </div>
          ))}
          {lint.clean && !lint.error && <div style={{ color: '#2e8b5e' }}>✓ {t.lintClean}</div>}
        </>
      )}
    </aside>
  )
}
