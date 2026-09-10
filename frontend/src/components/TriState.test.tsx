/**
 * The tri-state agent toggle used by the Agents matrix and the Projects cards.
 *
 * Cycles inherit → off → on → inherit (design §5.4). Three states, because a
 * project override is sparse: "says nothing" is not "says false", and a cell
 * that could only be on or off would make an override impossible to remove.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { DraftProvider, useDraft } from '../state/draft'
import { TriState } from './TriState'

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
      <TriState
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

function cell() {
  return screen.getByRole('button', { name: /reviewer for Release 2\.0/ })
}

/** The draft, parsed — the path contains quotes that JSON.stringify escapes. */
function edits(): Record<string, unknown> {
  return JSON.parse(screen.getByTestId('edits').textContent ?? '{}')
}

describe('reading the current state', () => {
  it('is inherit when the project says nothing', () => {
    render(<Harness saved={undefined} inherited />)
    expect(cell()).toHaveAttribute('data-state', 'inherit')
  })

  it('is off when the project overrides with false', () => {
    render(<Harness saved={false} inherited />)
    expect(cell()).toHaveAttribute('data-state', 'off')
  })

  it('is on when the project overrides with true', () => {
    render(<Harness saved={true} inherited={false} />)
    expect(cell()).toHaveAttribute('data-state', 'on')
  })

  it('reports the inherited value while inheriting, so the cell can show it', () => {
    render(<Harness saved={undefined} inherited={false} />)
    expect(cell()).toHaveAttribute('data-inherited', 'false')
  })

  it('names the state in its accessible label, not just in colour', () => {
    render(<Harness saved={false} inherited />)
    expect(cell().getAttribute('aria-label')).toMatch(/off/i)
  })

  it('says what an inheriting cell actually resolves to', () => {
    // "Inherited" alone would leave the operator unable to tell, from the
    // matrix, whether this agent runs for this project.
    render(<Harness saved={undefined} inherited />)
    expect(cell().getAttribute('aria-label')).toMatch(/inherited/i)
    expect(cell().getAttribute('aria-label')).toMatch(/on/i)
  })
})

describe('cycling', () => {
  it('goes from inherit to off', async () => {
    render(<Harness saved={undefined} inherited />)
    await userEvent.click(cell())
    expect(edits()).toEqual({ [PATH]: false })
    expect(cell()).toHaveAttribute('data-state', 'off')
  })

  it('goes from off to on', async () => {
    render(<Harness saved={undefined} inherited />)
    await userEvent.click(cell())
    await userEvent.click(cell())
    expect(edits()).toEqual({ [PATH]: true })
    expect(cell()).toHaveAttribute('data-state', 'on')
  })

  it('goes from on back to inherit', async () => {
    render(<Harness saved={undefined} inherited />)
    await userEvent.click(cell())
    await userEvent.click(cell())
    await userEvent.click(cell())
    // The removal prunes away: there was no key on disk to remove, so three
    // clicks leave no pending change at all rather than a phantom one.
    expect(edits()).toEqual({})
    expect(cell()).toHaveAttribute('data-state', 'inherit')
  })

  it('queues a real removal when the override is on disk', async () => {
    const savedConfig = {
      projects: { 'Release 2.0': { agents: { reviewer: { enabled: true } } } },
    }
    render(<Harness saved={true} inherited savedConfig={savedConfig} />)

    // Already `on`, so one click returns it to inherit.
    await userEvent.click(cell())

    expect(edits()).toEqual({ [PATH]: null })
    expect(cell()).toHaveAttribute('data-state', 'inherit')
  })

  it('cycles off → on → inherit from a saved false', async () => {
    const savedConfig = {
      projects: { 'Release 2.0': { agents: { reviewer: { enabled: false } } } },
    }
    render(<Harness saved={false} inherited savedConfig={savedConfig} />)

    await userEvent.click(cell())
    expect(cell()).toHaveAttribute('data-state', 'on')
    await userEvent.click(cell())
    expect(cell()).toHaveAttribute('data-state', 'inherit')
    expect(edits()).toEqual({ [PATH]: null })
  })
})

describe('read-only sessions', () => {
  it('renders the state but refuses to change it', async () => {
    render(<Harness saved={false} inherited readOnly />)
    await userEvent.click(cell())
    expect(edits()).toEqual({})
  })

  it('is marked disabled rather than silently inert', () => {
    render(<Harness saved={false} inherited readOnly />)
    expect(cell()).toBeDisabled()
  })
})
