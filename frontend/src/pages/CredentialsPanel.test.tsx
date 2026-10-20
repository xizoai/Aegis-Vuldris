import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { credentialApi } from '../api/client'
import { CredentialsPanel, REDACTED } from './TargetsPage'

const SECRET = 'sk-live-do-not-leak-1234567890'

function stubFetchOnce(body: unknown, ok = true, status = 200) {
  const text = JSON.stringify(body)
  return vi.fn(async () => ({
    ok,
    status,
    text: async () => text,
  })) as unknown as typeof fetch
}

function renderPanel(targetId = 'target-1') {
  return render(
    <MemoryRouter>
      <CredentialsPanel targetId={targetId} />
    </MemoryRouter>,
  )
}

describe('CredentialsPanel', () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('never renders a stored credential value, only a redaction placeholder', async () => {
    vi.stubGlobal(
      'fetch',
      stubFetchOnce([
        {
          id: 'cred-1',
          target_id: 'target-1',
          credential_type: 'api_key',
          version: 1,
          revoked: false,
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
      ]),
    )

    renderPanel()

    await waitFor(() => {
      expect(screen.getByText('api_key')).toBeInTheDocument()
    })

    // The secret is nowhere in the document.
    expect(document.body.textContent).not.toContain(SECRET)
    expect(screen.getAllByText(REDACTED).length).toBeGreaterThan(0)
  })

  it('masks the secret input while typing', async () => {
    vi.stubGlobal('fetch', stubFetchOnce([]))
    const user = userEvent.setup()
    renderPanel()

    const input = (await screen.findByLabelText('Secret value')) as HTMLInputElement
    expect(input).toHaveAttribute('type', 'password')
    expect(input).toHaveAttribute('autocomplete', 'off')

    await user.type(input, SECRET)
    // The value is in the DOM property but not rendered as visible text.
    expect(input.value).toBe(SECRET)
    expect(screen.queryByText(SECRET)).not.toBeInTheDocument()
  })

  it('clears the plaintext from state after a successful store', async () => {
    const user = userEvent.setup()
    const listCall = stubFetchOnce([
      {
        id: 'cred-1',
        target_id: 'target-1',
        credential_type: 'api_key',
        version: 1,
        revoked: false,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ])
    const createCall = stubFetchOnce({
      id: 'cred-1',
      target_id: 'target-1',
      credential_type: 'api_key',
      version: 1,
      revoked: false,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    })

    const fetchMock = vi
      .fn()
      .mockImplementationOnce(listCall)
      .mockImplementationOnce(createCall)
      .mockImplementation(listCall)
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch)

    renderPanel()

    const input = await screen.findByLabelText('Secret value')
    await user.type(input, SECRET)
    await user.click(screen.getByRole('button', { name: 'Store credential' }))

    // The form resets so the plaintext is not retained in component state.
    await waitFor(() => {
      expect((screen.getByLabelText('Secret value') as HTMLInputElement).value).toBe('')
    })
    expect(document.body.textContent).not.toContain(SECRET)
  })

  it('states that stored values cannot be read back', async () => {
    vi.stubGlobal('fetch', stubFetchOnce([]))
    renderPanel()

    expect(
      await screen.findByText(/never returns a stored secret/i),
    ).toBeInTheDocument()
  })

  it('marks revoked credentials and hides the revoke action', async () => {
    vi.stubGlobal(
      'fetch',
      stubFetchOnce([
        {
          id: 'cred-1',
          target_id: 'target-1',
          credential_type: 'api_key',
          version: 2,
          revoked: true,
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
      ]),
    )

    renderPanel()

    await waitFor(() => {
      expect(screen.getByText('Revoked')).toBeInTheDocument()
    })
    expect(screen.queryByRole('button', { name: 'Revoke' })).not.toBeInTheDocument()
  })

  it('exposes no control that would read back a secret', async () => {
    vi.stubGlobal('fetch', stubFetchOnce([]))
    renderPanel()

    await screen.findByLabelText('Secret value')
    // The panel must not offer a "reveal"/"resolve" affordance.
    expect(screen.queryByRole('button', { name: /reveal/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /show secret/i })).not.toBeInTheDocument()
    expect(credentialApi).not.toHaveProperty('resolve')
  })
})
