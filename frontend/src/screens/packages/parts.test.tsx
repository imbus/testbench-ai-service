import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { i18n } from '../../i18n'
import { ReportView } from './parts'
import { version } from './fixtures'

beforeEach(() => i18n.changeLanguage('en'))

describe('ReportView', () => {
  it('names each agent by its entry point and the keys it is registered under', () => {
    render(<ReportView report={version().report} registered={{ acme_risk_rater: 'risk_rater' }} />)

    const risk = screen.getByTestId('package-agent-risk_rater')
    expect(risk).toHaveTextContent('risk_rater')
    expect(risk).toHaveTextContent('registered as acme_risk_rater')
    expect(risk).toHaveTextContent('acme.risk.RiskRater')
    expect(screen.getByTestId('package-agent-dup_finder')).not.toHaveTextContent('registered as')
  })
})
