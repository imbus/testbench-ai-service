import { useState } from 'react'
import { Button } from 'primereact/button'
import { Message } from 'primereact/message'
import { ProgressBar } from 'primereact/progressbar'
import { useTranslation } from 'react-i18next'
import { useUploadPackage } from '../../api/packages'
import type { PackageVersion } from '../../api/types'
import { Modal } from '../../components/Modal'
import { PackageError, ReportView } from './parts'

/**
 * Pick a wheel, upload it, read its check report. The uploaded version is not
 * used yet: "Register agents" hands it to the register dialog.
 */
export function UploadDialog({
  onClose,
  onRegister,
}: {
  onClose: () => void
  onRegister: (version: PackageVersion) => void
}) {
  const { t } = useTranslation()
  const upload = useUploadPackage()
  const [file, setFile] = useState<File | null>(null)
  const uploaded = upload.data
  const registrable = uploaded && Object.values(uploaded.report.agents).some((agent) => agent.ok)

  return (
    <Modal label={t('packagesUploadTitle')} width={720} maxHeight="85vh">
      <h3 style={{ margin: 0 }}>{t('packagesUploadTitle')}</h3>

      {!uploaded && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <label htmlFor="package-file" style={{ fontSize: 13 }}>
            {t('packagesWheelFile')}
          </label>
          <input
            id="package-file"
            type="file"
            accept=".whl"
            disabled={upload.isPending}
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null)
              upload.reset()
            }}
          />
        </div>
      )}

      {upload.isPending && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <div style={{ fontSize: 13 }}>{t('packagesUploading')}</div>
          <ProgressBar mode="indeterminate" style={{ height: 4 }} />
        </div>
      )}

      {upload.isError && <PackageError error={upload.error} upload />}

      {uploaded && (
        <>
          <Message
            severity={uploaded.report.ok ? 'success' : 'warn'}
            style={{ justifyContent: 'flex-start' }}
            text={t('packagesUploaded', { name: uploaded.name, version: uploaded.version })}
          />
          <ReportView report={uploaded.report} />
        </>
      )}

      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <Button type="button" outlined label={t('close')} onClick={onClose} />
        {uploaded ? (
          registrable && (
            <Button
              type="button"
              label={t('packagesRegister')}
              onClick={() => onRegister(uploaded)}
            />
          )
        ) : (
          <Button
            type="button"
            label={t('packagesUpload')}
            disabled={!file || upload.isPending}
            onClick={() => file && upload.mutate(file)}
          />
        )}
      </div>
    </Modal>
  )
}
