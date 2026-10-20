/**
 * Translate a provider/adapter failure into something a user can act on.
 *
 * The backend reports failures as short internal phrases, which are precise
 * but not obvious to someone looking at a table of executions. Mapping the
 * common ones to a cause and a next step turns "failed" into a fix.
 */

interface ErrorExplanation {
  cause: string
  action: string
}

const EXPLANATIONS: Array<[RegExp, ErrorExplanation]> = [
  [
    /could not be decrypted/i,
    {
      cause: 'The stored credential can no longer be read',
      action:
        'The encryption key changed after this credential was saved. Revoke it and store the API key again.',
    },
  ],
  [
    /HTTP 401/i,
    {
      cause: 'The model provider rejected the API key',
      action: 'Check the credential stored on this target, or that the key is still active.',
    },
  ],
  [
    /HTTP 403/i,
    {
      cause: 'The model provider refused the request',
      action: 'The key may lack access to this model, or the provider blocked the request.',
    },
  ],
  [
    /HTTP 404/i,
    {
      cause: 'The endpoint path was not found',
      action: 'The provider is probably wrong for this URL. Use "OpenAI-compatible API" for hosted APIs and "Ollama" only for a local Ollama server.',
    },
  ],
  [
    /HTTP 429/i,
    {
      cause: 'The model provider is rate limiting',
      action: 'Wait a moment, or lower the target rate limit and run fewer tests at once.',
    },
  ],
  [
    /HTTP 5\d\d/i,
    {
      cause: 'The model provider returned a server error',
      action: 'This is a provider-side outage. Retry later.',
    },
  ],
  [
    /invalid JSON/i,
    {
      cause: 'The provider returned a response Aegis Vuldris could not parse',
      action: 'Confirm the provider is correct for this endpoint; some return streaming or non-JSON payloads.',
    },
  ],
  [
    /timed out|timeout/i,
    {
      cause: 'The model provider did not respond in time',
      action: 'Raise the target timeout, or use a smaller/faster model.',
    },
  ],
  [
    /not permitted|private target|local and private/i,
    {
      cause: 'The SSRF guard blocked this address',
      action:
        'Loopback and private addresses are blocked by design. A local model needs ALLOW_LOCAL_TARGETS=true.',
    },
  ],
  [
    /redirect/i,
    {
      cause: 'The endpoint tried to redirect',
      action: 'Use the final URL directly rather than one that redirects.',
    },
  ],
  [
    /connection|unreachable|failed to connect/i,
    {
      cause: 'Aegis Vuldris could not reach the endpoint',
      action: 'Check the endpoint URL and that the model server is running.',
    },
  ],
]

export function explainExecutionError(error: string | null | undefined): ErrorExplanation | null {
  if (!error) return null
  for (const [pattern, explanation] of EXPLANATIONS) {
    if (pattern.test(error)) return explanation
  }
  return { cause: 'The execution failed', action: error }
}
