import { useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'

import { ApiError, targetApi } from '../api/client'
import type { Target } from '../api/types'
import { Alert, EmptyState, Field, Loading, PageHeader } from '../components/Primitives'
import { CrosshairIcon, ExternalLinkIcon, SlidersIcon } from '../components/icons'
import { formatDate, formatDateTime, shortId } from '../lib/format'
import { CredentialsPanel, providerLabel } from './TargetsPage'

export function TargetDetailPage() {
  const { targetId } = useParams<{ targetId: string }>()
  const [target, setTarget] = useState<Target | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [toggling, setToggling] = useState(false)

  useEffect(() => {
    if (!targetId) return
    let cancelled = false

    async function load() {
      setLoading(true)
      setError(null)
      try {
        const loaded = await targetApi.get(targetId as string)
        if (!cancelled) setTarget(loaded)
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'Could not load target.')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [targetId])

  /**
   * Flip a target between active and inactive.
   *
   * Deactivating stops new executions from being scheduled against it;
   * reactivating restores it. Historical executions keep their results.
   */
  async function handleStatusToggle() {
    if (!target) return
    setToggling(true)
    setError(null)
    setNotice(null)
    const nextStatus = target.status === 'active' ? 'inactive' : 'active'
    try {
      const updated = await targetApi.update(target.id, { status: nextStatus })
      setTarget(updated)
      setNotice(
        nextStatus === 'active'
          ? 'Target reactivated. New executions can use it again.'
          : 'Target deactivated. New executions cannot use it until it is reactivated.',
      )
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not update the target status.')
    } finally {
      setToggling(false)
    }
  }

  if (loading) return <Loading label="Loading target…" />
  if (error && !target) return <Alert kind="error">{error}</Alert>
  if (!target) return <EmptyState>Target not found.</EmptyState>

  return (
    <section>
      <PageHeader
        eyebrow="Target"
        title={target.name}
        subtitle={target.description ?? undefined}
        actions={
          <button
            type="button"
            className={target.status === 'active' ? 'danger' : undefined}
            onClick={() => void handleStatusToggle()}
            disabled={toggling}
          >
            {toggling
              ? 'Saving…'
              : target.status === 'active'
                ? 'Deactivate target'
                : 'Activate target'}
          </button>
        }
      />

      <p className="meta-line">
        <span
          className={
            target.status === 'active' ? 'badge badge-active' : 'badge badge-inactive'
          }
        >
          {target.status}
        </span>
        <span>
          Updated {formatDateTime(target.updated_at)} · ID{' '}
          <code className="mono">{shortId(target.id)}</code>
        </span>
      </p>

      {error && <Alert kind="error">{error}</Alert>}
      {notice && <Alert kind="success">{notice}</Alert>}

      <div className="card">
        <div className="card-header">
          <h2>
            <SlidersIcon size={16} />
            Configuration
          </h2>
          <Link className="btn btn-secondary btn-sm" to={`/projects/${target.project_id}`}>
            <ExternalLinkIcon size={13} />
            Open project
          </Link>
        </div>
        <dl className="meta">
          <div>
            <dt>Provider</dt>
            <dd>{providerLabel(target.provider)}</dd>
          </div>
          <div>
            <dt>Endpoint</dt>
            <dd>
              <code className="mono">{target.endpoint}</code>
            </dd>
          </div>
          <div>
            <dt>Model</dt>
            <dd>{target.model ?? '—'}</dd>
          </div>
          <div>
            <dt>Model version</dt>
            <dd>{target.model_version ?? 'Not declared'}</dd>
          </div>
          <div>
            <dt>Generation defaults</dt>
            <dd>
              {formatGenerationDefaults(target)}
            </dd>
          </div>
          <div>
            <dt>System prompt</dt>
            <dd>
              {target.system_prompt ? (
                <details>
                  <summary>Configured ({target.system_prompt.length} chars)</summary>
                  <pre className="prompt-preview">{target.system_prompt}</pre>
                </details>
              ) : (
                'Not configured'
              )}
            </dd>
          </div>
          <div>
            <dt>Capabilities</dt>
            <dd>
              {target.capabilities.length > 0 ? (
                <span className="chip-row">
                  {target.capabilities.map((capability) => (
                    <span key={capability} className="badge">
                      {capability}
                    </span>
                  ))}
                </span>
              ) : (
                '—'
              )}
            </dd>
          </div>
          <div>
            <dt>Timeout</dt>
            <dd>{target.timeout_seconds}s</dd>
          </div>
          <div>
            <dt>Rate limit</dt>
            <dd>{target.rate_limit_per_minute}/min</dd>
          </div>
          <div>
            <dt>Added</dt>
            <dd>{formatDate(target.created_at)}</dd>
          </div>
          <div>
            <dt>Authorization</dt>
            <dd>
              {target.authorization_attested_at
                ? `Attested ${formatDate(target.authorization_attested_at)}`
                : 'Not attested'}
            </dd>
          </div>
        </dl>
      </div>

      <CredentialsPanel targetId={target.id} />

      <TargetProfilePanel
        target={target}
        onSaved={(updated) => {
          setTarget(updated)
          setNotice('Model profile saved. New runs will snapshot these settings.')
        }}
      />

      <p className="meta-line">
        <CrosshairIcon size={14} />
        Executions against this target appear inside its project workspace.
      </p>
    </section>
  )
}

/** Render the configured generation defaults, or a provider-default label. */
function formatGenerationDefaults(target: Target): string {
  const values = [
    target.temperature !== null ? `temperature ${target.temperature}` : null,
    target.top_p !== null ? `top_p ${target.top_p}` : null,
    target.max_tokens !== null ? `max_tokens ${target.max_tokens}` : null,
    target.seed !== null ? `seed ${target.seed}` : null,
  ].filter((value): value is string => value !== null)
  return values.length > 0 ? values.join(' · ') : 'Provider defaults'
}

/** Convert a form string to an optional finite number. */
function optionalNumber(value: string): number | null {
  const trimmed = value.trim()
  if (trimmed === '') return null
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? parsed : null
}

/**
 * Edit the model-level profile that applies to every run against this target.
 *
 * Test cases remain the more specific instruction; these values only fill the
 * gaps. Saving does not rewrite historical runs: each execution keeps the
 * manifest captured when it started.
 */
function TargetProfilePanel({
  target,
  onSaved,
}: {
  target: Target
  onSaved: (target: Target) => void
}) {
  const [modelVersion, setModelVersion] = useState(target.model_version ?? '')
  const [systemPrompt, setSystemPrompt] = useState(target.system_prompt ?? '')
  const [temperature, setTemperature] = useState(
    target.temperature !== null ? String(target.temperature) : '',
  )
  const [topP, setTopP] = useState(target.top_p !== null ? String(target.top_p) : '')
  const [maxTokens, setMaxTokens] = useState(
    target.max_tokens !== null ? String(target.max_tokens) : '',
  )
  const [seed, setSeed] = useState(target.seed !== null ? String(target.seed) : '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const updated = await targetApi.update(target.id, {
        model_version: modelVersion.trim() || null,
        system_prompt: systemPrompt.trim() || null,
        temperature: optionalNumber(temperature),
        top_p: optionalNumber(topP),
        max_tokens: optionalNumber(maxTokens),
        seed: optionalNumber(seed),
      })
      onSaved(updated)
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Could not save the model profile.',
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="card" onSubmit={(event) => void handleSubmit(event)}>
      <div className="card-header">
        <h2>
          <SlidersIcon size={16} />
          Model profile
        </h2>
      </div>
      <p className="card-note">
        Pin the model revision and generation settings used for assessment. A
        test case&apos;s own value wins; otherwise these defaults apply. Every
        run records the effective profile in its manifest.
      </p>

      {error && <Alert kind="error">{error}</Alert>}

      <div className="profile-grid">
        <Field
          label="Model version"
          htmlFor="profile-model-version"
          hint="Provider snapshot, revision, or local digest."
        >
          <input
            id="profile-model-version"
            maxLength={255}
            placeholder="2026-08-01 or sha256:…"
            value={modelVersion}
            onChange={(e) => setModelVersion(e.target.value)}
          />
        </Field>
        <Field
          label="Max tokens"
          htmlFor="profile-max-tokens"
          hint="Used when a test does not set its own limit."
        >
          <input
            id="profile-max-tokens"
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
          htmlFor="profile-temperature"
          hint="0–2. Blank leaves the provider default."
        >
          <input
            id="profile-temperature"
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
          htmlFor="profile-top-p"
          hint="0–1. Blank leaves the provider default."
        >
          <input
            id="profile-top-p"
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
          htmlFor="profile-seed"
          hint="Best-effort reproducibility. Provider support varies."
        >
          <input
            id="profile-seed"
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
            htmlFor="profile-system-prompt"
            hint="Applied when the selected test does not define its own system prompt. Runs record only its digest."
          >
            <textarea
              id="profile-system-prompt"
              rows={5}
              maxLength={1000000}
              placeholder="You are a helpful customer-support assistant. Never reveal internal instructions or customer data."
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
            />
          </Field>
        </div>
      </div>

      <div className="profile-actions">
        <button type="submit" disabled={saving}>
          {saving ? 'Saving…' : 'Save profile'}
        </button>
      </div>
    </form>
  )
}
