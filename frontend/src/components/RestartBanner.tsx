import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Button } from 'primereact/button'
import { Message } from 'primereact/message'
import { useTranslation } from 'react-i18next'
import { ApiError } from '../api/client'
import { movedTo, requestRestart, waitForRestart } from '../api/restart'
import { Modal } from './Modal'

/** What the console needs to offer a restart; absent when it cannot. */
export interface RestartOffer {
  /** `service.started_at` of the run this page talks to. */
  startedAt: string
  /** Agent runs a restart would cut short. */
  inFlight: number
}

type Phase =
  | { kind: 'idle' }
  | { kind: 'confirm' }
  | { kind: 'restarting'; moved: string | null }
  | { kind: 'done' }
  | { kind: 'failed'; message: string }

const DONE_SHOWN_MS = 5000

function failureMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    const detail = error.detail as { message?: string; issues?: { message: string }[] } | string
    if (typeof detail === 'string') return detail
    if (detail?.issues?.length) {
      return [detail.message, ...detail.issues.map((issue) => issue.message)].join(' ')
    }
    return detail?.message ?? error.message
  }
  return fallback
}

/**
 * "Restart needed", and what for -- with a button that restarts the service,
 * when `restart` is offered (an administrator, and a service started by
 * `testbench-ai-service start`).
 *
 * The restart happens inside the service process (testbench_ai_service.restart),
 * so it works in a terminal and as a Windows service alike. The banner then
 * waits for the new run to answer and refreshes every query; the operator stays
 * signed in. If the service will listen somewhere else, it links there.
 */
export function RestartBanner({ fields, restart }: { fields: string[]; restart?: RestartOffer }) {
  const { t } = useTranslation()
  const queries = useQueryClient()
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' })
  const abort = useRef<AbortController | null>(null)

  useEffect(() => () => abort.current?.abort(), [])
  useEffect(() => {
    if (phase.kind !== 'done') return
    const timer = setTimeout(() => setPhase({ kind: 'idle' }), DONE_SHOWN_MS)
    return () => clearTimeout(timer)
  }, [phase.kind])

  if (fields.length === 0 && phase.kind === 'idle') return null

  async function run(offer: RestartOffer) {
    setPhase({ kind: 'restarting', moved: null })
    let moved: string | null
    try {
      moved = movedTo(await requestRestart())
    } catch (error) {
      setPhase({ kind: 'failed', message: failureMessage(error, t('restartFailed')) })
      return
    }
    setPhase({ kind: 'restarting', moved })
    abort.current = new AbortController()
    const status = await waitForRestart(offer.startedAt, { signal: abort.current.signal })
    if (abort.current.signal.aborted) return
    if (status === null) {
      // Moved elsewhere: this address staying silent is expected.
      if (!moved) setPhase({ kind: 'failed', message: t('restartTimeout') })
      return
    }
    void queries.invalidateQueries()
    // Back on this address although it was to move: the new configuration did
    // not start and the service fell back to the previous one.
    setPhase(moved ? { kind: 'failed', message: t('restartFellBack') } : { kind: 'done' })
  }

  const severity = phase.kind === 'failed' ? 'warn' : phase.kind === 'done' ? 'success' : 'info'

  let text
  if (phase.kind === 'restarting') {
    text = phase.moved ? (
      <>
        {t('restartMoving')} <a href={phase.moved}>{phase.moved}</a>
      </>
    ) : (
      t('restarting')
    )
  } else if (phase.kind === 'done') {
    text = t('restartDone')
  } else if (phase.kind === 'failed') {
    text = phase.message
  } else {
    text = (
      <>
        {t('restartNeeded')} {t('restartWhich')}{' '}
        <code style={{ fontFamily: 'var(--font-code)' }}>{fields.join(', ')}</code>
      </>
    )
  }

  return (
    <>
      {/* A PrimeReact `Message` stretched into a full-width strip, with the
          restart glyph as its icon. It keeps the bar's `status` role rather than
          Message's own `alert`: nothing here demands the operator's attention now. */}
      <Message
        severity={severity}
        role="status"
        className="banner"
        style={{ gap: 12, borderColor: 'var(--color-divider)', padding: '6px 16px' }}
        icon={
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            aria-hidden="true"
          >
            <path d="M21 12a9 9 0 1 1-3-6.7" />
            <path d="M21 3v6h-6" />
          </svg>
        }
        text={
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <span>{text}</span>
            {restart && fields.length > 0 && (phase.kind === 'idle' || phase.kind === 'failed') && (
              <Button
                type="button"
                size="small"
                outlined
                label={t('restartNow')}
                onClick={() => setPhase({ kind: 'confirm' })}
              />
            )}
          </span>
        }
      />
      {phase.kind === 'confirm' && restart && (
        <Modal label={t('restartTitle')} onClose={() => setPhase({ kind: 'idle' })}>
          <h3 style={{ margin: 0 }}>{t('restartTitle')}</h3>
          <p style={{ margin: 0 }}>{t('restartExplain')}</p>
          {restart.inFlight > 0 && (
            <Message severity="warn" text={t('restartAbortsRuns', { count: restart.inFlight })} />
          )}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <Button
              type="button"
              outlined
              label={t('cancel')}
              onClick={() => setPhase({ kind: 'idle' })}
            />
            <Button type="button" label={t('restartNow')} onClick={() => void run(restart)} />
          </div>
        </Modal>
      )}
    </>
  )
}
