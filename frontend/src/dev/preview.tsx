/* Throwaway harness: mounts the real console against fixture responses so a
   rendered screen can be compared against the artboard. Not shipped. */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App } from '../App'
import { SessionProvider } from '../state/session'
import '../styles/fonts.css'
import '../styles/industry.css'
import '../styles/brand.css'

const signedIn = !new URLSearchParams(location.search).has('login')

const FIXTURES: Record<string, unknown> = {
  '/admin/api/meta': { tb_server_url: 'https://tb.example.com:9443/api/' },
  '/admin/api/session': {
    username: 'a.mueller',
    roles: ['Administrator'],
    is_admin: true,
    tb_server_url: 'https://tb.example.com:9443/api/',
  },
  '/admin/api/status': {
    service: {
      version: '1.0.1',
      host: '127.0.0.1',
      port: 8010,
      debug: false,
      uptime_seconds: 8040,
      language: 'de',
    },
    testbench: { url: 'https://tb.example.com:9443/api/', reachable: true, detail: null },
    api_keys: [
      { name: 'OPENAI_API_KEY', present: true },
      { name: 'AZURE_OPENAI_API_KEY', present: true },
      { name: 'ANTHROPIC_API_KEY', present: false },
    ],
    agents: { total: 4, enabled: 3, project_overrides: 2, projects: 2 },
    log_file: 'logs/testbench-ai-service.log',
    in_flight_tasks: 0,
    restart_required: [],
  },
  '/admin/api/config': {
    running: { host: '127.0.0.1', port: 8010, language: 'de' },
    disk: { host: '127.0.0.1', port: 8010 },
    config_path: 'C:/ProgramData/TestBench/config.toml',
  },
  '/admin/api/projects': {
    projects: [
      { name: 'Alpha', key: 'ALPHA' },
      { name: 'Beta', key: 'BETA' },
    ],
    fetched_at: null,
    source: 'testbench',
    error: null,
  },
  '/admin/api/prompts': {
    languages: [
      {
        lang: 'de',
        prompts: [
          {
            agent: 'test_case_set_reviewer',
            file: 'de/test_case_set_reviewer/prompt.yaml',
            name: 'Testfallmengen-Prüfer',
            variants: ['Gründlich', 'Kompakt'],
            ok: true,
            error: null,
            used_by: [],
          },
        ],
      },
      {
        lang: 'en',
        prompts: [
          {
            agent: 'test_case_set_reviewer',
            file: 'en/test_case_set_reviewer/prompt.yaml',
            name: 'Test Case Set Reviewer',
            variants: ['Thorough'],
            ok: true,
            error: null,
            used_by: [],
          },
        ],
      },
    ],
  },
  '/admin/api/prompts/de/test_case_set_reviewer': {
    lang: 'de',
    agent: 'test_case_set_reviewer',
    file: 'de/test_case_set_reviewer/prompt.yaml',
    name: 'Testfallmengen-Prüfer',
    summary: 'Prüft eine Testfallmenge auf Vollständigkeit und Konsistenz.',
    description:
      'Bewertet die übergebene Testfallmenge gegenüber den Anforderungen und liefert eine strukturierte Rückmeldung.',
    default_model: 'gpt-5.5',
    default_variant: 'Gründlich',
    variants: [
      {
        name: 'Gründlich',
        description: 'Ausführliche Prüfung mit Begründung',
        model: null,
        vars: {
          tone: {
            name: 'tone',
            description: 'Ton der Rückmeldung',
            value_type: 'string',
            choices: null,
            default_value: 'sachlich',
            required: false,
          },
        },
        messages: [
          {
            role: 'system',
            source: 'file',
            file: 'gruendlich_system.jinja',
            content: 'Du bist ein gründlicher Prüfer für Testfallmengen.',
            readable: true,
          },
          {
            role: 'user',
            source: 'inline',
            file: null,
            content: 'Prüfe {{ agent.test_case_set }} im Ton {{ vars.tone }}',
            readable: true,
          },
        ],
      },
      {
        name: 'Kompakt',
        description: null,
        model: null,
        vars: {},
        messages: [
          {
            role: 'user',
            source: 'inline',
            file: null,
            content: 'Kurzprüfung von {{ agent.test_case_set }}',
            readable: true,
          },
        ],
      },
    ],
    agent_context_skeleton: { test_case_set: '', test_cases: [], project_name: '' },
  },
}

const LOGS = [
  ['09:14:02', 'INFO', 'uvicorn.error', 'Application startup complete.'],
  ['09:14:02', 'INFO', 'tbai.config', 'Loaded config.toml'],
  ['09:31:44', 'WARNING', 'tbai.agents', 'reviewer: prompt variant "strict" not found'],
  ['10:02:11', 'ERROR', 'tbai.llm', 'Azure deployment gpt-4o-mini returned 429'],
  ['10:02:12', 'INFO', 'tbai.llm', 'Retrying in 2s'],
  ['11:20:03', 'INFO', 'tbai.testbench', 'Project list refreshed (2 projects)'],
].map(([timestamp, level, source, message]) => ({
  timestamp: `2026-09-10T${timestamp}`,
  level,
  source,
  message,
  raw: `${timestamp} ${level} ${source} ${message}`,
}))

window.fetch = (async (input: RequestInfo | URL) => {
  const url = String(typeof input === 'string' ? input : (input as Request).url ?? input)
  const path = url.split('?')[0]
  const body = path.startsWith('/admin/api/logs') ? LOGS : FIXTURES[path]
  if (body === undefined || (path === '/admin/api/session' && !signedIn)) {
    return new Response('{"detail":"no"}', { status: 401 })
  }
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}) as typeof fetch

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
})

// A data router, matching main.tsx -- PromptEditor's `useBlocker` needs one.
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
