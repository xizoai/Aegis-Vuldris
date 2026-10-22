import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'

import {
  ApiError,
  executionApi,
  findingApi,
  projectApi,
  reportApi,
  targetApi,
  testApi,
} from '../api/client'
import { explainExecutionError } from '../lib/executionErrors'
import type {
  Evidence,
  Execution,
  ExecutionStep,
  Finding,
  FindingConfirmation,
  FindingStatus,
  PatchProposal,
  PatchProposalCreate,
  Project,
  RemediationPlan,
  Report,
  ReportComparison,
  RunManifest,
  SecurityTest,
  Target,
  TestTriageStats,
} from '../api/types'
import { Alert, ConfirmDialog, EmptyState, Loading } from '../components/Primitives'
import {
  ActivityIcon,
  BeakerIcon,
  BookIcon,
  CheckCircleIcon,
  ClockIcon,
  DownloadIcon,
  FileTextIcon,
  GaugeIcon,
  PlayIcon,
  RefreshIcon,
  SlidersIcon,
  SparklesIcon,
} from '../components/icons'
import { formatDate, formatDateTime, shortId } from '../lib/format'

/**
 * Project workspace: run executions, inspect findings and evidence, and
 * generate or download reports.
 */
export function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const id = projectId as string

  const [project, setProject] = useState<Project | null>(null)
  const [tests, setTests] = useState<SecurityTest[]>([])
  const [targets, setTargets] = useState<Target[]>([])
  const [executions, setExecutions] = useState<Execution[]>([])
  const [reports, setReports] = useState<Report[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  // The project's judge target: the model that grades judge-model tests.
  // Empty string is "none selected"; the API expects null to clear it.
  const [judgeTargetId, setJudgeTargetId] = useState('')
  const [judgeSaving, setJudgeSaving] = useState(false)

  const [selectedTestId, setSelectedTestId] = useState('')
  const [selectedTargetId, setSelectedTargetId] = useState('')
  const [selectedExecutionId, setSelectedExecutionId] = useState<string | null>(null)
  const [findings, setFindings] = useState<Finding[]>([])
  const [evidenceByFinding, setEvidenceByFinding] = useState<Record<string, Evidence[]>>({})
  // AutoFix Level 1: review-only suggestions, fetched on demand per finding.
  const [remediationByFinding, setRemediationByFinding] = useState<Record<string, RemediationPlan>>({})
  const [remediationBusyId, setRemediationBusyId] = useState<string | null>(null)
  const [remediationErrors, setRemediationErrors] = useState<Record<string, string>>({})
  // Candidate patches: drafts for review, fetched and drafted on demand.
  const [patchesByFinding, setPatchesByFinding] = useState<Record<string, PatchProposal[]>>({})
  const [patchBusyId, setPatchBusyId] = useState<string | null>(null)
  const [patchErrors, setPatchErrors] = useState<Record<string, string>>({})
  // Fix lifecycle: the state change and the verification rerun share a busy id.
  const [findingBusyId, setFindingBusyId] = useState<string | null>(null)
  const [reportTitle, setReportTitle] = useState('')
  const [reportFormat, setReportFormat] = useState('json')
  const [seeding, setSeeding] = useState(false)
  const [baselineReportId, setBaselineReportId] = useState('')
  const [currentReportId, setCurrentReportId] = useState('')
  const [latestReportId, setLatestReportId] = useState('')
  const [comparison, setComparison] = useState<ReportComparison | null>(null)
  const [comparing, setComparing] = useState(false)
  // Destructive actions go through a styled confirmation dialog instead of
  // window.confirm, so the wording is consistent and reviewable.
  const [confirmDeleteExecution, setConfirmDeleteExecution] = useState<Execution | null>(null)
  const [confirmClearHistory, setConfirmClearHistory] = useState(false)
  const [destructiveBusy, setDestructiveBusy] = useState(false)

  // Bulk selection. A Set keeps membership checks O(1) and "select all" is a
  // single assignment rather than a loop over every test.
  const [checkedTestIds, setCheckedTestIds] = useState<Set<string>>(new Set())
  const [bulkRunning, setBulkRunning] = useState(false)
  const [bulkExecutionIds, setBulkExecutionIds] = useState<string[]>([])

  // Triage: the human confirmation stage. One review note per finding.
  const [triageReasonByFinding, setTriageReasonByFinding] = useState<Record<string, string>>({})
  // Per-test confirmation outcomes: the false-positive feedback loop.
  const [triageStats, setTriageStats] = useState<TestTriageStats[] | null>(null)
  const [triageStatsBusy, setTriageStatsBusy] = useState(false)
  // Transcripts: the recorded turns of one execution, fetched and collapsed.
  const [transcriptExecutionId, setTranscriptExecutionId] = useState<string | null>(null)
  const [transcriptByExecution, setTranscriptByExecution] = useState<Record<string, ExecutionStep[]>>({})
  const [transcriptBusyId, setTranscriptBusyId] = useState<string | null>(null)
  const [transcriptErrors, setTranscriptErrors] = useState<Record<string, string>>({})
  const [manifestExecutionId, setManifestExecutionId] = useState<string | null>(null)
  const [replayBusyId, setReplayBusyId] = useState<string | null>(null)

  /**
   * Refresh only the executions. Used by the poll loop so status updates do not
   * blank the page or clobber in-progress form input.
   */
  const refreshExecutions = useCallback(async () => {
    setExecutions(await executionApi.list(id))
  }, [id])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [projectDetail, testList, targetList, executionList, reportList] =
        await Promise.all([
          projectApi.get(id),
          testApi.list(id),
          targetApi.list(),
          executionApi.list(id),
          reportApi.list(id),
        ])
      setProject(projectDetail)
      setJudgeTargetId(projectDetail.judge_target_id ?? '')
      setTests(testList)
      const projectTargets = targetList.filter((target) => target.project_id === id)
      const runnableTargets = projectTargets.filter((target) => target.status === 'active')
      setTargets(projectTargets)
      setExecutions(executionList)
      setReports(reportList)
      setSelectedTestId((current) => current || testList[0]?.id || '')
      // Seed the target selection from this project's targets only. Using the
      // unfiltered list here selected another project's target, which the
      // dropdown then could not display and the run silently submitted.
      setSelectedTargetId((current) =>
        runnableTargets.some((target) => target.id === current)
          ? current
          : (runnableTargets[0]?.id ?? ''),
      )
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load project.')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    void load()
  }, [load])

  // Poll while any execution is still in flight, so status and progress update
  // without a manual refresh. The interval is torn down as soon as everything
  // reaches a terminal state, so an idle page makes no further requests.
  const hasActiveExecutions = executions.some(
    (execution) => execution.status === 'pending' || execution.status === 'running',
  )

  /**
   * Bulk progress, derived from the executions the page already polls.
   *
   * The bulk endpoint answers 202, so there is no bulk-specific fetch to drive
   * this. Matching by execution id keeps one source of truth: the same rows the
   * Executions table shows, so the two can never disagree.
   */
  const executionsById = new Map(executions.map((execution) => [execution.id, execution]))
  const bulkRows = bulkExecutionIds.flatMap((executionId) => {
    const execution = executionsById.get(executionId)
    return execution ? [execution] : []
  })
  const bulkFinished = bulkRows.length > 0 && bulkRows.every((row) => row.status !== 'pending' && row.status !== 'running')
  const bulkDoneCount = bulkRows.filter(
    (row) => row.status !== 'pending' && row.status !== 'running',
  ).length

  useEffect(() => {
    if (!hasActiveExecutions) return

    let cancelled = false
    const timer = window.setInterval(() => {
      if (cancelled) return
      refreshExecutions().catch(() => {
        // A transient poll failure should not surface as a page-level error;
        // the next tick will retry.
      })
    }, 2000)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [hasActiveExecutions, refreshExecutions])

  async function handleSeedLibrary() {
    setSeeding(true)
    setError(null)
    setNotice(null)
    try {
      const result = await testApi.seed(id)
      const parts = [`${result.created} tests loaded`]
      if (result.skipped > 0) parts.push(`${result.skipped} already present`)
      setNotice(`Attack library ready: ${parts.join(', ')}.`)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load the attack library.')
    } finally {
      setSeeding(false)
    }
  }

  /**
   * Point the project's judge-model grading at a target, or clear it.
   *
   * A judge target must belong to this project (the API enforces it); the
   * "none" option is sent as null so the API clears the reference.
   */
  async function handleJudgeTargetChange(value: string) {
    setJudgeSaving(true)
    setError(null)
    setNotice(null)
    const previous = judgeTargetId
    setJudgeTargetId(value)
    try {
      const updated = await projectApi.update(id, {
        judge_target_id: value === '' ? null : value,
      })
      setProject(updated)
      setJudgeTargetId(updated.judge_target_id ?? '')
      setNotice(
        updated.judge_target_id === null ? 'Judge target cleared.' : 'Judge target updated.',
      )
    } catch (err) {
      // Revert the optimistic selection so the dropdown never lies about
      // what the server stored.
      setJudgeTargetId(previous)
      setError(err instanceof ApiError ? err.message : 'Could not update the judge target.')
    } finally {
      setJudgeSaving(false)
    }
  }

  async function handleRun() {
    setError(null)
    setNotice(null)
    try {
      const execution = await executionApi.create(id, {
        test_id: selectedTestId || null,
        target_id: selectedTargetId || null,
      })
      // 202-style: the execution is queued, so poll it into the running state.
      await executionApi.run(id, execution.id)
      setNotice('Execution queued. It will appear below shortly.')
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not start execution.')
    }
  }

  async function handleCancel(execution: Execution) {
    try {
      await executionApi.cancel(id, execution.id)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not cancel execution.')
    }
  }

  function toggleTest(testId: string) {
    setCheckedTestIds((current) => {
      const next = new Set(current)
      if (next.has(testId)) {
        next.delete(testId)
      } else {
        next.add(testId)
      }
      return next
    })
  }

  function toggleAllTests() {
    setCheckedTestIds((current) =>
      current.size === tests.length ? new Set() : new Set(tests.map((test) => test.id)),
    )
  }

  async function handleBulkRun() {
    setError(null)
    setNotice(null)
    const testIds = tests.filter((test) => checkedTestIds.has(test.id)).map((test) => test.id)
    if (testIds.length === 0 || selectedTargetId === '') {
      setError('Select at least one test and a target.')
      return
    }

    setBulkRunning(true)
    try {
      const accepted = await executionApi.bulk(id, {
        test_ids: testIds,
        target_id: selectedTargetId,
      })
      setBulkExecutionIds(accepted.execution_ids)
      setNotice(
        `${accepted.total} ${accepted.total === 1 ? 'test' : 'tests'} queued. ` +
          'Progress and results appear below as each one finishes.',
      )
      // The 202 only proves the suite was scheduled, so re-read the executions
      // the bulk panel derives its rows from. Without this the panel would sit
      // empty until a poll happened to fire.
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not queue the bulk run.')
    } finally {
      setBulkRunning(false)
    }
  }

  async function handleSelectExecution(executionId: string) {
    setSelectedExecutionId(executionId)
    setFindings([])
    setEvidenceByFinding({})
    setRemediationByFinding({})
    setRemediationErrors({})
    setPatchesByFinding({})
    setPatchErrors({})
    try {
      const list = await findingApi.listForExecution(id, executionId)
      setFindings(list)
      const entries = await Promise.all(
        list.map(async (finding) => {
          const evidence = await findingApi.listEvidence(id, finding.id)
          return [finding.id, evidence] as const
        }),
      )
      setEvidenceByFinding(Object.fromEntries(entries))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load findings.')
    }
  }

  /**
   * Fetch or collapse the review-only AutoFix suggestion for one finding.
   *
   * The plan is cached after the first fetch and collapsed on a second
   * click. It is rendered as advice; nothing here changes the finding.
   */
  async function handleToggleRemediation(finding: Finding) {
    if (remediationByFinding[finding.id]) {
      setRemediationByFinding((current) => {
        const next = { ...current }
        delete next[finding.id]
        return next
      })
      return
    }

    setRemediationBusyId(finding.id)
    setRemediationErrors((current) => {
      const next = { ...current }
      delete next[finding.id]
      return next
    })
    try {
      const plan = await findingApi.getRemediation(id, finding.id)
      setRemediationByFinding((current) => ({ ...current, [finding.id]: plan }))
    } catch (err) {
      setRemediationErrors((current) => ({
        ...current,
        [finding.id]:
          err instanceof ApiError ? err.message : 'Could not load the suggested fix.',
      }))
    } finally {
      setRemediationBusyId(null)
    }
  }

  /**
   * Fetch or collapse the candidate patches for one finding.
   *
   * Patches are drafts for review: they never change code on their own and
   * never change the finding. The list is cached after the first fetch.
   */
  async function handleTogglePatches(finding: Finding) {
    if (patchesByFinding[finding.id]) {
      setPatchesByFinding((current) => {
        const next = { ...current }
        delete next[finding.id]
        return next
      })
      return
    }

    setPatchBusyId(finding.id)
    setPatchErrors((current) => {
      const next = { ...current }
      delete next[finding.id]
      return next
    })
    try {
      const list = await findingApi.listPatches(id, finding.id)
      setPatchesByFinding((current) => ({ ...current, [finding.id]: list }))
    } catch (err) {
      setPatchErrors((current) => ({
        ...current,
        [finding.id]:
          err instanceof ApiError ? err.message : 'Could not load candidate patches.',
      }))
    } finally {
      setPatchBusyId(null)
    }
  }

  /**
   * Draft a candidate patch. Deterministic by default; with a chat-capable
   * target selected, that model drafts a unified diff from the supplied file.
   * The response is a draft: nothing is applied and nothing is verified.
   */
  async function handleGeneratePatch(finding: Finding, payload: PatchProposalCreate) {
    setError(null)
    setNotice(null)
    setPatchBusyId(finding.id)
    setPatchErrors((current) => {
      const next = { ...current }
      delete next[finding.id]
      return next
    })
    try {
      const proposal = await findingApi.createPatch(id, finding.id, payload)
      setPatchesByFinding((current) => ({
        ...current,
        [finding.id]: [...(current[finding.id] ?? []), proposal],
      }))
      setNotice(
        proposal.diff_text
          ? 'Candidate patch drafted. Applying it stays manual; after applying, mark the finding fixed and re-run the attack to verify.'
          : 'Candidate patch recorded without a diff. Template mode states remediation intent only; select a drafting model to produce a diff.',
      )
    } catch (err) {
      setPatchErrors((current) => ({
        ...current,
        [finding.id]:
          err instanceof ApiError ? err.message : 'Could not draft the candidate patch.',
      }))
    } finally {
      setPatchBusyId(null)
    }
  }

  /**
   * Change a finding's fix state. 'verified' is deliberately absent: the
   * backend rejects it, and only a passed verification rerun can set it.
   */
  async function handleFindingStatus(
    finding: Finding,
    status: Exclude<FindingStatus, 'verified'>,
  ) {
    setError(null)
    setNotice(null)
    setFindingBusyId(finding.id)
    try {
      const updated = await findingApi.updateStatus(id, finding.id, status)
      setFindings((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      )
      setNotice(
        status === 'fixed'
          ? 'Marked fixed. That records an applied change; use "Verify fix" to re-run the attack before treating the finding as resolved.'
          : `Finding marked ${status.replace('_', ' ')}.`,
      )
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not update the finding.')
    } finally {
      setFindingBusyId(null)
    }
  }

  /**
   * Queue the deterministic rerun that decides whether the fix is real. The
   * backend marks the finding verified only if the exact attack stops
   * reproducing it; a rerun that still fails leaves the claim unproven.
   */
  async function handleVerifyFix(finding: Finding) {
    setError(null)
    setNotice(null)
    setFindingBusyId(finding.id)
    try {
      await findingApi.requestVerification(id, finding.id)
      setNotice(
        'Verification run queued. It re-executes the exact attack and appears in the executions table; the finding is marked verified only if the rerun no longer reproduces it. Use "Refresh findings" after it finishes.',
      )
      await refreshExecutions()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not start the verification run.')
    } finally {
      setFindingBusyId(null)
    }
  }

  async function handleRefreshFindings() {
    if (!selectedExecutionId) return
    await handleSelectExecution(selectedExecutionId)
  }

  /**
   * Triage: the human confirmation stage.
   *
   * Confirming or dismissing re-grades the run — only confirmed findings make
   * an execution a failure — so the executions table is refreshed afterwards.
   * The reason is required to dismiss (checked here and enforced by the
   * backend) and is kept with the finding so a dismissal can be audited.
   */
  async function handleTriage(finding: Finding, confirmation: FindingConfirmation) {
    setError(null)
    setNotice(null)
    const reason = (triageReasonByFinding[finding.id] ?? '').trim()
    if (confirmation === 'dismissed' && reason === '') {
      setError('A reason is required to dismiss a finding as a false positive.')
      return
    }
    setFindingBusyId(finding.id)
    try {
      const updated = await findingApi.triage(id, finding.id, {
        confirmation,
        ...(reason ? { reason } : {}),
      })
      setFindings((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      )
      setTriageReasonByFinding((current) => {
        const next = { ...current }
        delete next[finding.id]
        return next
      })
      setNotice(
        confirmation === 'confirmed'
          ? 'Confirmed: the attack is treated as landed and the execution is re-graded as a failure.'
          : confirmation === 'dismissed'
            ? 'Dismissed as a false positive. It no longer counts toward the execution verdict or the risk score.'
            : 'Returned to candidate: the match is pending review again.',
      )
      await refreshExecutions()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not triage the finding.')
    } finally {
      setFindingBusyId(null)
    }
  }

  /**
   * Fetch or collapse the recorded transcript of one execution.
   *
   * The backend stores every turn verbatim and redacts secrets on read, so
   * the transcript shows exactly what the target received and answered.
   */
  async function handleToggleTranscript(executionId: string) {
    if (transcriptExecutionId === executionId) {
      setTranscriptExecutionId(null)
      return
    }
    setTranscriptExecutionId(executionId)
    if (transcriptByExecution[executionId]) return

    setTranscriptBusyId(executionId)
    setTranscriptErrors((current) => {
      const next = { ...current }
      delete next[executionId]
      return next
    })
    try {
      const steps = await executionApi.steps(id, executionId)
      setTranscriptByExecution((current) => ({ ...current, [executionId]: steps }))
    } catch (err) {
      setTranscriptErrors((current) => ({
        ...current,
        [executionId]:
          err instanceof ApiError ? err.message : 'Could not load the transcript.',
      }))
    } finally {
      setTranscriptBusyId(null)
    }
  }

  /**
   * Queue a fresh run of the same test and target. The source execution is
   * never overwritten: the replay is a new run with its own result.
   */
  async function handleReplay(execution: Execution) {
    setError(null)
    setNotice(null)
    setReplayBusyId(execution.id)
    try {
      await executionApi.replay(id, execution.id)
      setNotice(
        'Replay queued as a new execution. The source result, findings, and transcript are unchanged.',
      )
      await refreshExecutions()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not queue the replay.')
    } finally {
      setReplayBusyId(null)
    }
  }

  /** Load the per-test confirmation outcomes, worst dismissal rate first. */
  async function handleLoadTriageStats() {
    setTriageStatsBusy(true)
    try {
      setTriageStats(await testApi.triageStats(id))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load triage stats.')
    } finally {
      setTriageStatsBusy(false)
    }
  }

  async function handleCreateReport(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setNotice(null)
    try {
      await reportApi.create(id, { title: reportTitle, format: reportFormat })
      setReportTitle('')
      setNotice('Report created. Generate it to produce the artifact.')
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not create report.')
    }
  }

  async function handleGenerateReport(report: Report) {
    setError(null)
    setNotice(null)
    try {
      const generated = await reportApi.generate(id, report.id)
      setNotice(`Report v${generated.version} generated.`)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not generate report.')
    }
  }

  async function handleCompareReports() {
    if (!baselineReportId || !currentReportId || baselineReportId === currentReportId) {
      setError('Choose two different generated reports to compare.')
      return
    }

    setComparing(true)
    setError(null)
    setNotice(null)
    try {
      const result = await reportApi.compare(id, baselineReportId, currentReportId)
      setComparison(result)
      setNotice('Report comparison is ready.')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not compare reports.')
    } finally {
      setComparing(false)
    }
  }

  async function handleExecutionReport(execution: Execution) {
    setError(null)
    setNotice(null)
    try {
      const report = await reportApi.create(id, {
        title: `Execution ${shortId(execution.id)}`,
        format: 'markdown',
      })
      const generated = await reportApi.generate(id, report.id)
      setLatestReportId(generated.id)
      setNotice(`Report v${generated.version} generated for execution ${shortId(execution.id)}.`)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not generate report.')
    }
  }

  async function handleDownloadLatestReport() {
    if (!latestReportId) return
    const report = reports.find((r) => r.id === latestReportId)
    if (!report) return
    await handleDownloadReport(report)
  }

  async function handleDownloadReport(report: Report) {
    setError(null)
    try {
      const content = await reportApi.download(id, report.id)
      const mime = report.format === 'json' ? 'application/json' : 'text/markdown'
      const extension = report.format === 'json' ? 'json' : 'md'
      const blob = new Blob([content], { type: mime })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `${report.title.replace(/[^a-z0-9-_]+/gi, '-').toLowerCase()}-v${report.version}.${extension}`
      document.body.appendChild(anchor)
      anchor.click()
      document.body.removeChild(anchor)
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not download report.')
    }
  }

  async function handleDeleteExecution(execution: Execution) {
    setConfirmDeleteExecution(execution)
  }

  async function handleDeleteExecutionConfirmed() {
    if (!confirmDeleteExecution) return
    setError(null)
    setNotice(null)
    setDestructiveBusy(true)
    try {
      await executionApi.delete(id, confirmDeleteExecution.id)
      setNotice(`Execution ${confirmDeleteExecution.id} deleted.`)
      setConfirmDeleteExecution(null)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not delete execution.')
    } finally {
      setDestructiveBusy(false)
    }
  }

  async function handleClearHistory() {
    setConfirmClearHistory(true)
  }

  async function handleClearHistoryConfirmed() {
    setError(null)
    setNotice(null)
    setDestructiveBusy(true)
    try {
      const result = await executionApi.clearHistory(id)
      setNotice(`${result.deleted} execution(s) deleted along with findings and evidence.`)
      setConfirmClearHistory(false)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not clear execution history.')
    } finally {
      setDestructiveBusy(false)
    }
  }

  if (loading) return <Loading />
  if (error && !project) return <Alert kind="error">{error}</Alert>
  if (!project) return <EmptyState>Project not found.</EmptyState>

  const projectTargets = targets
  const runnableTargets = projectTargets.filter((target) => target.status === 'active')
  // The run controls stay disabled unless the selected target is confirmed to
  // belong to this project. Backend validation remains authoritative; this only
  // prevents submitting a selection the UI cannot legitimately offer.
  const targetIsProjectScoped = runnableTargets.some(
    (target) => target.id === selectedTargetId,
  )
  const completedExecutions = executions.filter(
    (execution) => execution.status === 'succeeded' || execution.status === 'failed' || execution.status === 'cancelled',
  )
  const coveredTestIds = new Set(
    completedExecutions.flatMap((execution) => (execution.test_id ? [execution.test_id] : [])),
  )
  const coverage = tests.length === 0 ? 0 : Math.round((coveredTestIds.size / tests.length) * 100)
  const failedExecutions = executions.filter((execution) => execution.result === 'fail').length
  const needsReviewExecutions = executions.filter(
    (execution) => execution.result === 'needs_review',
  ).length
  const attentionExecutions = failedExecutions + needsReviewExecutions
  const generatedReports = reports.filter((report) => report.generated_at)

  // Latest successful result per (target, test). This is enough to render a
  // bake-off matrix without another round trip: users run the same suite
  // against each candidate model, then compare the resulting evidence.
  const comparisonExecutions = executions.filter(
    (execution) => execution.status === 'succeeded' && execution.test_id && execution.target_id,
  )
  const latestByTargetTest = new Map<string, Execution>()
  for (const execution of comparisonExecutions) {
    if (!execution.test_id || !execution.target_id) continue
    const key = `${execution.target_id}:${execution.test_id}`
    const previous = latestByTargetTest.get(key)
    if (
      previous === undefined ||
      new Date(execution.created_at).getTime() > new Date(previous.created_at).getTime()
    ) {
      latestByTargetTest.set(key, execution)
    }
  }
  const comparisonTargets = projectTargets.filter((target) =>
    comparisonExecutions.some((execution) => execution.target_id === target.id),
  )
  const comparisonTests = tests.filter((test) =>
    comparisonExecutions.some((execution) => execution.test_id === test.id),
  )

  return (
    <section>
      <div className="page-header">
        <div className="page-header-text">
          <p className="breadcrumb">
            <Link to="/projects">Projects</Link>
            <span className="breadcrumb-sep">/</span>
            {project.name}
          </p>
          <h1>{project.name}</h1>
          {project.description && <p className="page-subtitle">{project.description}</p>}
          <p className="meta-line">
            Created {formatDate(project.created_at)} · ID <code>{shortId(project.id)}</code>
          </p>
        </div>
      </div>

      {error && <Alert kind="error">{error}</Alert>}
      {notice && <Alert kind="success">{notice}</Alert>}

      <section className="overview" aria-labelledby="overview-heading">
        <div className="overview-heading">
          <div>
            <p className="eyebrow">Assessment overview</p>
            <h2 id="overview-heading">Know what needs attention</h2>
          </div>
          <p className="overview-note">A lexical match is a candidate until a judge or a reviewer confirms it; only confirmed findings count as vulnerabilities.</p>
        </div>
        <dl className="metric-grid">
          <div className="metric-card">
            <span className="metric-icon" aria-hidden="true">
              <GaugeIcon size={17} />
            </span>
            <dt>Test coverage</dt>
            <dd>{coverage}<span>%</span></dd>
            <p>{coveredTestIds.size} of {tests.length} tests completed</p>
          </div>
          <div className="metric-card">
            <span className="metric-icon" aria-hidden="true">
              <BeakerIcon size={17} />
            </span>
            <dt>Active targets</dt>
            <dd>{projectTargets.filter((target) => target.status === 'active').length}</dd>
            <p>{projectTargets.length} registered in this project</p>
          </div>
          <div className={attentionExecutions > 0 ? 'metric-card metric-card-alert' : 'metric-card'}>
            <span className="metric-icon" aria-hidden="true">
              <ActivityIcon size={17} />
            </span>
            <dt>Findings needing attention</dt>
            <dd>{attentionExecutions}</dd>
            <p>
              {failedExecutions} confirmed · {needsReviewExecutions} awaiting review
            </p>
          </div>
          <div className="metric-card">
            <span className="metric-icon" aria-hidden="true">
              <FileTextIcon size={17} />
            </span>
            <dt>Report snapshots</dt>
            <dd>{generatedReports.length}</dd>
            <p>Ready for comparison or export</p>
          </div>
        </dl>
      </section>

      <div className="card">
        <div className="card-header">
          <h2>
            <SlidersIcon size={16} />
            Judge model
          </h2>
        </div>
        <p className="card-note">
          Judge-model tests are graded by this project&apos;s judge target. Without one those tests
          return inconclusive rather than guessing, and a model never judges its own answers — pick
          a target other than the one under test, or a different model on the same endpoint.
        </p>
        <div className="inline-form">
          <label htmlFor="judge-target">Judge target</label>
          <select
            id="judge-target"
            value={judgeTargetId}
            disabled={judgeSaving}
            onChange={(e) => void handleJudgeTargetChange(e.target.value)}
          >
            <option value="">None — judge-model tests return inconclusive</option>
            {targets.map((target) => (
              <option key={target.id} value={target.id}>
                {target.name}
              </option>
            ))}
          </select>
          {judgeSaving && <p className="card-note">Saving…</p>}
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h2>
            <BookIcon size={16} />
            Security tests
          </h2>
          {tests.length > 0 && (
            <label className="checkbox-inline" htmlFor="select-all-tests">
              <input
                id="select-all-tests"
                type="checkbox"
                checked={checkedTestIds.size === tests.length}
                ref={(node) => {
                  if (node) {
                    node.indeterminate =
                      checkedTestIds.size > 0 && checkedTestIds.size < tests.length
                  }
                }}
                onChange={toggleAllTests}
              />
              Select all
            </label>
          )}
        </div>
        {tests.length === 0 ? (
          <div className="seed-panel">
            <p>
              This project has no security tests yet. Load the bundled attack library to get 224
              test cases across prompt injection, jailbreak, privacy leakage, RAG, and agent
              tool-use categories.
            </p>
            <button type="button" onClick={() => void handleSeedLibrary()} disabled={seeding}>
              <SparklesIcon size={14} />
              {seeding ? 'Loading library…' : 'Load attack library'}
            </button>
          </div>
        ) : (
          <>
            <p className="card-note">
              {tests.length} {tests.length === 1 ? 'test' : 'tests'} available ·{' '}
              {checkedTestIds.size} selected.
            </p>
            <ul className="checklist">
              {tests.map((test) => (
                <li key={test.id}>
                  <label htmlFor={`test-${test.id}`}>
                    <input
                      id={`test-${test.id}`}
                      type="checkbox"
                      checked={checkedTestIds.has(test.id)}
                      onChange={() => toggleTest(test.id)}
                    />
                    <span>{test.name}</span>
                  </label>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      <div className="card">
        <div className="card-header">
          <h2>
            <PlayIcon size={16} />
            Run a security test
          </h2>
        </div>
        {tests.length === 0 ? (
          <EmptyState>Load the attack library above to enable test runs.</EmptyState>
        ) : (
          <div className="inline-form">
            <label htmlFor="run-test">Test</label>
            <select
              id="run-test"
              value={selectedTestId}
              onChange={(e) => setSelectedTestId(e.target.value)}
            >
              {tests.map((test) => (
                <option key={test.id} value={test.id}>
                  {test.name}
                </option>
              ))}
            </select>

            <label htmlFor="run-target">Target</label>
            <select
              id="run-target"
              value={selectedTargetId}
              onChange={(e) => setSelectedTargetId(e.target.value)}
            >
              {runnableTargets.length === 0 && <option value="">No active targets in project</option>}
              {runnableTargets.map((target) => (
                <option key={target.id} value={target.id}>
                  {target.name}
                </option>
              ))}
            </select>

            <button
              type="button"
              onClick={() => void handleRun()}
              disabled={selectedTestId === '' || !targetIsProjectScoped}
            >
              <PlayIcon size={14} />
              Run test
            </button>
            <button
              type="button"
              className="bulk-run"
              onClick={() => void handleBulkRun()}
              disabled={checkedTestIds.size === 0 || !targetIsProjectScoped || bulkRunning}
            >
              {bulkRunning
                ? 'Queueing…'
                : `Run ${checkedTestIds.size} selected`}
            </button>
            {!targetIsProjectScoped && (
              <p className="inline-warning" role="status">
                {projectTargets.length === 0
                  ? 'Add a target to this project before running a test.'
                  : runnableTargets.length === 0
                    ? 'Reactivate a target in this project before running a test.'
                  : 'Select a target that belongs to this project.'}
              </p>
            )}
          </div>
        )}
      </div>

      <div className="card">
        <div className="card-header">
          <h2>
            <ActivityIcon size={16} />
            Executions
          </h2>
          {hasActiveExecutions && (
            <span className="live-indicator" role="status" aria-live="polite">
              <span className="live-dot" aria-hidden="true" />
              Updating live
            </span>
          )}
          {executions.length > 1 && (
            <button
              type="button"
              className="danger"
              onClick={() => void handleClearHistory()}
            >
              Clear all history
            </button>
          )}
         </div>
        {executions.length === 0 ? (
          <EmptyState>No executions yet.</EmptyState>
        ) : (
          <div className="table-wrap">
          <table className="table executions-table">
            <caption className="sr-only">Executions in this project</caption>
            <thead>
              <tr>
                <th scope="col">Started</th>
                <th scope="col">Status</th>
                <th scope="col">Result</th>
                <th scope="col">Reason</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {executions.map((execution) => {
                return (
                  <>
                  <tr key={execution.id}>
                    <td>
                      <time dateTime={execution.started_at ?? execution.created_at}>
                        {formatDateTime(execution.started_at ?? execution.created_at)}
                      </time>
                    </td>
                    <td>
                      <span className={`badge badge-${execution.status}`}>{execution.status}</span>{' '}
                      {execution.verifies_finding_id && (
                        <span className="badge badge-verification">verification</span>
                      )}
                    </td>
                    <td>
                      <span className={`badge badge-${execution.result}`}>
                        {formatResultLabel(execution.result)}
                      </span>
                    </td>
                    <td className="failure-cell">
                      <ExecutionReason execution={execution} />
                    </td>
                    <td>
                      <div className="executions-actions">
                        <button
                          type="button"
                          className="secondary sm"
                          onClick={() => void handleToggleTranscript(execution.id)}
                        >
                          {transcriptExecutionId === execution.id
                            ? 'Hide transcript'
                            : 'Transcript'}
                        </button>{' '}
                        <button
                          type="button"
                          className="secondary sm"
                          onClick={() => void handleExecutionReport(execution)}
                        >
                          Generate report
                        </button>{' '}
                        <button
                          type="button"
                          className="secondary sm"
                          disabled={!latestReportId}
                          onClick={() => void handleDownloadLatestReport()}
                        >
                          Download report
                        </button>{' '}
                        {execution.run_manifest && (
                          <button
                            type="button"
                            className="secondary sm"
                            onClick={() =>
                              setManifestExecutionId(
                                manifestExecutionId === execution.id ? null : execution.id,
                              )
                            }
                          >
                            {manifestExecutionId === execution.id
                              ? 'Hide model profile'
                              : 'Model profile'}
                          </button>
                        )}{' '}
                        {(execution.status === 'pending' || execution.status === 'running') && (
                          <button type="button" onClick={() => void handleCancel(execution)}>
                            Cancel
                          </button>
                        )}
                        {(execution.status === 'succeeded' ||
                          execution.status === 'failed' ||
                          execution.status === 'cancelled') && (
                          <button
                            type="button"
                            className="secondary sm"
                            disabled={replayBusyId === execution.id}
                            onClick={() => void handleReplay(execution)}
                          >
                            {replayBusyId === execution.id ? 'Queueing…' : 'Replay'}
                          </button>
                        )}
                        <button
                          type="button"
                          className="danger"
                          onClick={() => void handleDeleteExecution(execution)}
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                  {transcriptExecutionId === execution.id && (
                    <tr>
                      <td colSpan={5}>
                        <TranscriptPanel
                          steps={transcriptByExecution[execution.id]}
                          busy={transcriptBusyId === execution.id}
                          error={transcriptErrors[execution.id] ?? null}
                        />
                      </td>
                    </tr>
                  )}
                  {manifestExecutionId === execution.id && (
                    <tr>
                      <td colSpan={5}>
                        <RunManifestPanel
                          manifest={execution.run_manifest ?? null}
                        />
                      </td>
                    </tr>
                  )}
                  </>
                )
              })}
            </tbody>
          </table>
          </div>
        )}
      </div>

      {comparisonTargets.length > 0 && comparisonTests.length > 0 && (
        <div className="card">
          <div className="card-header">
            <h2>
              <GaugeIcon size={16} />
              Model comparison
            </h2>
            <span className="count-chip">
              {comparisonTargets.length} targets · {comparisonTests.length} tests
            </span>
          </div>
          <p className="card-note">
            Latest successful result for each test and target. Run the same suite against
            each candidate model to fill the matrix; a blank cell means that model has not
            been tested with that case.
          </p>
          <div className="table-wrap">
            <table className="table">
              <caption className="sr-only">Model comparison matrix</caption>
              <thead>
                <tr>
                  <th scope="col">Test</th>
                  {comparisonTargets.map((target) => (
                    <th key={target.id} scope="col">
                      <span className="comparison-target">
                        {target.name}
                        <small>
                          {target.model ?? '—'}
                          {target.model_version ? ` · ${target.model_version}` : ''}
                        </small>
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {comparisonTests.map((test) => (
                  <tr key={test.id}>
                    <th scope="row">{test.name}</th>
                    {comparisonTargets.map((target) => {
                      const execution = latestByTargetTest.get(`${target.id}:${test.id}`)
                      return (
                        <td key={target.id}>
                          {execution ? (
                            <span className={`badge badge-${execution.result}`}>
                              {formatResultLabel(execution.result)}
                            </span>
                          ) : (
                            <span className="muted">—</span>
                          )}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {bulkExecutionIds.length > 0 && (
        <div className="card">
          <div className="card-header">
            <h2>
              <GaugeIcon size={16} />
              Bulk run
            </h2>
            <span
              className={bulkFinished ? 'bulk-progress bulk-progress-done' : 'bulk-progress'}
              role="status"
              aria-live="polite"
            >
              {bulkFinished
                ? `${bulkRows.length} of ${bulkExecutionIds.length} finished`
                : `${bulkDoneCount} of ${bulkExecutionIds.length} finished`}
            </span>
          </div>

          <div className="progress-track" role="progressbar" aria-valuemin={0} aria-valuemax={bulkExecutionIds.length} aria-valuenow={bulkDoneCount}>
            <div
              className="progress-fill"
              style={{
                width: `${bulkExecutionIds.length === 0 ? 0 : (bulkDoneCount / bulkExecutionIds.length) * 100}%`,
              }}
            />
          </div>

          {bulkRows.length === 0 ? (
            <EmptyState>Waiting for the first results…</EmptyState>
          ) : (
            <div className="table-wrap">
            <table className="table">
              <caption className="sr-only">Results of the bulk run</caption>
              <thead>
                <tr>
                  <th scope="col">Test</th>
                  <th scope="col">Status</th>
                  <th scope="col">Result</th>
                  <th scope="col">Reason</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {bulkRows.map((execution) => {
                  const testName =
                    tests.find((test) => test.id === execution.test_id)?.name ??
                    (execution.test_id ? 'Deleted test' : 'Unknown test')
                  return (
                    <tr key={execution.id}>
                      <td>{testName}</td>
                      <td>
                        <span className={`badge badge-${execution.status}`}>
                          {execution.status}
                        </span>
                      </td>
                      <td>
                        <span className={`badge badge-${execution.result}`}>
                          {formatResultLabel(execution.result)}
                        </span>
                      </td>
                      <td className="failure-cell">
                        <ExecutionReason execution={execution} />
                      </td>
                      <td>
                        <button
                          type="button"
                          onClick={() => void handleSelectExecution(execution.id)}
                        >
                          Findings
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            </div>
          )}
        </div>
      )}

      <div className="card">
        <div className="card-header">
          <h2>
            <GaugeIcon size={16} />
            Detection quality
          </h2>
          <button
            type="button"
            className="secondary sm"
            disabled={triageStatsBusy}
            onClick={() => void handleLoadTriageStats()}
          >
            {triageStatsBusy ? 'Loading…' : 'Load triage stats'}
          </button>
        </div>
        <p className="card-note">
          Per-test confirmation outcomes, computed from the findings themselves. A test
          whose findings reviewers keep dismissing is producing false positives and its
          patterns should be tightened — the rate is evidence about the detector, not
          about the target.
        </p>
        {triageStats === null ? (
          <EmptyState>Load triage stats to see which tests produce false positives.</EmptyState>
        ) : triageStats.length === 0 ? (
          <EmptyState>No findings recorded yet to triage.</EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <caption className="sr-only">Per-test triage outcomes</caption>
              <thead>
                <tr>
                  <th scope="col">Test</th>
                  <th scope="col">Findings</th>
                  <th scope="col">Confirmed</th>
                  <th scope="col">Unconfirmed</th>
                  <th scope="col">Dismissed</th>
                  <th scope="col">Dismissed rate</th>
                </tr>
              </thead>
              <tbody>
                {triageStats.map((row) => (
                  <tr key={row.test_id}>
                    <td>{row.test_name}</td>
                    <td>{row.findings}</td>
                    <td>{row.confirmed}</td>
                    <td>{row.candidate}</td>
                    <td>{row.dismissed}</td>
                    <td>{Math.round(row.dismissed_rate * 100)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selectedExecutionId && (
        <div className="card">
          <div className="card-header">
            <h2>
              <CheckCircleIcon size={16} />
              Findings
            </h2>
            <button type="button" className="secondary sm" onClick={() => void handleRefreshFindings()}>
              <RefreshIcon size={14} />
              Refresh findings
            </button>
          </div>
          {findings.length === 0 ? (
            <EmptyState>No findings recorded for this execution.</EmptyState>
          ) : (
            findings.map((finding) => (
              <article key={finding.id} className={`finding finding-${finding.severity}`}>
                <div className="finding-header">
                  <h3>{finding.title}</h3>
                  <span className={`badge badge-severity-${finding.severity}`}>
                    {finding.severity}
                  </span>
                </div>
                {finding.description && <p>{finding.description}</p>}
                <FindingResponseExcerpt details={finding.details} />
                <p className="finding-meta">
                  <span className={`badge badge-finding-${finding.status}`}>
                    {finding.status}
                  </span>
                  <span className={`badge badge-confirmation-${finding.confirmation}`}>
                    {finding.confirmation === 'candidate'
                      ? 'unconfirmed'
                      : finding.confirmation}
                  </span>
                  <span>Created {formatDateTime(finding.created_at)}</span>
                </p>
                {finding.disposition_reason && (
                  <p className="finding-disposition">
                    {finding.confirmation === 'dismissed'
                      ? 'Dismissed'
                      : finding.confirmation === 'confirmed'
                        ? 'Confirmed'
                        : 'Reviewed'}
                    {finding.confirmation_source ? ` by ${finding.confirmation_source}` : ''}:{' '}
                    {finding.disposition_reason}
                  </p>
                )}
                {finding.status === 'verified' && (
                  <p className="finding-verified-note">
                    Verified: a re-run of the exact attack no longer reproduces this
                    finding.
                  </p>
                )}
                <h4>Confirmation</h4>
                <p className="card-note">
                  The deterministic match is a candidate until something confirms it.
                  Confirming or dismissing re-grades the execution: only confirmed
                  findings count as failures, and dismissed ones stop counting toward
                  the risk score. A dismissal needs a reason.
                </p>
                <div className="finding-triage">
                  <label htmlFor={`triage-reason-${finding.id}`}>Review note</label>
                  <input
                    id={`triage-reason-${finding.id}`}
                    value={triageReasonByFinding[finding.id] ?? ''}
                    maxLength={500}
                    placeholder="Why? Required to dismiss."
                    onChange={(event) =>
                      setTriageReasonByFinding((current) => ({
                        ...current,
                        [finding.id]: event.target.value,
                      }))
                    }
                  />
                  <button
                    type="button"
                    disabled={findingBusyId === finding.id || finding.confirmation === 'confirmed'}
                    onClick={() => void handleTriage(finding, 'confirmed')}
                  >
                    Confirm attack landed
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    disabled={findingBusyId === finding.id || finding.confirmation === 'dismissed'}
                    onClick={() => void handleTriage(finding, 'dismissed')}
                  >
                    Dismiss as false positive
                  </button>
                  {finding.confirmation !== 'candidate' && (
                    <button
                      type="button"
                      className="secondary"
                      disabled={findingBusyId === finding.id}
                      onClick={() => void handleTriage(finding, 'candidate')}
                    >
                      Reset to candidate
                    </button>
                  )}
                </div>
                <div className="finding-actions">
                  <label htmlFor={`finding-status-${finding.id}`}>Fix state</label>
                  <select
                    id={`finding-status-${finding.id}`}
                    value={finding.status}
                    disabled={findingBusyId === finding.id}
                    onChange={(event) =>
                      void handleFindingStatus(
                        finding,
                        event.target.value as Exclude<FindingStatus, 'verified'>,
                      )
                    }
                  >
                    <option value="open">open</option>
                    <option value="in_progress">in progress</option>
                    <option value="fixed">fixed (applied, unverified)</option>
                    <option value="wont_fix">won&apos;t fix</option>
                    {finding.status === 'verified' && (
                      <option value="verified" disabled>
                        verified (proven by a re-run)
                      </option>
                    )}
                  </select>
                  {finding.status === 'fixed' && (
                    <button
                      type="button"
                      onClick={() => void handleVerifyFix(finding)}
                      disabled={findingBusyId === finding.id}
                    >
                      {findingBusyId === finding.id ? 'Working…' : 'Verify fix (re-run attack)'}
                    </button>
                  )}
                </div>

                <h4>Evidence</h4>
                {(evidenceByFinding[finding.id] ?? []).length === 0 ? (
                  <EmptyState>No evidence attached.</EmptyState>
                ) : (
                  (evidenceByFinding[finding.id] ?? []).map((item) => (
                    <details key={item.id} className="evidence">
                      <summary>
                        {item.kind} — {item.description ?? 'no description'}
                      </summary>
                      <pre>{JSON.stringify(item.content, null, 2)}</pre>
                    </details>
                  ))
                )}

                <h4>Suggested fix</h4>
                <p className="card-note">
                  Review-only suggestion (AutoFix Level 1). It does not change code,
                  configuration, or this finding, and it is not evidence that the issue
                  is resolved.
                </p>
                <button
                  type="button"
                  onClick={() => void handleToggleRemediation(finding)}
                  disabled={remediationBusyId === finding.id}
                >
                  {remediationByFinding[finding.id]
                    ? 'Hide suggested fix'
                    : remediationBusyId === finding.id
                      ? 'Loading plan…'
                      : 'View suggested fix'}
                </button>
                {remediationErrors[finding.id] && (
                  <p className="inline-warning" role="alert">
                    {remediationErrors[finding.id]}
                  </p>
                )}
                {remediationByFinding[finding.id] && (
                  <RemediationPanel plan={remediationByFinding[finding.id]} />
                )}

                <h4>Candidate patch</h4>
                <p className="card-note">
                  Draft for review (AutoFix Level 1). Drafting records a proposal only;
                  applying the change and marking the finding fixed stay manual, and only
                  a rerun that stops reproducing the attack marks it verified.
                </p>
                <button
                  type="button"
                  onClick={() => void handleTogglePatches(finding)}
                  disabled={patchBusyId === finding.id}
                >
                  {patchesByFinding[finding.id]
                    ? 'Hide candidate patch'
                    : patchBusyId === finding.id
                      ? 'Loading patches…'
                      : 'View candidate patch'}
                </button>
                {patchErrors[finding.id] && (
                  <p className="inline-warning" role="alert">
                    {patchErrors[finding.id]}
                  </p>
                )}
                {patchesByFinding[finding.id] && (
                  <PatchPanel
                    findingId={finding.id}
                    proposals={patchesByFinding[finding.id]}
                    targets={targets}
                    busy={patchBusyId === finding.id}
                    onGenerate={(payload) => void handleGeneratePatch(finding, payload)}
                  />
                )}
              </article>
            ))
          )}
        </div>
      )}

      <div className="card">
        <div className="card-header">
          <h2>
            <FileTextIcon size={16} />
            Reports
          </h2>
        </div>
        <form className="inline-form" onSubmit={(e) => void handleCreateReport(e)}>
          <label htmlFor="report-title">Title</label>
          <input
            id="report-title"
            required
            maxLength={200}
            value={reportTitle}
            onChange={(e) => setReportTitle(e.target.value)}
          />
          <label htmlFor="report-format">Format</label>
          <select
            id="report-format"
            value={reportFormat}
            onChange={(e) => setReportFormat(e.target.value)}
          >
            <option value="json">JSON</option>
            <option value="markdown">Markdown</option>
          </select>
          <button type="submit" disabled={reportTitle.trim() === ''}>
            Create report
          </button>
        </form>

        {reports.length === 0 ? (
          <EmptyState>No reports yet.</EmptyState>
        ) : (
          <div className="table-wrap">
          <table className="table">
            <caption className="sr-only">Reports in this project</caption>
            <thead>
              <tr>
                <th scope="col">Title</th>
                <th scope="col">Format</th>
                <th scope="col">Version</th>
                <th scope="col">Generated</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((report) => (
                <tr key={report.id}>
                  <td>{report.title}</td>
                  <td>{report.format}</td>
                  <td>v{report.version}</td>
                  <td>
                    {report.generated_at ? (
                      <time dateTime={report.generated_at}>
                        {formatDateTime(report.generated_at)}
                      </time>
                    ) : (
                      'not generated'
                    )}
                  </td>
                  <td>
                    <div className="actions">
                    <button type="button" className="secondary sm" onClick={() => void handleGenerateReport(report)}>
                      Generate
                    </button>
                    <button
                      type="button"
                      className="secondary sm"
                      disabled={!report.generated_at}
                      onClick={() => void handleDownloadReport(report)}
                    >
                      <DownloadIcon size={13} />
                      Download
                    </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </div>

      <section className="card report-comparison" aria-labelledby="comparison-heading">
        <div className="card-header">
          <div>
            <p className="eyebrow">Regression tracking</p>
            <h2 id="comparison-heading">Compare report snapshots</h2>
          </div>
        </div>
        <p className="card-note">
          Select an earlier baseline and a later generated report to surface new, resolved, and
          severity-changing findings. Comparisons use immutable report snapshots.
        </p>

        {generatedReports.length < 2 ? (
          <EmptyState>Generate at least two reports to compare security posture over time.</EmptyState>
        ) : (
          <>
            <div className="comparison-controls">
              <div className="field">
                <label htmlFor="baseline-report">Baseline report</label>
                <select
                  id="baseline-report"
                  value={baselineReportId}
                  onChange={(event) => setBaselineReportId(event.target.value)}
                >
                  <option value="">Select baseline</option>
                  {generatedReports.map((report) => (
                    <option key={report.id} value={report.id}>
                      {report.title} · v{report.version}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="current-report">Current report</label>
                <select
                  id="current-report"
                  value={currentReportId}
                  onChange={(event) => setCurrentReportId(event.target.value)}
                >
                  <option value="">Select current report</option>
                  {generatedReports.map((report) => (
                    <option key={report.id} value={report.id}>
                      {report.title} · v{report.version}
                    </option>
                  ))}
                </select>
              </div>
              <button
                type="button"
                onClick={() => void handleCompareReports()}
                disabled={comparing || !baselineReportId || !currentReportId || baselineReportId === currentReportId}
              >
                {comparing ? 'Comparing…' : 'Compare reports'}
              </button>
            </div>

            {comparison && (
              <div className="comparison-result" aria-live="polite">
                <dl className="comparison-grid">
                  <div><dt>New</dt><dd>{comparison.new_count}</dd></div>
                  <div><dt>Resolved</dt><dd>{comparison.resolved_count}</dd></div>
                  <div className={comparison.regressed_count > 0 ? 'comparison-alert' : undefined}><dt>Regressed</dt><dd>{comparison.regressed_count}</dd></div>
                  <div><dt>Improved</dt><dd>{comparison.improved_count}</dd></div>
                  <div><dt>Unchanged</dt><dd>{comparison.unchanged_count}</dd></div>
                </dl>
                {(comparison.regressed_findings.length > 0 || comparison.improved_findings.length > 0) && (
                  <ul className="comparison-list">
                    {comparison.regressed_findings.map((finding) => (
                      <li key={`regressed-${finding.category}-${finding.title}`}>
                        <strong>Regression:</strong> {finding.title} changed from {finding.severity_before} to {finding.severity_after}.
                      </li>
                    ))}
                    {comparison.improved_findings.map((finding) => (
                      <li key={`improved-${finding.category}-${finding.title}`}>
                        <strong>Improved:</strong> {finding.title} changed from {finding.severity_before} to {finding.severity_after}.
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </>
        )}
      </section>

      <ConfirmDialog
        open={confirmDeleteExecution !== null}
        title="Delete execution"
        message={
          <p>
            Delete execution <code className="mono">{shortId(confirmDeleteExecution?.id)}</code>{' '}
            and all its findings and evidence? This cannot be undone.
          </p>
        }
        busy={destructiveBusy}
        onConfirm={() => void handleDeleteExecutionConfirmed()}
        onCancel={() => setConfirmDeleteExecution(null)}
      />

      <ConfirmDialog
        open={confirmClearHistory}
        title="Clear execution history"
        message={
          <p>
            Delete <strong>all</strong> execution logs, findings, and evidence for this
            project? Tests, targets, and generated reports are kept. This cannot be undone.
          </p>
        }
        confirmLabel="Delete everything"
        busy={destructiveBusy}
        onConfirm={() => void handleClearHistoryConfirmed()}
        onCancel={() => setConfirmClearHistory(false)}
      />
    </section>
  )
}

/** Human labels for the remediation strategy, keeping the two engines distinct. */
/** Server enum values read as labels: `needs_review` becomes "needs review". */
function formatResultLabel(result: string | null | undefined): string {
  return result ? result.replace(/_/g, ' ') : '—'
}

/**
 * The Reason cell of an execution table: why this row reads the way it does.
 *
 * An infrastructure failure carries its reason in `error`; an attack that
 * landed carries it in the finding its grader produced. Without the finding,
 * the rows users care about most — the failed tests — would show nothing.
 */
function ExecutionReason({ execution }: { execution: Execution }) {
  const failure = explainExecutionError(execution.error)
  if (failure) {
    return (
      <>
        <strong>{failure.cause}</strong>
        <span>{failure.action}</span>
      </>
    )
  }

  const finding = execution.finding_summary
  if (finding) {
    return (
      <>
        <strong>{finding.title}</strong>
        <span>
          {finding.confirmation === 'candidate' && 'Unconfirmed match — '}
          {finding.description ?? 'Open Findings for the full response and evidence.'}
        </span>
      </>
    )
  }

  return <span className="failure-none">—</span>
}

/**
 * The recorded transcript of one execution: what was sent and what the target
 * answered, turn by turn.
 *
 * Steps are stored verbatim so a run stays auditable and reproducible; the
 * backend redacts sensitive values when serving them, and `redacted` /
 * `detected_kinds` say what was replaced. A transcript where a secret was
 * found is shown as such, never silently cleaned.
 */
function TranscriptPanel({
  steps,
  busy,
  error,
}: {
  steps: ExecutionStep[] | undefined
  busy: boolean
  error: string | null
}) {
  if (busy) {
    return <Loading label="Loading transcript…" />
  }
  if (error) {
    return (
      <p className="inline-warning" role="alert">
        {error}
      </p>
    )
  }
  if (!steps) {
    return null
  }
  if (steps.length === 0) {
    return <EmptyState>No steps were recorded for this execution.</EmptyState>
  }

  return (
    <div className="transcript">
      <h4>
        <ClockIcon size={14} /> Transcript
      </h4>
      {steps.map((step) => {
        const rawMessages = step.request_content['messages']
        // Steps recorded by the engine carry the request as a `messages`
        // array; older or hand-recorded steps (the demo fixture) store the
        // single message directly, so both shapes render.
        const messages = Array.isArray(rawMessages)
          ? (rawMessages as Array<Record<string, unknown>>)
          : typeof step.request_content['content'] === 'string'
            ? [step.request_content]
            : []
        return (
          <div key={step.id} className="transcript-step">
            <p className="transcript-meta">
              <strong>Turn {step.turn_number + 1}</strong>{' '}
              <span className={`badge badge-${step.status}`}>{step.status}</span>{' '}
              {step.redacted && (
                <span className="badge badge-redacted">
                  redacted: {step.detected_kinds.join(', ') || 'sensitive data'}
                </span>
              )}
            </p>
            {messages.map((message, index) => (
              <p key={index} className="transcript-message">
                <span className="transcript-role">{String(message.role ?? 'message')}</span>
                <span>{String(message.content ?? '')}</span>
              </p>
            ))}
            {step.response_output !== null && step.response_output !== '' && (
              <p className="transcript-message transcript-response">
                <span className="transcript-role">assistant</span>
                <span>{step.response_output}</span>
              </p>
            )}
            {step.error && (
              <p className="inline-warning" role="alert">
                {step.error}
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}

/**
 * Immutable run snapshot: the target/model profile and test definition that
 * produced an execution. Kept next to the transcript because the target row
 * can be edited later without changing historical evidence.
 */
function RunManifestPanel({ manifest }: { manifest: RunManifest | null }) {
  if (!manifest) {
    return null
  }
  const generation = Object.entries(manifest.effective_generation)
    .filter(([, value]) => value !== null)
    .map(([key, value]) => `${key}=${value}`)
    .join(', ')

  return (
    <div className="transcript run-manifest">
      <h4>
        <SlidersIcon size={14} /> Run manifest
      </h4>
      <dl className="meta">
        <div>
          <dt>Captured</dt>
          <dd>{formatDateTime(manifest.captured_at)}</dd>
        </div>
        <div>
          <dt>Target</dt>
          <dd>
            {manifest.target.name} ({shortId(manifest.target.id)})
          </dd>
        </div>
        <div>
          <dt>Model</dt>
          <dd>
            {manifest.target.model ?? '—'}
            {manifest.target.model_version
              ? ` · ${manifest.target.model_version}`
              : ' · version not declared'}
          </dd>
        </div>
        <div>
          <dt>Provider</dt>
          <dd>{manifest.target.provider}</dd>
        </div>
        <div>
          <dt>Endpoint</dt>
          <dd>
            <code className="mono">{manifest.target.endpoint}</code>
          </dd>
        </div>
        <div>
          <dt>Effective generation</dt>
          <dd>{generation || 'provider defaults'}</dd>
        </div>
        <div>
          <dt>System prompt</dt>
          <dd>
            {manifest.system_prompt_source
              ? `${manifest.system_prompt_source} · ${manifest.target.system_prompt_length} chars · sha256 ${manifest.target.system_prompt_sha256?.slice(0, 12)}…`
              : 'not used'}
          </dd>
        </div>
        <div>
          <dt>Test</dt>
          <dd>{manifest.test.name}</dd>
        </div>
        <div>
          <dt>Test config SHA-256</dt>
          <dd>
            <code className="mono">{manifest.test.config_sha256}</code>
          </dd>
        </div>
      </dl>
    </div>
  )
}

/**
 * The model's actual reply, kept with the finding by the grader.
 *
 * Pattern lists say what matched; the reply shows whether that was a real leak
 * or a refusal echoing the test's own wording, so the finding is reviewable
 * without opening its evidence.
 */
function FindingResponseExcerpt({ details }: { details: Record<string, unknown> }) {
  const snippet = details['output_snippet']
  if (typeof snippet !== 'string' || snippet.trim() === '') {
    return null
  }

  return (
    <blockquote className="finding-response">
      <span>Model response excerpt</span>
      <p>{snippet}</p>
    </blockquote>
  )
}

const REMEDIATION_KIND_LABELS: Record<string, string> = {
  application: 'Application fix',
  llm_behavior: 'Model behavior fix',
  hybrid: 'Application + behavior fix',
  manual_review: 'Manual review needed',
}

/**
 * Render a review-only AutoFix suggestion.
 *
 * Deliberately informational: there is no apply, approve, or fix action in
 * this component, because no such backend route exists.
 */
function RemediationPanel({ plan }: { plan: RemediationPlan }) {
  const kindLabel = REMEDIATION_KIND_LABELS[plan.kind] ?? `Fix type: ${plan.kind}`

  return (
    <div className="remediation-plan">
      <p className="remediation-badges">
        <span className="badge badge-remediation">Level 1 · Suggest only</span>{' '}
        <span className="badge badge-remediation">{kindLabel}</span>{' '}
        {plan.requires_human_approval && (
          <span className="badge badge-remediation">Human approval required</span>
        )}
      </p>
      <h5>Likely root cause</h5>
      <p>{plan.root_cause_hypothesis}</p>
      <h5>Recommended controls</h5>
      <ul>
        {plan.recommendations.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      <h5>How to verify the fix</h5>
      <ol>
        {plan.verification_steps.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ol>
      <h5>Limitations</h5>
      <ul>
        {plan.limitations.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      {plan.attack_id && (
        <p className="finding-meta">
          Reproduce with attack <code>{plan.attack_id}</code>
          {plan.attack_version ? ` v${plan.attack_version}` : ''} · plan template v
          {plan.template_version}
        </p>
      )}
    </div>
  )
}

/** Human labels for where a candidate change lives. */
const PATCH_APPROACH_LABELS: Record<string, string> = {
  prompt_engineering: 'Usage / prompt change',
  config: 'Configuration change',
  code: 'Application code change',
  manual_review: 'Manual review needed',
}

/** Download a drafted diff; nothing is applied server-side or client-side. */
function downloadProposal(proposal: PatchProposal) {
  if (!proposal.diff_text) return

  const blob = new Blob([proposal.diff_text], { type: 'text/x-diff' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `finding-${proposal.finding_id.slice(0, 8)}-${proposal.id.slice(0, 8)}.diff`
  anchor.click()
  URL.revokeObjectURL(url)
}

/**
 * Draft and display candidate patches for one finding.
 *
 * Deterministic by default: with no drafting model selected, the proposal
 * records remediation intent and writes no diff, because a diff without
 * comprehension of the target code would be a fabricated fix. Selecting an
 * active OpenAI-compatible or Ollama target asks that model to draft a diff
 * from the supplied file. There is deliberately no apply, approve, or fix
 * action here: applying a change belongs to the user's own tooling, and only
 * a verification rerun can mark the finding verified.
 */
function PatchPanel({
  findingId,
  proposals,
  targets,
  busy,
  onGenerate,
}: {
  findingId: string
  proposals: PatchProposal[]
  targets: Target[]
  busy: boolean
  onGenerate: (payload: PatchProposalCreate) => void
}) {
  const [draftingTargetId, setDraftingTargetId] = useState('')
  const [filePath, setFilePath] = useState('')
  const [fileContent, setFileContent] = useState('')

  const draftingTargets = targets.filter(
    (target) =>
      target.status === 'active' &&
      (target.provider === 'openai_compatible' || target.provider === 'ollama'),
  )
  const drafting = draftingTargetId !== ''
  const canGenerate =
    !busy && (!drafting || (filePath.trim() !== '' && fileContent.trim() !== ''))

  return (
    <div className="patch-panel">
      <div className="inline-form">
        <label htmlFor={`patch-drafting-target-${findingId}`}>
          Draft with model (optional)
        </label>
        <select
          id={`patch-drafting-target-${findingId}`}
          value={draftingTargetId}
          onChange={(event) => setDraftingTargetId(event.target.value)}
        >
          <option value="">None — deterministic intent only</option>
          {draftingTargets.map((target) => (
            <option key={target.id} value={target.id}>
              {target.name} ({target.provider})
            </option>
          ))}
        </select>
      </div>
      {draftingTargets.length === 0 && (
        <p className="card-note">
          No active OpenAI-compatible or Ollama target is available to draft a diff; the
          proposal records remediation intent only.
        </p>
      )}
      {drafting && (
        <>
          <div className="inline-form">
            <label htmlFor={`patch-file-path-${findingId}`}>File path</label>
            <input
              id={`patch-file-path-${findingId}`}
              placeholder="app/handlers.py"
              maxLength={500}
              value={filePath}
              onChange={(event) => setFilePath(event.target.value)}
            />
          </div>
          <label htmlFor={`patch-file-content-${findingId}`}>File content to patch</label>
          <textarea
            id={`patch-file-content-${findingId}`}
            className="patch-file-content"
            rows={8}
            maxLength={100000}
            value={fileContent}
            onChange={(event) => setFileContent(event.target.value)}
          />
          <p className="card-note">
            Only this file reaches the selected model, together with the finding summary
            and evidence metadata. Stored credentials are never included.
          </p>
        </>
      )}
      <button
        type="button"
        disabled={!canGenerate}
        onClick={() =>
          onGenerate(
            drafting
              ? {
                  drafting_target_id: draftingTargetId,
                  file_path: filePath.trim(),
                  file_content: fileContent,
                }
              : {},
          )
        }
      >
        {busy ? 'Drafting…' : 'Generate candidate patch'}
      </button>

      {proposals.length === 0 ? (
        <EmptyState>No candidate patches drafted yet.</EmptyState>
      ) : (
        proposals.map((proposal) => (
          <div key={proposal.id} className="patch-proposal">
            <p className="remediation-badges">
              <span className="badge badge-remediation">
                {proposal.mode === 'llm' ? 'Model-drafted' : 'Deterministic draft'}
              </span>{' '}
              <span className="badge badge-remediation">
                {PATCH_APPROACH_LABELS[proposal.approach] ?? proposal.approach}
              </span>{' '}
              {proposal.files_touched.length > 0 && (
                <span className="badge badge-remediation">
                  {proposal.files_touched.length} file
                  {proposal.files_touched.length === 1 ? '' : 's'}
                </span>
              )}
            </p>
            <p>{proposal.rationale}</p>
            {proposal.diff_text ? (
              <>
                <pre className="patch-diff">{proposal.diff_text}</pre>
                <button type="button" onClick={() => downloadProposal(proposal)}>
                  Download .diff
                </button>
              </>
            ) : (
              <p className="card-note">No diff recorded in this proposal.</p>
            )}
            {proposal.drafting_model && (
              <p className="finding-meta">
                Drafted with <code>{proposal.drafting_model}</code>
                {proposal.prompt_hash ? ` · prompt ${proposal.prompt_hash.slice(0, 12)}…` : ''}
              </p>
            )}
          </div>
        ))
      )}
    </div>
  )
}
