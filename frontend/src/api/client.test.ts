import { describe, expect, it, beforeEach, vi, afterEach } from 'vitest'

import { ApiError, authApi, credentialApi, tokenStore } from './client'

interface MockResponse {
  ok?: boolean
  status?: number
  json?: unknown
}

/**
 * Build a minimal `fetch` double returning a JSON body. Typed as
 * `(...args: unknown[]) => Promise<unknown>` so callers can pass any payload
 * and assert against the recorded call arguments.
 */
function mockFetch(response: MockResponse) {
  const text = response.json === undefined ? '' : JSON.stringify(response.json)
  const impl = async (..._args: unknown[]) => ({
    ok: response.ok ?? true,
    status: response.status ?? 200,
    statusText: '',
    text: async () => text,
  })
  return vi.fn(impl)
}

/** Read the headers recorded on the nth `fetch` call. */
function headersOf(mock: ReturnType<typeof mockFetch>, index = 0): Record<string, string> {
  const call = mock.mock.calls[index]
  const init = call?.[1] as { headers?: Record<string, string> } | undefined
  return init?.headers ?? {}
}

describe('tokenStore', () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  it('starts empty', () => {
    expect(tokenStore.get()).toBeNull()
  })

  it('stores a token and its expiry', () => {
    tokenStore.set('abc123', 3600)
    expect(tokenStore.get()).toBe('abc123')
    expect(tokenStore.getExpiresAt()).toBeGreaterThan(Date.now())
  })

  it('clears the token', () => {
    tokenStore.set('abc123', 3600)
    tokenStore.clear()
    expect(tokenStore.get()).toBeNull()
    expect(tokenStore.getExpiresAt()).toBeNull()
  })

  it('treats an expired token as absent', () => {
    // A token that expired a second ago.
    tokenStore.set('expired-token', -1)
    expect(tokenStore.getValid()).toBeNull()
    // getValid also prunes the stale value.
    expect(tokenStore.get()).toBeNull()
  })

  it('returns a live token from getValid', () => {
    tokenStore.set('live-token', 3600)
    expect(tokenStore.getValid()).toBe('live-token')
  })

  it('does not persist across sessions by using sessionStorage', () => {
    tokenStore.set('scoped', 3600)
    // localStorage must remain untouched: tokens should not outlive the tab.
    expect(localStorage.getItem('aegis.access_token')).toBeNull()
  })
})

describe('request authorization', () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends a bearer token when one is present', async () => {
    const fetchMock = mockFetch({ ok: true, json: [] })
    vi.stubGlobal('fetch', fetchMock)
    tokenStore.set('tok', 3600)

    await credentialApi.list('target-1')

    expect(fetchMock.mock.calls[0]?.[0]).toContain('/api/v1/targets/target-1/credentials')
    expect(headersOf(fetchMock).Authorization).toBe('Bearer tok')
  })

  it('omits the Authorization header when signed out', async () => {
    const fetchMock = mockFetch({ ok: true, json: [] })
    vi.stubGlobal('fetch', fetchMock)

    await credentialApi.list('target-1')

    expect(headersOf(fetchMock).Authorization).toBeUndefined()
  })

  it('does not send a stale token after expiry', async () => {
    const fetchMock = mockFetch({ ok: true, json: [] })
    vi.stubGlobal('fetch', fetchMock)
    tokenStore.set('stale', -1)

    await credentialApi.list('target-1')

    expect(headersOf(fetchMock).Authorization).toBeUndefined()
  })
})

describe('error handling', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('raises ApiError with the backend code and message', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        ok: false,
        status: 403,
        json: { error: { code: 'PERMISSION_DENIED', message: 'You do not have permission.' } },
      }),
    )

    await expect(credentialApi.list('t')).rejects.toThrowError(ApiError)
    try {
      await credentialApi.list('t')
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError)
      const apiError = error as ApiError
      expect(apiError.status).toBe(403)
      expect(apiError.code).toBe('PERMISSION_DENIED')
      expect(apiError.message).toBe('You do not have permission.')
    }
  })

  it('flags 401 responses as unauthorized', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        ok: false,
        status: 401,
        json: { error: { code: 'AUTHENTICATION_REQUIRED', message: 'Auth required.' } },
      }),
    )

    try {
      await credentialApi.list('t')
      expect.unreachable('should have thrown')
    } catch (error) {
      expect((error as ApiError).isUnauthorized).toBe(true)
    }
  })

  it('falls back gracefully when the body is not an error envelope', async () => {
    vi.stubGlobal('fetch', mockFetch({ ok: false, status: 500 }))

    try {
      await credentialApi.list('t')
      expect.unreachable('should have thrown')
    } catch (error) {
      const apiError = error as ApiError
      expect(apiError.status).toBe(500)
      expect(apiError.code).toBe('UNKNOWN_ERROR')
    }
  })
})

describe('auth flow', () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('login stores the issued token and its expiry', async () => {
    const fetchMock = mockFetch({
      ok: true,
      json: { access_token: 'jwt-abc', token_type: 'bearer', expires_in: 1800 },
    })
    vi.stubGlobal('fetch', fetchMock)

    const tokens = await authApi.login('aegis@example.com', 'a-very-strong-password')

    expect(tokens.access_token).toBe('jwt-abc')
    expect(tokenStore.get()).toBe('jwt-abc')
    expect(tokenStore.getExpiresAt()).toBeGreaterThan(Date.now())
  })

  it('login does not persist the token to localStorage', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        ok: true,
        json: { access_token: 'jwt-abc', token_type: 'bearer', expires_in: 1800 },
      }),
    )

    await authApi.login('aegis@example.com', 'a-very-strong-password')

    expect(localStorage.getItem('aegis.access_token')).toBeNull()
  })

  it('login sends no Authorization header and never puts the password in the URL', async () => {
    const fetchMock = mockFetch({
      ok: true,
      json: { access_token: 'jwt-abc', token_type: 'bearer', expires_in: 1800 },
    })
    vi.stubGlobal('fetch', fetchMock)

    await authApi.login('aegis@example.com', 'a-very-strong-password')

    const url = fetchMock.mock.calls[0]?.[0] as string
    expect(url).toBe('/api/v1/auth/login')
    expect(url).not.toContain('a-very-strong-password')
    expect(url).not.toContain('?')
    expect(headersOf(fetchMock).Authorization).toBeUndefined()
  })

  it('logout revokes server-side and clears the stored token', async () => {
    tokenStore.set('jwt-abc', 1800)
    const fetchMock = mockFetch({ status: 204 })
    vi.stubGlobal('fetch', fetchMock)

    await authApi.logout()

    expect(tokenStore.get()).toBeNull()
    // Revocation must be requested, not just a local wipe.
    const post = fetchMock.mock.calls.find(
      ([url, init]) =>
        String(url).endsWith('/auth/logout') &&
        (init as RequestInit | undefined)?.method === 'POST',
    )
    expect(post).toBeDefined()
  })

it('logout clears the token even when revocation fails', async () => {
    // A network failure must not leave the user stuck in a signed-in UI.
    tokenStore.set('jwt-abc', 1800)
    vi.stubGlobal('fetch', mockFetch({ status: 500 }))

    await authApi.logout()

    expect(tokenStore.get()).toBeNull()
  })
})

describe('credential plaintext handling', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends a plaintext value only on create and never reads it back', async () => {
    const fetchMock = mockFetch({
      ok: true,
      json: {
        id: 'cred-1',
        target_id: 't1',
        credential_type: 'api_key',
        version: 1,
        revoked: false,
        created_at: 'now',
        updated_at: 'now',
      },
    })
    vi.stubGlobal('fetch', fetchMock)

    const created = await credentialApi.create('t1', {
      credential_type: 'api_key',
      value: 'sk-super-secret',
    })

    // The response must not echo the secret back.
    expect(JSON.stringify(created)).not.toContain('sk-super-secret')
    expect('value' in created).toBe(false)

    // The client exposes no resolve/read method for a stored secret.
    expect(Object.keys(credentialApi)).not.toContain('resolve')
  })
})
