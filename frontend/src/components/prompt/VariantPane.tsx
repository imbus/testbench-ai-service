import type { PromptVarDecl, PromptVariantDoc } from '../../api/types'
import { VarDeclTable } from '../../components/VarDeclTable'
import { useTranslations, type Lang } from '../../i18n'

/**
 * The workbench's centre pane for a variant's own settings (design §5.6,
 * Task 6): its name, model, and `VarDeclTable`. The name/model/Remove block
 * is copied verbatim from `PromptEditor.tsx`'s `isAdmin && selectedVariantObj`
 * block -- same ids, same `data-testid="variant-actions"` -- so this pane's
 * own tests pin exactly the behaviour the old screen already had.
 * `PromptEditor.tsx` keeps its own copy until Task 8 rewires it to render
 * this instead.
 */
export function VariantPane({
  variant,
  readOnly,
  canRemove,
  lang = 'de',
  onRename,
  onModel,
  onRemove,
  onAddVar,
  onEditVar,
  onRemoveVar,
}: {
  variant: PromptVariantDoc
  readOnly: boolean
  /** False on a document's only variant: the reducer keeps the last one
   * (a prompt needs a variant), so Remove there could only be a no-op. */
  canRemove: boolean
  lang?: Lang
  onRename: (to: string) => void
  onModel: (model: string | null) => void
  onRemove: () => void
  onAddVar: (key: string) => void
  onEditVar: (key: string, decl: PromptVarDecl) => void
  onRemoveVar: (key: string) => void
}) {
  const t = useTranslations(lang)

  return (
    <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 16, overflow: 'auto' }}>
      <h4 style={{ margin: 0 }}>
        {t.variantSettings} · {variant.name}
      </h4>

      {!readOnly && (
        <div
          data-testid="variant-actions"
          style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <label htmlFor="variant-name" style={{ fontSize: 12 }}>
              {t.variantName}
            </label>
            <input
              className="input"
              id="variant-name"
              value={variant.name}
              onChange={(event) => onRename(event.target.value)}
            />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <label htmlFor="variant-model" style={{ fontSize: 12 }}>
              {t.variantModel}
            </label>
            <input
              className="input"
              id="variant-model"
              value={variant.model ?? ''}
              onChange={(event) => onModel(event.target.value || null)}
            />
          </div>
          {canRemove && (
            <button type="button" className="btn btn-ghost" onClick={onRemove}>
              {t.remove}
            </button>
          )}
        </div>
      )}

      <VarDeclTable
        vars={variant.vars}
        readOnly={readOnly}
        lang={lang}
        onAdd={onAddVar}
        onEdit={onEditVar}
        onRemove={onRemoveVar}
      />
    </div>
  )
}
