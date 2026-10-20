/**
 * Small display formatters shared across pages.
 *
 * These only shape presentation; no parsing or validation happens here.
 */

const DATE_TIME_FORMAT = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'short',
})

const DATE_FORMAT = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' })

/** Render an ISO timestamp as a compact local date and time. */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : DATE_TIME_FORMAT.format(parsed)
}

/** Render an ISO timestamp as a compact local date. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : DATE_FORMAT.format(parsed)
}

/** Short, human-readable form of a UUID for compact metadata rows. */
export function shortId(value: string | null | undefined): string {
  if (!value) return '—'
  return value.slice(0, 8)
}

/** Up to two uppercase initials for avatar placeholders. */
export function initials(value: string | null | undefined): string {
  if (!value) return '?'
  return value.trim().slice(0, 2).toUpperCase()
}

/** Turn snake_case identifiers into readable labels: `no_findings` → `no findings`. */
export function humanize(value: string): string {
  return value.replaceAll('_', ' ')
}
