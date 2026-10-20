import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { ApiError, credentialApi, projectApi, targetApi } from '../api/client'
import type { Credential, Project, Target, TargetProvider } from '../api/types'
import {
  Alert,
  ConfirmDialog,
  EmptyState,
  Field,
  Loading,
  PageHeader,
} from '../components/Primitives'
import { CrosshairIcon, KeyIcon, PlusIcon, TrashIcon } from '../components/icons'
import { formatDate, shortId } from '../lib/format'

const PROVIDERS: Array<{
  value: TargetProvider
  label: string
  /** Show a model chooser at all. */
  hasModel: boolean
  /** The model identifier is required to run this provider. */
  needsModel: boolean
}> = [
  { value: 'openai_compatible', label: 'OpenAI-compatible API', hasModel: true, needsModel: true },
  { value: 'ollama', label: 'Ollama', hasModel: true, needsModel: true },
  // Custom REST endpoints have no standard listing API, but the common
  // conventions are probed so the tester can still pick from a list; the
  // model stays optional there.
  { value: 'custom_rest', label: 'Custom REST endpoint', hasModel: true, needsModel: false },
]

/** Human-readable provider label for lists and cards. */
export function providerLabel(provider: TargetProvider | string): string {
  return PROVIDERS.find((option) => option.value === provider)?.label ?? provider
}

/** Redacted placeholder shown wherever a secret value would otherwise appear. */
export const REDACTED = '••••••••'

/**
 * A worked endpoint example per provider.
 *
 * The endpoint is a base URL and Aegis Vuldris appends the request path, which is
 * the most common misconfiguration: pasting the full completion URL produces a
 * doubled path and an HTTP 404 that is hard to diagnose from the UI.
 */
function endpointExample(provider: TargetProvider): string {
  switch (provider) {
    case 'openai_compatible':
      return 'Aegis Vuldris adds /chat/completions. e.g. https://openrouter.ai/api/v1'
    case 'ollama':
      return 'Aegis Vuldris adds /api/chat. e.g. http://localhost:11434'
    default:
      return 'https://host/v1 or the full inference URL'
  }
}

/** Convert a form string to an optional finite number. */
function optionalNumber(value: string): number | null {
  const trimmed = value.trim()
  if (trimmed === '') return null
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? parsed : null
}

export function TargetsPage() {
  const [targets, setTargets] = useState<Target[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const [projectId, setProjectId] = useState('')
  const [name, setName] = useState('')
  const [provider, setProvider] = useState<TargetProvider>('openai_compatible')
  const [endpoint, setEndpoint] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState('')
  const [modelVersion, setModelVersion] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [temperature, setTemperature] = useState('')
  const [topP, setTopP] = useState('')
  const [maxTokens, setMaxTokens] = useState('')
  const [seed, setSeed] = useState('')
  const [modelOptions, setModelOptions] = useState<string[]>([])
  const [fetchingModels, setFetchingModels] = useState(false)
  const [modelFetchError, setModelFetchError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [attested, setAttested] = useState(false)
  const [pendingDelete, setPendingDelete] = useState<Target | null>(null)
  const [deleting, setDeleting] = useState(false)

  // The provider+endpoint+key triple of the most recent discovery request, so
  // a blur that does not change any of them does not refetch.
  const lastDiscoveryKey = useRef('')

  const hasModel = PROVIDERS.find((p) => p.value === provider)?.hasModel ?? false
  const needsModel = PROVIDERS.find((p) => p.value === provider)?.needsModel ?? false

  /**
   * Fetch the model list a provider endpoint advertises ("Test connection").
   *
   * Triggered automatically after the endpoint or API key is entered and when
   * the provider changes, so the model field can offer a chooser instead of
   * expecting the operator to know the exact identifier. The API key is used
   * transiently for the request; it is persisted only when the target itself
   * is created, via the encrypted credential endpoint. Failures are reported
   * but never block creation: manual entry always still works.
   */
  async function fetchModels(
    nextProvider: TargetProvider,
    nextEndpoint: string,
    nextApiKey: string,
    options: { force?: boolean } = {},
  ) {
    const trimmed = nextEndpoint.trim()
    const trimmedKey = nextApiKey.trim()
    const providerHasModel =
      PROVIDERS.find((p) => p.value === nextProvider)?.hasModel ?? false
    if (!providerHasModel) return

    let parsed: URL
    try {
      parsed = new URL(trimmed)
    } catch {
      return
    }
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return

    const key = `${nextProvider}\n${trimmed}\n${trimmedKey}`
    if (!options.force && key === lastDiscoveryKey.current) return
    lastDiscoveryKey.current = key

    setFetchingModels(true)
    setModelFetchError(null)
    try {
      const result = await targetApi.discoverModels({
        provider: nextProvider,
        endpoint: trimmed,
        ...(trimmedKey !== '' ? { api_key: trimmedKey } : {}),
      })
      // A newer request superseded this one; its result owns the UI state.
      if (lastDiscoveryKey.current !== key) return
      setModelOptions(result.models)
      if (result.models.length === 0) {
        setModelFetchError('The provider reported no models.')
      }
    } catch (err) {
      if (lastDiscoveryKey.current !== key) return
      setModelOptions([])
      setModelFetchError(
        err instanceof ApiError
          ? `Could not fetch models: ${err.message}`
          : 'Could not fetch models automatically.',
      )
    } finally {
      if (lastDiscoveryKey.current === key) setFetchingModels(false)
    }
  }

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [targetList, projectList] = await Promise.all([
        targetApi.list(),
        projectApi.list(),
      ])
      setTargets(targetList)
      setProjects(projectList)
      if (projectList.length > 0 && projectId === '') {
        setProjectId(projectList[0].id)
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load targets.')
    } finally {
      setLoading(false)
    }
    // projectId intentionally omitted: it is only seeded, never a load input.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function handleCreate(event: FormEvent) {
    event.preventDefault()
    // The backend requires an explicit affirmative attestation, so refuse to
    // submit without it rather than sending a request it will reject.
    if (!attested) {
      setError(
        'Confirm you are authorized to security-test this target before creating it.',
      )
      return
    }
    setCreating(true)
    setError(null)
    const key = apiKey.trim()
    try {
      const created = await targetApi.create({
        project_id: projectId,
        name,
        provider,
        endpoint,
        model: model || null,
        model_version: modelVersion.trim() || null,
        system_prompt: systemPrompt.trim() || null,
        temperature: optionalNumber(temperature),
        top_p: optionalNumber(topP),
        max_tokens: optionalNumber(maxTokens),
        seed: optionalNumber(seed),
        authorization_attestation: true,
      })
      if (key !== '') {
        // One-step setup: store the key with the new target so test runs and
        // future discovery are authenticated. The value is encrypted at rest
        // and can never be read back through the API.
        try {
          await credentialApi.create(created.id, {
            credential_type: 'api_key',
            value: key,
          })
          setNotice('Target created. Its API key is stored encrypted for runs.')
        } catch (err) {
          setError(
            err instanceof ApiError
              ? `Target created, but the API key could not be stored: ${err.message} Add it from the target's page.`
              : "Target created, but the API key could not be stored. Add it from the target's page.",
          )
        }
      } else {
        setNotice('Target created.')
      }
      setName('')
      setEndpoint('')
      setApiKey('')
      setModel('')
      setModelVersion('')
      setSystemPrompt('')
      setTemperature('')
      setTopP('')
      setMaxTokens('')
      setSeed('')
      setModelOptions([])
      setModelFetchError(null)
      lastDiscoveryKey.current = ''
      setAttested(false)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not create target.')
    } finally {
      setCreating(false)
    }
  }

  async function handleDeleteConfirmed() {
    if (!pendingDelete) return
    setDeleting(true)
    try {
      await targetApi.remove(pendingDelete.id)
      setPendingDelete(null)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not delete target.')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <section>
      <PageHeader
        eyebrow="Workspace"
        title="Targets"
        subtitle="A target is the AI system under test. Aegis Vuldris only tests systems you are authorized to assess."
        actions={
          targets.length > 0 ? (
            <span className="count-chip">
              {targets.length} {targets.length === 1 ? 'target' : 'targets'}
            </span>
          ) : undefined
        }
      />

      {error && <Alert kind="error">{error}</Alert>}
      {notice && <Alert kind="success">{notice}</Alert>}

      <div className="split-layout">
        <div>
          {loading ? (
            <div className="card">
              <Loading label="Loading targets…" />
            </div>
          ) : targets.length === 0 ? (
            <EmptyState icon={<CrosshairIcon size={18} />}>
              No targets yet. Create one with the form to start testing a model.
            </EmptyState>
          ) : (
            <ul className="card-list">
              {targets.map((target) => {
                const project = projects.find((p) => p.id === target.project_id)
                return (
                  <li key={target.id} className="card target-card">
                    <div className="card-body">
                      <h3>
                        <CrosshairIcon size={16} />
                        {target.name}
                        <span
                          className={
                            target.status === 'active'
                              ? 'badge badge-active'
                              : 'badge badge-inactive'
                          }
                        >
                          {target.status}
                        </span>
                      </h3>
                      {target.description && <p>{target.description}</p>}
                      <dl className="meta">
                        <div>
                          <dt>Project</dt>
                          <dd>
                            <Link to={`/projects/${target.project_id}`}>
                              {project?.name ?? shortId(target.project_id)}
                            </Link>
                          </dd>
                        </div>
                        <div>
                          <dt>Provider</dt>
                          <dd>{providerLabel(target.provider)}</dd>
                        </div>
                        <div>
                          <dt>Model</dt>
                          <dd>
                            {target.model ?? '—'}
                            {target.model_version ? ` · ${target.model_version}` : ''}
                          </dd>
                        </div>
                        <div>
                          <dt>Added</dt>
                          <dd>{formatDate(target.created_at)}</dd>
                        </div>
                      </dl>
                    </div>
                    <div className="card-actions">
                      <Link className="btn btn-secondary btn-sm" to={`/targets/${target.id}`}>
                        Manage
                      </Link>
                      <button
                        type="button"
                        className="danger sm"
                        onClick={() => setPendingDelete(target)}
                      >
                        <TrashIcon size={14} />
                        Delete
                      </button>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </div>

        <div className="split-side">
          {projects.length > 0 ? (
            <form className="card create-form" onSubmit={handleCreate}>
              <div className="card-header">
                <h2>
                  <PlusIcon size={16} />
                  New target
                </h2>
              </div>

              <Field label="Project" htmlFor="target-project">
                <select
                  id="target-project"
                  name="project"
                  required
                  value={projectId}
                  onChange={(e) => setProjectId(e.target.value)}
                >
                  {projects.map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.name}
                    </option>
                  ))}
                </select>
              </Field>

              <Field label="Name" htmlFor="target-name">
                <input
                  id="target-name"
                  name="name"
                  required
                  maxLength={200}
                  placeholder="Production chatbot"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </Field>

              <Field
                label="Provider"
                htmlFor="target-provider"
                hint="Pick the one matching your endpoint. Hosted OpenAI-compatible APIs (OpenAI, Groq, Together, vLLM) use 'OpenAI-compatible API'; only a local Ollama server uses 'Ollama'. A mismatch returns HTTP 404."
              >
                <select
                  id="target-provider"
                  name="provider"
                  value={provider}
                  onChange={(e) => {
                    const nextProvider = e.target.value as TargetProvider
                    setProvider(nextProvider)
                    // Model identifiers are provider-specific; a list fetched
                    // for the previous provider no longer applies.
                    setModelOptions([])
                    setModelFetchError(null)
                    void fetchModels(nextProvider, endpoint, apiKey)
                  }}
                >
                  {PROVIDERS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </Field>

              <Field
                label="Endpoint"
                htmlFor="target-endpoint"
                hint={
                  provider === 'custom_rest'
                    ? 'Full inference URL, or a base like https://host/v1 — Aegis Vuldris appends /chat/completions when needed and probes /models, /v1/models and /api/tags for the model list.'
                    : `Base URL only. ${endpointExample(provider)}`
                }
              >
                <input
                  id="target-endpoint"
                  name="endpoint"
                  type="url"
                  required
                  placeholder={endpointExample(provider)}
                  value={endpoint}
                  onChange={(e) => {
                    setEndpoint(e.target.value)
                    // The endpoint identifies the model source; a list from
                    // the previous value may not apply to the new one.
                    setModelOptions([])
                    setModelFetchError(null)
                  }}
                  onBlur={() => void fetchModels(provider, endpoint, apiKey)}
                />
              </Field>

              <Field
                label="API key"
                htmlFor="target-api-key"
                hint="Optional. Used as Bearer auth to fetch the model list, then stored encrypted with the target so test runs authenticate. It is never shown again."
              >
                <input
                  id="target-api-key"
                  name="api_key"
                  type="password"
                  autoComplete="off"
                  spellCheck={false}
                  placeholder="sk-…"
                  value={apiKey}
                  onChange={(e) => {
                    setApiKey(e.target.value)
                    // A list fetched without (or with another) key may not
                    // reflect what this key can see.
                    setModelOptions([])
                    setModelFetchError(null)
                  }}
                  onBlur={() => void fetchModels(provider, endpoint, apiKey)}
                />
              </Field>

              {hasModel && (
                <Field label="Model" htmlFor="target-model">
                  <input
                    id="target-model"
                    name="model"
                    list="target-model-options"
                    autoComplete="off"
                    required={needsModel}
                    placeholder="gpt-4o-mini"
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                  />
                  <datalist id="target-model-options">
                    {modelOptions.map((option) => (
                      <option key={option} value={option} />
                    ))}
                  </datalist>
                  <div className="field-status-row">
                    <p
                      className={
                        modelFetchError && !fetchingModels
                          ? 'field-status field-status-error'
                          : 'field-status'
                      }
                      role="status"
                    >
                      {fetchingModels
                        ? 'Fetching models from the provider…'
                        : modelFetchError
                          ? `${modelFetchError} You can still type the model name manually.`
                          : modelOptions.length > 0
                            ? `${modelOptions.length} ${
                                modelOptions.length === 1 ? 'model' : 'models'
                              } available — pick from the list or keep typing to filter.`
                            : 'Enter the endpoint first — Aegis Vuldris fetches the provider’s model list automatically.'}
                    </p>
                    <button
                      type="button"
                      className="secondary sm"
                      disabled={fetchingModels || endpoint.trim() === ''}
                      onClick={() => void fetchModels(provider, endpoint, apiKey, { force: true })}
                    >
                      Test connection
                    </button>
                  </div>
                </Field>
              )}

              <details className="model-profile">
                <summary>Model profile (optional)</summary>
                <p className="field-hint">
                  Record the model revision and generation defaults that should
                  apply to every test. A test case's own value overrides these.
                  The effective profile is snapshotted into each run manifest.
                </p>
                <div className="profile-grid">
                  <Field
                    label="Model version"
                    htmlFor="target-model-version"
                    hint="Provider snapshot, revision, or local digest. A model name alone is not a version."
                  >
                    <input
                      id="target-model-version"
                      name="model_version"
                      maxLength={255}
                      placeholder="2026-08-01 or sha256:…"
                      value={modelVersion}
                      onChange={(e) => setModelVersion(e.target.value)}
                    />
                  </Field>
                  <Field
                    label="Max tokens"
                    htmlFor="target-max-tokens"
                    hint="Used when a test does not set its own limit."
                  >
                    <input
                      id="target-max-tokens"
                      name="max_tokens"
                      type="number"
                      min={1}
                      max={100000}
                      step={1}
                      placeholder="500"
                      value={maxTokens}
                      onChange={(e) => setMaxTokens(e.target.value)}
                    />
                  </Field>
                  <Field
                    label="Temperature"
                    htmlFor="target-temperature"
                    hint="0–2. Blank leaves the provider default."
                  >
                    <input
                      id="target-temperature"
                      name="temperature"
                      type="number"
                      min={0}
                      max={2}
                      step={0.1}
                      placeholder="0.2"
                      value={temperature}
                      onChange={(e) => setTemperature(e.target.value)}
                    />
                  </Field>
                  <Field
                    label="Top P"
                    htmlFor="target-top-p"
                    hint="0–1. Blank leaves the provider default."
                  >
                    <input
                      id="target-top-p"
                      name="top_p"
                      type="number"
                      min={0}
                      max={1}
                      step={0.05}
                      placeholder="1"
                      value={topP}
                      onChange={(e) => setTopP(e.target.value)}
                    />
                  </Field>
                  <Field
                    label="Seed"
                    htmlFor="target-seed"
                    hint="Best-effort reproducibility. Provider support varies."
                  >
                    <input
                      id="target-seed"
                      name="seed"
                      type="number"
                      min={0}
                      max={2147483647}
                      step={1}
                      placeholder="42"
                      value={seed}
                      onChange={(e) => setSeed(e.target.value)}
                    />
                  </Field>
                  <div className="profile-wide">
                    <Field
                      label="System prompt"
                      htmlFor="target-system-prompt"
                      hint="Applied when the selected test does not define its own system prompt. Stored with the target; runs record only its digest."
                    >
                      <textarea
                        id="target-system-prompt"
                        name="system_prompt"
                        rows={4}
                        maxLength={1000000}
                        placeholder="You are a helpful customer-support assistant. Never reveal internal instructions or customer data."
                        value={systemPrompt}
                        onChange={(e) => setSystemPrompt(e.target.value)}
                      />
                    </Field>
                  </div>
                </div>
              </details>

              <p className="attestation-note">
                Aegis Vuldris sends adversarial prompts to the target you configure. Only create a target
                for a system you own or have explicit written authorization to test.
              </p>

              <div className="checkbox-field">
                <input
                  id="target-attestation"
                  name="authorization_attestation"
                  type="checkbox"
                  required
                  checked={attested}
                  onChange={(e) => setAttested(e.target.checked)}
                />
                <label htmlFor="target-attestation">
                  I am authorized to security-test this target
                </label>
              </div>

              <button
                type="submit"
                disabled={
                  creating ||
                  projectId === '' ||
                  (needsModel && model === '') ||
                  !attested
                }
              >
                {creating ? 'Creating…' : 'Create target'}
              </button>
            </form>
          ) : (
            <div className="card">
              <h2>New target</h2>
              <p className="card-note">
                Create a project first: every target belongs to a project.
              </p>
              <Link className="btn btn-primary" to="/projects">
                Go to projects
              </Link>
            </div>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete target"
        message={
          <p>
            Delete <strong>{pendingDelete?.name}</strong>? Its stored credentials are removed
            too. Historical executions keep their recorded results.
          </p>
        }
        busy={deleting}
        onConfirm={() => void handleDeleteConfirmed()}
        onCancel={() => setPendingDelete(null)}
      />
    </section>
  )
}

interface CredentialsPanelProps {
  targetId: string
}

export function CredentialsPanel({ targetId }: CredentialsPanelProps) {
  const [credentials, setCredentials] = useState<Credential[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [credentialType, setCredentialType] = useState('api_key')
  // Held only for the lifetime of the form; cleared on submit and on unmount.
  const [secretValue, setSecretValue] = useState('')
  const [notice, setNotice] = useState<string | null>(null)
  const [pendingRemove, setPendingRemove] = useState<Credential | null>(null)
  const [removing, setRemoving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setCredentials(await credentialApi.list(targetId))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load credentials.')
    } finally {
      setLoading(false)
    }
  }, [targetId])

  useEffect(() => {
    void load()
  }, [load])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setNotice(null)
    try {
      await credentialApi.create(targetId, {
        credential_type: credentialType,
        value: secretValue,
      })
      // Drop the plaintext immediately; it is never needed again in the UI.
      setSecretValue('')
      setNotice('Credential stored. The value is encrypted and cannot be read back.')
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not store credential.')
    }
  }

  async function handleRevoke(credential: Credential) {
    try {
      await credentialApi.revoke(targetId, credential.id)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not revoke credential.')
    }
  }

  async function handleRemoveConfirmed() {
    if (!pendingRemove) return
    setRemoving(true)
    try {
      await credentialApi.remove(targetId, pendingRemove.id)
      setPendingRemove(null)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not remove credential.')
    } finally {
      setRemoving(false)
    }
  }

  return (
    <div className="card">
      <div className="card-header">
        <h2>
          <KeyIcon size={16} />
          Credentials
        </h2>
      </div>
      <p className="card-note">
        Credentials are encrypted at rest with Fernet. Values are write-only — the API never
        returns a stored secret, so it cannot be displayed here.
      </p>

      {error && <Alert kind="error">{error}</Alert>}
      {notice && <Alert kind="success">{notice}</Alert>}

      <form className="inline-form credentials-form" onSubmit={handleSubmit}>
        <Field label="Type" htmlFor="cred-type">
          <input
            id="cred-type"
            name="credentialType"
            list="credential-types"
            value={credentialType}
            onChange={(e) => setCredentialType(e.target.value)}
          />
          <datalist id="credential-types">
            <option value="api_key" />
            <option value="bearer_token" />
            <option value="basic_auth" />
          </datalist>
        </Field>
        <Field label="Secret value" htmlFor="cred-value">
          <input
            id="cred-value"
            name="secretValue"
            type="password"
            required
            autoComplete="off"
            spellCheck={false}
            placeholder="sk-…"
            value={secretValue}
            onChange={(e) => setSecretValue(e.target.value)}
          />
        </Field>
        <button type="submit" disabled={secretValue === ''}>
          Store credential
        </button>
      </form>

      <h3>Stored credentials</h3>
      {loading ? (
        <Loading label="Loading credentials…" />
      ) : credentials.length === 0 ? (
        <EmptyState icon={<KeyIcon size={18} />}>
          No credentials stored for this target.
        </EmptyState>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <caption className="sr-only">Stored credentials for this target</caption>
            <thead>
              <tr>
                <th scope="col">Type</th>
                <th scope="col">Value</th>
                <th scope="col">Version</th>
                <th scope="col">State</th>
                <th scope="col">Added</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {credentials.map((credential) => (
                <tr key={credential.id}>
                  <td>
                    <code className="mono">{credential.credential_type}</code>
                  </td>
                  <td>
                    <code className="mono">{REDACTED}</code>
                  </td>
                  <td>v{credential.version}</td>
                  <td>
                    <span
                      className={
                        credential.revoked
                          ? 'badge badge-inactive'
                          : 'badge badge-active'
                      }
                    >
                      {credential.revoked ? 'Revoked' : 'Active'}
                    </span>
                  </td>
                  <td>
                    <time dateTime={credential.created_at}>
                      {formatDate(credential.created_at)}
                    </time>
                  </td>
                  <td>
                    <div className="actions">
                      {!credential.revoked && (
                        <button
                          type="button"
                          className="secondary sm"
                          onClick={() => void handleRevoke(credential)}
                        >
                          Revoke
                        </button>
                      )}
                      {credential.revoked && (
                        <button
                          type="button"
                          className="danger sm"
                          onClick={() => setPendingRemove(credential)}
                        >
                          Remove
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={pendingRemove !== null}
        title="Remove credential"
        message={
          <p>
            Remove the revoked <strong>{pendingRemove?.credential_type}</strong> credential
            (v{pendingRemove?.version})? This cannot be undone.
          </p>
        }
        confirmLabel="Remove"
        busy={removing}
        onConfirm={() => void handleRemoveConfirmed()}
        onCancel={() => setPendingRemove(null)}
      />
    </div>
  )
}
