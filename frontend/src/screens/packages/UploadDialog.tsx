import { useRef, useState, type DragEvent, type ReactNode } from 'react'
import { Button } from 'primereact/button'
import { Column } from 'primereact/column'
import { DataTable } from 'primereact/datatable'
import { Message } from 'primereact/message'
import { ProgressBar } from 'primereact/progressbar'
import { Tag } from 'primereact/tag'
import { useTranslation } from 'react-i18next'
import { useUploadPackage } from '../../api/packages'
import type {
  PackageAgentReport,
  PackageReport,
  PackagesResponse,
  PackageVersion,
} from '../../api/types'
import { Modal } from '../../components/Modal'
import { Icon, ICONS, PackageError, type PackageKind } from './parts'
import { RegisterForm } from './RegisterDialog'

const MONO = { fontFamily: 'var(--font-code)' } as const
const MUTED = { color: 'var(--color-muted)' } as const

/** A visually hidden but focusable and label-addressable file input. */
const HIDDEN_INPUT = {
  position: 'absolute',
  width: 1,
  height: 1,
  opacity: 0,
  overflow: 'hidden',
} as const

const { upload: UPLOAD, file: FILE, close: CLOSE } = ICONS

function formatSize(bytes: number): string {
  return bytes < 1024 * 1024
    ? `${(bytes / 1024).toFixed(1)} KB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/**
 * The upload wizard: pick a wheel, upload it and read its check report, then
 * register its agents -- all in this one dialog. Opened for the LLM provider
 * (`kind`), the last step is using the wheel's LLM client instead, in the
 * provider dialog (`onUseProvider`).
 *
 * Registering is refused while another version of the package is active; for
 * such a version the report step hands over to the activate dialog instead
 * (`onActivate`).
 */
export function UploadDialog({
  packages,
  kind = 'agents',
  onClose,
  onActivate,
  onUseProvider,
}: {
  /** The package list, for what is registered already and the folder setting. */
  packages: PackagesResponse
  /** What the wheel is uploaded for; a wheel's other side is not offered. */
  kind?: PackageKind
  onClose: () => void
  onActivate: (version: PackageVersion) => void
  /** Continue in the dialog that puts the version's LLM client to use. */
  onUseProvider?: (version: PackageVersion) => void
}) {
  const { t } = useTranslation()
  const upload = useUploadPackage()
  const [file, setFile] = useState<File | null>(null)
  const [registering, setRegistering] = useState(false)
  const uploaded = upload.data
  const forProvider = kind === 'provider'
  // A finding about the package as a whole rules out every use of it; one
  // about a single entry point only that entry point.
  const usable = !!uploaded && (uploaded.report.errors ?? []).length === 0
  const registrable =
    !forProvider && usable && Object.values(uploaded.report.agents).some((agent) => agent.ok)
  const providable =
    forProvider &&
    !!onUseProvider &&
    usable &&
    Object.values(uploaded.report.llm_clients ?? {}).some((client) => client.ok)
  // The versions the console knew when the upload started: a wheel that comes
  // back as one of them was stored before, and nothing was added now.
  const knownBefore = useRef<Set<string>>(new Set())
  const startUpload = (wheel: File) => {
    knownBefore.current = new Set(
      (packages.packages ?? []).flatMap((entry) =>
        entry.versions.map((version) => `${entry.name}@${version.version}`),
      ),
    )
    upload.mutate(wheel)
  }
  const uploadedText = !uploaded
    ? ''
    : !usable
      ? t('packagesUploadedFailed', { name: uploaded.name, version: uploaded.version })
      : knownBefore.current.has(`${uploaded.name}@${uploaded.version}`)
        ? t('packagesUploadedAgain', { name: uploaded.name, version: uploaded.version })
        : forProvider
          ? t('packagesUploadedProvider', { name: uploaded.name, version: uploaded.version })
          : t('packagesUploaded', { name: uploaded.name, version: uploaded.version })
  // Checking a wheel cannot be called back once it is sent: the server finishes
  // it and stores the wheel if it passes. The dialog stays until the answer is
  // in, so the operator sees what happened instead of finding the package later.
  const close = upload.isPending ? undefined : onClose
  const known = uploaded && (packages.packages ?? []).find((entry) => entry.name === uploaded.name)
  const otherActive =
    !!uploaded &&
    !!known?.versions.some((entry) => entry.active && entry.version !== uploaded.version)

  const choose = (next: File | null) => {
    setFile(next)
    upload.reset()
  }

  const step = !uploaded ? 0 : registering ? 2 : 1
  const steps = [
    t('packagesStepWheel'),
    t('packagesStepReport'),
    forProvider ? t('packagesStepProvider') : t('packagesStepRegister'),
  ]
  const title = forProvider ? t('providerPackagesUploadTitle') : t('packagesUploadTitle')
  // A wheel with nothing for this screen is stored all the same; say where it went.
  const elsewhere =
    !uploaded || otherActive
      ? null
      : forProvider
        ? Object.keys(uploaded.report.llm_clients ?? {}).length === 0 &&
          Object.keys(uploaded.report.agents).length > 0
          ? t('packagesOnlyAgents')
          : null
        : Object.keys(uploaded.report.agents).length === 0 &&
            Object.keys(uploaded.report.llm_clients ?? {}).length > 0
          ? t('packagesOnlyLlmClient')
          : null
  const position = t('packagesStepOf', { step: step + 1, total: steps.length })

  return (
    <Modal label={title} width={780} maxHeight="85vh" onClose={close}>
      <div style={HEADER}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <h3 style={{ margin: 0 }}>{title}</h3>
            <div className="text-muted" style={{ fontSize: 12 }}>
              {uploaded
                ? `${uploaded.name} ${uploaded.version}`
                : forProvider
                  ? t('providerPackagesSub')
                  : t('packagesSub')}
            </div>
          </div>
          <Button
            type="button"
            text
            rounded
            severity="secondary"
            aria-label={t('close')}
            icon={<Icon d={CLOSE} />}
            disabled={upload.isPending}
            onClick={onClose}
          />
        </div>
        <WizardSteps steps={steps} active={step} />
      </div>

      {step === 2 && uploaded ? (
        <RegisterForm
          name={uploaded.name}
          version={uploaded}
          registered={known?.registered ?? {}}
          defaultDirs={packages.default_dirs}
          onDone={onClose}
          body={(content) => <div style={BODY}>{content}</div>}
          footer={({ submit, disabled }) => (
            <WizardFooter position={position}>
              <Button
                type="button"
                outlined
                label={t('packagesBack')}
                onClick={() => setRegistering(false)}
              />
              <Button
                type="button"
                label={t('packagesRegister')}
                onClick={submit}
                disabled={disabled}
              />
            </WizardFooter>
          )}
        />
      ) : (
        <>
          <div style={BODY}>
            {upload.isError && <PackageError error={upload.error} upload />}

            {!uploaded && !upload.isPending && (
              <Dropzone file={file} onChoose={choose} compact={upload.isError} />
            )}

            {upload.isPending && file && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <FileChip file={file} />
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                    <span>{t('packagesUploading')}</span>
                    <span style={MUTED}>{t('packagesCheckHint')}</span>
                  </div>
                  <ProgressBar mode="indeterminate" style={{ height: 6 }} />
                  <span style={MUTED}>{t('packagesUploadNoCancel')}</span>
                </div>
              </div>
            )}

            {uploaded && (
              <>
                <Message
                  severity={uploaded.report.ok ? 'success' : 'warn'}
                  style={{ justifyContent: 'flex-start' }}
                  text={uploadedText}
                />
                <ReportTable report={uploaded.report} />
                {elsewhere && (
                  <Message
                    severity="info"
                    style={{ justifyContent: 'flex-start' }}
                    text={elsewhere}
                  />
                )}
                {otherActive && (
                  <Message
                    severity="info"
                    style={{ justifyContent: 'flex-start' }}
                    text={t('packagesOtherActive', { name: uploaded.name })}
                  />
                )}
              </>
            )}
          </div>

          <WizardFooter position={position}>
            <Button
              type="button"
              outlined
              label={t('close')}
              disabled={upload.isPending}
              title={upload.isPending ? t('packagesUploadNoCancel') : undefined}
              onClick={onClose}
            />
            {uploaded ? (
              otherActive ? (
                <Button
                  type="button"
                  label={t('packagesActivate')}
                  onClick={() => onActivate(uploaded)}
                />
              ) : (
                <>
                  {providable && (
                    <Button
                      type="button"
                      label={t('packagesNextProvider')}
                      onClick={() => onUseProvider?.(uploaded)}
                    />
                  )}
                  {registrable && (
                    <Button
                      type="button"
                      label={t('packagesNextRegister')}
                      onClick={() => setRegistering(true)}
                    />
                  )}
                </>
              )
            ) : (
              <Button
                type="button"
                label={forProvider ? t('providerPackagesUpload') : t('packagesUpload')}
                disabled={!file || upload.isPending}
                loading={upload.isPending}
                onClick={() => file && startUpload(file)}
              />
            )}
          </WizardFooter>
        </>
      )}
    </Modal>
  )
}

// The dialog content pads by 20px and scrolls; header and footer reach to its
// edges and stick to them while the body scrolls between. A sticky box sticks
// to the scroller's edge INSIDE its padding, so the offsets are -20px too:
// with 0 the header and footer sit 20px in from the dialog's edge.
const HEADER = {
  position: 'sticky',
  top: -20,
  zIndex: 1,
  margin: '-20px -20px 0',
  padding: '14px 20px 12px',
  background: 'var(--color-bg)',
  borderBottom: '1px solid var(--color-divider)',
  display: 'flex',
  flexDirection: 'column',
  gap: 12,
} as const

// The step's content; the dialog takes the height of what it shows.
const BODY = {
  display: 'flex',
  flexDirection: 'column',
  gap: 12,
} as const

/** The step bar: equal columns, a numbered circle each, joined by a line. */
function WizardSteps({ steps, active }: { steps: string[]; active: number }) {
  return (
    <ol
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${steps.length}, minmax(0, 1fr))`,
        margin: 0,
        padding: 0,
        listStyle: 'none',
      }}
    >
      {steps.map((label, index) => {
        const done = index < active
        const current = index === active
        const reached = done || current
        return (
          <li
            key={label}
            aria-current={current ? 'step' : undefined}
            style={{
              position: 'relative',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 6,
              minWidth: 0,
            }}
          >
            {index > 0 && (
              <span
                aria-hidden
                style={{
                  position: 'absolute',
                  top: 14,
                  right: 'calc(50% + 22px)',
                  left: 'calc(-50% + 22px)',
                  height: 2,
                  borderRadius: 1,
                  background: reached ? 'var(--color-accent)' : 'var(--color-divider)',
                }}
              />
            )}
            <span
              style={{
                width: 30,
                height: 30,
                borderRadius: '50%',
                display: 'grid',
                placeItems: 'center',
                fontSize: 13,
                fontWeight: 600,
                fontFamily: 'var(--font-heading)',
                border: `2px solid ${reached ? 'var(--color-accent)' : 'var(--color-divider)'}`,
                background: reached
                  ? 'color-mix(in srgb, var(--color-accent) 16%, transparent)'
                  : 'transparent',
                color: reached ? 'var(--color-accent-fg)' : 'var(--color-muted)',
              }}
            >
              {done ? <Icon d={ICONS.check} size={15} /> : index + 1}
            </span>
            <span
              style={{
                fontSize: 13,
                fontWeight: current ? 600 : 400,
                color: reached ? 'var(--color-text)' : 'var(--color-muted)',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                maxWidth: '100%',
              }}
            >
              {label}
            </span>
          </li>
        )
      })}
    </ol>
  )
}

/** The button bar: where in the wizard one is on the left, the actions right. */
function WizardFooter({ position, children }: { position: string; children: ReactNode }) {
  return (
    <div
      style={{
        position: 'sticky',
        bottom: -20,
        zIndex: 1,
        margin: '0 -20px -20px',
        padding: '10px 20px',
        background: 'color-mix(in srgb, var(--color-surface) 70%, var(--color-bg))',
        borderTop: '1px solid var(--color-divider)',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
      }}
    >
      <span className="text-muted" style={{ fontSize: 12, flex: 1 }}>
        {position}
      </span>
      {children}
    </div>
  )
}

/** The drop area: drag a wheel onto it, or open the file chooser. */
function Dropzone({
  file,
  onChoose,
  compact,
}: {
  file: File | null
  onChoose: (file: File | null) => void
  compact?: boolean
}) {
  const { t } = useTranslation()
  const [over, setOver] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  const drop = (event: DragEvent) => {
    event.preventDefault()
    setOver(false)
    const dropped = event.dataTransfer.files?.[0]
    if (dropped) onChoose(dropped)
  }

  return (
    <div
      data-testid="package-dropzone"
      onDragOver={(event) => {
        event.preventDefault()
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={drop}
      style={{
        position: 'relative',
        border: `2px dashed ${over ? 'var(--color-accent)' : 'var(--color-divider)'}`,
        borderRadius: 8,
        padding: compact ? '14px 16px' : '22px 16px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 8,
        textAlign: 'center',
        background: over
          ? 'color-mix(in srgb, var(--color-surface) 90%, transparent)'
          : 'color-mix(in srgb, var(--color-surface) 50%, transparent)',
      }}
    >
      <Icon d={UPLOAD} size={compact ? 22 : 32} color="var(--color-muted)" />
      <div style={{ fontSize: 14 }}>{t('packagesDrop')}</div>
      <div style={{ ...MUTED, fontSize: 12 }}>{t('packagesOr')}</div>
      <Button
        type="button"
        outlined
        size="small"
        icon={<Icon d={FILE} />}
        label={t('packagesChooseFile')}
        onClick={() => input.current?.click()}
        style={{ gap: 6 }}
      />
      <div style={{ ...MUTED, fontSize: 12 }}>{t('packagesDropHint')}</div>
      <input
        id="package-file"
        type="file"
        accept=".whl"
        aria-label={t('packagesWheelFile')}
        ref={input}
        tabIndex={-1}
        style={HIDDEN_INPUT}
        onChange={(event) => {
          onChoose(event.target.files?.[0] ?? null)
          // Cleared, so choosing the same file again still reports a change.
          event.target.value = ''
        }}
      />
      {file && <FileChip file={file} onRemove={() => onChoose(null)} />}
    </div>
  )
}

function FileChip({ file, onRemove }: { file: File; onRemove?: () => void }) {
  const { t } = useTranslation()
  return (
    <div
      style={{
        display: 'inline-flex',
        alignSelf: 'center',
        alignItems: 'center',
        gap: 8,
        padding: '6px 10px',
        borderRadius: 6,
        border: '1px solid var(--color-divider)',
        background: 'var(--color-bg)',
        fontSize: 13,
      }}
    >
      <Icon d={FILE} />
      <span style={MONO}>{file.name}</span>
      <span style={MUTED}>{formatSize(file.size)}</span>
      {onRemove && (
        <Button
          type="button"
          text
          rounded
          severity="secondary"
          aria-label={t('packagesRemoveFile')}
          icon={<Icon d={CLOSE} size={14} />}
          style={{ width: 24, height: 24, padding: 0 }}
          onClick={onRemove}
        />
      )}
    </div>
  )
}

/** What the table shows of an agent's or an LLM client's report. */
type Row = Pick<PackageAgentReport, 'class_path' | 'ok' | 'errors' | 'warnings'> & {
  entry: string
  /** Agents only. */
  default_endpoint_path: string | null
  /** An LLM client rather than an agent. */
  client: boolean
}

/** The check report as a table: one row per agent or LLM client entry point. */
function ReportTable({ report }: { report: PackageReport }) {
  const { t } = useTranslation()
  const rows: Row[] = [
    ...Object.entries(report.agents).map(([entry, agent]) => ({ ...agent, entry, client: false })),
    ...Object.entries(report.llm_clients ?? {}).map(([entry, client]) => ({
      ...client,
      // Prefixed: an agent and a client may share an entry point name.
      entry: `llm:${entry}`,
      default_endpoint_path: null,
      client: true,
    })),
  ]

  return (
    <>
      {report.errors.map((error) => (
        <Message
          key={`e-${error}`}
          severity="error"
          style={{ justifyContent: 'flex-start' }}
          text={`${t('packagesPackageFinding')}: ${error}`}
        />
      ))}
      {report.warnings.map((warning) => (
        <Message
          key={`w-${warning}`}
          severity="warn"
          style={{ justifyContent: 'flex-start' }}
          text={`${t('packagesPackageFinding')}: ${warning}`}
        />
      ))}
      {rows.length === 0 ? (
        <div className="text-muted" style={{ fontSize: 13 }}>
          {t('packagesNothingDeclared')}
        </div>
      ) : (
        <DataTable value={rows} size="small" stripedRows dataKey="entry">
          <Column
            header={t('packagesColStatus')}
            style={{ width: 100 }}
            body={(row: Row) => <StatusTag agent={row} />}
          />
          <Column
            header={t('packagesColEntryPoint')}
            body={(row: Row) => (
              <div>
                <div style={{ ...MONO, fontSize: 13 }}>
                  {row.client ? row.entry.slice('llm:'.length) : row.entry}
                  {row.client && (
                    <Tag
                      severity="info"
                      value={t('packagesLlmClient')}
                      style={{ marginLeft: 8, fontSize: 11, padding: '1px 8px' }}
                    />
                  )}
                </div>
                <div style={{ ...MUTED, ...MONO, fontSize: 11 }}>{row.class_path}</div>
              </div>
            )}
          />
          <Column
            header={t('packagesColEndpoint')}
            body={(row: Row) => (
              <span style={{ ...MONO, fontSize: 12 }}>{row.default_endpoint_path ?? '—'}</span>
            )}
          />
          <Column header={t('packagesColFindings')} body={(row: Row) => <Findings agent={row} />} />
        </DataTable>
      )}
    </>
  )
}

function StatusTag({ agent }: { agent: Row }) {
  const { t } = useTranslation()
  const [severity, label] = !agent.ok
    ? (['danger', t('packagesError')] as const)
    : agent.warnings.length > 0
      ? (['warning', t('packagesWarning')] as const)
      : (['success', 'OK'] as const)
  return <Tag severity={severity} value={label} style={{ fontSize: 11, padding: '2px 8px' }} />
}

function Findings({ agent }: { agent: Row }) {
  if (agent.errors.length === 0 && agent.warnings.length === 0)
    return <span style={{ ...MUTED, fontSize: 12 }}>—</span>
  return (
    <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12 }}>
      {agent.errors.map((error) => (
        <li key={`e-${error}`} style={{ color: 'var(--color-danger)' }}>
          {error}
        </li>
      ))}
      {agent.warnings.map((warning) => (
        <li key={`w-${warning}`} style={{ color: 'var(--color-warning)' }}>
          {warning}
        </li>
      ))}
    </ul>
  )
}
