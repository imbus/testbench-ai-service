import { useState } from 'react'
import { Button } from 'primereact/button'
import { Checkbox } from 'primereact/checkbox'
import { InputTextarea } from 'primereact/inputtextarea'
import { Message } from 'primereact/message'
import { RadioButton } from 'primereact/radiobutton'
import { useTranslation } from 'react-i18next'
import { modelNameProblem, useClearLlmClient, useUseLlmClient } from '../../api/packages'
import type { PackageVersion } from '../../api/types'
import { Modal } from '../../components/Modal'
import { PackageError } from './parts'

/** The names typed into the model field: one per line, commas work too. */
function parseModels(text: string): string[] {
  const names = text
    .split(/[\n,]/)
    .map((name) => name.trim())
    .filter(Boolean)
  return [...new Set(names)]
}

/**
 * Put an LLM client of a package version to use as the service's custom
 * provider: which client (when the package has several), and the model names
 * it serves. The names matter: a custom provider is only ever called for the
 * models listed for it.
 */
export function ProviderDialog({
  name,
  version,
  onClose,
}: {
  name: string
  version: PackageVersion
  onClose: () => void
}) {
  const { t } = useTranslation()
  const use = useUseLlmClient()
  const clients = Object.entries(version.report.llm_clients ?? {}).filter(([, client]) => client.ok)
  const [entryPoint, setEntryPoint] = useState(clients[0]?.[0] ?? '')
  const [text, setText] = useState('')
  const [asDefault, setAsDefault] = useState(true)

  const models = parseModels(text)
  const problems = models
    .map((model) => ({ model, problem: modelNameProblem(model) }))
    .filter((entry) => entry.problem !== null)
  const title = t('packagesProviderTitle', { name, version: version.version })
  const disabled = !entryPoint || models.length === 0 || problems.length > 0 || use.isPending

  const submit = () =>
    use.mutate(
      {
        name,
        version: version.version,
        entry_point: entryPoint,
        models,
        default_model: asDefault ? models[0] : null,
      },
      { onSuccess: onClose },
    )

  return (
    <Modal label={title}>
      <h3 style={{ margin: 0 }}>{title}</h3>
      <div style={{ fontSize: 13 }}>{t('packagesProviderHint')}</div>

      {clients.length > 1 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>{t('packagesLlmClient')}</div>
          {clients.map(([entry, client]) => (
            <label
              key={entry}
              htmlFor={`provider-client-${entry}`}
              style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}
            >
              <RadioButton
                inputId={`provider-client-${entry}`}
                name="provider-client"
                value={entry}
                checked={entryPoint === entry}
                onChange={() => setEntryPoint(entry)}
              />
              <code>{entry}</code>
              <span className="text-muted" style={{ fontSize: 11, fontFamily: 'var(--font-code)' }}>
                {client.class_path}
              </span>
            </label>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <label htmlFor="provider-models" style={{ fontSize: 13, fontWeight: 600 }}>
          {t('packagesProviderModels')}
        </label>
        <InputTextarea
          id="provider-models"
          rows={4}
          value={text}
          onChange={(event) => setText(event.target.value)}
          style={{ fontFamily: 'var(--font-code)', fontSize: 13 }}
        />
        <div className="text-muted" style={{ fontSize: 12 }}>
          {t('packagesProviderModelsHint')}
        </div>
      </div>

      {problems.length > 0 && (
        <Message
          severity="error"
          role="alert"
          style={{ justifyContent: 'flex-start' }}
          content={
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
              {problems.map(({ model, problem }) => (
                <li key={model}>
                  {t(
                    problem === 'reserved'
                      ? 'packagesProviderModelReserved'
                      : 'packagesProviderModelInvalid',
                    { model },
                  )}
                </li>
              ))}
            </ul>
          }
        />
      )}

      <label
        htmlFor="provider-default"
        style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}
      >
        <Checkbox
          inputId="provider-default"
          checked={asDefault}
          onChange={(event) => setAsDefault(!!event.checked)}
        />
        {models.length > 0
          ? t('packagesProviderDefault', { model: models[0] })
          : t('packagesProviderDefaultNone')}
      </label>

      {use.isError && <PackageError error={use.error} />}
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <Button type="button" outlined label={t('cancel')} onClick={onClose} />
        <Button
          type="button"
          label={t('packagesUseProvider')}
          disabled={disabled}
          onClick={submit}
        />
      </div>
    </Modal>
  )
}

/** Confirm taking a package's LLM client out of use. */
export function StopProviderDialog({ name, onClose }: { name: string; onClose: () => void }) {
  const { t } = useTranslation()
  const clear = useClearLlmClient()
  const title = t('packagesStopProviderTitle', { name })
  return (
    <Modal label={title}>
      <h3 style={{ margin: 0 }}>{title}</h3>
      <div style={{ fontSize: 13 }}>{t('packagesStopProviderHint')}</div>
      {clear.isError && <PackageError error={clear.error} />}
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <Button type="button" outlined label={t('cancel')} onClick={onClose} />
        <Button
          type="button"
          severity="danger"
          label={t('packagesStopProvider')}
          disabled={clear.isPending}
          onClick={() => clear.mutate(name, { onSuccess: onClose })}
        />
      </div>
    </Modal>
  )
}
