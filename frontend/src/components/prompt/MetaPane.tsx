import { Dropdown } from 'primereact/dropdown'
import { InputText } from 'primereact/inputtext'
import { InputTextarea } from 'primereact/inputtextarea'
import { Message } from 'primereact/message'
import type { PromptDocument } from '../../api/types'
import { useTranslation } from 'react-i18next'

/**
 * The workbench's centre pane for the prompt.yaml header fields (design
 * §5.6, Task 6). Copied verbatim from `PromptEditor.tsx`'s `Header` helper
 * and its default-variant `<select>` block -- same ids, same
 * `aria-invalid`/`aria-describedby` logic -- so this pane's own tests pin
 * exactly the behaviour the old screen already had. `PromptEditor.tsx` keeps
 * its own copies until Task 8 rewires it to render this instead.
 */
function Header({
  label,
  id,
  value,
  readOnly,
  multiline,
  onChange,
}: {
  label: string
  id: string
  value: string
  readOnly?: boolean
  multiline?: boolean
  onChange: (value: string) => void
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <label htmlFor={id} style={{ fontSize: 12 }}>
        {label}
      </label>
      {multiline ? (
        <InputTextarea
          id={id}
          readOnly={readOnly}
          value={value}
          rows={3}
          onChange={(event) => onChange(event.target.value)}
        />
      ) : (
        <InputText
          id={id}
          type="text"
          readOnly={readOnly}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
    </div>
  )
}

export function MetaPane({
  draft,
  readOnly,
  defaultVariantIssue,
  onHeader,
}: {
  draft: PromptDocument
  readOnly: boolean
  defaultVariantIssue: string | null
  onHeader: (
    field: 'name' | 'summary' | 'description' | 'default_model' | 'default_variant',
    value: string,
  ) => void
}) {
  const { t } = useTranslation()

  return (
    <div
      data-testid="prompt-header"
      style={{
        padding: '20px 24px',
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
        gap: '16px 24px',
        alignContent: 'start',
        overflow: 'auto',
      }}
    >
      <Header
        label={t('promptName')}
        id="prompt-name"
        value={draft.name}
        readOnly={readOnly}
        onChange={(value) => onHeader('name', value)}
      />
      <Header
        label={t('promptSummary')}
        id="prompt-summary"
        value={draft.summary ?? ''}
        readOnly={readOnly}
        onChange={(value) => onHeader('summary', value)}
      />
      {/* Prototype reference: description spans the full row, between the
          name/summary pair above and default_model/default_variant below. */}
      <div style={{ gridColumn: '1 / -1' }}>
        <Header
          label={t('promptDescription')}
          id="prompt-description"
          value={draft.description ?? ''}
          readOnly={readOnly}
          multiline
          onChange={(value) => onHeader('description', value)}
        />
      </div>
      <Header
        label={t('defaultModel')}
        id="prompt-default-model"
        value={draft.default_model}
        readOnly={readOnly}
        onChange={(value) => onHeader('default_model', value)}
      />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <label htmlFor="prompt-default-variant" style={{ fontSize: 12 }}>
          {t('defaultVariant')}
        </label>
        <Dropdown
          inputId="prompt-default-variant"
          disabled={readOnly}
          invalid={!!defaultVariantIssue}
          aria-invalid={defaultVariantIssue ? true : undefined}
          aria-describedby={defaultVariantIssue ? 'default-variant-issue' : undefined}
          value={draft.default_variant}
          options={draft.variants.map((v) => ({ label: v.name, value: v.name }))}
          onChange={(event) => onHeader('default_variant', event.value as string)}
          style={{ maxWidth: 260 }}
        />
        {defaultVariantIssue && (
          <Message
            id="default-variant-issue"
            severity="error"
            text={defaultVariantIssue}
            style={{ fontSize: 11, alignSelf: 'flex-start' }}
          />
        )}
      </div>
    </div>
  )
}
