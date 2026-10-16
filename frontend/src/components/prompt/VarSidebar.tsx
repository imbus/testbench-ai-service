import { useState } from 'react'
import { Button } from 'primereact/button'
import { InputText } from 'primereact/inputtext'
import { Message } from 'primereact/message'
import type { LintError } from '../../api/types'
import { useTranslation } from 'react-i18next'

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

/** What can follow `vars.` in a template: a Jinja attribute name. */
const VAR_NAME = /^[A-Za-z_]\w*$/

/**
 * Declares a variable without leaving the editor. Only the name: type,
 * description and default stay with the ⚙ variant settings, which this
 * narrow column has no room for.
 */
function NewVar({ onAdd }: { onAdd: (name: string) => void }) {
  const { t } = useTranslation()
  const [name, setName] = useState('')
  const key = name.trim()
  const invalid = key !== '' && !VAR_NAME.test(key)
  return (
    <form
      style={{ display: 'flex', flexDirection: 'column', gap: 4 }}
      onSubmit={(event) => {
        event.preventDefault()
        if (!key || invalid) return
        onAdd(key)
        setName('')
      }}
    >
      <div style={{ display: 'flex', gap: 4 }}>
        <InputText
          aria-label={t('varNewName')}
          aria-invalid={invalid || undefined}
          placeholder={t('varNewName')}
          value={name}
          onChange={(event) => setName(event.target.value)}
          style={{ flex: 1, minWidth: 0, fontFamily: mono, fontSize: 12, padding: '2px 6px' }}
        />
      </div>
      {invalid && <span className="text-muted" style={{ fontSize: 11 }}>{t('varNameInvalid')}</span>}
    </form>
  )
}
const mono = 'ui-monospace, Menlo, monospace'

function VarButton({ name, label, type, used, disabled, onInsert }: { name: string; label?: string; type?: string; used: boolean; disabled: boolean; onInsert: () => void }) {
  return (
    <Button
      type="button"
      text
      data-used={used}
      disabled={disabled}
      onClick={onInsert}
      title={name}
      style={{ flex: 1, minWidth: 0, textAlign: 'left', color: 'inherit', fontFamily: mono, fontSize: 12, fontWeight: 400, padding: '2px 0', minHeight: 0, display: 'flex', justifyContent: 'space-between', gap: 6 }}
    >
      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{label ?? name}</span>
      <span style={{ display: 'flex', gap: 4, flex: 'none' }}>
        {type && <span className="text-muted">{type}</span>}
        {used && <span aria-hidden style={{ color: 'var(--color-accent-fg)' }}>●</span>}
      </span>
    </Button>
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
          <Button
            type="button"
            text
            label={open ? '▾' : '▸'}
            aria-expanded={open}
            aria-label={`${open ? '▾' : '▸'} ${path}`}
            onClick={() => setOpen(!open)}
            style={{ color: 'inherit', padding: 0, width: 12, minHeight: 0, fontSize: 10, flex: 'none' }}
          />
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
 * The editor's right column: insertable variables and the syntax check.
 */
export function VarSidebar({ agentVars, agentContext, declaredVars, used, undeclared, canInsert, canDeclare, lint, onInsert, onDeclare, onLint, onAddVar }: {
  agentVars: string[]
  /** Typed sample of the agent.* namespace; shown as a foldable field tree. */
  agentContext?: Record<string, unknown>
  declaredVars: string[]
  used: string[]
  undeclared: string[]
  canInsert: boolean
  canDeclare: boolean
  lint: LintState
  onInsert: (name: string) => void
  onDeclare: () => void
  onLint: () => void
  /** Declares the variable (if new) and inserts it at the cursor. */
  onAddVar: (name: string) => void
}) {
  const { t } = useTranslation()
  // Each in a row like `AgentField`'s: directly in this column, the button's
  // `flex: 1` would stretch it vertically into the free space below.
  const list = (names: string[]) =>
    names.map((name) => (
      <div key={name} style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
        <span style={{ width: 12, flex: 'none' }} />
        <VarButton name={name} used={used.includes(name)} disabled={!canInsert} onInsert={() => onInsert(`{{ ${name} }}`)} />
      </div>
    ))

  const chrome = { width: 230, borderLeft: '1px solid var(--color-divider)', background: 'var(--color-surface)', padding: 12, overflow: 'auto' }

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
      <div className="text-muted" style={{ ...caps, marginTop: 8 }}>vars.* ({t('varsVariantScope')})</div>
      {list(declaredVars)}
      {/* Creating a variable also inserts it, so it needs an editor that takes inserts. */}
      {canInsert && <NewVar onAdd={onAddVar} />}
      {undeclared.length > 0 && (
        // `status`, not Prime's default `alert`: a notice about the draft,
        // not an error the operator has to stop for.
        <Message
          severity="warn"
          role="status"
          style={{ padding: 6, fontSize: 12, justifyContent: 'flex-start' }}
          content={
            <div>
              {t('undeclaredVars')} <span style={{ fontFamily: mono }}>{undeclared.join(', ')}</span>{' '}
              {canDeclare && (
                <Button type="button" text label={t('declareVars')} style={{ fontSize: 11, padding: '0 4px' }} onClick={onDeclare} />
              )}
            </div>
          }
        />
      )}
      <div style={{ flex: 1 }} />
      <Button type="button" text label={lint.running ? t('linting') : t('lint')} disabled={lint.running} onClick={onLint} style={{ alignSelf: 'flex-start', fontSize: 12 }} />
      {lint.checking && !lint.running && <div className="text-muted">{t('lintChecking')}</div>}
      {lint.error && <Message severity="error" text={lint.error} style={{ fontSize: 12, justifyContent: 'flex-start' }} />}
      {/* `status`, not Prime's default `alert`: the editor's own marker
          is already the alert for each of these lines. */}
      {lint.errors.map((error, index) => (
        <Message key={index} severity="error" role="status" text={t('lintLine', { line: error.line, message: error.message })} style={{ padding: '6px 8px', fontSize: 12, justifyContent: 'flex-start' }} />
      ))}
      {lint.clean && !lint.error && <Message severity="success" role="status" text={t('lintClean')} style={{ padding: '6px 8px', fontSize: 12, justifyContent: 'flex-start' }} />}
    </aside>
  )
}
