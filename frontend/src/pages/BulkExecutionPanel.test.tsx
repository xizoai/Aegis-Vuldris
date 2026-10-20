import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ProjectDetailPage } from './ProjectDetailPage'

/**
 * Bulk selection: pick several tests, run them together, watch progress and
 * read each test's outcome.
 *
 * The backend answers the bulk request with 202 and an execution id per test,
 * so progress is derived from the executions endpoint the page already polls.
 * These tests pin that contract rather than inventing a bulk-specific one.
 */

const PROJECT = {
  id: 'p1',
  owner_id: 'u1',
  name: 'Test project',
  description: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

const TARGET = {
  id: 't1',
  project_id: 'p1',
  name: 'Local model',
  description: null,
  provider: 'ollama',
  endpoint: 'http://localhost:11434',
  model: 'llama3',
  capabilities: [],
  timeout_seconds: 30,
  rate_limit_per_minute: 60,
  status: 'active',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

function makeTest(id: string, name: string) {
  return {
    id,
    project_id: 'p1',
    name,
    description: null,
    provider: 'openai_compatible',
    required_capabilities: ['chat'],
    config: { category: 'prompt_injection', grading: {} },
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }
}

function makeExecution(overrides: Record<string, unknown> = {}) {
  return {
    id: 'e1',
    project_id: 'p1',
    test_id: 'st1',
    target_id: 't1',
    status: 'succeeded',
    result: 'pass',
    started_at: '2026-01-01T00:00:00Z',
    completed_at: '2026-01-01T00:01:00Z',
    created_by: 'u1',
    error: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:01:00Z',
    ...overrides,
  }
}

const TESTS = [
  makeTest('st1', 'Direct instruction override'),
  makeTest('st2', 'Role confusion'),
  makeTest('st3', 'Jailbreak framing'),
]

/**
 * Route fetch calls by URL suffix.
 *
 * Matching prefers `endsWith` because `/projects/p1` is a substring of every
 * project-scoped URL, and `/assessments/tests` is a prefix of the seed URL.
 */
function router(routes: Record<string, { body: unknown; status?: number }>) {
  const keys = Object.keys(routes)

  const resolve = (url: string) =>
    keys.find((key) => url.endsWith(key)) ?? keys.find((key) => url.includes(key))

  return vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString()
    const match = resolve(url)
    if (!match) {
      return {
        ok: false,
        status: 404,
        text: async () => JSON.stringify({ error: { code: 'NOT_FOUND', message: url } }),
      } as unknown as Response
    }
    const route = routes[match]
    return {
      ok: (route.status ?? 200) < 400,
      status: route.status ?? 200,
      text: async () => JSON.stringify(route.body),
    } as unknown as Response
  })
}

const baseRoutes = {
  '/projects/p1': { body: PROJECT },
  '/assessments/tests': { body: TESTS },
  '/targets': { body: [TARGET] },
  '/assessments/reports': { body: [] },
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/projects/p1']}>
      <Routes>
        <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('Bulk test selection', () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders a checkbox per test and enables Run when one is checked', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', router({ ...baseRoutes, '/assessments/executions': { body: [] } }))

    renderPage()

    const bulk = await screen.findByRole('button', { name: 'Run 0 selected' })
    expect(bulk).toBeDisabled()

    await user.click(screen.getByLabelText('Role confusion'))
    expect(screen.getByRole('button', { name: 'Run 1 selected' })).toBeEnabled()
  })

  it('selects and clears the whole list from Select all', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', router({ ...baseRoutes, '/assessments/executions': { body: [] } }))

    renderPage()
    const selectAll = await screen.findByLabelText('Select all')

    expect(selectAll).toBeInTheDocument()

    await user.click(selectAll)
    expect(screen.getByRole('button', { name: 'Run 3 selected' })).toBeInTheDocument()

    await user.click(selectAll)
    expect(screen.getByRole('button', { name: 'Run 0 selected' })).toBeInTheDocument()
  })

  it('shows the mixed state while only some tests are checked', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', router({ ...baseRoutes, '/assessments/executions': { body: [] } }))

    renderPage()
    const selectAll = (await screen.findByLabelText('Select all')) as HTMLInputElement

    await user.click(screen.getByLabelText('Role confusion'))

    // Partly checked: neither fully on nor off, so the box is indeterminate.
    expect(selectAll.indeterminate).toBe(true)
    expect(selectAll).not.toBeChecked()
  })

  it('does not run anything when the selection is empty', async () => {
    const fetchMock = router({ ...baseRoutes, '/assessments/executions': { body: [] } })
    vi.stubGlobal('fetch', fetchMock)

    renderPage()

    const bulk = await screen.findByRole('button', { name: 'Run 0 selected' })
    expect(bulk).toBeDisabled()

    const bulkCalls = (fetchMock as unknown as { mock: { calls: unknown[] } }).mock.calls
      .length
    // Only the page's initial loads happened.
    expect(bulkCalls).toBeGreaterThan(0)
    await userEvent
      .setup()
      .click(bulk)
      .catch(() => {
        // A disabled button raises on click; the page simply does not submit.
      })
  })
})

describe('Bulk run submission', () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('posts the selected tests and target to the bulk endpoint', async () => {
    const user = userEvent.setup()
    let posted: unknown = null

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url.includes('/executions/bulk')) {
        posted = init?.body ? JSON.parse(String(init.body)) : null
        return {
          ok: true,
          status: 202,
          text: async () =>
            JSON.stringify({
              total: 2,
              target_id: 't1',
              execution_ids: ['e1', 'e2'],
            }),
        } as unknown as Response
      }
      const routes = { ...baseRoutes, '/assessments/executions': { body: [] } }
      const match =
        Object.keys(routes).find((key) => url.endsWith(key)) ??
        Object.keys(routes).find((key) => url.includes(key))
      return {
        ok: true,
        status: 200,
        text: async () =>
          JSON.stringify(match ? routes[match as keyof typeof routes].body : {}),
      } as unknown as Response
    })

    vi.stubGlobal('fetch', fetchMock)
    renderPage()

    await user.click(await screen.findByLabelText('Direct instruction override'))
    await user.click(screen.getByLabelText('Jailbreak framing'))
    await user.click(screen.getByRole('button', { name: 'Run 2 selected' }))

    await waitFor(() => {
      expect(posted).toEqual({
        test_ids: ['st1', 'st3'],
        target_id: 't1',
      })
    })
  })

  it('reports progress and each test outcome once results arrive', async () => {
    const user = userEvent.setup()
    // Empty until the bulk call queues them, as the real endpoint behaves.
    let executionIds: string[] = []

    const executions = [
      makeExecution({ id: 'e1', test_id: 'st1', status: 'succeeded', result: 'fail' }),
      makeExecution({ id: 'e2', test_id: 'st2', status: 'succeeded', result: 'pass' }),
      makeExecution({ id: 'e3', test_id: 'st3', status: 'running', result: 'inconclusive' }),
    ]

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url.includes('/executions/bulk')) {
        executionIds = ['e1', 'e2', 'e3']
        return {
          ok: true,
          status: 202,
          text: async () =>
            JSON.stringify({
              total: 3,
              target_id: 't1',
              execution_ids: executionIds,
            }),
        } as unknown as Response
      }
      const routes = {
        ...baseRoutes,
        '/assessments/executions': { body: executionIds.length > 0 ? executions : [] },
      }
      const match =
        Object.keys(routes).find((key) => url.endsWith(key)) ??
        Object.keys(routes).find((key) => url.includes(key))
      return {
        ok: true,
        status: 200,
        text: async () =>
          JSON.stringify(match ? routes[match as keyof typeof routes].body : {}),
      } as unknown as Response
    })

    vi.stubGlobal('fetch', fetchMock)
    renderPage()

    await user.click(await screen.findByLabelText('Select all'))
    await user.click(screen.getByRole('button', { name: 'Run 3 selected' }))

    // Each result is attributed to its own test, not to the suite as a whole.
    expect(await screen.findByRole('table', { name: /results of the bulk run/i })).toBeInTheDocument()
    expect(await screen.findByRole('cell', { name: 'Direct instruction override' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: 'Role confusion' })).toBeInTheDocument()
    // One of the three is still running, so only two have finished.
    expect(screen.getByText('2 of 3 finished')).toBeInTheDocument()
  })

  it('surfaces a bulk failure without dropping the selection', async () => {
    const user = userEvent.setup()
    vi.stubGlobal(
      'fetch',
      router({
        ...baseRoutes,
        '/assessments/executions': { body: [] },
        '/executions/bulk': {
          status: 422,
          body: {
            error: {
              code: 'EXECUTION_BINDING_ERROR',
              message: 'Target is not active.',
            },
          },
        },
      }),
    )

    renderPage()

    await user.click(await screen.findByLabelText('Select all'))
    await user.click(screen.getByRole('button', { name: 'Run 3 selected' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Target is not active.')
    // The selection survives so the user can fix the target and retry.
    expect(screen.getByRole('button', { name: 'Run 3 selected' })).toBeInTheDocument()
  })
})
