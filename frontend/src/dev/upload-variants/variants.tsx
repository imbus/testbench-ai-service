/* Throwaway: five designs of the "upload agent package" dialog, built from
   real PrimeReact components so they can be compared with the console's own
   theme. Rendered to static HTML by generate.tsx. Not shipped. */
import type { CSSProperties, ReactNode } from 'react'
import { Badge } from 'primereact/badge'
import { Button } from 'primereact/button'
import { Column } from 'primereact/column'
import { DataTable } from 'primereact/datatable'
import { Divider } from 'primereact/divider'
import { Message } from 'primereact/message'
import { ProgressBar } from 'primereact/progressbar'
import { Steps } from 'primereact/steps'
import { TabPanel, TabView } from 'primereact/tabview'
import { Tag } from 'primereact/tag'

export type State = 'pick' | 'uploading' | 'result' | 'error'
export const STATES: { key: State; label: string }[] = [
  { key: 'pick', label: '1 · Datei gewählt' },
  { key: 'uploading', label: '2 · Upload und Prüfung laufen' },
  { key: 'result', label: '3 · Prüfbericht mit Befunden' },
  { key: 'error', label: '4 · Upload abgelehnt' },
]

// --- sample data -------------------------------------------------------------

const FILE = { name: 'acme_tb_agents-1.2.0-py3-none-any.whl', size: '48,2 KB' }
const PKG = { name: 'acme-tb-agents', version: '1.2.0', sha: '3f9a0c1d2e3f4a5b' }
const PKG_WARNINGS = ['Das Paket enthält keine README.']

interface Agent {
  entry: string
  cls: string
  endpoint: string | null
  llm: boolean
  errors: string[]
  warnings: string[]
}
const AGENTS: Agent[] = [
  {
    entry: 'risk_rater',
    cls: 'acme.risk.RiskRater',
    endpoint: '/acme-risk-rater',
    llm: true,
    errors: [],
    warnings: [],
  },
  {
    entry: 'coverage_hint',
    cls: 'acme.coverage.CoverageHint',
    endpoint: '/acme-coverage-hint',
    llm: false,
    errors: [],
    warnings: ['Keine Write-back-Vorlage für en.'],
  },
  {
    entry: 'dup_finder',
    cls: 'acme.dup.DupFinder',
    endpoint: null,
    llm: true,
    errors: ['prompts/de/prompt.yaml fehlt.', 'endpoint_path ist nicht gesetzt.'],
    warnings: [],
  },
]
const OK = AGENTS.filter((a) => a.errors.length === 0).length
const ERRORS = AGENTS.reduce((n, a) => n + a.errors.length, 0)
const WARNINGS = AGENTS.reduce((n, a) => n + a.warnings.length, PKG_WARNINGS.length)
const REJECT = {
  text: 'Die Datei ist kein gültiges Wheel.',
  detail: 'BadZipFile: File is not a zip file',
}

const TITLE = 'Agenten-Paket hochladen'

// --- small shared pieces ---------------------------------------------------------

const muted: CSSProperties = { color: 'var(--color-muted)' }
const mono: CSSProperties = { fontFamily: 'var(--font-code)' }

function Svg({ d, size = 16, color }: { d: string; size?: number; color?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color ?? 'currentColor'}
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      style={{ flex: 'none' }}
    >
      <path d={d} />
    </svg>
  )
}
const ICON = {
  upload: 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12',
  file: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6',
  box: 'M21 16V8a2 2 0 0 0-1-1.7l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.7l7 4a2 2 0 0 0 2 0l7-4a2 2 0 0 0 1-1.7zM3.3 7 12 12l8.7-5M12 22V12',
  check: 'M20 6 9 17l-5-5',
  x: 'M18 6 6 18M6 6l12 12',
  warn: 'M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01',
}

function status(agent: Agent) {
  if (agent.errors.length) return { severity: 'danger' as const, label: 'Fehler', icon: ICON.x }
  if (agent.warnings.length)
    return { severity: 'warning' as const, label: 'Warnung', icon: ICON.warn }
  return { severity: 'success' as const, label: 'OK', icon: ICON.check }
}

function StatusTag({ agent }: { agent: Agent }) {
  const s = status(agent)
  return <Tag severity={s.severity} value={s.label} style={{ fontSize: 11, padding: '2px 8px' }} />
}

/** The PrimeReact dialog markup, drawn in place instead of portalled. */
function Shell({
  width = 720,
  header,
  footer,
  children,
}: {
  width?: number
  header?: ReactNode
  footer: ReactNode
  children: ReactNode
}) {
  return (
    <div
      className="p-dialog p-component"
      role="dialog"
      style={{ width, maxWidth: '100%', position: 'relative', transform: 'none' }}
    >
      {header && <div className="p-dialog-header">{header}</div>}
      <div
        className="p-dialog-content"
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 14,
          ...(header ? {} : { paddingTop: 24 }),
        }}
      >
        {children}
      </div>
      <div className="p-dialog-footer" style={{ display: 'flex', justifyContent: 'flex-end' }}>
        {footer}
      </div>
    </div>
  )
}

function HeaderTitle({ sub, closable }: { sub?: string; closable?: boolean }) {
  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <span className="p-dialog-title">{TITLE}</span>
        {sub && <span style={{ ...muted, fontSize: 12, fontWeight: 400 }}>{sub}</span>}
      </div>
      {closable && (
        <div className="p-dialog-header-icons">
          <button type="button" className="p-dialog-header-icon p-dialog-header-close p-link">
            <Svg d={ICON.x} />
          </button>
        </div>
      )}
    </>
  )
}

function Footer({ state, cancel = 'Abbrechen' }: { state: State; cancel?: string }) {
  const done = state === 'result'
  return (
    <>
      <Button type="button" outlined label={done ? 'Schließen' : cancel} />
      {done ? (
        <Button type="button" label="Agenten registrieren" />
      ) : (
        <Button
          type="button"
          label="Hochladen und prüfen"
          disabled={state === 'uploading'}
          loading={state === 'uploading'}
        />
      )}
    </>
  )
}

function Dropzone({ compact, file }: { compact?: boolean; file?: boolean }) {
  return (
    <div
      style={{
        border: '2px dashed var(--color-divider)',
        borderRadius: 8,
        padding: compact ? '18px 16px' : '34px 16px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 8,
        textAlign: 'center',
        background: 'color-mix(in srgb, var(--color-surface) 50%, transparent)',
      }}
    >
      <Svg d={ICON.upload} size={compact ? 22 : 32} color="var(--color-muted)" />
      <div style={{ fontSize: 14 }}>
        Wheel hierher ziehen oder{' '}
        <Button type="button" link label="Datei wählen" style={{ padding: 0 }} />
      </div>
      <div style={{ ...muted, fontSize: 12 }}>Nur .whl · max. 20 MB</div>
      {file && <FileChip />}
    </div>
  )
}

function FileChip({ removable = true }: { removable?: boolean }) {
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 8,
        padding: '6px 10px',
        borderRadius: 6,
        border: '1px solid var(--color-divider)',
        background: 'var(--color-bg)',
        fontSize: 13,
      }}
    >
      <Svg d={ICON.file} />
      <span style={mono}>{FILE.name}</span>
      <span style={muted}>{FILE.size}</span>
      {removable && (
        <Button
          type="button"
          text
          rounded
          severity="secondary"
          aria-label="Entfernen"
          icon={<Svg d={ICON.x} size={14} />}
          style={{ width: 24, height: 24, padding: 0 }}
        />
      )}
    </div>
  )
}

function Uploading({ label = 'Wird hochgeladen und geprüft…' }: { label?: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
        <span>{label}</span>
        <span style={muted}>Prüfung in separatem Prozess · max. 30 s</span>
      </div>
      <ProgressBar mode="indeterminate" style={{ height: 6 }} />
    </div>
  )
}

function Reject() {
  return (
    <Message
      severity="error"
      style={{ justifyContent: 'flex-start', width: '100%' }}
      content={
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <strong>{REJECT.text}</strong>
          <span style={{ ...mono, fontSize: 12 }}>{REJECT.detail}</span>
        </div>
      }
    />
  )
}

function Findings({ agent }: { agent: Agent }) {
  if (!agent.errors.length && !agent.warnings.length)
    return <span style={{ ...muted, fontSize: 12 }}>—</span>
  return (
    <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12 }}>
      {agent.errors.map((e) => (
        <li key={e} style={{ color: 'var(--color-danger)' }}>
          {e}
        </li>
      ))}
      {agent.warnings.map((w) => (
        <li key={w} style={{ color: 'var(--color-warning)' }}>
          {w}
        </li>
      ))}
    </ul>
  )
}

function Summary() {
  return (
    <Message
      severity="warn"
      style={{ justifyContent: 'flex-start', width: '100%' }}
      text={`${PKG.name} ${PKG.version} hochgeladen. ${OK} von ${AGENTS.length} Agenten registrierbar.`}
    />
  )
}

// --- A: wizard with steps and a table -----------------------------------------------

export function VariantA({ state }: { state: State }) {
  const step = state === 'result' ? 1 : 0
  return (
    <Shell header={<HeaderTitle sub="Python-Wheel mit eigenen Agenten" closable />} footer={<Footer state={state} />}>
      <Steps
        readOnly
        activeIndex={step}
        model={[{ label: 'Wheel wählen' }, { label: 'Prüfbericht' }, { label: 'Registrieren' }]}
      />
      {state === 'pick' && <Dropzone file />}
      {state === 'uploading' && (
        <>
          <FileChip removable={false} />
          <Uploading />
        </>
      )}
      {state === 'error' && (
        <>
          <Reject />
          <Dropzone compact />
        </>
      )}
      {state === 'result' && (
        <>
          <Summary />
          {PKG_WARNINGS.map((w) => (
            <Message key={w} severity="secondary" text={`Paket: ${w}`} style={{ justifyContent: 'flex-start' }} />
          ))}
          <DataTable value={AGENTS} size="small" stripedRows dataKey="entry">
            <Column header="Status" body={(a: Agent) => <StatusTag agent={a} />} style={{ width: 90 }} />
            <Column
              header="Einstiegspunkt"
              body={(a: Agent) => (
                <div>
                  <div style={{ ...mono, fontSize: 13 }}>{a.entry}</div>
                  <div style={{ ...muted, ...mono, fontSize: 11 }}>{a.cls}</div>
                </div>
              )}
            />
            <Column
              header="Endpunkt"
              body={(a: Agent) => <span style={{ ...mono, fontSize: 12 }}>{a.endpoint ?? '—'}</span>}
            />
            <Column header="Befunde" body={(a: Agent) => <Findings agent={a} />} />
          </DataTable>
        </>
      )}
    </Shell>
  )
}

// --- B: big dropzone and one card per agent ---------------------------------------------

function AgentCard({ agent }: { agent: Agent }) {
  const s = status(agent)
  const color =
    s.severity === 'danger'
      ? 'var(--color-danger)'
      : s.severity === 'warning'
        ? 'var(--color-warning)'
        : 'var(--color-success)'
  return (
    <div
      style={{
        border: '1px solid var(--color-divider)',
        borderLeft: `4px solid ${color}`,
        borderRadius: 6,
        padding: '10px 14px',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <Svg d={s.icon} color={color} />
        <span style={{ ...mono, fontWeight: 600, fontSize: 14 }}>{agent.entry}</span>
        {agent.llm && <Tag value="LLM" severity="info" style={{ fontSize: 10, padding: '1px 6px' }} />}
        <span style={{ flex: 1 }} />
        <span style={{ ...muted, ...mono, fontSize: 11 }}>{agent.cls}</span>
      </div>
      <div style={{ ...muted, fontSize: 12 }}>
        Endpunkt <span style={mono}>{agent.endpoint ?? 'nicht gesetzt'}</span>
      </div>
      {agent.errors.map((e) => (
        <Message key={e} severity="error" text={e} style={{ justifyContent: 'flex-start', padding: '6px 10px' }} />
      ))}
      {agent.warnings.map((w) => (
        <Message key={w} severity="warn" text={w} style={{ justifyContent: 'flex-start', padding: '6px 10px' }} />
      ))}
    </div>
  )
}

export function VariantB({ state }: { state: State }) {
  return (
    <Shell header={<HeaderTitle closable />} footer={<Footer state={state} />}>
      {state === 'pick' && <Dropzone file />}
      {state === 'uploading' && (
        <div
          style={{
            border: '2px dashed var(--color-divider)',
            borderRadius: 8,
            padding: '26px 20px',
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
            alignItems: 'center',
          }}
        >
          <FileChip removable={false} />
          <div style={{ width: '100%' }}>
            <Uploading />
          </div>
        </div>
      )}
      {state === 'error' && (
        <>
          <Dropzone />
          <Reject />
        </>
      )}
      {state === 'result' && (
        <>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '12px 14px',
              borderRadius: 8,
              background: 'var(--color-surface)',
            }}
          >
            <Svg d={ICON.box} size={28} color="var(--color-muted)" />
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <span style={{ fontFamily: 'var(--font-heading)', fontWeight: 600, fontSize: 17 }}>
                {PKG.name} <span style={{ ...mono, fontWeight: 400, fontSize: 14 }}>{PKG.version}</span>
              </span>
              <span style={{ ...muted, fontSize: 12 }}>
                {FILE.size} · sha256 <span style={mono}>{PKG.sha.slice(0, 8)}…</span>
              </span>
            </div>
            <span style={{ flex: 1 }} />
            <Tag severity="success" value={`${OK} registrierbar`} />
            <Tag severity="danger" value={`${AGENTS.length - OK} fehlerhaft`} />
          </div>
          {PKG_WARNINGS.map((w) => (
            <Message key={w} severity="warn" text={`Paket: ${w}`} style={{ justifyContent: 'flex-start' }} />
          ))}
          {AGENTS.map((a) => (
            <AgentCard key={a.entry} agent={a} />
          ))}
        </>
      )}
    </Shell>
  )
}

// --- C: compact, a single file row and a dense list ----------------------------------------

export function VariantC({ state }: { state: State }) {
  return (
    <Shell width={640} footer={<Footer state={state} cancel="Schließen" />}>
      <div>
        <h3 style={{ margin: 0 }}>{TITLE}</h3>
        <div style={{ ...muted, fontSize: 12 }}>
          Das Wheel wird in einem separaten Prozess geprüft; es wird noch nichts aktiviert.
        </div>
      </div>
      {state !== 'result' && (
        <div className="p-inputgroup">
          <Button type="button" outlined label="Datei wählen…" icon={<Svg d={ICON.file} />} disabled={state === 'uploading'} />
          <span
            className="p-inputtext p-component"
            style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}
          >
            <span style={mono}>{FILE.name}</span>
            <span style={muted}>{FILE.size}</span>
          </span>
        </div>
      )}
      {state === 'uploading' && <ProgressBar mode="indeterminate" style={{ height: 4 }} />}
      {state === 'error' && <Reject />}
      {state === 'result' && (
        <>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, fontSize: 13 }}>
            <Svg d={ICON.box} />
            <strong>{PKG.name}</strong>
            <span style={mono}>{PKG.version}</span>
            <span style={muted}>{FILE.size}</span>
            <span style={{ flex: 1 }} />
            <span style={muted}>
              {OK}/{AGENTS.length} Agenten ok · {ERRORS} Fehler · {WARNINGS} Warnungen
            </span>
          </div>
          <Divider style={{ margin: 0 }} />
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {PKG_WARNINGS.map((w) => (
              <Row key={w} icon={ICON.warn} color="var(--color-warning)" title="Paket" detail={w} />
            ))}
            {AGENTS.map((a) => {
              const s = status(a)
              const color =
                s.severity === 'danger'
                  ? 'var(--color-danger)'
                  : s.severity === 'warning'
                    ? 'var(--color-warning)'
                    : 'var(--color-success)'
              return (
                <Row
                  key={a.entry}
                  icon={s.icon}
                  color={color}
                  title={<span style={mono}>{a.entry}</span>}
                  aside={a.cls}
                  detail={[...a.errors, ...a.warnings].join(' · ') || undefined}
                />
              )
            })}
          </div>
        </>
      )}
    </Shell>
  )
}

function Row({
  icon,
  color,
  title,
  aside,
  detail,
}: {
  icon: string
  color: string
  title: ReactNode
  aside?: string
  detail?: string
}) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '20px 1fr auto',
        columnGap: 8,
        padding: '7px 0',
        borderBottom: '1px solid var(--color-divider)',
        fontSize: 13,
      }}
    >
      <Svg d={icon} color={color} />
      <span>{title}</span>
      <span style={{ ...muted, ...mono, fontSize: 11 }}>{aside}</span>
      {detail && <span style={{ gridColumn: 2, fontSize: 12, color }}>{detail}</span>}
    </div>
  )
}

// --- D: summary tiles first, details in an accordion ---------------------------------------------

function Tile({ value, label, color }: { value: number; label: string; color: string }) {
  return (
    <div
      style={{
        flex: 1,
        border: '1px solid var(--color-divider)',
        borderRadius: 8,
        padding: '10px 14px',
        display: 'flex',
        flexDirection: 'column',
        gap: 2,
      }}
    >
      <span style={{ fontFamily: 'var(--font-heading)', fontSize: 26, fontWeight: 600, color }}>
        {value}
      </span>
      <span style={{ ...muted, fontSize: 12 }}>{label}</span>
    </div>
  )
}

/** PrimeReact's AccordionTab markup; the component renders nothing server-side. */
function AccTab({ header, open, children }: { header: ReactNode; open?: boolean; children: ReactNode }) {
  return (
    <div className={`p-accordion-tab${open ? ' p-accordion-tab-active' : ''}`}>
      <div className={`p-accordion-header${open ? ' p-highlight' : ''}`}>
        <a className="p-accordion-header-link" role="button" aria-expanded={open} style={{ gap: 10 }}>
          <Svg d={open ? 'm6 9 6 6 6-6' : 'm9 18 6-6-6-6'} size={14} />
          <span className="p-accordion-header-text" style={{ flex: 1 }}>{header}</span>
        </a>
      </div>
      {open && (
        <div className="p-toggleable-content">
          <div className="p-accordion-content">{children}</div>
        </div>
      )}
    </div>
  )
}

export function VariantD({ state }: { state: State }) {
  return (
    <Shell header={<HeaderTitle sub="Schritt 1 von 2 · danach Agenten registrieren" closable />} footer={<Footer state={state} />}>
      {state === 'pick' && (
        <>
          <Dropzone compact file />
          <Message
            severity="info"
            style={{ justifyContent: 'flex-start' }}
            text="Beim Upload wird kein Paketcode im Service ausgeführt. Aktiviert wird erst beim Registrieren."
          />
        </>
      )}
      {state === 'uploading' && (
        <>
          <FileChip removable={false} />
          <Uploading label="Prüfe Einstiegspunkte, Prompts und Vorlagen…" />
        </>
      )}
      {state === 'error' && (
        <>
          <Reject />
          <Dropzone compact />
        </>
      )}
      {state === 'result' && (
        <>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <span style={{ fontFamily: 'var(--font-heading)', fontWeight: 600, fontSize: 18 }}>{PKG.name}</span>
            <Tag value={PKG.version} severity="secondary" />
            <span style={{ ...muted, fontSize: 12, ...mono }}>sha256 {PKG.sha.slice(0, 8)}…</span>
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <Tile value={OK} label="Agenten registrierbar" color="var(--color-success)" />
            <Tile value={ERRORS} label="Fehler" color="var(--color-danger)" />
            <Tile value={WARNINGS} label="Warnungen" color="var(--color-warning)" />
          </div>
          <div className="p-accordion p-component">
            {AGENTS.map((a, i) => (
              <AccTab
                key={a.entry}
                open={i === 2}
                header={
                  <span style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%' }}>
                    <span style={{ ...mono, fontSize: 13 }}>{a.entry}</span>
                    <StatusTag agent={a} />
                    {a.errors.length + a.warnings.length > 0 && (
                      <Badge value={a.errors.length + a.warnings.length} severity={a.errors.length ? 'danger' : 'warning'} />
                    )}
                  </span>
                }
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 13 }}>
                  <div>
                    <span style={muted}>Klasse </span>
                    <span style={mono}>{a.cls}</span>
                  </div>
                  <div>
                    <span style={muted}>Endpunkt </span>
                    <span style={mono}>{a.endpoint ?? '—'}</span>
                  </div>
                  <Findings agent={a} />
                </div>
              </AccTab>
            ))}
            <AccTab header={<span style={{ display: 'flex', gap: 10, alignItems: 'center' }}>Paket-Hinweise <Badge value={PKG_WARNINGS.length} severity="warning" /></span>}>
              <Findings agent={{ ...AGENTS[0], warnings: PKG_WARNINGS }} />
            </AccTab>
          </div>
        </>
      )}
    </Shell>
  )
}

// --- E: two columns, file on the left, report tabs on the right ---------------------------------------

function Meta({ label, value, code }: { label: string; value: ReactNode; code?: boolean }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <span style={{ ...muted, fontSize: 11, textTransform: 'uppercase', letterSpacing: '.06em' }}>{label}</span>
      <span style={{ fontSize: 13, wordBreak: 'break-all', ...(code ? mono : {}) }}>{value}</span>
    </div>
  )
}

export function VariantE({ state }: { state: State }) {
  const left =
    state === 'result' ? (
      <>
        <Svg d={ICON.box} size={36} color="var(--color-muted)" />
        <Meta label="Paket" value={PKG.name} />
        <Meta label="Version" value={PKG.version} code />
        <Meta label="Datei" value={FILE.name} code />
        <Meta label="Größe" value={FILE.size} />
        <Meta label="SHA-256" value={`${PKG.sha}…`} code />
      </>
    ) : (
      <>
        <Svg d={ICON.upload} size={36} color="var(--color-muted)" />
        <div style={{ fontSize: 13 }}>Wheel hierher ziehen</div>
        <Button type="button" outlined size="small" label="Datei wählen" disabled={state === 'uploading'} />
        <Divider style={{ margin: '4px 0' }} />
        <Meta label="Datei" value={FILE.name} code />
        <Meta label="Größe" value={FILE.size} />
      </>
    )

  const right =
    state === 'result' ? (
      <TabView>
        <TabPanel header={`Agenten (${AGENTS.length})`}>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {AGENTS.map((a) => (
              <div
                key={a.entry}
                style={{
                  display: 'flex',
                  gap: 10,
                  alignItems: 'flex-start',
                  padding: '8px 0',
                  borderBottom: '1px solid var(--color-divider)',
                }}
              >
                <StatusTag agent={a} />
                <div style={{ display: 'flex', flexDirection: 'column', gap: 2, flex: 1 }}>
                  <span style={{ ...mono, fontSize: 13 }}>{a.entry}</span>
                  <span style={{ ...muted, ...mono, fontSize: 11 }}>
                    {a.cls} · {a.endpoint ?? 'kein Endpunkt'}
                  </span>
                  <Findings agent={a} />
                </div>
              </div>
            ))}
          </div>
        </TabPanel>
        <TabPanel header={`Fehler (${ERRORS})`} />
        <TabPanel header={`Warnungen (${WARNINGS})`} />
      </TabView>
    ) : (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, justifyContent: 'center', height: '100%' }}>
        {state === 'pick' && (
          <>
            <div style={{ fontSize: 14, fontWeight: 600 }}>Was geprüft wird</div>
            {['Wheel lesbar und Metadaten vollständig', 'Einstiegspunkte importierbar', 'prompt.yaml je Sprache vorhanden', 'Write-back-Vorlagen gültig'].map((t) => (
              <div key={t} style={{ display: 'flex', gap: 8, fontSize: 13, alignItems: 'center' }}>
                <Svg d={ICON.check} color="var(--color-muted)" />
                {t}
              </div>
            ))}
          </>
        )}
        {state === 'uploading' && <Uploading />}
        {state === 'error' && <Reject />}
      </div>
    )

  return (
    <Shell width={860} header={<HeaderTitle closable />} footer={<Footer state={state} />}>
      <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr', gap: 20, minHeight: 260 }}>
        <div
          style={{
            background: 'var(--color-surface)',
            borderRadius: 8,
            padding: 16,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'flex-start',
            gap: 10,
          }}
        >
          {left}
        </div>
        <div style={{ minWidth: 0 }}>{right}</div>
      </div>
    </Shell>
  )
}

export const VARIANTS = [
  {
    key: 'a',
    name: 'A · Assistent mit Steps',
    pitch: 'Steps zeigen den Weg Wheel → Prüfbericht → Registrieren; der Bericht ist eine DataTable mit Status-Tags.',
    Component: VariantA,
  },
  {
    key: 'b',
    name: 'B · Dropzone und Agentenkarten',
    pitch: 'Große Drag-&-Drop-Fläche; im Ergebnis ein Paketkopf und je Agent eine Karte mit farbiger Kante und Message-Befunden.',
    Component: VariantB,
  },
  {
    key: 'c',
    name: 'C · Kompakt',
    pitch: 'Am nächsten am heutigen Dialog: eine Dateizeile als InputGroup, Ergebnis als dichte Liste mit einer Statuszeile.',
    Component: VariantC,
  },
  {
    key: 'd',
    name: 'D · Zusammenfassung und Accordion',
    pitch: 'Kennzahlen-Kacheln zuerst, Details je Agent im Accordion; nur der fehlerhafte Agent ist aufgeklappt.',
    Component: VariantD,
  },
  {
    key: 'e',
    name: 'E · Zweispaltig mit Tabs',
    pitch: 'Links Datei und Paketdaten, rechts der Bericht in einer TabView (Agenten / Fehler / Warnungen). Breiter Dialog.',
    Component: VariantE,
  },
]
