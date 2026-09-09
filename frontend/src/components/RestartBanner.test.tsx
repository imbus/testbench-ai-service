import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RestartBanner } from './RestartBanner'

describe('RestartBanner', () => {
  it('renders nothing when nothing needs a restart', () => {
    render(<RestartBanner lang="en" fields={[]} />)

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('says a restart is needed and names the fields', () => {
    render(<RestartBanner lang="en" fields={['host', 'port']} />)

    expect(screen.getByRole('status')).toHaveTextContent(
      'Some changes need a service restart to take effect.',
    )
    expect(screen.getByRole('status')).toHaveTextContent('host, port')
  })

  it('offers no button that claims to restart the service', () => {
    // Spec 7: re-execing only works under a supervisor and would kill a bare
    // terminal process outright.
    render(<RestartBanner lang="en" fields={['port']} />)

    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
