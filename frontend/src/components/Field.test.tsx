import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { DraftProvider, useDraft } from '../state/draft'
import type { FieldSpec } from '../screens/fields'
import { Field } from './Field'

function Harness({ spec, saved }: { spec: FieldSpec; saved: Record<string, unknown> }) {
  return (
    <DraftProvider saved={saved}>
      <Field spec={spec} saved={saved[spec.key]} lang="en" />
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

describe('Field', () => {
  it('renders a text field with the saved value', () => {
    const spec: FieldSpec = { key: 'host', type: 'text', hint: 'Bind address' }

    render(<Harness spec={spec} saved={{ host: '127.0.0.1' }} />)

    expect(screen.getByLabelText('host')).toHaveValue('127.0.0.1')
    expect(screen.getByText('Bind address')).toBeInTheDocument()
  })

  it('records a text edit against the field key', async () => {
    const spec: FieldSpec = { key: 'host', type: 'text', hint: 'Bind address' }
    render(<Harness spec={spec} saved={{ host: '127.0.0.1' }} />)

    await userEvent.clear(screen.getByLabelText('host'))
    await userEvent.type(screen.getByLabelText('host'), '0.0.0.0')

    expect(screen.getByTestId('edits')).toHaveTextContent('{"host":"0.0.0.0"}')
  })

  it('records an emptied optional text field as a removal', async () => {
    const spec: FieldSpec = { key: 'ssl_cert', type: 'text', hint: 'Certificate file' }
    render(<Harness spec={spec} saved={{ ssl_cert: '/etc/cert.pem' }} />)

    await userEvent.clear(screen.getByLabelText('ssl_cert'))

    // Not the empty string: '' is a value the model would reject, while
    // removing the key restores the default of "no certificate".
    expect(screen.getByTestId('edits')).toHaveTextContent('{"ssl_cert":null}')
  })

  it('records a number edit as a number, not a string', async () => {
    const spec: FieldSpec = { key: 'port', type: 'number', hint: 'Port to listen on' }
    render(<Harness spec={spec} saved={{ port: 8010 }} />)

    await userEvent.clear(screen.getByLabelText('port'))
    await userEvent.type(screen.getByLabelText('port'), '9999')

    expect(screen.getByTestId('edits')).toHaveTextContent('{"port":9999}')
  })

  it('records a cleared number field as a removal', async () => {
    const spec: FieldSpec = { key: 'port', type: 'number', hint: 'Port to listen on' }
    render(<Harness spec={spec} saved={{ port: 8010 }} />)

    await userEvent.clear(screen.getByLabelText('port'))

    expect(screen.getByTestId('edits')).toHaveTextContent('{"port":null}')
  })

  it('toggles a boolean', async () => {
    const spec: FieldSpec = { key: 'debug', type: 'bool', hint: 'Verbose logging' }
    render(<Harness spec={spec} saved={{ debug: false }} />)

    await userEvent.click(screen.getByRole('switch', { name: 'debug' }))

    expect(screen.getByTestId('edits')).toHaveTextContent('{"debug":true}')
  })

  it('reflects the boolean state to assistive technology', () => {
    const spec: FieldSpec = { key: 'debug', type: 'bool', hint: 'Verbose logging' }
    render(<Harness spec={spec} saved={{ debug: true }} />)

    expect(screen.getByRole('switch', { name: 'debug' })).toHaveAttribute('aria-checked', 'true')
  })

  it('renders a select with the spec options', async () => {
    const spec: FieldSpec = {
      key: 'language',
      type: 'select',
      options: ['de', 'en'],
      hint: 'Default language',
    }
    render(<Harness spec={spec} saved={{ language: 'de' }} />)

    await userEvent.selectOptions(screen.getByLabelText('language'), 'en')

    expect(screen.getByTestId('edits')).toHaveTextContent('{"language":"en"}')
  })

  it('edits a list as comma-separated text and stores an array', async () => {
    const spec: FieldSpec = { key: 'trusted_proxies', type: 'list', hint: 'Trusted proxies' }
    render(<Harness spec={spec} saved={{ trusted_proxies: null }} />)

    await userEvent.type(screen.getByLabelText('trusted_proxies'), '10.0.0.1, 10.0.0.2')

    expect(screen.getByTestId('edits')).toHaveTextContent(
      '{"trusted_proxies":["10.0.0.1","10.0.0.2"]}',
    )
  })

  it('records an emptied list as a removal', async () => {
    const spec: FieldSpec = { key: 'trusted_proxies', type: 'list', hint: 'Trusted proxies' }
    render(<Harness spec={spec} saved={{ trusted_proxies: ['10.0.0.1'] }} />)

    await userEvent.clear(screen.getByLabelText('trusted_proxies'))

    expect(screen.getByTestId('edits')).toHaveTextContent('{"trusted_proxies":null}')
  })

  it('marks a changed field and offers to revert it', async () => {
    const spec: FieldSpec = { key: 'host', type: 'text', hint: 'Bind address' }
    render(<Harness spec={spec} saved={{ host: '127.0.0.1' }} />)

    await userEvent.type(screen.getByLabelText('host'), 'x')
    await userEvent.click(screen.getByRole('button', { name: /revert/i }))

    expect(screen.getByTestId('edits')).toHaveTextContent('{}')
    expect(screen.getByLabelText('host')).toHaveValue('127.0.0.1')
  })

  it('offers no revert control on an unchanged field', () => {
    const spec: FieldSpec = { key: 'host', type: 'text', hint: 'Bind address' }
    render(<Harness spec={spec} saved={{ host: '127.0.0.1' }} />)

    expect(screen.queryByRole('button', { name: /revert/i })).not.toBeInTheDocument()
  })

  it('shows a validation issue against the field', () => {
    const spec: FieldSpec = { key: 'port', type: 'number', hint: 'Port to listen on' }
    render(
      <DraftProvider saved={{ port: 8010 }}>
        <Field spec={spec} saved={8010} issue="Input should be a valid integer" />
      </DraftProvider>,
    )

    expect(screen.getByLabelText('port')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByRole('alert')).toHaveTextContent('Input should be a valid integer')
  })

  it('preserves the comma in the list input while editing', async () => {
    const spec: FieldSpec = { key: 'trusted_proxies', type: 'list', hint: 'Trusted proxies' }
    render(<Harness spec={spec} saved={{ trusted_proxies: null }} />)

    await userEvent.type(screen.getByLabelText('trusted_proxies'), '10.0.0.1,')

    expect(screen.getByLabelText('trusted_proxies')).toHaveValue('10.0.0.1,')
  })

  it('appends to an existing list when editing', async () => {
    const spec: FieldSpec = { key: 'trusted_proxies', type: 'list', hint: 'Trusted proxies' }
    render(<Harness spec={spec} saved={{ trusted_proxies: ['10.0.0.1', '10.0.0.2'] }} />)

    await userEvent.type(screen.getByLabelText('trusted_proxies'), ', 10.0.0.3')

    expect(screen.getByTestId('edits')).toHaveTextContent('{"trusted_proxies":["10.0.0.1","10.0.0.2","10.0.0.3"]}')
  })

  it('restores the saved value in the visible input when reverting a list field', async () => {
    const spec: FieldSpec = { key: 'trusted_proxies', type: 'list', hint: 'Trusted proxies' }
    render(<Harness spec={spec} saved={{ trusted_proxies: ['10.0.0.1', '10.0.0.2'] }} />)

    await userEvent.type(screen.getByLabelText('trusted_proxies'), ', 10.0.0.3')
    expect(screen.getByLabelText('trusted_proxies')).toHaveValue('10.0.0.1, 10.0.0.2, 10.0.0.3')

    await userEvent.click(screen.getByRole('button', { name: /revert/i }))

    expect(screen.getByLabelText('trusted_proxies')).toHaveValue('10.0.0.1, 10.0.0.2')
  })

  it('links a validation issue to the bool switch via aria-invalid and aria-describedby', () => {
    const spec: FieldSpec = { key: 'debug', type: 'bool', hint: 'Verbose logging' }
    render(
      <DraftProvider saved={{ debug: false }}>
        <Field spec={spec} saved={false} issue="Invalid boolean value" />
      </DraftProvider>,
    )

    const switchButton = screen.getByRole('switch', { name: 'debug' })
    expect(switchButton).toHaveAttribute('aria-invalid', 'true')
    expect(switchButton).toHaveAttribute('aria-describedby', 'debug-issue')
    expect(screen.getByRole('alert')).toHaveTextContent('Invalid boolean value')
  })

  it('toggles the bool switch via keyboard (Enter key)', async () => {
    const spec: FieldSpec = { key: 'debug', type: 'bool', hint: 'Verbose logging' }
    render(<Harness spec={spec} saved={{ debug: false }} />)

    const switchButton = screen.getByRole('switch', { name: 'debug' })
    await userEvent.tab()
    await userEvent.keyboard('{Enter}')

    expect(switchButton).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByTestId('edits')).toHaveTextContent('{"debug":true}')
  })

  it('links a validation issue to the select via aria-invalid and aria-describedby', () => {
    const spec: FieldSpec = {
      key: 'language',
      type: 'select',
      options: ['de', 'en'],
      hint: 'Default language',
    }
    render(
      <DraftProvider saved={{ language: 'de' }}>
        <Field spec={spec} saved="de" issue="Invalid language selection" />
      </DraftProvider>,
    )

    const selectElement = screen.getByLabelText('language')
    expect(selectElement).toHaveAttribute('aria-invalid', 'true')
    expect(selectElement).toHaveAttribute('aria-describedby', 'language-issue')
    expect(screen.getByRole('alert')).toHaveTextContent('Invalid language selection')
  })
})
