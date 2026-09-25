import type { PromptDocument } from '../../api/types'
import { useTranslations, type Lang } from '../../i18n'

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
        <textarea
          className="input"
          id={id}
          readOnly={readOnly}
          value={value}
          rows={3}
          onChange={(event) => onChange(event.target.value)}
        />
      ) : (
        <input
          className="input"
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
  lang = 'de',
  onHeader,
}: {
  draft: PromptDocument
  readOnly: boolean
  defaultVariantIssue: string | null
  lang?: Lang
  onHeader: (
    field: 'name' | 'summary' | 'description' | 'default_model' | 'default_variant',
    value: string,
  ) => void
}) {
  const t = useTranslations(lang)

  return (
    <div
      data-testid="prompt-header"
      style={{
        padding: '20px 24px',
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
        gap: '16px 24px',
        maxWidth: 900,
        alignContent: 'start',
        overflow: 'auto',
      }}
    >
      <Header
        label={t.promptName}
        id="prompt-name"
        value={draft.name}
        readOnly={readOnly}
        onChange={(value) => onHeader('name', value)}
      />
      <Header
        label={t.promptSummary}
        id="prompt-summary"
        value={draft.summary ?? ''}
        readOnly={readOnly}
        onChange={(value) => onHeader('summary', value)}
      />
      {/* Prototype reference: description spans the full row, between the
          name/summary pair above and default_model/default_variant below. */}
      <div style={{ gridColumn: '1 / -1' }}>
        <Header
          label={t.promptDescription}
          id="prompt-description"
          value={draft.description ?? ''}
          readOnly={readOnly}
          multiline
          onChange={(value) => onHeader('description', value)}
        />
      </div>
      <Header
        label={t.defaultModel}
        id="prompt-default-model"
        value={draft.default_model}
        readOnly={readOnly}
        onChange={(value) => onHeader('default_model', value)}
      />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <label htmlFor="prompt-default-variant" style={{ fontSize: 12 }}>
          {t.defaultVariant}
        </label>
        <select
          className="input"
          id="prompt-default-variant"
          disabled={readOnly}
          aria-invalid={defaultVariantIssue ? true : undefined}
          aria-describedby={defaultVariantIssue ? 'default-variant-issue' : undefined}
          value={draft.default_variant}
          onChange={(event) => onHeader('default_variant', event.target.value)}
          style={{ maxWidth: 260 }}
        >
          {draft.variants.map((v) => (
            <option key={v.name} value={v.name}>
              {v.name}
            </option>
          ))}
        </select>
        {defaultVariantIssue && (
          <span id="default-variant-issue" role="alert" style={{ fontSize: 11, color: '#a33a2b' }}>
            {defaultVariantIssue}
          </span>
        )}
      </div>
    </div>
  )
}
