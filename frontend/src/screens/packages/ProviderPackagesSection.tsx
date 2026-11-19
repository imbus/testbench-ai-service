import type { ReactNode } from 'react'
import { Message } from 'primereact/message'
import { useTranslation } from 'react-i18next'
import { usePackages } from '../../api/packages'
import { useStatus } from '../../api/queries'
import { hasLlmClient, PackageCard, PackageUploadButton, usePackageDialogs } from '../AgentPackages'

/**
 * The uploaded packages that provide an LLM client: a section of the LLM
 * screen. The same cards and dialogs as on the agents screen, limited to the
 * packages that matter here; a package may carry agents as well.
 */
export function ProviderPackagesSection({ isAdmin }: { isAdmin: boolean }) {
  const { t } = useTranslation()
  const packages = usePackages()
  const dialogs = usePackageDialogs(packages.data)
  const clientError = useStatus().data?.llm_client_error

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
    const list = (data.packages ?? []).filter(hasLlmClient)
    body = (
      <>
        {isAdmin && data.allow_upload === false && (
          <div className="text-muted" style={{ fontSize: 12 }}>
            {t('packagesUploadDisabled')}
          </div>
        )}
        {list.length === 0 && (
          <div className="text-muted" style={{ fontSize: 13 }}>
            {t('providerPackagesEmpty')}
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
            onUseProvider={(version) =>
              dialogs.open({ kind: 'provider', pkg: entry.name, version })
            }
            onStopProvider={() => dialogs.open({ kind: 'stopProvider', pkg: entry.name })}
          />
        ))}
      </>
    )
  }

  return (
    <section
      aria-label={t('providerPackages')}
      style={{ display: 'flex', flexDirection: 'column', gap: 14 }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 14, flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h3 style={{ margin: 0, fontFamily: 'var(--font-heading)', fontSize: 20 }}>
            {t('providerPackages')}
          </h3>
          <div className="text-muted" style={{ fontSize: 12 }}>
            {t('providerPackagesSub')}
          </div>
        </div>
        {isAdmin && (
          <PackageUploadButton
            data={packages.data}
            dialogs={dialogs}
            label={t('providerPackagesUpload')}
          />
        )}
      </div>
      {clientError && (
        <Message
          severity="warn"
          role="alert"
          style={{ justifyContent: 'flex-start' }}
          content={
            <div>
              <div>{t('statusLlmClientError')}</div>
              <div style={{ fontSize: 12, marginTop: 4, opacity: 0.8 }}>{clientError}</div>
            </div>
          }
        />
      )}
      {body}
      {dialogs.element}
    </section>
  )
}
