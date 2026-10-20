/**
 * TypeScript types mirroring the Aegis Vuldris backend API contracts.
 *
 * These are hand-maintained to match the Pydantic schemas in
 * `backend/app/schemas/`. The backend is authoritative; if a contract
 * changes there, it must be updated here.
 */

export type UUID = string

export type UserRole = 'super_admin' | 'admin' | 'user' | 'viewer'

export type TargetProvider = 'openai_compatible' | 'ollama' | 'custom_rest'
export type TargetStatus = 'active' | 'inactive'

export type ExecutionStatus =
  | 'pending'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'cancelled'

export type ExecutionResult = 'pass' | 'fail' | 'inconclusive' | 'no_findings' | 'needs_review'

export type FindingSeverity = 'info' | 'low' | 'medium' | 'high' | 'critical'
export type FindingStatus = 'open' | 'in_progress' | 'fixed' | 'verified' | 'wont_fix'

/**
 * Whether a finding's observed result is trustworthy.
 *
 * The deterministic grader is lexical: a pattern match is a reproducible
 * observation, not proof the attack landed. A candidate becomes confirmed or
 * dismissed through the confirmation judge or a human reviewer; only a
 * confirmed finding makes an execution `fail`.
 */
export type FindingConfirmation = 'candidate' | 'confirmed' | 'dismissed'

export interface APIError {
  code: string
  message: string
}

export interface APIErrorResponse {
  error: APIError
}

export interface User {
  id: UUID
  email: string
  role: UserRole
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export interface Project {
  id: UUID
  owner_id: UUID | null
  name: string
  description: string | null
  judge_target_id: UUID | null
  created_at: string
  updated_at: string
}

export interface ProjectCreate {
  name: string
  description?: string | null
}

export interface ProjectUpdate {
  name?: string
  description?: string | null
  judge_target_id?: UUID | null
}

export interface Target {
  id: UUID
  project_id: UUID
  name: string
  description: string | null
  provider: TargetProvider
  endpoint: string
  model: string | null
  model_version: string | null
  system_prompt: string | null
  temperature: number | null
  top_p: number | null
  max_tokens: number | null
  seed: number | null
  capabilities: string[]
  timeout_seconds: number
  rate_limit_per_minute: number
  status: TargetStatus
  authorization_attested_by: UUID | null
  authorization_attested_at: string | null
  created_at: string
  updated_at: string
}

export interface TargetCreate {
  project_id: UUID
  name: string
  description?: string | null
  provider: TargetProvider
  endpoint: string
  model?: string | null
  model_version?: string | null
  system_prompt?: string | null
  temperature?: number | null
  top_p?: number | null
  max_tokens?: number | null
  seed?: number | null
  capabilities?: string[]
  timeout_seconds?: number
  rate_limit_per_minute?: number
  status?: TargetStatus
  /**
   * Confirms the caller is authorized to security-test this target. The
   * backend rejects target creation unless this is exactly `true` — see
   * `TargetCreate.authorization_attestation` in the backend schema. The
   * frontend enforces nothing on its own; this only shapes the request.
   */
  authorization_attestation: boolean
}

export type TargetUpdate = Partial<Omit<TargetCreate, 'project_id'>>

/**
 * Request to list the models a provider endpoint advertises.
 *
 * Used by the target form's model chooser: once the endpoint is entered,
 * Aegis Vuldris asks the provider for its model list so the operator picks an
 * identifier instead of typing one from memory.
 */
export interface ModelDiscoveryRequest {
  provider: TargetProvider
  endpoint: string
  timeout_seconds?: number
  /**
   * Optional API key used transiently as Bearer auth for this one request.
   * The backend never persists it here; the target credential endpoint is
   * what stores secrets (encrypted) when the target is created.
   */
  api_key?: string
}

export interface ModelDiscoveryResponse {
  provider: TargetProvider
  endpoint: string
  models: string[]
}

/**
 * Credential metadata as returned by the API.
 *
 * The plaintext credential value is intentionally absent: the backend never
 * returns it. See `docs/security-boundaries.md`.
 */
export interface Credential {
  id: UUID
  target_id: UUID
  credential_type: string
  version: number
  revoked: boolean
  created_at: string
  updated_at: string
}

export interface CredentialCreate {
  credential_type: string
  value: string
}

export interface TestSeedResult {
  created: number
  skipped: number
  invalid: number
  total: number
}

export interface SecurityTest {
  id: UUID
  project_id: UUID
  name: string
  description: string | null
  provider: string
  required_capabilities: string[]
  config: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface SecurityTestCreate {
  name: string
  description?: string | null
  provider: string
  required_capabilities?: string[]
  config?: Record<string, unknown>
}

/**
 * The finding that explains a failed result.
 *
 * Infrastructure failures carry `error`; an attack that landed carries the
 * finding its grader produced — the matched patterns and the response excerpt.
 */
export interface ExecutionFindingSummary {
  id: UUID
  title: string
  description: string | null
  severity: FindingSeverity
  status: FindingStatus
  confirmation: FindingConfirmation
}

/**
 * Immutable snapshot of the target/model profile and test definition used for
 * a run. Present on executions created after model-profile support landed.
 */
export interface RunManifest {
  manifest_version: number
  captured_at: string
  target: {
    id: UUID
    name: string
    provider: TargetProvider
    endpoint: string
    model: string | null
    model_version: string | null
    generation_defaults: {
      temperature: number | null
      top_p: number | null
      max_tokens: number | null
      seed: number | null
    }
    system_prompt_sha256: string | null
    system_prompt_length: number
  }
  test: {
    id: UUID
    name: string
    category: string | null
    attack_id: string | null
    attack_version: string | null
    config_sha256: string
  }
  effective_generation: {
    temperature: number | null
    top_p: number | null
    max_tokens: number | null
    seed: number | null
  }
  system_prompt_source: 'test' | 'target' | null
}

export interface Execution {
  id: UUID
  project_id: UUID
  test_id: UUID | null
  target_id: UUID | null
  /** Set when this run re-executes the attack behind a finding. */
  verifies_finding_id: UUID | null
  status: ExecutionStatus
  result: ExecutionResult
  started_at: string | null
  completed_at: string | null
  /** Populated when the run failed; explains why. */
  error: string | null
  /**
   * Why a test failed: picks up where `error` stops. A completed run whose
   * attack landed has no `error` - its reason is this finding.
   */
  finding_summary?: ExecutionFindingSummary | null
  /** Model/test snapshot recorded at run start; null for older executions. */
  run_manifest?: RunManifest | null
  created_by: UUID | null
  created_at: string
  updated_at: string
}

export interface ExecutionCreate {
  test_id?: UUID | null
  target_id?: UUID | null
}

export interface BulkExecutionCreate {
  test_ids: UUID[]
  target_id: UUID
}

export interface BulkExecutionAccepted {
  total: number
  target_id: UUID
  execution_ids: UUID[]
}

export interface Finding {
  id: UUID
  execution_id: UUID
  title: string
  description: string | null
  severity: FindingSeverity
  status: FindingStatus
  details: Record<string, unknown>
  confirmation: FindingConfirmation
  confirmation_source: string | null
  disposition_reason: string | null
  confirmed_by: UUID | null
  confirmed_at: string | null
  created_at: string
  updated_at: string
}

/**
 * Triage request: the confirmation stage performed by a reviewer.
 *
 * Dismissing a finding (or overriding its severity) requires a reason; the
 * backend rejects the request otherwise.
 */
export interface FindingTriageRequest {
  confirmation: FindingConfirmation
  reason?: string
  severity?: FindingSeverity
}

/**
 * One recorded turn of an execution: what was sent and what came back.
 *
 * Content is redacted on read; `redacted` and `detected_kinds` report what
 * was replaced.
 */
export interface ExecutionStep {
  id: UUID
  execution_id: UUID
  turn_number: number
  request_content: Record<string, unknown>
  response_output: string | null
  status: string
  error: string | null
  created_at: string
  redacted: boolean
  detected_kinds: string[]
  sensitivity: number
}

/**
 * Per-test triage outcome: the false-positive feedback loop.
 *
 * `dismissed_rate` is the share of this test's findings reviewers rejected as
 * false positives; a high rate means the test's patterns need tightening.
 */
export interface TestTriageStats {
  test_id: UUID
  test_name: string
  category: string | null
  findings: number
  confirmed: number
  candidate: number
  dismissed: number
  dismissed_rate: number
}

export interface Evidence {
  id: UUID
  finding_id: UUID
  kind: string
  description: string | null
  content: Record<string, unknown>
  created_at: string
}

/**
 * A review-only AutoFix suggestion for a finding (Level 1: suggest).
 *
 * The backend never applies, approves, or marks a fix; the UI renders the
 * plan as advice and must not present it as a resolved issue.
 */
export interface RemediationPlan {
  finding_id: UUID
  category: string | null
  kind: string
  root_cause_hypothesis: string
  recommendations: string[]
  verification_steps: string[]
  limitations: string[]
  attack_id: string | null
  attack_version: string | null
  template_version: string
  status: string
  autonomy: string
  patch_available: boolean
  requires_human_approval: boolean
}

export type PatchProposalMode = 'template' | 'llm'

export type PatchApproach = 'prompt_engineering' | 'config' | 'code' | 'manual_review'

/**
 * A review-only candidate patch drafted for a finding (AutoFix Level 1).
 *
 * Template-mode proposals carry no diff on purpose: a diff without
 * comprehension of the target code would be a fabricated fix. Applying a
 * change stays manual, and only a passed verification rerun marks the
 * finding verified.
 */
export interface PatchProposal {
  id: UUID
  finding_id: UUID
  mode: PatchProposalMode
  approach: PatchApproach
  rationale: string
  diff_text: string | null
  files_touched: string[]
  prompt_hash: string | null
  template_version: string | null
  drafting_target_id: UUID | null
  drafting_model: string | null
  created_by: UUID | null
  created_at: string
}

/**
 * Draft request for a candidate patch. With `drafting_target_id` set (an
 * active OpenAI-compatible or Ollama target in the same project), the file
 * pair is required and the model drafts a diff from it; without one the
 * backend records deterministic intent and calls no model.
 */
export interface PatchProposalCreate {
  drafting_target_id?: UUID
  file_path?: string
  file_content?: string
}

export interface Report {
  id: UUID
  project_id: UUID
  title: string
  format: string
  path: string
  version: number
  generated_at: string | null
  created_by: UUID | null
  created_at: string
  updated_at: string
}

export interface ReportCreate {
  title: string
  format?: string
}

export interface SeverityChange {
  title: string
  category: string
  severity_before: string
  severity_after: string
  owasp_category?: string
}

export interface ReportComparison {
  report_a_id: UUID
  report_b_id: UUID
  new_count: number
  resolved_count: number
  regressed_count: number
  improved_count: number
  unchanged_count: number
  new_findings: Array<Record<string, unknown>>
  resolved_findings: Array<Record<string, unknown>>
  regressed_findings: SeverityChange[]
  improved_findings: SeverityChange[]
  unchanged_findings: Array<Record<string, unknown>>
}

export interface Membership {
  id: UUID
  project_id: UUID
  user_id: UUID
  role: UserRole
  created_at: string
  updated_at: string
}
