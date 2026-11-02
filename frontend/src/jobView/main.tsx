import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { PrimeReactProvider } from 'primereact/api'
import { JobViewApp, type JobViewConfig } from './JobViewApp'
import { i18n } from '../i18n'
// The console's stylesheets, in the console's order (see ../main.tsx).
import 'primereact/resources/themes/lara-light-amber/theme.css'
import '../styles/fonts.css'
import '../styles/industry.css'
import '../styles/brand.css'
import '../styles/brand-orange.css'
import '../styles/prime-bridge.css'

interface PageConfig extends JobViewConfig {
  language?: string
  /** Lets PrimeReact's injected <style> elements pass the page's CSP. */
  nonce?: string
}

// Put into the page by the service (jobs/view.py), as data rather than script.
const element = document.getElementById('job-view-config')
const config = (element ? JSON.parse(element.textContent ?? '{}') : {}) as PageConfig

if (config.language === 'de' || config.language === 'en') {
  void i18n.changeLanguage(config.language)
}

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <PrimeReactProvider value={{ nonce: config.nonce }}>
      <QueryClientProvider client={queryClient}>
        <JobViewApp config={config} />
      </QueryClientProvider>
    </PrimeReactProvider>
  </StrictMode>,
)
