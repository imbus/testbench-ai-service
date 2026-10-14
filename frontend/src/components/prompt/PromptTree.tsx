import { Button } from 'primereact/button'
import { Tag } from 'primereact/tag'
import type { PromptVariantDoc } from '../../api/types'
import { useTranslation } from 'react-i18next'
import { messageTabOf, type TabId } from '../../state/editorTabs'
import { messageLabel } from './selection'

const mono = 'ui-monospace, Menlo, monospace'
const rowButton = { border: 0, background: 'transparent', color: 'inherit', font: 'inherit', cursor: 'pointer', textAlign: 'left' as const }

/**
 * The Split layout's left column: prompt.yaml, then variants with the selected one expanded.
 *
 * The rows stay plain buttons rather than a PrimeReact `Tree`: a variant row
 * carries its own settings button beside the expander, the open row is
 * marked with `aria-current` (not tree selection), and a `Tree` would also
 * fold the meta row and the file list into nodes that are not part of it.
 *
 * A single click opens a row in the preview tab, a double click keeps it
 * open -- VS Code's explorer. The marked row is the active tab's.
 */
export function PromptTree({ variants, selectedVariant, activeTab, flagged, invalidVariants = [], readOnly, onOpenMeta, onPickVariant, onOpenVariantSettings, onPickMessage, onAddVariant, onAddMessage, onOpenRender }: {
  variants: PromptVariantDoc[]
  selectedVariant: string
  activeTab: TabId | null
  flagged: number[]
  /** Variants a save 422 named (e.g. "needs at least one message") -- marked on their row. */
  invalidVariants?: string[]
  readOnly: boolean
  onOpenMeta: (pin: boolean) => void
  onPickVariant: (name: string) => void
  onOpenVariantSettings: (name: string, pin: boolean) => void
  onPickMessage: (index: number, pin: boolean) => void
  onAddVariant: () => void
  onAddMessage: () => void
  /** Opens the variant's render preview tab. No handler, no row: the render
   * endpoint is admin-gated, and the preview renders nothing without it. */
  onOpenRender?: (pin: boolean) => void
}) {
  const { t } = useTranslation()
  const files = [...new Set(variants.flatMap((v) => v.messages.filter((m) => m.source === 'file' && m.file).map((m) => m.file as string)))]

  return (
    // No aria-label: `t('variants')` already names the toolbar's variant select,
    // and a second element with that label makes getByLabelText ambiguous.
    <nav
      data-testid="prompt-tree"
      style={{ width: 250, flex: 'none', borderRight: '1px solid var(--color-divider)', display: 'flex', flexDirection: 'column', overflow: 'auto', fontSize: 13 }}
    >
      <button
        type="button"
        aria-current={activeTab === 'meta' || undefined}
        onClick={() => onOpenMeta(false)}
        onDoubleClick={() => onOpenMeta(true)}
        style={{ ...rowButton, padding: '8px 14px', display: 'flex', flexDirection: 'column', background: activeTab === 'meta' ? 'var(--color-surface)' : 'transparent' }}
      >
        <span style={{ fontFamily: mono, fontSize: 12 }}>prompt.yaml</span>
        <span className="text-muted" style={{ fontSize: 11 }}>{t('promptMetaHint')}</span>
      </button>

      <div className="text-muted" style={{ display: 'flex', alignItems: 'center', padding: '10px 14px 4px', fontSize: 11, letterSpacing: '.08em', textTransform: 'uppercase' }}>
        <span>{t('variants')}</span>
        <div style={{ flex: 1 }} />
        {!readOnly && (
          <Button type="button" text label="+" aria-label={t('newVariantDefault')} title={t('newVariantDefault')} style={{ padding: '0 4px', fontSize: 12 }} onClick={onAddVariant} />
        )}
      </div>

      {variants.map((variant) => {
        const open = variant.name === selectedVariant
        const invalid = invalidVariants.includes(variant.name)
        return (
          <div key={variant.name} style={{ display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', alignItems: 'center', padding: '6px 14px', gap: 6, background: open && activeTab === 'variant' ? 'var(--color-surface)' : 'transparent' }}>
              <button type="button" aria-expanded={open} aria-invalid={invalid || undefined} onClick={() => onPickVariant(variant.name)} style={{ ...rowButton, fontWeight: 500, padding: 0, flex: 1, display: 'flex', alignItems: 'center', gap: 6, color: invalid ? '#a33a2b' : 'inherit' }}>
                <span aria-hidden style={{ fontSize: 10 }}>{open ? '▾' : '▸'}</span>
                {variant.name}
              </button>
              {variant.model && <span className="text-muted" style={{ fontFamily: mono, fontSize: 11 }}>{variant.model}</span>}
              <Button type="button" text label="⚙" aria-label={`${t('variantSettings')}: ${variant.name}`} title={t('variantSettings')} onClick={() => onOpenVariantSettings(variant.name, false)} onDoubleClick={() => onOpenVariantSettings(variant.name, true)} style={{ padding: '0 4px', fontSize: 12 }} />
            </div>
            {open && variant.messages.map((message, index) => {
              const current = activeTab === messageTabOf(message, index)
              return (
                <button
                  key={index}
                  type="button"
                  aria-current={current || undefined}
                  aria-invalid={flagged.includes(index) || undefined}
                  onClick={() => onPickMessage(index, false)}
                  onDoubleClick={() => onPickMessage(index, true)}
                  style={{ ...rowButton, fontSize: 12, padding: '5px 14px 5px 34px', display: 'flex', gap: 6, alignItems: 'center', background: current ? 'var(--color-surface)' : 'transparent' }}
                >
                  <Tag severity="secondary" value={message.role} style={{ padding: '0 5px', fontSize: 10 }} />
                  <span style={{ fontFamily: mono, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{messageLabel(message, t('emptyMessage'))}</span>
                  {flagged.includes(index) && <span aria-hidden style={{ color: '#c0392b' }}>●</span>}
                </button>
              )
            })}
            {open && !readOnly && (
              <Button type="button" text className="text-muted" label={t('addMessageShort')} onClick={onAddMessage} style={{ fontSize: 12, padding: '4px 14px 6px 34px', justifyContent: 'flex-start' }} />
            )}
            {/* Not gated on readOnly: rendering is not an edit. */}
            {open && onOpenRender && (
              <button
                type="button"
                aria-current={activeTab === 'render' || undefined}
                onClick={() => onOpenRender(false)}
                onDoubleClick={() => onOpenRender(true)}
                style={{ ...rowButton, fontSize: 12, padding: '5px 14px 5px 34px', display: 'flex', gap: 6, alignItems: 'center', background: activeTab === 'render' ? 'var(--color-surface)' : 'transparent' }}
              >
                <span aria-hidden className="text-muted" style={{ fontSize: 10 }}>▶</span>
                {t('render')}
              </button>
            )}
          </div>
        )
      })}

      <div style={{ flex: 1 }} />
      <div data-testid="tree-files" className="text-muted" style={{ padding: '10px 14px', borderTop: '1px solid var(--color-divider)', fontSize: 11 }}>
        {t('promptFiles')}: <span style={{ fontFamily: mono }}>{files.length ? files.join(', ') : '—'}</span>
      </div>
    </nav>
  )
}
