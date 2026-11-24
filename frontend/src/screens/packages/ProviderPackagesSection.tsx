import type { ReactNode } from 'react'
import { Message } from 'primereact/message'
import { useTranslation } from 'react-i18next'
import { usePackages } from '../../api/packages'
import { useStatus } from '../../api/queries'
import { SectionPanel } from '../../components/SectionPanel'
import { hasLlmClient, PackageCard, PackageUploadButton, usePackageDialogs } from '../AgentPackages'

/**
 * The uploaded packages that provide an LLM client: a section of its own on
 * the LLM screen, drawn like the settings and the models above it. The
 * cards of the agents screen, showing the LLM client side only: a package's
 * agents, if it has any, are the agents screen's business.
 */
export function ProviderPackagesSection({ isAdmin }: { isAdmin: boolean }) {
  const { t } = useTranslation()
  const packages = usePackages()
  const dialogs = usePackageDialogs(packages.data, 'provider')
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
            kind="provider"
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
    <SectionPanel
      title={t('providerPackages')}
      hint={t('providerPackagesSub')}
      action={
        isAdmin && (
          <PackageUploadButton
            data={packages.data}
            dialogs={dialogs}
            label={t('providerPackagesUpload')}
          />
        )
      }
    >
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
    </SectionPanel>
  )
}
