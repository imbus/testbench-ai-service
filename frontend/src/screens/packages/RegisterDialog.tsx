import { useState } from 'react'
import { Button } from 'primereact/button'
import { Checkbox } from 'primereact/checkbox'
import { InputText } from 'primereact/inputtext'
import { Message } from 'primereact/message'
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

/**
 * The files that exist with other content, each with a "replace" choice and
 * a way to compare both versions. Unchecked files keep their content.
 */
function ConflictList({
  conflicts,
  overwrite,
  onToggle,
}: {
  conflicts: FileConflict[]
  overwrite: string[]
  onToggle: (path: string) => void
}) {
  const { t } = useTranslation()
  const [shown, setShown] = useState<FileConflict | null>(null)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <Message
        severity="warn"
        style={{ justifyContent: 'flex-start' }}
        text={t('packagesFileConflicts')}
      />
      {conflicts.map((conflict, index) => {
        const id = `conflict-${index}`
        return (
          <div key={conflict.path} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Checkbox
              inputId={id}
              checked={overwrite.includes(conflict.path)}
              onChange={() => onToggle(conflict.path)}
              aria-label={`${conflict.path} ${t('packagesReplaceFile')}`}
            />
            <label htmlFor={id} style={{ fontSize: 13, minWidth: 0, overflowWrap: 'anywhere' }}>
              <code>{conflict.path}</code>{' '}
              <span className="text-muted">{t('packagesReplaceFile')}</span>
            </label>
            <span style={{ flex: 1 }} />
            <Button
              type="button"
              text
              size="small"
              label={t('packagesViewDiff')}
              aria-label={`${t('packagesViewDiff')} ${conflict.path}`}
              onClick={() => setShown(conflict)}
            />
          </div>
        )
      })}
      {shown && <FileDiffDialog conflict={shown} onClose={() => setShown(null)} />}
    </div>
  )
}

/** The conflict choices a register or activate call collects across retries. */
function useOverwrite() {
  const [overwrite, setOverwrite] = useState<string[]>([])
  const toggle = (path: string) =>
    setOverwrite((current) =>
      current.includes(path) ? current.filter((entry) => entry !== path) : [...current, path],
    )
  return { overwrite, toggle }
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

/**
 * Configure the entry points of a package version as agents.
 *
 * Only entry points that passed the check and are not configured yet are
 * offered. While the service uses the shipped prompt and template folders the
 * server refuses, so the dialog says so up front and cannot be submitted.
 */
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
  const register = useRegisterAgents()
  const { overwrite, toggle } = useOverwrite()
  const taken = new Set(Object.values(registered))
  const agents = Object.values(version.report.agents)
  const failed = agents.filter((agent) => !agent.ok)
  const [rows, setRows] = useState<Row[]>(() =>
    agents
      .filter((agent) => agent.ok && !taken.has(agent.entry_point))
      .map((agent) => {
        const key = suggestedKey(agent.entry_point)
        return {
          entry_point: agent.entry_point,
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
  const conflicts = conflictsOf(register.error)
  const title = t('packagesRegisterTitle', { name, version: version.version })

  const submit = () =>
    register.mutate(
      {
        name,
        version: version.version,
        agents: selected.map(({ include: _include, ...agent }) => agent),
        overwrite,
      },
      { onSuccess: onClose },
    )

  return (
    <Modal label={title} width={760} maxHeight="85vh">
      <h3 style={{ margin: 0 }}>{title}</h3>

      {defaultDirs && (
        <Message
          severity="warn"
          style={{ justifyContent: 'flex-start' }}
          text={t('packagesDefaultDirs')}
        />
      )}

      {rows.length === 0 && <div style={{ fontSize: 13 }}>{t('packagesNothingToRegister')}</div>}

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

      {failed.map((agent) => (
        <div
          key={agent.entry_point}
          data-testid={`not-registrable-${agent.entry_point}`}
          className="text-muted"
          style={{ fontSize: 12 }}
        >
          <code>{agent.entry_point}</code> — {t('packagesNotRegistrable')}:{' '}
          {agent.errors.join('; ')}
        </div>
      ))}

      {conflicts.length > 0 && (
        <ConflictList conflicts={conflicts} overwrite={overwrite} onToggle={toggle} />
      )}
      {register.isError && conflicts.length === 0 && <PackageError error={register.error} />}

      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <Button type="button" outlined label={t('cancel')} onClick={onClose} />
        <Button
          type="button"
          label={t('packagesRegister')}
          onClick={submit}
          disabled={defaultDirs || selected.length === 0 || register.isPending}
        />
      </div>
    </Modal>
  )
}

/**
 * Switch the active version of a package. Its agents stay configured; the
 * version is loaded at the next start. File conflicts are resolved as in
 * `RegisterDialog`.
 */
export function ActivateDialog({
  name,
  version,
  onClose,
}: {
  name: string
  version: string
  onClose: () => void
}) {
  const { t } = useTranslation()
  const activate = useActivateVersion()
  const { overwrite, toggle } = useOverwrite()
  const conflicts = conflictsOf(activate.error)
  const title = t('packagesActivateTitle', { name, version })

  return (
    <Modal label={title} width={760} maxHeight="85vh">
      <h3 style={{ margin: 0 }}>{title}</h3>
      <div style={{ fontSize: 13 }}>{t('packagesActivateHint')}</div>
      {conflicts.length > 0 && (
        <ConflictList conflicts={conflicts} overwrite={overwrite} onToggle={toggle} />
      )}
      {activate.isError && conflicts.length === 0 && <PackageError error={activate.error} />}
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <Button type="button" outlined label={t('cancel')} onClick={onClose} />
        <Button
          type="button"
          label={t('packagesActivate')}
          disabled={activate.isPending}
          onClick={() => activate.mutate({ name, version, overwrite }, { onSuccess: onClose })}
        />
      </div>
    </Modal>
  )
}
