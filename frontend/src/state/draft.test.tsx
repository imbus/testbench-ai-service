import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { DRAFT_STORAGE_KEY, DraftProvider, useDraft } from './draft'

function Probe() {
  const draft = useDraft()
  return (
    <div>
      <span data-testid="count">{draft.changeCount}</span>
      <span data-testid="port">{String(draft.valueOf('port', 8010))}</span>
      <span data-testid="changed">{String(draft.isChanged('port'))}</span>
      <span data-testid="edits">{JSON.stringify(draft.edits)}</span>
      <button onClick={() => draft.setValue('port', 9999)}>set</button>
      <button onClick={() => draft.setValue('port', 8010)}>set-same</button>
      <button onClick={() => draft.unsetValue('port')}>unset</button>
      <button onClick={() => draft.revert('port')}>revert</button>
      <button onClick={() => draft.discardAll()}>discard</button>
    </div>
  )
}

function renderProbe(saved: Record<string, unknown> = { port: 8010 }) {
  return render(
    <DraftProvider saved={saved}>
      <Probe />
    </DraftProvider>,
  )
}

beforeEach(() => {
  window.localStorage.clear()
})

describe('useDraft', () => {
  it('starts with no changes and shows the saved value', () => {
    renderProbe()

    expect(screen.getByTestId('count')).toHaveTextContent('0')
    expect(screen.getByTestId('port')).toHaveTextContent('8010')
    expect(screen.getByTestId('changed')).toHaveTextContent('false')
  })

  it('records an edit and counts it once', async () => {
    renderProbe()

    await userEvent.click(screen.getByText('set'))

    expect(screen.getByTestId('count')).toHaveTextContent('1')
    expect(screen.getByTestId('port')).toHaveTextContent('9999')
    expect(screen.getByTestId('changed')).toHaveTextContent('true')
  })

  it('drops an edit that sets the value back to what is saved', async () => {
    renderProbe()

    await userEvent.click(screen.getByText('set'))
    await userEvent.click(screen.getByText('set-same'))

    // Otherwise the operator is told they have an unapplied change that
    // would produce an empty diff.
    expect(screen.getByTestId('count')).toHaveTextContent('0')
  })

  it('records an unset as a null edit, which is a change', async () => {
    renderProbe()

    await userEvent.click(screen.getByText('unset'))

    expect(screen.getByTestId('count')).toHaveTextContent('1')
    expect(screen.getByTestId('edits')).toHaveTextContent('{"port":null}')
  })

  it('reverting a field forgets the edit rather than recording one', async () => {
    renderProbe()

    await userEvent.click(screen.getByText('set'))
    await userEvent.click(screen.getByText('revert'))

    expect(screen.getByTestId('count')).toHaveTextContent('0')
    expect(screen.getByTestId('edits')).toHaveTextContent('{}')
    expect(screen.getByTestId('port')).toHaveTextContent('8010')
  })

  it('discards every edit at once', async () => {
    renderProbe()

    await userEvent.click(screen.getByText('set'))
    await userEvent.click(screen.getByText('discard'))

    expect(screen.getByTestId('count')).toHaveTextContent('0')
    expect(screen.getByTestId('edits')).toHaveTextContent('{}')
  })

  it('persists edits to localStorage', async () => {
    renderProbe()

    await userEvent.click(screen.getByText('set'))

    expect(JSON.parse(window.localStorage.getItem(DRAFT_STORAGE_KEY) ?? '{}')).toEqual({
      port: 9999,
    })
  })

  it('restores edits from localStorage on mount', () => {
    window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify({ port: 9999 }))

    renderProbe()

    expect(screen.getByTestId('count')).toHaveTextContent('1')
    expect(screen.getByTestId('port')).toHaveTextContent('9999')
  })

  it('ignores unparseable localStorage rather than crashing the console', () => {
    window.localStorage.setItem(DRAFT_STORAGE_KEY, 'not json')

    renderProbe()

    expect(screen.getByTestId('count')).toHaveTextContent('0')
  })

  it('ignores a stored value that is not an object', () => {
    window.localStorage.setItem(DRAFT_STORAGE_KEY, '[1,2,3]')

    renderProbe()

    expect(screen.getByTestId('count')).toHaveTextContent('0')
  })

  it('clears the stored draft when everything is discarded', async () => {
    renderProbe()

    await userEvent.click(screen.getByText('set'))
    await userEvent.click(screen.getByText('discard'))

    expect(window.localStorage.getItem(DRAFT_STORAGE_KEY)).toBeNull()
  })

  it('drops an edit that a concurrent save has made redundant', () => {
    // The operator queued port = 9999; someone else applied the same value.
    window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify({ port: 9999 }))

    renderProbe({ port: 9999 })

    expect(screen.getByTestId('count')).toHaveTextContent('0')
  })

  it('compares structurally so a re-fetched list is not a phantom change', () => {
    window.localStorage.setItem(
      DRAFT_STORAGE_KEY,
      JSON.stringify({ trusted_proxies: ['10.0.0.1'] }),
    )

    render(
      <DraftProvider saved={{ trusted_proxies: ['10.0.0.1'] }}>
        <Probe />
      </DraftProvider>,
    )

    expect(screen.getByTestId('count')).toHaveTextContent('0')
  })
})
