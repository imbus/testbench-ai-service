import type { ReactNode } from 'react'
import { Button } from 'primereact/button'
import { Message } from 'primereact/message'
import type { PromptPlanResponse } from '../api/types'
import { useTranslation } from 'react-i18next'
import { Modal } from './Modal'

function FileGroup({
  heading,
  files,
  testid,
}: {
  heading: string
  files: string[]
  testid: string
}) {
  if (files.length === 0) return null
  return (
    <div data-testid={testid}>
      <div style={{ fontSize: 13 }}>{heading}</div>
      <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, fontFamily: 'ui-monospace, Menlo, monospace' }}>
        {files.map((file) => (
          <li key={file} data-testid="confirm-file">
            {file}
          </li>
        ))}
      </ul>
    </div>
  )
}

/**
 * The save-confirm dialog, rendering the SERVER's plan rather than guessing
 * from the shape of the draft's own diff (spec §5.7, §3.9, D8).
 *
 * Only the server can name a deletion -- orphan detection needs a scan of the
 * whole prompt tree, which the browser cannot do. `plan === null` covers both
 * "the plan request is still in flight" and "it failed": either way there is
 * nothing yet to confirm, so Confirm stays disabled regardless of `pending`.
 *
 * `error` renders INSIDE this dialog, not only as a field marker on the form
 * sitting behind it -- that form is behind this dialog's `position: fixed`
 * overlay, so a marker alone is invisible to an operator looking at the
 * dialog. That silent-failure shape is exactly the defect phase 4a parked as
 * M7 for a save refusal; this closes it for a plan refusal too.
 *
 * `children` is where the caller projects content this component has no
 * opinion about -- `PromptEditor` uses it for the client-computed orphan
 * warnings, which are unrelated to the server's plan and keep their existing
 * behaviour unchanged.
 */
export function SavePromptDialog({
  plan,
  error,
  pending,
  onCancel,
  onConfirm,
  children,
}: {
  plan: PromptPlanResponse | null
  error: string | null
  pending: boolean
  onCancel: () => void
  onConfirm: () => void
  children?: ReactNode
}) {
  const { t } = useTranslation()

  return (
    <Modal label={t('confirmSaveTitle')}>
      <h3 style={{ margin: 0 }}>{t('confirmSaveTitle')}</h3>

      {plan && (
        <>
          <FileGroup heading={t('confirmSaveCreated')} files={plan.created} testid="confirm-created" />
          <FileGroup heading={t('confirmSaveUpdated')} files={plan.updated} testid="confirm-updated" />
          <FileGroup heading={t('confirmSaveDeleted')} files={plan.deleted} testid="confirm-deleted" />
          {plan.deletions_skipped && (
            <Message
              severity="error"
              style={{ justifyContent: 'flex-start', fontSize: 12 }}
              text={
                <>
                  {t('confirmSaveDeletionsSkipped')} {plan.deletions_skipped}
                </>
              }
            />
          )}
        </>
      )}

      {children}

      {error && (
        <Message
          severity="error"
          style={{ justifyContent: 'flex-start', fontSize: 12 }}
          text={error}
        />
      )}

      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <Button type="button" outlined label={t('cancel')} onClick={onCancel} />
        <Button
          type="button"
          label={pending ? (plan === null ? t('planning') : t('saving')) : t('confirm')}
          onClick={onConfirm}
          disabled={pending || plan === null}
        />
      </div>
    </Modal>
  )
}
