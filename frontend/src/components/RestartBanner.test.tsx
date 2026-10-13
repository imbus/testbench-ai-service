import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RestartBanner } from './RestartBanner'
import { i18n } from '../i18n'

// The assertions match the English copy.
beforeEach(() => i18n.changeLanguage('en'))

describe('RestartBanner', () => {
  it('renders nothing when nothing needs a restart', () => {
    render(<RestartBanner fields={[]} />)

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('says a restart is needed and names the fields', () => {
    render(<RestartBanner fields={['host', 'port']} />)

    expect(screen.getByRole('status')).toHaveTextContent(
      'Some changes need a service restart to take effect.',
    )
    expect(screen.getByRole('status')).toHaveTextContent('host, port')
  })

  it('offers no button that claims to restart the service', () => {
    // Spec 7: re-execing only works under a supervisor and would kill a bare
    // terminal process outright.
    render(<RestartBanner fields={['port']} />)

    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
