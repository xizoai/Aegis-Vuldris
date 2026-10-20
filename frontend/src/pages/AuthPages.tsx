import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'

import { ApiError } from '../api/client'
import { useAuth } from '../auth/useAuth'
import { Alert, Field } from '../components/Primitives'
import { CheckCircleIcon, ShieldIcon } from '../components/icons'

const MIN_PASSWORD_LENGTH = 12

/** Marketing-class hero shown beside the sign-in forms on wide screens. */
function AuthHero() {
  return (
    <div className="auth-hero">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true">
          <ShieldIcon size={20} />
        </span>
        <span className="brand-text">
          <span className="brand-name">Aegis Vuldris</span>
          <span className="brand-tagline">AI model security assurance</span>
        </span>
      </div>

      <div>
        <h2 className="auth-hero-title">
          Assess the security of your AI model endpoints with evidence, not guesswork.
        </h2>
        <p className="auth-hero-copy">
          Point Aegis Vuldris at an OpenAI-compatible, Ollama, or custom REST endpoint and run a
          structured adversarial test suite — every finding carries the exact request and
          response that produced it.
        </p>
        <ul className="auth-feature-list">
          <li>
            <CheckCircleIcon size={16} />
            224 bundled cases: 195 core model-security probes plus experimental RAG and
            agent-oriented prompts
          </li>
          <li>
            <CheckCircleIcon size={16} />
            OWASP GenAI LLM Top 10 2026 mapping, severity scoring, and JSON or Markdown
            reports
          </li>
          <li>
            <CheckCircleIcon size={16} />
            Model profiles, reproducible run manifests, and side-by-side model comparison
          </li>
        </ul>
      </div>

      <p className="auth-hero-footnote">
        Authorized testing only. Only assess systems you own or have explicit written
        authorization to test.
      </p>
    </div>
  )
}

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const from = (location.state as { from?: string } | null)?.from ?? '/projects'

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(email, password)
      navigate(from, { replace: true })
    } catch (err) {
      // Surface the backend's message; it never includes secrets.
      setError(err instanceof ApiError ? err.message : 'Sign in failed. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-page">
      <AuthHero />
      <div className="auth-panel">
        <form className="auth-card" onSubmit={handleSubmit} noValidate>
          <h1>Sign in to Aegis Vuldris</h1>
          <p className="auth-subtitle">Self-hosted, evidence-first security assurance for AI model endpoints</p>

          {error && <Alert kind="error">{error}</Alert>}

          <Field label="Email" htmlFor="email">
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </Field>

          <Field label="Password" htmlFor="password">
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>

          <button type="submit" disabled={submitting}>
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>

          <p className="auth-switch">
            No account? <Link to="/register">Create one</Link>
          </p>
        </form>
      </div>
    </div>
  )
}

export function RegisterPage() {
  const { register } = useAuth()
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const passwordTooShort = password.length > 0 && password.length < MIN_PASSWORD_LENGTH
  const passwordsMismatch = confirmPassword.length > 0 && confirmPassword !== password

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (passwordsMismatch) return
    setError(null)
    setSubmitting(true)
    try {
      await register(email, password)
      navigate('/projects', { replace: true })
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Registration failed. Please try again.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-page">
      <AuthHero />
      <div className="auth-panel">
        <form className="auth-card" onSubmit={handleSubmit} noValidate>
          <h1>Create your account</h1>
          <p className="auth-subtitle">Authorized security testing only</p>

          {error && <Alert kind="error">{error}</Alert>}

          <Field label="Email" htmlFor="reg-email">
            <input
              id="reg-email"
              name="email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </Field>

          <Field
            label="Password"
            htmlFor="reg-password"
            hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}
            error={passwordTooShort ? `Password must be at least ${MIN_PASSWORD_LENGTH} characters.` : undefined}
          >
            <input
              id="reg-password"
              name="password"
              type="password"
              autoComplete="new-password"
              required
              minLength={MIN_PASSWORD_LENGTH}
              aria-describedby="reg-password-hint"
              aria-invalid={passwordTooShort}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>

          <Field
            label="Confirm password"
            htmlFor="reg-confirm"
            error={passwordsMismatch ? 'Passwords do not match.' : undefined}
          >
            <input
              id="reg-confirm"
              name="confirmPassword"
              type="password"
              autoComplete="new-password"
              required
              aria-invalid={passwordsMismatch}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
            />
          </Field>

          <button
            type="submit"
            disabled={submitting || passwordTooShort || passwordsMismatch}
          >
            {submitting ? 'Creating account…' : 'Create account'}
          </button>

          <p className="auth-switch">
            Already registered? <Link to="/login">Sign in</Link>
          </p>
        </form>
      </div>
    </div>
  )
}
