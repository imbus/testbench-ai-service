import { useEffect, useRef, useState } from 'react'
import type { LintError } from '../../api/types'

/** How long the operator must pause typing before the open message is re-checked. */
export const LIVE_LINT_DELAY_MS = 500

/**
 * The message the live check watches. `key` names WHICH message: a new key
 * (another message opened, or every prior result invalidated) is checked at
 * once; new `content` under the same key waits for a pause in the typing.
 */
export type LiveLintSubject = { key: string; content: string }

/**
 * Re-checks the open message's Jinja syntax as the operator types.
 *
 * `onResult` gets the errors of exactly the text that was sent -- a response
 * that arrives after the text or the open message changed is dropped, so an
 * old verdict can never land on new text. A failed request is reported as
 * `null`, never as `[]`: an unreachable server is not a clean template.
 */
export function useLiveLint(
  subject: LiveLintSubject | null,
  check: (content: string) => Promise<LintError[]>,
  onResult: (errors: LintError[] | null) => void,
): { checking: boolean } {
  const checkRef = useRef(check)
  checkRef.current = check
  const onResultRef = useRef(onResult)
  onResultRef.current = onResult
  // The key the last request went out for. Recorded when the request is
  // SENT, not when the effect runs, so StrictMode's mount-unmount-mount
  // still sees a new key as new and checks it at once.
  const sentKey = useRef<string | null>(null)
  const [checking, setChecking] = useState(false)

  const key = subject?.key ?? null
  const content = subject?.content ?? ''

  useEffect(() => {
    if (key === null) return
    let live = true
    const timer = setTimeout(
      () => {
        sentKey.current = key
        setChecking(true)
        checkRef.current(content)
          .then(
            (errors) => live && onResultRef.current(errors),
            () => live && onResultRef.current(null),
          )
          .finally(() => live && setChecking(false))
      },
      key === sentKey.current ? LIVE_LINT_DELAY_MS : 0,
    )
    return () => {
      live = false
      clearTimeout(timer)
      setChecking(false)
    }
  }, [key, content])

  return { checking }
}
