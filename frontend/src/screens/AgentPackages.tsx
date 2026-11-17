import { useState } from 'react'
import { Button } from 'primereact/button'
import { Message } from 'primereact/message'
import { Tag } from 'primereact/tag'
import { useTranslation } from 'react-i18next'
import { usePackages, useDeleteVersion, useRemovePackage } from '../api/packages'
import { useConfig } from '../api/queries'
import type { AgentPackage, PackagesResponse, PackageVersion } from '../api/types'
import { Modal } from '../components/Modal'
import { PackageError, ReportView } from './packages/parts'
import { ActivateDialog, RegisterDialog } from './packages/RegisterDialog'
import { UploadDialog } from './packages/UploadDialog'

type Dialog =
  | { kind: 'upload' }
  | { kind: 'register'; pkg: string; version: PackageVersion }
  | { kind: 'activate'; pkg: string; version: string }
  | { kind: 'delete'; pkg: string; version: string }
  | { kind: 'remove'; pkg: AgentPackage }

function formatDate(iso: string, language: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString(language)
}

/**
 * Uploaded agent packages (Python wheels), their check reports, and the
 * actions that put their agents to use. Every action is admin-only; a
 * non-admin reads the same page without them.
 */
export function AgentPackages({ isAdmin }: { isAdmin: boolean }) {
  const { t } = useTranslation()
  const packages = usePackages()
  const [dialog, setDialog] = useState<Dialog | null>(null)
  const close = () => setDialog(null)

  if (packages.isLoading) return <div style={{ padding: 28 }}>…</div>
  if (packages.isError || !packages.data) {
    return (
      <div role="alert" style={{ padding: 28 }}>
        <div>{t('packagesLoadError')}</div>
        <div className="text-muted" style={{ fontSize: 12, marginTop: 4 }}>
          {(packages.error as Error | null)?.message}
        </div>
      </div>
    )
  }
  const data = packages.data

  /** Register a version, or activate it when another version of its package is active. */
  const openVersion = (name: string, version: PackageVersion) => {
    const other = data.packages
      .find((entry) => entry.name === name)
      ?.versions.some((entry) => entry.active && entry.version !== version.version)
    setDialog(
      other
        ? { kind: 'activate', pkg: name, version: version.version }
        : { kind: 'register', pkg: name, version },
    )
  }

  return (
    <div style={{ padding: '28px 32px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
        <div>
          <h2 className="page-title" style={{ margin: 0, fontSize: 30 }}>
            {t('agentPackages')}
          </h2>
          <div className="text-muted" style={{ fontSize: 12 }}>
            {t('packagesSub')}
          </div>
        </div>
        <div style={{ flex: 1 }} />
        {isAdmin && (
          // The wrapper carries the explanation: a disabled button takes no
          // pointer events, so a title on the button itself never shows.
          <span title={data.allow_upload ? undefined : t('packagesUploadDisabled')}>
            <Button
              type="button"
              label={t('packagesUpload')}
              disabled={!data.allow_upload}
              onClick={() => setDialog({ kind: 'upload' })}
            />
          </span>
        )}
      </div>

      {isAdmin && !data.allow_upload && (
        <div className="text-muted" style={{ fontSize: 12 }}>
          {t('packagesUploadDisabled')}
        </div>
      )}

      {data.packages.length === 0 && (
        <div className="text-muted" style={{ fontSize: 13 }}>
          {t('packagesEmpty')}
        </div>
      )}

      {data.packages.map((entry) => (
        <PackageCard
          key={entry.name}
          pkg={entry}
          isAdmin={isAdmin}
          onUse={(version) => openVersion(entry.name, version)}
          onActivate={(version) => setDialog({ kind: 'activate', pkg: entry.name, version })}
          onDelete={(version) => setDialog({ kind: 'delete', pkg: entry.name, version })}
          onRemove={() => setDialog({ kind: 'remove', pkg: entry })}
        />
      ))}

      {dialog?.kind === 'upload' && (
        <UploadDialog
          onClose={close}
          onRegister={(version) => openVersion(version.name, version)}
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
    </div>
  )
}

function registeredOf(data: PackagesResponse, name: string): Record<string, string> {
  return data.packages.find((entry) => entry.name === name)?.registered ?? {}
}

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
        borderRadius: 6,
        padding: '14px 18px',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: 'var(--font-heading)', fontWeight: 600, fontSize: 17 }}>
          {pkg.name}
        </span>
        {active ? (
          <>
            <span style={{ fontFamily: 'var(--font-code)', fontSize: 13 }}>{active.version}</span>
            <Tag value={t('packagesActive')} style={{ padding: '1px 6px', fontSize: 10 }} />
          </>
        ) : (
          <span className="text-muted" style={{ fontSize: 12 }}>
            {t('packagesNoActiveVersion')}
          </span>
        )}
        {inUse && (
          <Tag
            severity={pkg.loaded ? 'success' : 'warning'}
            value={pkg.loaded ? t('packagesLoaded') : t('packagesNotLoaded')}
            style={{ padding: '1px 6px', fontSize: 10 }}
          />
        )}
        {shown && (
          <span className="text-muted" style={{ fontSize: 12 }}>
            <span style={{ fontFamily: 'var(--font-code)' }} title={shown.sha256}>
              sha256 {shown.sha256.slice(0, 8)}…
            </span>{' '}
            ·{' '}
            {shown.uploaded_by
              ? t('packagesUploadedBy', { user: shown.uploaded_by, date })
              : t('packagesUploadedAt', { date })}
          </span>
        )}
      </div>

      {pkg.load_error && (
        <Message severity="warn" style={{ justifyContent: 'flex-start' }} text={pkg.load_error} />
      )}

      {shown && <ReportView report={shown.report} registered={pkg.registered} />}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <div
          className="text-muted"
          style={{ fontSize: 11, letterSpacing: '.08em', textTransform: 'uppercase' }}
        >
          {t('packagesVersions')}
        </div>
        {pkg.versions.map((entry) => (
          <div
            key={entry.version}
            data-testid={`package-version-${entry.version}`}
            style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13 }}
          >
            <span style={{ fontFamily: 'var(--font-code)' }}>{entry.version}</span>
            {entry.active && (
              <Tag value={t('packagesActive')} style={{ padding: '1px 6px', fontSize: 10 }} />
            )}
            {!entry.report.ok && (
              <span style={{ color: 'var(--color-danger)', fontSize: 12 }}>
                ✖ {t('packagesCheckFailed')}
              </span>
            )}
            <span className="text-muted" style={{ fontSize: 12 }}>
              {formatDate(entry.uploaded_at, i18n.language)}
            </span>
            <span style={{ flex: 1 }} />
            {isAdmin && (
              <VersionActions
                version={entry}
                otherActive={!!active && !entry.active}
                onUse={() => onUse(entry)}
                onActivate={() => onActivate(entry.version)}
                onDelete={() => onDelete(entry.version)}
              />
            )}
          </div>
        ))}
      </div>

      {isAdmin && (inUse || active) && (
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Button
            type="button"
            outlined
            severity="danger"
            size="small"
            label={t('packagesRemove')}
            onClick={onRemove}
          />
        </div>
      )}
    </section>
  )
}

/**
 * The actions of one version: an inactive version is activated while another
 * one is active (the server refuses registering then), registered otherwise;
 * only inactive versions can be deleted.
 */
function VersionActions({
  version,
  otherActive,
  onUse,
  onActivate,
  onDelete,
}: {
  version: PackageVersion
  otherActive: boolean
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
          text
          size="small"
          label={t('packagesActivate')}
          onClick={onActivate}
        />
      ) : (
        <Button type="button" text size="small" label={t('packagesRegister')} onClick={onUse} />
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
