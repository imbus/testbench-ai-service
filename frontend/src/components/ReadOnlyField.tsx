import type { FieldSpec } from '../screens/fields'

/** Renders one config value as text. Phase 2 replaces this with real inputs. */
export function ReadOnlyField({ spec, value }: { spec: FieldSpec; value: unknown }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(180px, 260px) 1fr',
        gap: 16,
        padding: '10px 0',
        borderBottom: '1px solid var(--color-divider)',
      }}
    >
      <div>
        <div style={{ fontSize: 13, fontFamily: 'ui-monospace, Menlo, monospace' }}>
          {spec.key.split('.').pop()}
        </div>
        <div className="text-muted" style={{ fontSize: 11 }}>
          {spec.hint}
        </div>
      </div>
      <div style={{ fontSize: 14, wordBreak: 'break-word' }}>{display(value)}</div>
    </div>
  )
}

function display(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (Array.isArray(value)) return value.length ? value.join(', ') : '—'
  return String(value)
}
