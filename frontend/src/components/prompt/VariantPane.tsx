import { useEffect, useState } from 'react'
import { Button } from 'primereact/button'
import { InputText } from 'primereact/inputtext'
import { Message } from 'primereact/message'
import type { PromptVarDecl, PromptVariantDoc } from '../../api/types'
import { VarDeclTable } from '../../components/VarDeclTable'
import { useTranslation } from 'react-i18next'

/**
 * The workbench's centre pane for a variant's own settings (design §5.6,
 * Task 6): its name, model, and `VarDeclTable`. The name/model/Remove block
 * is copied verbatim from `PromptEditor.tsx`'s `isAdmin && selectedVariantObj`
 * block -- same ids, same `data-testid="variant-actions"` -- so this pane's
 * own tests pin exactly the behaviour the old screen already had.
 */
export function VariantPane({
  variant,
  otherNames,
  readOnly,
  canRemove,
  onRename,
  onModel,
  onRemove,
  onAddVar,
  onEditVar,
  onRemoveVar,
}: {
  variant: PromptVariantDoc
  /** The document's other variant names. The reducer finds a variant by
   * name, so a rename may never pass through one of these. */
  otherNames: string[]
  readOnly: boolean
  /** False on a document's only variant: the reducer keeps the last one
   * (a prompt needs a variant), so Remove there could only be a no-op. */
  canRemove: boolean
  onRename: (to: string) => void
  onModel: (model: string | null) => void
  onRemove: () => void
  onAddVar: (key: string) => void
  onEditVar: (key: string, decl: PromptVarDecl) => void
  onRemoveVar: (key: string) => void
}) {
  const { t } = useTranslation()
  // The field may hold a name the draft must not take (empty, or another
  // variant's). Only a valid one is sent; leaving the field puts the
  // variant's real name back.
  const [name, setName] = useState(variant.name)
  useEffect(() => setName(variant.name), [variant.name])
  const nameError = !name.trim()
    ? t('variantNameEmpty')
    : otherNames.includes(name)
      ? t('variantNameTaken')
      : null

  return (
    <div
      style={{
        padding: '20px 24px',
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
        overflow: 'auto',
      }}
    >
      <h4 style={{ margin: 0 }}>
        {t('variantSettings')} · {variant.name}
      </h4>

      {!readOnly && (
        <div
          data-testid="variant-actions"
          style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <label htmlFor="variant-name" style={{ fontSize: 12 }}>
              {t('variantName')}
            </label>
            <InputText
              id="variant-name"
              value={name}
              invalid={nameError !== null}
              aria-invalid={nameError ? true : undefined}
              aria-describedby={nameError ? 'variant-name-error' : undefined}
              onChange={(event) => {
                const to = event.target.value
                setName(to)
                if (to.trim() && !otherNames.includes(to)) onRename(to)
              }}
              onBlur={() => setName(variant.name)}
            />
            {nameError && (
              <Message
                id="variant-name-error"
                severity="error"
                text={nameError}
                style={{ fontSize: 11, alignSelf: 'flex-start' }}
              />
            )}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <label htmlFor="variant-model" style={{ fontSize: 12 }}>
              {t('variantModel')}
            </label>
            <InputText
              id="variant-model"
              value={variant.model ?? ''}
              onChange={(event) => onModel(event.target.value || null)}
            />
          </div>
          {canRemove && <Button type="button" text label={t('remove')} onClick={onRemove} />}
        </div>
      )}

      <VarDeclTable
        vars={variant.vars}
        readOnly={readOnly}
        onAdd={onAddVar}
        onEdit={onEditVar}
        onRemove={onRemoveVar}
      />

      {variant.steps && Object.keys(variant.steps).length > 0 && (
        <section
          data-testid="variant-steps"
          style={{ display: 'flex', flexDirection: 'column', gap: 4 }}
        >
          <h5 style={{ margin: 0 }}>{t('variantSteps')}</h5>
          <div className="text-muted" style={{ fontSize: 12 }}>
            {t('variantStepsFixed')}
          </div>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {Object.entries(variant.steps).map(([step, messages]) => (
              <li key={step}>
                <strong>{step}</strong>
                {': '}
                {messages
                  .map((message) => `${message.role} · ${message.file ?? t('inlineMessage')}`)
                  .join(', ')}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
