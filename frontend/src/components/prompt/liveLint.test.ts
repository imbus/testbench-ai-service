import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { LintError } from '../../api/types'
import { LIVE_LINT_DELAY_MS, useLiveLint, type LiveLintSubject } from './liveLint'

const ERROR: LintError = { line: 1, column: 1, message: 'Unexpected end of template' }

/** A `check` whose every call waits until the test settles it by hand. */
function deferredCheck() {
  const calls: { content: string; resolve: (errors: LintError[]) => void; reject: (e: Error) => void }[] = []
  const check = vi.fn(
    (content: string) =>
      new Promise<LintError[]>((resolve, reject) => {
        calls.push({ content, resolve, reject })
      }),
  )
  return { check, calls }
}

function setup(initial: LiveLintSubject | null) {
  const { check, calls } = deferredCheck()
  const onResult = vi.fn<(errors: LintError[] | null) => void>()
  const hook = renderHook(({ subject }) => useLiveLint(subject, check, onResult), {
    initialProps: { subject: initial },
  })
  return { check, calls, onResult, hook }
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useLiveLint', () => {
  it('checks a newly opened message at once, without waiting for the debounce', async () => {
    const { check } = setup({ key: 'a', content: 'Hi' })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(check).toHaveBeenCalledWith('Hi')
  })

  it('sends one request for a burst of edits, after the typing pauses', async () => {
    const { check, hook } = setup({ key: 'a', content: 'H' })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    check.mockClear()

    for (const content of ['Hi', 'Hi {', 'Hi {{']) {
      hook.rerender({ subject: { key: 'a', content } })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(LIVE_LINT_DELAY_MS - 100)
      })
    }
    expect(check).not.toHaveBeenCalled()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })
    expect(check).toHaveBeenCalledTimes(1)
    expect(check).toHaveBeenCalledWith('Hi {{')
  })

  it('delivers the errors of the text it checked', async () => {
    const { calls, onResult } = setup({ key: 'a', content: '{% bad' })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    await act(async () => {
      calls[0].resolve([ERROR])
    })
    expect(onResult).toHaveBeenCalledWith([ERROR])
  })

  it('drops a response that describes text the operator has since changed', async () => {
    const { calls, onResult, hook } = setup({ key: 'a', content: '{% bad' })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    hook.rerender({ subject: { key: 'a', content: '{% bad %}' } })
    await act(async () => {
      calls[0].resolve([ERROR])
    })
    expect(onResult).not.toHaveBeenCalled()
  })

  it('drops a response for a message that is no longer open', async () => {
    const { calls, onResult, hook } = setup({ key: 'a', content: '{% bad' })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    hook.rerender({ subject: null })
    await act(async () => {
      calls[0].resolve([ERROR])
    })
    expect(onResult).not.toHaveBeenCalled()
  })

  it('reports a failed request as null, not as a clean result', async () => {
    const { calls, onResult } = setup({ key: 'a', content: 'Hi' })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    await act(async () => {
      calls[0].reject(new Error('500'))
    })
    expect(onResult).toHaveBeenCalledWith(null)
  })

  it('says it is checking only while a request is in flight', async () => {
    const { calls, hook } = setup({ key: 'a', content: 'Hi' })
    expect(hook.result.current.checking).toBe(false)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(hook.result.current.checking).toBe(true)
    await act(async () => {
      calls[0].resolve([])
    })
    expect(hook.result.current.checking).toBe(false)
  })

  it('checks nothing while no message is open', async () => {
    const { check } = setup(null)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(LIVE_LINT_DELAY_MS * 2)
    })
    expect(check).not.toHaveBeenCalled()
  })
})
