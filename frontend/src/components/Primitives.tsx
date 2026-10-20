import { useEffect, useRef, type ReactNode } from 'react'

import {
  AlertCircleIcon,
  CheckCircleIcon,
  InfoIcon,
  XIcon,
} from './icons'

/** A labeled form field with accessible labelling and error wiring. */
export function Field({
  label,
  htmlFor,
  error,
  hint,
  children,
}: {
  label: string
  htmlFor: string
  error?: string
  hint?: string
  children: ReactNode
}) {
  return (
    <div className="field">
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && !error && (
        <p className="field-hint" id={`${htmlFor}-hint`}>
          {hint}
        </p>
      )}
      {error && (
        <p className="field-error" id={`${htmlFor}-error`} role="alert">
          {error}
        </p>
      )}
    </div>
  )
}

/** Inline alert used for API and form errors. */
export function Alert({ kind, children }: { kind: 'error' | 'info' | 'success'; children: ReactNode }) {
  const Icon = kind === 'error' ? AlertCircleIcon : kind === 'success' ? CheckCircleIcon : InfoIcon
  return (
    <div className={`alert alert-${kind}`} role={kind === 'error' ? 'alert' : 'status'}>
      <span className="alert-icon" aria-hidden="true">
        <Icon size={16} />
      </span>
      <span className="alert-body">{children}</span>
    </div>
  )
}

/** Full-width message shown while data loads. */
export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <p className="loading" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      {label}
    </p>
  )
}

/** Empty-state message for lists with no records. */
export function EmptyState({ children, icon }: { children: ReactNode; icon?: ReactNode }) {
  return (
    <div className="empty-state">
      {icon && (
        <span className="empty-state-icon" aria-hidden="true">
          {icon}
        </span>
      )}
      <p>{children}</p>
    </div>
  )
}

/** Consistent page heading with optional eyebrow, subtitle, and actions. */
export function PageHeader({
  title,
  subtitle,
  eyebrow,
  actions,
}: {
  title: string
  subtitle?: ReactNode
  eyebrow?: string
  actions?: ReactNode
}) {
  return (
    <div className="page-header">
      <div className="page-header-text">
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {subtitle && <p className="page-subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </div>
  )
}

/**
 * Modal confirmation dialog.
 *
 * Replaces `window.confirm` so destructive actions get consistent, styled
 * confirmation. Rendered only when `open` is true and dismissed on Escape or
 * backdrop click; focus moves to the confirm button on open.
 */
export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Delete',
  busy = false,
  onConfirm,
  onCancel,
}: {
  open: boolean
  title: string
  message: ReactNode
  confirmLabel?: string
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  const confirmRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    confirmRef.current?.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onCancel])

  if (!open) return null

  return (
    <div className="dialog-backdrop" onClick={onCancel}>
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="dialog-header">
          <h2 id="confirm-dialog-title">{title}</h2>
          <button
            type="button"
            className="icon-ghost"
            aria-label="Close dialog"
            onClick={onCancel}
          >
            <XIcon size={16} />
          </button>
        </div>
        <div className="dialog-body">{message}</div>
        <div className="dialog-actions">
          <button type="button" className="secondary" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button
            ref={confirmRef}
            type="button"
            className="danger-solid"
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? 'Working…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
