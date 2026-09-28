/**
 * The on/off agent switch on the Projects cards.
 *
 * The switch shows what applies; flipping it writes an override, and "Clear
 * override" is the way back to inheriting the global setting.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { DraftProvider, useDraft } from '../state/draft'
import { AgentSwitch } from './AgentSwitch'

const PATH = 'projects."Release 2.0".agents.reviewer.enabled'

function Harness({
  saved,
  inherited = true,
  savedConfig = {},
  readOnly = false,
}: {
  saved: unknown
  inherited?: boolean
  savedConfig?: Record<string, unknown>
  readOnly?: boolean
}) {
  return (
    <DraftProvider saved={savedConfig}>
      <AgentSwitch
        path={PATH}
        saved={saved}
        inherited={inherited}
        label="reviewer for Release 2.0"
        readOnly={readOnly}
        lang="en"
      />
      <Edits />
    </DraftProvider>
  )
}

function Edits() {
  const draft = useDraft()
  return <span data-testid="edits">{JSON.stringify(draft.edits)}</span>
}

beforeEach(() => {
  window.localStorage.clear()
})

function toggle() {
  return screen.getByRole('switch', { name: /reviewer for Release 2\.0/ })
}

function clear() {
  return screen.queryByRole('button', { name: 'Clear override' })
}

function edits(): Record<string, unknown> {
  return JSON.parse(screen.getByTestId('edits').textContent ?? '{}')
}

describe('reading the current state', () => {
  it('shows the inherited value when there is no override', () => {
    render(<Harness saved={undefined} inherited={false} />)
    expect(toggle()).toHaveAttribute('aria-checked', 'false')
    expect(toggle()).toHaveAttribute('data-state', 'inherit')
    expect(toggle()).toHaveAccessibleName(/Inherited \(Off\)/)
    expect(clear()).not.toBeInTheDocument()
  })

  it('shows the override over the inherited value', () => {
    render(
      <Harness
        saved={false}
        inherited
        savedConfig={{ projects: { 'Release 2.0': { agents: { reviewer: { enabled: false } } } } }}
      />,
    )
    expect(toggle()).toHaveAttribute('aria-checked', 'false')
    expect(toggle()).toHaveAttribute('data-state', 'off')
    expect(clear()).toBeInTheDocument()
  })
})

describe('switching', () => {
  it('writes the opposite of what applies as an override', async () => {
    render(<Harness saved={undefined} inherited />)
    await userEvent.click(toggle())
    expect(edits()).toEqual({ [PATH]: false })
    expect(toggle()).toHaveAttribute('aria-checked', 'false')

    await userEvent.click(toggle())
    expect(edits()).toEqual({ [PATH]: true })
    expect(toggle()).toHaveAttribute('aria-checked', 'true')
  })

  it('clearing an unsaved override leaves no pending change', async () => {
    render(<Harness saved={undefined} inherited />)
    await userEvent.click(toggle())
    await userEvent.click(clear()!)
    expect(edits()).toEqual({})
    expect(toggle()).toHaveAttribute('data-state', 'inherit')
  })

  it('clearing a saved override queues its removal', async () => {
    render(
      <Harness
        saved={false}
        savedConfig={{ projects: { 'Release 2.0': { agents: { reviewer: { enabled: false } } } } }}
      />,
    )
    await userEvent.click(clear()!)
    expect(edits()).toEqual({ [PATH]: null })
    expect(toggle()).toHaveAttribute('aria-checked', 'true')
  })

  it('is inert when read-only', () => {
    render(<Harness saved={false} readOnly />)
    expect(toggle()).toBeDisabled()
    expect(clear()).not.toBeInTheDocument()
  })
})
