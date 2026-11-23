import { useState, type ReactNode } from 'react'
import { Button } from 'primereact/button'
import { Checkbox } from 'primereact/checkbox'
import { InputText } from 'primereact/inputtext'
import { Message } from 'primereact/message'
import { RadioButton } from 'primereact/radiobutton'
import { useTranslation } from 'react-i18next'
import { conflictsOf, useActivateVersion, useRegisterAgents } from '../../api/packages'
import type { FileConflict, PackageVersion } from '../../api/types'
import { Modal } from '../../components/Modal'
import { PackageError } from './parts'

const PRE = {
  margin: 0,
  padding: 12,
  overflow: 'auto',
  maxHeight: '60vh',
  background: 'var(--color-surface)',
  border: '1px solid var(--color-divider)',
  fontSize: 12.5,
  lineHeight: 1.5,
  fontFamily: 'var(--font-code)',
  whiteSpace: 'pre-wrap',
} as const

/** The file on disk next to the package's version of it. */
function FileDiffDialog({ conflict, onClose }: { conflict: FileConflict; onClose: () => void }) {
  const { t } = useTranslation()
  return (
    <Modal label={conflict.path} width={1100} maxHeight="85vh">
      <h3 style={{ margin: 0, fontFamily: 'var(--font-code)', fontSize: 15 }}>{conflict.path}</h3>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, minHeight: 0 }}>
        <div style={{ minWidth: 0 }}>
          <div className="text-muted" style={{ fontSize: 12 }}>
            {t('packagesCurrent')}
          </div>
          <pre data-testid="diff-current" style={PRE}>
            {conflict.current}
          </pre>
        </div>
        <div style={{ minWidth: 0 }}>
          <div className="text-muted" style={{ fontSize: 12 }}>
            {t('packagesIncoming')}
          </div>
          <pre data-testid="diff-incoming" style={PRE}>
            {conflict.incoming}
          </pre>
        </div>
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <Button type="button" outlined label={t('close')} onClick={onClose} />
      </div>
    </Modal>
  )
}

type Choice = 'keep' | 'overwrite'

/**
 * The files that exist with other content, each with an explicit choice --
 * keep the operator's file or replace it with the package version -- and a way
 * to compare both. The server refuses a file nobody decided on.
 */
function ConflictList({
  conflicts,
  choices,
  onChoose,
}: {
  conflicts: FileConflict[]
  choices: Record<string, Choice>
  onChoose: (path: string, choice: Choice) => void
}) {
  const { t } = useTranslation()
  const [shown, setShown] = useState<FileConflict | null>(null)
  const options: { choice: Choice; label: string }[] = [
    { choice: 'keep', label: t('packagesKeepFile') },
    { choice: 'overwrite', label: t('packagesReplaceFile') },
  ]
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <Message
        severity="warn"
        style={{ justifyContent: 'flex-start' }}
        text={t('packagesFileConflicts')}
      />
      {conflicts.map((conflict, index) => (
        <div
          key={conflict.path}
          role="radiogroup"
          aria-label={conflict.path}
          style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}
        >
          <code style={{ fontSize: 13, minWidth: 0, overflowWrap: 'anywhere' }}>
            {conflict.path}
          </code>
          <span style={{ flex: 1 }} />
          {options.map(({ choice, label }) => {
            const id = `conflict-${index}-${choice}`
            return (
              <span key={choice} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <RadioButton
                  inputId={id}
                  name={`conflict-${index}`}
                  value={choice}
                  checked={choices[conflict.path] === choice}
                  onChange={() => onChoose(conflict.path, choice)}
                  aria-label={`${conflict.path} ${label}`}
                />
                <label htmlFor={id} style={{ fontSize: 12 }}>
                  {label}
                </label>
              </span>
            )
          })}
          <Button
            type="button"
            text
            size="small"
            label={t('packagesViewDiff')}
            aria-label={`${t('packagesViewDiff')} ${conflict.path}`}
            onClick={() => setShown(conflict)}
          />
        </div>
      ))}
      {shown && <FileDiffDialog conflict={shown} onClose={() => setShown(null)} />}
    </div>
  )
}

/**
 * The file conflicts a register or activate call met, collected across
 * retries, and the operator's choice for each.
 */
function useConflicts() {
  const [conflicts, setConflicts] = useState<FileConflict[]>([])
  const [choices, setChoices] = useState<Record<string, Choice>>({})
  const decided = (choice: Choice) =>
    conflicts.filter((conflict) => choices[conflict.path] === choice).map(({ path }) => path)
  return {
    conflicts,
    choices,
    choose: (path: string, choice: Choice) =>
      setChoices((current) => ({ ...current, [path]: choice })),
    /** Add the conflicts a failed call reports; other errors change nothing. */
    learn: (error: unknown) => {
      const found = conflictsOf(error)
      if (found.length === 0) return
      setConflicts((current) => [
        ...current.filter((known) => !found.some((entry) => entry.path === known.path)),
        ...found,
      ])
    },
    undecided: conflicts.some((conflict) => choices[conflict.path] === undefined),
    files: () => ({ overwrite: decided('overwrite'), keep: decided('keep') }),
  }
}

/** A suggested agent key: the entry point in the form `agent_key` accepts. */
function suggestedKey(entryPoint: string): string {
  const key = entryPoint
    .toLowerCase()
    .replace(/[^a-z0-9_]/g, '_')
    .replace(/^[^a-z]+/, '')
  return key.slice(0, 64) || 'agent'
}

interface Row {
  entry_point: string
  include: boolean
  agent_key: string
  endpoint_path: string
  enabled: boolean
}

/** What a register form hands its footer: the submit action and whether it may run. */
export interface RegisterFooter {
  submit: () => void
  disabled: boolean
}

/**
 * Configure the entry points of a package version as agents: the form both
 * the register dialog and the upload wizard's last step show.
 *
 * Only entry points that passed the check and are not configured yet are
 * offered. While the service uses the shipped prompt and template folders the
 * server refuses, so the form says so up front and cannot be submitted.
 * The caller draws the buttons through `footer`.
 */
export function RegisterForm({
  name,
  version,
  registered,
  defaultDirs,
  onDone,
  body = (content) => content,
  footer,
}: {
  name: string
  version: PackageVersion
  registered: Record<string, string>
  defaultDirs: boolean
  onDone: () => void
  /** Wraps the form's fields, e.g. into a body of fixed height; as-is by default. */
  body?: (content: ReactNode) => ReactNode
  footer: (props: RegisterFooter) => ReactNode
}) {
  const { t } = useTranslation()
  const register = useRegisterAgents()
  const files = useConflicts()
  const taken = new Set(Object.values(registered))
  // Keyed by entry point name, which the server expects; `agent.entry_point` is
  // the entry point's value ("module:Class").
  const agents = Object.entries(version.report.agents)
  const failed = agents.filter(([, agent]) => !agent.ok)
  const [rows, setRows] = useState<Row[]>(() =>
    agents
      .filter(([entryPoint, agent]) => agent.ok && !taken.has(entryPoint))
      .map(([entryPoint, agent]) => {
        const key = suggestedKey(entryPoint)
        return {
          entry_point: entryPoint,
          include: true,
          agent_key: key,
          endpoint_path: agent.default_endpoint_path ?? `/${key.replace(/_/g, '-')}`,
          enabled: true,
        }
      }),
  )
  const update = (index: number, change: Partial<Row>) =>
    setRows((current) => current.map((row, i) => (i === index ? { ...row, ...change } : row)))

  const selected = rows.filter((row) => row.include)

  const submit = () =>
    register.mutate(
      {
        name,
        version: version.version,
        agents: selected.map(({ include: _include, ...agent }) => agent),
        ...files.files(),
      },
      { onSuccess: onDone, onError: files.learn },
    )

  return (
    <>
      {body(
        <>
          {defaultDirs && (
            <Message
              severity="warn"
              style={{ justifyContent: 'flex-start' }}
              text={t('packagesDefaultDirs')}
            />
          )}

          {rows.length === 0 && (
            <div style={{ fontSize: 13 }}>{t('packagesNothingToRegister')}</div>
          )}

          {rows.length > 0 && (
            <div
              className="text-muted"
              style={{
                display: 'grid',
                gridTemplateColumns: 'auto minmax(0, 1fr) minmax(0, 1fr) auto',
                gap: 10,
                fontSize: 11,
                letterSpacing: '.06em',
                textTransform: 'uppercase',
              }}
            >
              <span>{t('packagesColEntryPoint')}</span>
              <span>agent_key</span>
              <span>endpoint_path</span>
              <span />
            </div>
          )}

          {rows.map((row, index) => (
            <div
              key={row.entry_point}
              style={{
                display: 'grid',
                gridTemplateColumns: 'auto minmax(0, 1fr) minmax(0, 1fr) auto',
                gap: 10,
                alignItems: 'center',
              }}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <Checkbox
                  inputId={`include-${index}`}
                  checked={row.include}
                  onChange={() => update(index, { include: !row.include })}
                  aria-label={`${row.entry_point} ${t('packagesInclude')}`}
                />
                <label htmlFor={`include-${index}`} style={{ fontSize: 13 }}>
                  <code>{row.entry_point}</code>
                </label>
              </span>
              <InputText
                value={row.agent_key}
                aria-label={`${row.entry_point} agent_key`}
                onChange={(event) => update(index, { agent_key: event.target.value })}
                style={{ fontFamily: 'var(--font-code)', fontSize: 13 }}
              />
              <InputText
                value={row.endpoint_path}
                aria-label={`${row.entry_point} endpoint_path`}
                onChange={(event) => update(index, { endpoint_path: event.target.value })}
                style={{ fontFamily: 'var(--font-code)', fontSize: 13 }}
              />
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <Checkbox
                  inputId={`enabled-${index}`}
                  checked={row.enabled}
                  onChange={() => update(index, { enabled: !row.enabled })}
                  aria-label={`${row.entry_point} ${t('packagesAgentEnabled')}`}
                />
                <label htmlFor={`enabled-${index}`} style={{ fontSize: 12 }} className="text-muted">
                  {t('packagesAgentEnabled')}
                </label>
              </span>
            </div>
          ))}

          {failed.map(([entryPoint, agent]) => (
            <div
              key={entryPoint}
              data-testid={`not-registrable-${entryPoint}`}
              className="text-muted"
              style={{ fontSize: 12 }}
            >
              <code>{entryPoint}</code> — {t('packagesNotRegistrable')}: {agent.errors.join('; ')}
            </div>
          ))}

          {files.conflicts.length > 0 && (
            <ConflictList
              conflicts={files.conflicts}
              choices={files.choices}
              onChoose={files.choose}
            />
          )}
          {register.isError && conflictsOf(register.error).length === 0 && (
            <PackageError error={register.error} />
          )}
        </>,
      )}
      {footer({
        submit,
        disabled: defaultDirs || selected.length === 0 || files.undecided || register.isPending,
      })}
    </>
  )
}

/** The register form on its own, for a version that is already uploaded. */
export function RegisterDialog({
  name,
  version,
  registered,
  defaultDirs,
  onClose,
}: {
  name: string
  version: PackageVersion
  registered: Record<string, string>
  defaultDirs: boolean
  onClose: () => void
}) {
  const { t } = useTranslation()
  const title = t('packagesRegisterTitle', { name, version: version.version })
  return (
    <Modal label={title} width={760} maxHeight="85vh">
      <h3 style={{ margin: 0 }}>{title}</h3>
      <RegisterForm
        name={name}
        version={version}
        registered={registered}
        defaultDirs={defaultDirs}
        onDone={onClose}
        footer={({ submit, disabled }) => (
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <Button type="button" outlined label={t('cancel')} onClick={onClose} />
            <Button
              type="button"
              label={t('packagesRegister')}
              onClick={submit}
              disabled={disabled}
            />
          </div>
        )}
      />
    </Modal>
  )
}

/**
 * Switch the active version of a package. Its agents stay configured; the
 * version is loaded at the next start. The version's files are copied for the
 * configured agents too, so the default folders block it and file conflicts
 * are resolved as in `RegisterDialog`.
 */
export function ActivateDialog({
  name,
  version,
  defaultDirs,
  onClose,
}: {
  name: string
  version: string
  defaultDirs: boolean
  onClose: () => void
}) {
  const { t } = useTranslation()
  const activate = useActivateVersion()
  const files = useConflicts()
  const title = t('packagesActivateTitle', { name, version })

  return (
    <Modal label={title} width={760} maxHeight="85vh">
      <h3 style={{ margin: 0 }}>{title}</h3>
      <div style={{ fontSize: 13 }}>{t('packagesActivateHint')}</div>
      {defaultDirs && (
        <Message
          severity="warn"
          style={{ justifyContent: 'flex-start' }}
          text={t('packagesDefaultDirs')}
        />
      )}
      {files.conflicts.length > 0 && (
        <ConflictList conflicts={files.conflicts} choices={files.choices} onChoose={files.choose} />
      )}
      {activate.isError && conflictsOf(activate.error).length === 0 && (
        <PackageError error={activate.error} />
      )}
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <Button type="button" outlined label={t('cancel')} onClick={onClose} />
        <Button
          type="button"
          label={t('packagesActivate')}
          disabled={defaultDirs || files.undecided || activate.isPending}
          onClick={() =>
            activate.mutate(
              { name, version, ...files.files() },
              { onSuccess: onClose, onError: files.learn },
            )
          }
        />
      </div>
    </Modal>
  )
}
