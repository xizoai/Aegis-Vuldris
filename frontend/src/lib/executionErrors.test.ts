import { describe, expect, it } from 'vitest'

import { explainExecutionError } from './executionErrors'

describe('explainExecutionError', () => {
  it('returns null when there is no error', () => {
    expect(explainExecutionError(null)).toBeNull()
    expect(explainExecutionError(undefined)).toBeNull()
    expect(explainExecutionError('')).toBeNull()
  })

  it('explains an undecryptable credential', () => {
    // The exact error that produced repeated unexplained failures.
    const result = explainExecutionError('credential could not be decrypted')
    expect(result?.cause).toMatch(/can no longer be read/i)
    expect(result?.action).toMatch(/store the API key again/i)
  })

  it('explains a 404 as a provider/endpoint mismatch', () => {
    const result = explainExecutionError('model provider returned HTTP 404')
    expect(result?.cause).toMatch(/not found/i)
    expect(result?.action).toMatch(/OpenAI-compatible API/i)
  })

  it('explains a 401 as a bad key', () => {
    const result = explainExecutionError('model provider returned HTTP 401')
    expect(result?.cause).toMatch(/rejected the API key/i)
  })

  it('explains rate limiting', () => {
    const result = explainExecutionError('model provider returned HTTP 429')
    expect(result?.cause).toMatch(/rate limiting/i)
  })

  it('explains the SSRF guard', () => {
    const result = explainExecutionError(
      'target endpoint is not permitted: local and private target addresses are blocked',
    )
    expect(result?.cause).toMatch(/SSRF/i)
    expect(result?.action).toMatch(/ALLOW_LOCAL_TARGETS/i)
  })

  it('explains an unparseable provider response', () => {
    const result = explainExecutionError('model provider returned invalid JSON')
    expect(result?.cause).toMatch(/could not parse/i)
  })

  it('explains a timeout', () => {
    const result = explainExecutionError('model provider request timed out')
    expect(result?.cause).toMatch(/did not respond in time/i)
  })

  it('falls back to the raw error so nothing is hidden', () => {
    const result = explainExecutionError('something entirely unexpected happened')
    expect(result?.cause).toBe('The execution failed')
    expect(result?.action).toBe('something entirely unexpected happened')
  })
})
