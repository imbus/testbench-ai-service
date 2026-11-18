import { useState, type ReactNode } from 'react'
import { Button } from 'primereact/button'
import { Message } from 'primereact/message'
import { Tag } from 'primereact/tag'
import { useTranslation } from 'react-i18next'
import { usePackages, useDeleteVersion, useRemovePackage } from '../api/packages'
import { useConfig } from '../api/queries'
import type { AgentPackage, PackagesResponse, PackageVersion } from '../api/types'
import { Modal } from '../components/Modal'
import { Icon, ICONS, LIST_GROUP, LIST_ROW, PackageError, ReportView } from './packages/parts'
import { ActivateDialog, RegisterDialog } from './packages/RegisterDialog'
import { UploadDialog } from './packages/UploadDialog'

export type Dialog =
  | { kind: 'upload' }
  | { kind: 'register'; pkg: string; version: PackageVersion }
  | { kind: 'activate'; pkg: string; version: string }
  | { kind: 'delete'; pkg: string; version: string }
  | { kind: 'remove'; pkg: AgentPackage }

function formatDate(iso: string, language: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString(language)
}

export interface PackageDialogs {
  open: (dialog: Dialog) => void
  /** Register a version, or activate it when another version of its package is active. */
  openVersion: (name: string, version: PackageVersion) => void
  /** The open dialog, if any; render it once, anywhere on the page. */
  element: ReactNode
}

/**
 * The dialogs of the package actions, shared by the upload button in the
 * agents header and the package cards below the agent table: an upload ends
 * in the register dialog, so both have to open the same set.
 */
export function usePackageDialogs(data: PackagesResponse | undefined): PackageDialogs {
  const [dialog, setDialog] = useState<Dialog | null>(null)
  const close = () => setDialog(null)

  const openVersion = (name: string, version: PackageVersion) => {
    const other = data?.packages
      .find((entry) => entry.name === name)
      ?.versions.some((entry) => entry.active && entry.version !== version.version)
    setDialog(
      other
        ? { kind: 'activate', pkg: name, version: version.version }
        : { kind: 'register', pkg: name, version },
    )
  }

  const element = data ? (
    <>
      {dialog?.kind === 'upload' && (
        <UploadDialog
          onClose={close}
          packages={data}
          onActivate={(version) =>
            setDialog({ kind: 'activate', pkg: version.name, version: version.version })
          }
        />
      )}
      {dialog?.kind === 'register' && (
        <RegisterDialog
          name={dialog.pkg}
          version={dialog.version}
          registered={registeredOf(data, dialog.pkg)}
          defaultDirs={data.default_dirs}
          onClose={close}
        />
      )}
      {dialog?.kind === 'activate' && (
        <ActivateDialog
          name={dialog.pkg}
          version={dialog.version}
          defaultDirs={data.default_dirs}
          onClose={close}
        />
      )}
      {dialog?.kind === 'delete' && (
        <DeleteDialog name={dialog.pkg} version={dialog.version} onClose={close} />
      )}
      {dialog?.kind === 'remove' && <RemoveDialog pkg={dialog.pkg} onClose={close} />}
    </>
  ) : null

  return { open: setDialog, openVersion, element }
}

/**
 * The admin's button that imports an agent wheel. Disabled, with the reason,
 * while uploading is switched off in the config; absent until the package
 * list has loaded, since the upload flow needs it.
 */
export function PackageUploadButton({
  data,
  dialogs,
}: {
  data: PackagesResponse | undefined
  dialogs: PackageDialogs
}) {
  const { t } = useTranslation()
  if (!data) return null
  return (
    // The wrapper carries the explanation: a disabled button takes no
    // pointer events, so a title on the button itself never shows.
    <span title={data.allow_upload ? undefined : t('packagesUploadDisabled')}>
      <Button
        type="button"
        label={t('packagesUpload')}
        disabled={!data.allow_upload}
        onClick={() => dialogs.open({ kind: 'upload' })}
      />
    </span>
  )
}

/**
 * Uploaded agent packages (Python wheels), their check reports, and the
 * actions that put their agents to use: a section of the agents screen.
 * Every action is admin-only; a non-admin reads the same section without them.
 */
export function AgentPackagesSection({
  packages,
  dialogs,
  isAdmin,
}: {
  packages: ReturnType<typeof usePackages>
  dialogs: PackageDialogs
  isAdmin: boolean
}) {
  const { t } = useTranslation()

  let body: ReactNode
  if (packages.isLoading) body = <div>…</div>
  else if (packages.isError || !packages.data) {
    body = (
      <div role="alert">
        <div>{t('packagesLoadError')}</div>
        <div className="text-muted" style={{ fontSize: 12, marginTop: 4 }}>
          {(packages.error as Error | null)?.message}
        </div>
      </div>
    )
  } else {
    const data = packages.data
    // `?? []`: a payload without the list renders an empty section rather
    // than taking the agents screen above it down.
    const list = data.packages ?? []
    body = (
      <>
        {isAdmin && !data.allow_upload && (
          <div className="text-muted" style={{ fontSize: 12 }}>
            {t('packagesUploadDisabled')}
          </div>
        )}
        {list.length === 0 && (
          <div className="text-muted" style={{ fontSize: 13 }}>
            {t('packagesEmpty')}
          </div>
        )}
        {list.map((entry) => (
          <PackageCard
            key={entry.name}
            pkg={entry}
            isAdmin={isAdmin}
            onUse={(version) => dialogs.openVersion(entry.name, version)}
            onActivate={(version) => dialogs.open({ kind: 'activate', pkg: entry.name, version })}
            onDelete={(version) => dialogs.open({ kind: 'delete', pkg: entry.name, version })}
            onRemove={() => dialogs.open({ kind: 'remove', pkg: entry })}
          />
        ))}
      </>
    )
  }

  return (
    <section
      aria-label={t('agentPackages')}
      style={{ display: 'flex', flexDirection: 'column', gap: 14 }}
    >
      <div>
        <h3 style={{ margin: 0, fontFamily: 'var(--font-heading)', fontSize: 20 }}>
          {t('agentPackages')}
        </h3>
        <div className="text-muted" style={{ fontSize: 12 }}>
          {t('packagesSub')}
        </div>
      </div>
      {body}
    </section>
  )
}

function registeredOf(data: PackagesResponse, name: string): Record<string, string> {
  return data.packages.find((entry) => entry.name === name)?.registered ?? {}
}

const SECTION_LABEL = {
  fontSize: 11,
  letterSpacing: '.08em',
  textTransform: 'uppercase',
  color: 'var(--color-muted)',
} as const

function PackageCard({
  pkg,
  isAdmin,
  onUse,
  onActivate,
  onDelete,
  onRemove,
}: {
  pkg: AgentPackage
  isAdmin: boolean
  onUse: (version: PackageVersion) => void
  onActivate: (version: string) => void
  onDelete: (version: string) => void
  onRemove: () => void
}) {
  const { t, i18n } = useTranslation()
  const active = pkg.versions.find((entry) => entry.active)
  // The report shown is the active version's, or the newest upload's.
  const shown = active ?? pkg.versions[0]
  const inUse = Object.keys(pkg.registered).length > 0
  const date = shown ? formatDate(shown.uploaded_at, i18n.language) : ''

  return (
    <section
      data-testid={`package-${pkg.name}`}
      aria-label={pkg.name}
      style={{
        border: '1px solid var(--color-divider)',
        borderRadius: 10,
        background: 'var(--color-bg)',
        boxShadow: 'var(--shadow-sm)',
        overflow: 'hidden',
      }}
    >
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 14,
          padding: '14px 18px',
          background: 'color-mix(in srgb, var(--color-surface) 60%, transparent)',
          borderBottom: '1px solid var(--color-divider)',
          flexWrap: 'wrap',
        }}
      >
        <span
          style={{
            width: 40,
            height: 40,
            borderRadius: 8,
            display: 'grid',
            placeItems: 'center',
            background: 'var(--color-bg)',
            border: '1px solid var(--color-divider)',
          }}
        >
          <Icon d={ICONS.box} size={20} color="var(--color-muted)" />
        </span>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0, flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span style={{ fontFamily: 'var(--font-heading)', fontWeight: 600, fontSize: 18 }}>
              {pkg.name}
            </span>
            {active ? (
              <>
                <span style={{ fontFamily: 'var(--font-code)', fontSize: 13 }}>
                  {active.version}
                </span>
                <Tag value={t('packagesActive')} style={{ padding: '1px 8px', fontSize: 11 }} />
              </>
            ) : (
              <Tag
                severity="secondary"
                value={t('packagesNoActiveVersion')}
                style={{ padding: '1px 8px', fontSize: 11 }}
              />
            )}
            {inUse && (
              <Tag
                severity={pkg.loaded ? 'success' : 'warning'}
                value={pkg.loaded ? t('packagesLoaded') : t('packagesNotLoaded')}
                style={{ padding: '1px 8px', fontSize: 11 }}
              />
            )}
          </div>
          {shown && (
            <span className="text-muted" style={{ fontSize: 12 }}>
              {shown.uploaded_by
                ? t('packagesUploadedBy', { user: shown.uploaded_by, date })
                : t('packagesUploadedAt', { date })}{' '}
              ·{' '}
              <span style={{ fontFamily: 'var(--font-code)' }} title={shown.sha256}>
                sha256 {shown.sha256.slice(0, 8)}…
              </span>
            </span>
          )}
        </div>
        {isAdmin && (inUse || active) && (
          <Button
            type="button"
            text
            severity="danger"
            size="small"
            label={t('packagesRemove')}
            onClick={onRemove}
          />
        )}
      </header>

      <div style={{ padding: '14px 18px 18px', display: 'flex', flexDirection: 'column', gap: 16 }}>
        {pkg.load_error && (
          <Message severity="warn" style={{ justifyContent: 'flex-start' }} text={pkg.load_error} />
        )}

        {shown && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={SECTION_LABEL}>{t('packagesAgentsOf', { version: shown.version })}</div>
            <ReportView report={shown.report} registered={pkg.registered} />
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={SECTION_LABEL}>{t('packagesVersions')}</div>
          <div style={LIST_GROUP}>
            {pkg.versions.map((entry, index) => (
              <div
                key={entry.version}
                data-testid={`package-version-${entry.version}`}
                style={{
                  ...LIST_ROW,
                  ...(index === 0 ? { borderTop: 'none' } : {}),
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  fontSize: 13,
                  padding: '6px 8px 6px 14px',
                  minHeight: 42,
                  ...(entry.active
                    ? { background: 'color-mix(in srgb, var(--color-surface) 45%, transparent)' }
                    : {}),
                }}
              >
                <span style={{ fontFamily: 'var(--font-code)', fontWeight: 600, minWidth: 56 }}>
                  {entry.version}
                </span>
                {entry.active && (
                  <Tag value={t('packagesActive')} style={{ padding: '1px 8px', fontSize: 11 }} />
                )}
                {!entry.report.ok && (
                  <Tag
                    severity="danger"
                    value={t('packagesCheckFailed')}
                    style={{ padding: '1px 8px', fontSize: 11 }}
                  />
                )}
                <span className="text-muted" style={{ fontSize: 12 }}>
                  {formatDate(entry.uploaded_at, i18n.language)}
                </span>
                <span style={{ flex: 1 }} />
                {isAdmin && (
                  <VersionActions
                    version={entry}
                    otherActive={!!active && !entry.active}
                    registrable={hasUnregistered(entry, pkg.registered)}
                    onUse={() => onUse(entry)}
                    onActivate={() => onActivate(entry.version)}
                    onDelete={() => onDelete(entry.version)}
                  />
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

/**
 * Whether a version has agents left to register: an entry point that passed
 * the check and is not configured under any agent key yet.
 */
function hasUnregistered(version: PackageVersion, registered: Record<string, string>): boolean {
  const taken = new Set(Object.values(registered))
  return Object.entries(version.report.agents).some(
    ([entryPoint, agent]) => agent.ok && !taken.has(entryPoint),
  )
}

/**
 * The actions of one version: an inactive version is activated while another
 * one is active (the server refuses registering then); otherwise it offers
 * registering, but only while it has agents left to register. Only inactive
 * versions can be deleted.
 */
function VersionActions({
  version,
  otherActive,
  registrable,
  onUse,
  onActivate,
  onDelete,
}: {
  version: PackageVersion
  otherActive: boolean
  registrable: boolean
  onUse: () => void
  onActivate: () => void
  onDelete: () => void
}) {
  const { t } = useTranslation()
  return (
    <span style={{ display: 'flex', gap: 6 }}>
      {otherActive ? (
        <Button
          type="button"
          outlined
          size="small"
          label={t('packagesActivate')}
          onClick={onActivate}
        />
      ) : (
        registrable && (
          <Button
            type="button"
            outlined
            size="small"
            label={t('packagesRegister')}
            onClick={onUse}
          />
        )
      )}
      {!version.active && (
        <Button
          type="button"
          text
          size="small"
          severity="danger"
          label={t('packagesDelete')}
          onClick={onDelete}
        />
      )}
    </span>
  )
}

function DeleteDialog({
  name,
  version,
  onClose,
}: {
  name: string
  version: string
  onClose: () => void
}) {
  const { t } = useTranslation()
  const remove = useDeleteVersion()
  const title = t('packagesDeleteTitle', { name, version })
  return (
    <Modal label={title}>
      <h3 style={{ margin: 0 }}>{title}</h3>
      <div style={{ fontSize: 13 }}>{t('packagesDeleteHint')}</div>
      {remove.isError && <PackageError error={remove.error} />}
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <Button type="button" outlined label={t('cancel')} onClick={onClose} />
        <Button
          type="button"
          severity="danger"
          label={t('packagesDelete')}
          disabled={remove.isPending}
          onClick={() => remove.mutate({ name, version }, { onSuccess: onClose })}
        />
      </div>
    </Modal>
  )
}

/** The projects of the config file that override any of `keys`: what removing drops. */
function projectsUsing(disk: Record<string, unknown> | undefined, keys: string[]): string[] {
  const projects = (disk?.projects ?? {}) as Record<string, { agents?: unknown }>
  return Object.keys(projects)
    .filter((project) => {
      const agents = projects[project]?.agents
      return (
        agents !== null &&
        typeof agents === 'object' &&
        keys.some((key) => key in (agents as object))
      )
    })
    .sort()
}

function RemoveDialog({ pkg, onClose }: { pkg: AgentPackage; onClose: () => void }) {
  const { t } = useTranslation()
  const remove = useRemovePackage()
  const config = useConfig()
  const keys = Object.keys(pkg.registered).sort()
  const projects = projectsUsing(config.data?.disk, keys)
  const title = t('packagesRemoveTitle', { name: pkg.name })
  return (
    <Modal label={title}>
      <h3 style={{ margin: 0 }}>{title}</h3>
      {keys.length === 0 ? (
        <div style={{ fontSize: 13 }}>{t('packagesRemoveNoAgents')}</div>
      ) : (
        <div style={{ fontSize: 13 }}>
          {t('packagesRemoveAgents')}
          <ul style={{ margin: '4px 0 0', paddingLeft: 18, fontFamily: 'var(--font-code)' }}>
            {keys.map((key) => (
              <li key={key}>{key}</li>
            ))}
          </ul>
        </div>
      )}
      {projects.length > 0 && (
        <div style={{ fontSize: 13 }}>
          {t('packagesRemoveProjects')}
          <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>
            {projects.map((project) => (
              <li key={project}>{project}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="text-muted" style={{ fontSize: 12 }}>
        {t('packagesFilesKept')}
      </div>
      {remove.isError && <PackageError error={remove.error} />}
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <Button type="button" outlined label={t('cancel')} onClick={onClose} />
        <Button
          type="button"
          severity="danger"
          label={t('packagesRemove')}
          disabled={remove.isPending}
          onClick={() => remove.mutate(pkg.name, { onSuccess: onClose })}
        />
      </div>
    </Modal>
  )
}
