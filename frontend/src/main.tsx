import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App } from './App'
import { SessionProvider } from './state/session'
import './styles/fonts.css'
import './styles/industry.css'
import './styles/brand.css'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
})

// A data router, not a plain `<BrowserRouter>`: `PromptEditor`'s `useBlocker`
// (Task 15 fix round, Finding 2 -- warns before an IN-APP navigation discards
// unsaved edits) only works under one. `App`'s own `<Routes>`/`<Route>` tree
// underneath this single catch-all route needs no change for it -- only
// `loader`/`action` are unavailable to a route matched this way, and this app
// uses neither.
const router = createBrowserRouter([
  {
    path: '*',
    element: (
      <SessionProvider>
        <App />
      </SessionProvider>
    ),
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
