import type { PromptVariantDoc } from '../../api/types'
import { useTranslations, type Lang } from '../../i18n'
import { messageLabel, type Selection } from './selection'

const mono = 'ui-monospace, Menlo, monospace'
const rowButton = { border: 0, background: 'transparent', color: 'inherit', font: 'inherit', cursor: 'pointer', textAlign: 'left' as const }

/** The Split layout's left column: prompt.yaml, then variants with the selected one expanded. */
export function PromptTree({ variants, selectedVariant, selection, flagged, invalidVariants = [], readOnly, lang = 'de', onOpenMeta, onPickVariant, onOpenVariantSettings, onPickMessage, onAddVariant, onAddMessage }: {
  variants: PromptVariantDoc[]
  selectedVariant: string
  selection: Selection
  flagged: number[]
  /** Variants a save 422 named (e.g. "needs at least one message") -- marked on their row. */
  invalidVariants?: string[]
  readOnly: boolean
  lang?: Lang
  onOpenMeta: () => void
  onPickVariant: (name: string) => void
  onOpenVariantSettings: (name: string) => void
  onPickMessage: (index: number) => void
  onAddVariant: () => void
  onAddMessage: () => void
}) {
  const t = useTranslations(lang)
  const files = [...new Set(variants.flatMap((v) => v.messages.filter((m) => m.source === 'file' && m.file).map((m) => m.file as string)))]

  return (
    // No aria-label: `t.variants` already names the toolbar's variant select,
    // and a second element with that label makes getByLabelText ambiguous.
    <nav
      data-testid="prompt-tree"
      style={{ width: 250, flex: 'none', borderRight: '1px solid var(--color-divider)', display: 'flex', flexDirection: 'column', overflow: 'auto', fontSize: 13 }}
    >
      <button
        type="button"
        aria-current={selection.kind === 'meta' || undefined}
        onClick={onOpenMeta}
        style={{ ...rowButton, padding: '8px 14px', display: 'flex', flexDirection: 'column', background: selection.kind === 'meta' ? 'var(--color-surface)' : 'transparent' }}
      >
        <span style={{ fontFamily: mono, fontSize: 12 }}>prompt.yaml</span>
        <span className="text-muted" style={{ fontSize: 11 }}>{t.promptMetaHint}</span>
      </button>

      <div className="text-muted" style={{ display: 'flex', alignItems: 'center', padding: '10px 14px 4px', fontSize: 11, letterSpacing: '.08em', textTransform: 'uppercase' }}>
        <span>{t.variants}</span>
        <div style={{ flex: 1 }} />
        {!readOnly && (
          <button type="button" className="btn btn-ghost" aria-label={t.newVariantDefault} title={t.newVariantDefault} style={{ padding: '0 4px', fontSize: 12 }} onClick={onAddVariant}>+</button>
        )}
      </div>

      {variants.map((variant) => {
        const open = variant.name === selectedVariant
        const invalid = invalidVariants.includes(variant.name)
        return (
          <div key={variant.name} style={{ display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', alignItems: 'center', padding: '6px 14px', gap: 6, background: open && selection.kind === 'variant' ? 'var(--color-surface)' : 'transparent' }}>
              <button type="button" aria-expanded={open} aria-invalid={invalid || undefined} onClick={() => onPickVariant(variant.name)} style={{ ...rowButton, fontWeight: 500, padding: 0, flex: 1, display: 'flex', alignItems: 'center', gap: 6, color: invalid ? '#a33a2b' : 'inherit' }}>
                <span aria-hidden style={{ fontSize: 10 }}>{open ? '▾' : '▸'}</span>
                {variant.name}
              </button>
              {variant.model && <span className="text-muted" style={{ fontFamily: mono, fontSize: 11 }}>{variant.model}</span>}
              <button type="button" className="btn btn-ghost" aria-label={`${t.variantSettings}: ${variant.name}`} title={t.variantSettings} onClick={() => onOpenVariantSettings(variant.name)} style={{ padding: '0 4px', fontSize: 12 }}>⚙</button>
            </div>
            {open && variant.messages.map((message, index) => {
              const current = selection.kind === 'message' && selection.index === index
              return (
                <button
                  key={index}
                  type="button"
                  aria-current={current || undefined}
                  aria-invalid={flagged.includes(index) || undefined}
                  onClick={() => onPickMessage(index)}
                  style={{ ...rowButton, fontSize: 12, padding: '5px 14px 5px 34px', display: 'flex', gap: 6, alignItems: 'center', background: current ? 'var(--color-surface)' : 'transparent' }}
                >
                  <span className="tag tag-neutral" style={{ padding: '0 5px', fontSize: 10 }}>{message.role}</span>
                  <span style={{ fontFamily: mono, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{messageLabel(message, t.emptyMessage)}</span>
                  {flagged.includes(index) && <span aria-hidden style={{ color: '#c0392b' }}>●</span>}
                </button>
              )
            })}
            {open && !readOnly && (
              <button type="button" className="text-muted" onClick={onAddMessage} style={{ ...rowButton, fontSize: 12, padding: '4px 14px 6px 34px' }}>{t.addMessageShort}</button>
            )}
          </div>
        )
      })}

      <div style={{ flex: 1 }} />
      <div data-testid="tree-files" className="text-muted" style={{ padding: '10px 14px', borderTop: '1px solid var(--color-divider)', fontSize: 11 }}>
        {t.promptFiles}: <span style={{ fontFamily: mono }}>{files.length ? files.join(', ') : '—'}</span>
      </div>
    </nav>
  )
}
