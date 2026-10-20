"""Execution engine for running security tests against model targets.

Manages the lifecycle of an ``Execution`` from PENDING through RUNNING to
a terminal state (SUCCEEDED, FAILED, or CANCELLED). Provides in-process
async task scheduling with retry, timeout, cancellation, and progress
tracking. Supports both single-turn and multi-turn conversation flows.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import BaseTargetAdapter, ModelProviderError
from app.adapters.registry import create_model_adapter
from app.api.errors import AssessmentNotFoundError
from app.db.session import create_session_factory
from app.models.execution import Execution, ExecutionResult, ExecutionStatus
from app.models.execution_step import ExecutionStep
from app.models.finding import Finding, FindingConfirmation
from app.models.model import ModelMessage, ModelRequest, ModelResponse
from app.models.project import Project
from app.models.target import Target, TargetStatus
from app.models.test import SecurityTest
from app.security.secrets import SecretStore, get_secret_store
from app.services.assessments import validate_execution_binding
from app.services.audit import record_audit_event
from app.services.confirmation import (
    apply_confirmation,
    build_confirmation_prompt,
    confirmation_for_verdict,
    derive_execution_result,
    load_execution_findings,
    parse_judge_verdict,
)
from app.services.converters import apply_converters
from app.services.evidence import persist_execution_evidence
from app.services.finding_classifier import (
    determine_execution_result,
)
from app.services.grading import DeterministicResponseGrader, ResponseGrader
from app.services.model_profile import (
    build_run_manifest,
    resolved_generation_config,
    resolved_system_prompt,
)
from app.services.verification import record_verification_outcome

_logger = logging.getLogger("aegis.execution")


class ExecutionError(Exception):
    """Raised when an execution cannot be started or completed."""


class ExecutionEngine:
    """In-process async execution engine.

    Schedules executions as ``asyncio`` tasks within the running event loop.
    Each task creates its own database session, runs the security test
    against the target via the appropriate model adapter, classifies the
    response for findings, persists evidence, and transitions the execution
    to a terminal state.
    """

    def __init__(
        self,
        *,
        store: SecretStore | None = None,
        adapter_factory: Callable[..., BaseTargetAdapter] | None = None,
        judge_factory: Callable[..., BaseTargetAdapter] | None = None,
        grader: ResponseGrader | None = None,
    ) -> None:
        self._store = store or get_secret_store()
        self._adapter_factory = adapter_factory
        self._judge_factory = judge_factory
        self._grader = grader or DeterministicResponseGrader()
        self._tasks: dict[UUID, asyncio.Task[None]] = {}

    @property
    def store(self) -> SecretStore:
        return self._store

    def schedule(self, execution_id: UUID) -> None:
        """Schedule an execution for background processing.

        Raises ExecutionError if no task can be created (e.g. no running
        event loop). In FastAPI request handlers this is always available.
        """

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise ExecutionError(
                "Cannot schedule execution outside of a running event loop."
            ) from exc

        task = loop.create_task(self._run(execution_id))
        self._tasks[execution_id] = task
        task.add_done_callback(lambda _t, eid=execution_id: self._tasks.pop(eid, None))

    def is_running(self, execution_id: UUID) -> bool:
        """Return whether an execution task is currently in progress."""

        task = self._tasks.get(execution_id)
        return task is not None and not task.done()

    def cancel(self, execution_id: UUID) -> bool:
        """Cancel a running execution. Returns True if a task was cancelled."""

        task = self._tasks.get(execution_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    async def run_single(self, execution_id: UUID) -> None:
        """Run one execution end to end with its own DB session.

        Public wrapper over ``_run`` so callers outside the engine -- notably the
        bulk runner, which needs a bounded-concurrency loop rather than one
        unbounded task per execution -- do not reach into a private method.
        """

        await self._run(execution_id)

    async def _run(self, execution_id: UUID) -> None:
        """Run a single execution end-to-end with its own DB session."""

        session = create_session_factory()()
        try:
            await self.execute(session, execution_id)
        except asyncio.CancelledError:
            await self._record_cancelled(session, execution_id)
            raise
        finally:
            session.close()

    async def execute(self, session: Session, execution_id: UUID) -> None:
        """Load, run, classify, and persist results for a single execution."""

        execution = session.get(Execution, execution_id)
        if execution is None:
            _logger.warning("execution not found: %s", execution_id)
            return

        if execution.status != ExecutionStatus.PENDING:
            _logger.info(
                "execution %s already in %s state, skipping",
                execution_id,
                execution.status.value,
            )
            return

        project = session.get(Project, execution.project_id)
        if project is None:
            await self._record_failure(session, execution_id, "project not found")
            return

        test = None
        if execution.test_id is not None:
            test = session.get(SecurityTest, execution.test_id)
        if test is None:
            await self._record_failure(session, execution_id, "security test not found")
            return

        target = None
        if execution.target_id is not None:
            target = session.get(Target, execution.target_id)
        if target is None:
            await self._record_failure(session, execution_id, "target not found")
            return

        # Re-check the pairing at run time as well as at creation time. A target
        # can be deactivated, or its capabilities changed, between the two.
        try:
            validate_execution_binding(test, target)
        except AssessmentNotFoundError as exc:
            await self._record_failure(session, execution_id, str(exc))
            return

        # Snapshot the model profile and test definition before any request is
        # sent. The target row can be edited while a long run is in progress;
        # the result must still point at what actually produced it.
        execution.run_manifest = build_run_manifest(target, test)
        execution.status = ExecutionStatus.RUNNING
        execution.started_at = datetime.now(UTC)
        session.commit()

        record_audit_event(
            session,
            actor_id=execution.created_by,
            action="execution.started",
            resource_type="execution",
            resource_id=str(execution.id),
        )

        adapter: BaseTargetAdapter | None = None
        try:
            config = test.config or {}
            turns = config.get("turns", [])
            has_multi_turn = isinstance(turns, list) and len(turns) > 0

            adapter = _create_adapter(target, self._store, session, self._adapter_factory)

            if has_multi_turn:
                all_findings, judge_output, grader_result = await self._run_multi_turn(
                    session, execution, test, target, adapter, turns
                )
            else:
                all_findings, judge_output, grader_result = await self._run_single_turn(
                    session, execution, test, target, adapter
                )

            # A model judge is a separate, fallible evidence source with its
            # own explicit result contract. All other methods use the injected
            # response grader's decision, so changing a grader does not
            # require changing adapter or execution code.
            if _uses_judge_model(test.config):
                result = determine_execution_result(
                    all_findings, test.config, judge_output=judge_output
                )
            else:
                result = grader_result

            # Two-stage grading. The stage above produces candidates; this
            # stage resolves them to confirmed or dismissed with the
            # confirmation judge, or deliberately leaves them as candidates
            # for review. Only confirmed findings produce a ``fail``.
            result = await self._confirm_findings(session, execution, test, target, result)
            execution.result = result

            execution.status = ExecutionStatus.SUCCEEDED
            execution.completed_at = datetime.now(UTC)
            session.commit()

            record_audit_event(
                session,
                actor_id=execution.created_by,
                action="execution.succeeded",
                resource_type="execution",
                resource_id=str(execution.id),
                event_metadata={"result": result.value},
            )

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            error_msg = str(exc) or exc.__class__.__name__
            execution.status = ExecutionStatus.FAILED
            execution.error = error_msg
            execution.completed_at = datetime.now(UTC)
            execution.result = ExecutionResult.INCONCLUSIVE
            session.commit()

            record_audit_event(
                session,
                actor_id=execution.created_by,
                action="execution.failed",
                resource_type="execution",
                resource_id=str(execution.id),
                event_metadata={"error": error_msg},
            )
        finally:
            # The adapter owns an httpx client and its connection pool. Release
            # it on every path -- success, failure, and cancellation -- so
            # repeated executions do not exhaust sockets.
            if adapter is not None:
                await adapter.close()

        if execution.verifies_finding_id is not None:
            # A verification run's verdict only exists once the run itself is
            # recorded. Do not fail the execution if linkage recording fails:
            # the run's own result is already persisted and the verdict can be
            # re-derived from it.
            try:
                record_verification_outcome(session, execution)
            except Exception:
                _logger.exception("failed to record verification outcome for %s", execution_id)

    async def _run_single_turn(
        self,
        session: Session,
        execution: Execution,
        test: SecurityTest,
        target: Target,
        adapter: BaseTargetAdapter,
    ) -> tuple[list, str | None, ExecutionResult]:
        """Run a single-turn execution: one request, one response."""

        request = _build_request(test, target)
        response = await _execute_with_retries(adapter, target, request, test)

        decision = self._grader.grade(response.output, test.config)
        findings = list(decision.findings)

        step = ExecutionStep(
            execution_id=execution.id,
            turn_number=0,
            request_content={
                **request.model_dump(),
                "converters_applied": _converter_trace(test),
            },
            response_output=response.output,
            status="succeeded",
        )
        session.add(step)
        session.commit()
        session.refresh(step)

        for classified in findings:
            finding = Finding(
                execution_id=execution.id,
                title=classified.title,
                description=classified.description,
                severity=classified.severity,
                details=classified.details,
            )
            session.add(finding)
            session.commit()
            session.refresh(finding)

            persist_execution_evidence(
                session,
                finding=finding,
                request=request,
                response=response,
            )

        # Judge after the response and any findings are persisted. A
        # misconfigured judge fails the execution, and the evidence of what the
        # target actually said must survive that.
        judge_output = await self._maybe_judge(session, execution, test, target, response.output)

        return findings, judge_output, decision.result

    async def _run_multi_turn(
        self,
        session: Session,
        execution: Execution,
        test: SecurityTest,
        target: Target,
        adapter: BaseTargetAdapter,
        turns: list,
    ) -> tuple[list, str | None, ExecutionResult]:
        """Run a multi-turn execution: iterate through conversation turns."""

        config = test.config or {}
        all_findings: list = []
        grader_results: list[ExecutionResult] = []
        conversation_messages: list[ModelMessage] = []
        judge_output: str | None = None
        generation = resolved_generation_config(config, target)

        system_prompt, _source = resolved_system_prompt(config, target)
        if system_prompt:
            conversation_messages.append(ModelMessage(role="system", content=system_prompt))

        for turn_idx, turn in enumerate(turns):
            converters = config.get("converters") or []
            turn_messages = _parse_turn_messages(turn, conversation_messages, converters)

            # Carry the turn's new user messages into the running history so
            # later turns see the full conversation, not just prior replies.
            for message in turn_messages[len(conversation_messages) :]:
                conversation_messages.append(message)

            request = ModelRequest(
                messages=turn_messages,
                system_prompt=None,
                **generation,
                stop=config.get("stop"),
            )

            response = await _execute_with_retries(adapter, target, request, test)

            step = ExecutionStep(
                execution_id=execution.id,
                turn_number=turn_idx,
                request_content={
                    **request.model_dump(),
                    "converters_applied": _converter_trace(test),
                },
                response_output=response.output,
                status="succeeded",
            )
            session.add(step)
            session.commit()
            session.refresh(step)

            decision = self._grader.grade(response.output, test.config)
            findings = list(decision.findings)
            all_findings.extend(findings)
            grader_results.append(decision.result)

            for classified in findings:
                finding = Finding(
                    execution_id=execution.id,
                    title=classified.title,
                    description=classified.description,
                    severity=classified.severity,
                    # The turn number lets the confirmation stage judge the
                    # response this finding actually came from instead of the
                    # final turn's reply.
                    details={**classified.details, "turn_number": turn_idx},
                )
                session.add(finding)
                session.commit()
                session.refresh(finding)

                persist_execution_evidence(
                    session,
                    finding=finding,
                    request=request,
                    response=response,
                )

            conversation_messages.append(ModelMessage(role="assistant", content=response.output))

        judge_output = await self._maybe_judge(
            session, execution, test, target, conversation_messages[-1].content
        )

        return all_findings, judge_output, _combine_grader_results(grader_results)

    async def _confirm_findings(
        self,
        session: Session,
        execution: Execution,
        test: SecurityTest,
        target: Target,
        result: ExecutionResult,
    ) -> ExecutionResult:
        """Resolve a run's findings into confirmed/dismissed/candidate state.

        The deterministic grader is lexical: its matches are candidates until
        something semantic confirms them. This stage is that confirmation:

        - judge-model tests already carry a verdict; the deterministic matches
          are aligned with it (fail confirms, pass dismisses);
        - a deterministic test with a configured judge gets the second-stage
          judge call, which confirms matches that show an attack landing and
          dismisses matches that are refusals or echoes;
        - with no usable judge, or when the judge answers unclearly, findings
          stay candidates and the run becomes ``needs_review`` — never a
          guessed ``fail`` and never a silent ``pass``.

        Returns the execution's new result.
        """

        findings = load_execution_findings(session, execution.id)
        if not findings:
            return result

        config = test.config or {}
        grading = config.get("grading", {}) if isinstance(config, dict) else {}

        if _uses_judge_model(test.config):
            # The judge verdict already decided this run; the deterministic
            # matches only corroborate it. Align them with the verdict so the
            # findings and the result do not contradict each other.
            if result == ExecutionResult.FAIL:
                apply_confirmation(
                    findings,
                    FindingConfirmation.CONFIRMED,
                    source="judge",
                    reason="judge-model grading found the response unsafe",
                )
                session.commit()
            elif result == ExecutionResult.PASS:
                apply_confirmation(
                    findings,
                    FindingConfirmation.DISMISSED,
                    source="judge",
                    reason="judge-model grading found the response safe",
                )
                session.commit()
            return result

        if result == ExecutionResult.INCONCLUSIVE:
            # Grading itself could not run. Resolving the findings here would
            # invent evidence the run deliberately refused to produce.
            return result

        if isinstance(grading, dict) and grading.get("confirm") is False:
            # Explicit opt-out for tests whose rules are decisive by
            # construction (an exact canary token, for example). The match is
            # the evidence, so it stands as confirmed rather than pending.
            if result == ExecutionResult.FAIL:
                apply_confirmation(
                    findings,
                    FindingConfirmation.CONFIRMED,
                    source="test-config",
                    reason="test opted out of two-stage confirmation",
                )
                session.commit()
            elif result == ExecutionResult.PASS:
                apply_confirmation(
                    findings,
                    FindingConfirmation.DISMISSED,
                    source="test-config",
                    reason="test opted out of two-stage confirmation",
                )
                session.commit()
            return result

        judge_target, judge_model = self._resolve_judge_target(session, execution, target)
        if judge_target is None or judge_model is None:
            # No usable judge. Nothing is confirmed and nothing is hidden:
            # every finding stays a candidate and the run needs review.
            return ExecutionResult.NEEDS_REVIEW

        steps = {
            step.turn_number: step
            for step in session.scalars(
                select(ExecutionStep).where(ExecutionStep.execution_id == execution.id)
            ).all()
        }

        judged_any = False
        for turn in sorted({_finding_turn(finding) for finding in findings}):
            step = steps.get(turn)
            verdict = await self._judge_confirmation(
                session,
                execution,
                test,
                target,
                judge_target,
                judge_model,
                attack=_attack_text_from_step(step, config),
                response=(step.response_output if step is not None else "") or "",
            )
            if verdict is None:
                # Unparseable or failed judge answer: those findings stay
                # candidates. Silence must not resolve an attack either way.
                continue
            kind, rationale = verdict
            confirmation = confirmation_for_verdict(kind)
            if confirmation is None:
                continue
            apply_confirmation(
                [finding for finding in findings if _finding_turn(finding) == turn],
                confirmation,
                source="judge",
                reason=f"judge: {rationale}" if rationale else f"judge: {kind}",
            )
            judged_any = True

        if judged_any:
            session.commit()

        derived = derive_execution_result(findings)
        return derived if derived is not None else result

    async def _judge_confirmation(
        self,
        session: Session,
        execution: Execution,
        test: SecurityTest,
        target: Target,
        judge_target: Target,
        judge_model: str,
        *,
        attack: str,
        response: str,
    ) -> tuple[str, str] | None:
        """Ask the confirmation judge whether an attack actually landed.

        Returns ``(verdict, rationale)`` or ``None`` when the judge call could
        not run or answered unusably. ``None`` always leaves findings as
        candidates: neither a network failure nor a garbled answer may be
        read as confirmation or as dismissal.
        """

        config = test.config or {}
        attack_meta = config.get("attack")
        attack_meta = attack_meta if isinstance(attack_meta, dict) else {}
        prompt = build_confirmation_prompt(
            test_name=test.name,
            test_description=test.description,
            expected_behavior=attack_meta.get("security_property")
            or config.get("expected_safe_behavior"),
            attack=attack,
            response=response,
        )

        judge_request = ModelRequest(
            messages=[ModelMessage(role="user", content=prompt)],
            model=judge_model,
        )

        try:
            judge_adapter = _create_adapter(
                judge_target,
                self._store,
                session,
                self._judge_factory or self._adapter_factory,
            )
        except Exception as exc:
            _logger.warning(
                "could not build the confirmation judge adapter for execution %s: %s",
                execution.id,
                exc,
            )
            return None

        try:
            judge_response = await _execute_with_retries(
                judge_adapter, judge_target, judge_request, test
            )
        except Exception as exc:
            _logger.warning(
                "confirmation judge call failed for execution %s: %s",
                execution.id,
                exc,
            )
            return None
        finally:
            if hasattr(judge_adapter, "close"):
                await judge_adapter.close()

        return parse_judge_verdict(judge_response.output)

    def _resolve_judge_target(
        self,
        session: Session,
        execution: Execution,
        target: Target,
        pinned_model: str | None = None,
    ) -> tuple[Target | None, str | None]:
        """Resolve the project's judge target for a grading call.

        Returns ``(judge_target, judge_model)``, or ``(None, None)`` with a
        logged reason when judging cannot run: the project has no judge
        target, the judge target is inactive, or the judge would be the model
        under test itself (ADR-005: a model must not judge its own answers).
        """

        project = session.get(Project, execution.project_id)
        judge_target = None
        if project is not None and project.judge_target_id is not None:
            judge_target = session.get(Target, project.judge_target_id)

        if judge_target is None:
            _logger.warning(
                "a judge is required for execution %s but the project has no "
                "judge target configured",
                execution.id,
            )
            return None, None

        if judge_target.status != TargetStatus.ACTIVE:
            _logger.warning(
                "judge target %s for execution %s is %s; judging cannot run",
                judge_target.id,
                execution.id,
                judge_target.status.value,
            )
            return None, None

        # The case may pin a specific model on the judge endpoint; otherwise
        # the judge target's own model is used.
        judge_model = pinned_model or judge_target.model

        # ADR-005: a judge must remain logically separate from the target
        # model. The same target row with the same effective model is the
        # model grading its own answers; a different model on the same
        # endpoint is a legitimate, separate judge.
        if judge_target.id == execution.target_id and judge_model == target.model:
            _logger.warning(
                "judge target for execution %s is the target under test with the "
                "same model %r; a model must not judge its own response",
                execution.id,
                judge_model,
            )
            return None, None

        return judge_target, judge_model

    async def _maybe_judge(
        self,
        session: Session,
        execution: Execution,
        test: SecurityTest,
        target: Target,
        response_output: str,
    ) -> str | None:
        """Invoke the configured judge target for judge-model grading.

        The judge is an explicit, project-scoped target: either named for this
        test under ``grading.judge.target_id`` or configured on the project as
        its default judge target. It is never the model under test (ADR-005).

        Returns the judge's output, or None when grading cannot run: no judge
        target is available, the judge target is inactive, the judge would be
        the model under test itself, or the judge call failed. None makes the
        execution INCONCLUSIVE - it never downgrades to a keyword guess, which
        would report a target as PASS because judging could not run.

        A judge target named explicitly by the test is validated strictly: a
        missing, foreign, or inactive target raises ``ExecutionError`` so a
        broken configuration fails the run instead of looking like a verdict.
        """

        config = test.config or {}
        grading = config.get("grading", {}) if isinstance(config, dict) else {}
        if not isinstance(grading, dict):
            return None
        if grading.get("method") != "judge_model":
            return None

        judge_raw = grading.get("judge")
        judge = judge_raw if isinstance(judge_raw, dict) else {}

        judge_model: str | None
        if judge.get("target_id"):
            judge_target = _resolve_judge_target(session, execution, grading)
            judge_model = judge.get("model") or judge_target.model
            if judge_target.id == execution.target_id and judge_model == target.model:
                _logger.warning(
                    "judge target for execution %s is the target under test with the "
                    "same model %r; a model must not judge its own response",
                    execution.id,
                    judge_model,
                )
                return None
        else:
            judge_target, judge_model = self._resolve_judge_target(
                session, execution, target, pinned_model=judge.get("model")
            )
            if judge_target is None or judge_model is None:
                return None

        judge_prompt = judge.get("prompt", "Evaluate the following response: {{response}}")
        if not isinstance(judge_prompt, str):
            raise ExecutionError("grading.judge.prompt must be a string")
        judge_prompt = judge_prompt.replace("{{response}}", response_output)

        judge_request = ModelRequest(
            messages=[ModelMessage(role="user", content=judge_prompt)],
            model=judge_model,
        )

        try:
            judge_adapter = _create_adapter(
                judge_target,
                self._store,
                session,
                self._judge_factory or self._adapter_factory,
            )
        except Exception as exc:
            _logger.warning(
                "could not build the judge adapter for execution %s: %s",
                execution.id,
                exc,
            )
            return None

        try:
            judge_response = await _execute_with_retries(
                judge_adapter, judge_target, judge_request, test
            )
            return judge_response.output
        except Exception as exc:
            _logger.warning(
                "judge model call failed for execution %s: %s",
                execution.id,
                exc,
            )
            return None
        finally:
            if hasattr(judge_adapter, "close"):
                await judge_adapter.close()

    async def _record_failure(
        self,
        session: Session,
        execution_id: UUID,
        message: str = "",
    ) -> None:
        """Record a terminal FAILED state for an execution that could not run."""

        execution = session.get(Execution, execution_id)
        if execution is None:
            return

        if execution.status not in (ExecutionStatus.PENDING, ExecutionStatus.RUNNING):
            return

        execution.status = ExecutionStatus.FAILED
        execution.error = message or "execution could not be started"
        execution.completed_at = datetime.now(UTC)
        execution.result = ExecutionResult.INCONCLUSIVE
        session.commit()

    async def _record_cancelled(self, session: Session, execution_id: UUID) -> None:
        """Record a terminal CANCELLED state for a cancelled execution."""

        execution = session.get(Execution, execution_id)
        if execution is None:
            return

        if execution.status in (
            ExecutionStatus.PENDING,
            ExecutionStatus.RUNNING,
        ):
            execution.status = ExecutionStatus.CANCELLED
            execution.completed_at = datetime.now(UTC)
            session.commit()

        record_audit_event(
            session,
            actor_id=execution.created_by,
            action="execution.cancelled",
            resource_type="execution",
            resource_id=str(execution_id),
        )


_engine: ExecutionEngine | None = None


def get_engine() -> ExecutionEngine:
    """Return the shared module-level execution engine (lazily created)."""

    global _engine
    if _engine is None:
        _engine = ExecutionEngine()
    return _engine


def set_engine(engine: ExecutionEngine) -> None:
    """Override the shared engine (for testing)."""

    global _engine
    _engine = engine


def start_execution(execution_id: UUID) -> None:
    """Schedule an execution for background processing."""

    get_engine().schedule(execution_id)


def cancel_execution(execution_id: UUID) -> bool:
    """Cancel a running execution. Returns True if a task was found and cancelled."""

    return get_engine().cancel(execution_id)


def is_execution_running(execution_id: UUID) -> bool:
    """Return whether an execution task is currently in progress."""

    return get_engine().is_running(execution_id)


def _uses_judge_model(config: dict | None) -> bool:
    grading = config.get("grading", {}) if isinstance(config, dict) else {}
    return isinstance(grading, dict) and grading.get("method") == "judge_model"


def _combine_grader_results(results: list[ExecutionResult]) -> ExecutionResult:
    """Combine turn outcomes without turning uncertainty into a pass."""

    if not results:
        return ExecutionResult.INCONCLUSIVE
    if ExecutionResult.FAIL in results:
        return ExecutionResult.FAIL
    if ExecutionResult.INCONCLUSIVE in results:
        return ExecutionResult.INCONCLUSIVE
    return ExecutionResult.PASS


def _finding_turn(finding: Finding) -> int:
    """The turn number a finding came from; single-turn findings are turn 0."""

    details = finding.details if isinstance(finding.details, dict) else {}
    turn = details.get("turn_number", 0)
    if isinstance(turn, int) and turn >= 0:
        return turn
    return 0


def _attack_text_from_step(step: ExecutionStep | None, config: dict) -> str:
    """The user instruction the target received for one turn.

    Read back from the persisted request rather than from the test config:
    the step records what the adapter actually sent, converters included.
    Falls back to the configured prompts when no step was recorded.
    """

    if step is not None and isinstance(step.request_content, dict):
        messages = step.request_content.get("messages", [])
        user_texts = [
            message.get("content", "")
            for message in messages
            if isinstance(message, dict)
            and message.get("role") == "user"
            and message.get("content")
        ]
        if user_texts:
            return user_texts[-1]

    prompts = config.get("prompts", []) if isinstance(config, dict) else []
    if not isinstance(prompts, list):
        return ""
    parts = [
        message.get("content", "")
        for message in prompts
        if isinstance(message, dict) and message.get("role") == "user"
    ]
    return "\n\n".join(part for part in parts if part)


def _build_request(test: SecurityTest, target: Target) -> ModelRequest:
    """Build a ``ModelRequest`` from the test configuration and target profile.

    The test is the more specific instruction: its explicit generation values
    override the target defaults. The target profile supplies the model-level
    settings that should apply to every test (system prompt, temperature,
    top_p, max_tokens, seed).

    Any converters declared on the test are applied here, so every downstream
    consumer -- the adapter, the persisted step, the stored evidence -- sees the
    encoding the target actually received rather than the plain instruction.
    """

    config = test.config or {}

    prompts = config.get("prompts", [])
    messages = [ModelMessage(**msg) for msg in prompts if isinstance(msg, dict)]

    if not messages:
        messages = [ModelMessage(role="user", content="hello")]

    system_prompt, _source = resolved_system_prompt(config, target)
    generation = resolved_generation_config(config, target)
    converters = config.get("converters") or []
    if converters:
        transformed: list[ModelMessage] = []
        for message in messages:
            # Only user and system messages carry an instruction to encode.
            # Assistant and tool content is a prior turn's output; rewriting it
            # would fabricate a conversation the model never had.
            if message.role in {"user", "system"}:
                content, _trace = apply_converters(message.content, converters)
                transformed.append(ModelMessage(role=message.role, content=content))
            else:
                transformed.append(message)
        messages = transformed

        # The system prompt rides outside ``messages`` on ModelRequest, so it
        # needs its own pass. Missing it would leave the highest-value target --
        # the system instruction -- sent in the clear while the user turn was
        # encoded, which an attacker could exploit with a plaintext injection.
        if system_prompt:
            system_prompt, _trace = apply_converters(system_prompt, converters)

    return ModelRequest(
        messages=messages,
        system_prompt=system_prompt,
        **generation,
        stop=config.get("stop"),
    )


def _encode_message(message: ModelMessage, converters: list[dict]) -> ModelMessage:
    """Apply converters to one message's content, leaving its role intact.

    Only user and system messages carry an instruction to encode. Assistant and
    tool content is a prior turn's output, and rewriting it would fabricate a
    conversation the model never had.
    """

    if message.role not in {"user", "system"}:
        return message
    content, _trace = apply_converters(message.content, converters)
    return ModelMessage(role=message.role, content=content)


def _converter_trace(test: SecurityTest) -> list[dict]:
    """Describe the transforms a test applies, for the execution record.

    Applied to a harmless placeholder rather than the real attack text: the
    point is to record *which* transform ran, so an operator can reproduce the
    request the target received without the attack being stored twice.
    """

    converters = (test.config or {}).get("converters") or []
    if not converters:
        return []
    _out, trace = apply_converters("<prompt>", converters)
    return trace


def _parse_turn_messages(
    turn: dict | list,
    history: list[ModelMessage],
    converters: list[dict] | None = None,
) -> list[ModelMessage]:
    """Extract messages from a multi-turn turn definition.

    If the turn is a dict with a ``messages`` key, uses those messages.
    If it's a list, uses the items directly. The current conversation
    history is prepended so the model sees context from prior turns.

    Converters are applied only to this turn's new messages. The history is
    already encoded by the turns that produced it, and re-encoding it would
    double-encode a payload the model had already been shown once.
    """

    if isinstance(turn, dict):
        raw_messages = turn.get("messages", [])
    elif isinstance(turn, list):
        raw_messages = turn
    else:
        return list(history)

    turn_messages = [ModelMessage(**msg) for msg in raw_messages if isinstance(msg, dict)]

    if converters:
        turn_messages = [_encode_message(msg, converters) for msg in turn_messages]

    return list(history) + turn_messages


def _create_adapter(
    target: Target,
    store: SecretStore,
    session: Session,
    adapter_factory: Callable[..., BaseTargetAdapter] | None,
) -> BaseTargetAdapter:
    """Create a model adapter for the target, respecting SSRF/network policy.

    The adapter always uses the project credential store and the validated
    network policy — there is no bypass path for execution.
    """

    from app.adapters.resolver import create_credential_resolver

    credential_resolver = create_credential_resolver(session, store)

    if adapter_factory is not None:
        return adapter_factory(
            target.provider,
            credential_resolver=credential_resolver,
        )

    return create_model_adapter(
        target.provider,
        credential_resolver=credential_resolver,
    )


def _resolve_judge_target(
    session: Session,
    execution: Execution,
    grading: dict,
) -> Target:
    """Return the explicit judge target configured for a judge-model test.

    The judge is a separate, project-scoped model connection. Resolving it from
    configuration, instead of reusing the target under test, is what keeps the
    grader independent of the model it grades.

    Configuration errors raise ``ExecutionError`` so the execution fails with a
    message the operator can act on, rather than reporting a verdict of
    INCONCLUSIVE that looks like a legitimate grading outcome.
    """

    judge = grading.get("judge")
    if not isinstance(judge, dict):
        raise ExecutionError(
            "judge_model grading requires a 'judge' configuration with a target_id"
        )

    raw_target_id = judge.get("target_id")
    if not raw_target_id:
        raise ExecutionError(
            "judge_model grading requires grading.judge.target_id naming a "
            "project target to use as the judge"
        )

    try:
        target_id = UUID(str(raw_target_id))
    except (TypeError, ValueError) as exc:
        raise ExecutionError("grading.judge.target_id must be a UUID") from exc

    judge_target = session.get(Target, target_id)
    if judge_target is None or judge_target.project_id != execution.project_id:
        raise ExecutionError("grading.judge.target_id does not name a target in this project")
    if judge_target.status != TargetStatus.ACTIVE:
        raise ExecutionError("the configured judge target is inactive")

    return judge_target


async def _execute_with_retries(
    adapter: BaseTargetAdapter,
    target: Target,
    request: ModelRequest,
    test: SecurityTest,
) -> ModelResponse:
    """Execute a model request with configurable retries and timeout.

    Retries are limited to transient provider errors and timeouts.
    """

    config = test.config or {}
    max_retries = int(config.get("max_retries", 0))
    timeout = float(config.get("timeout_seconds", target.timeout_seconds))

    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return await asyncio.wait_for(adapter.generate(target, request), timeout=timeout)
        except (ModelProviderError, TimeoutError) as exc:
            last_error = exc
            if attempt < max_retries:
                backoff = 2**attempt
                _logger.info(
                    "execution attempt %d failed, retrying in %ds",
                    attempt + 1,
                    backoff,
                )
                await asyncio.sleep(backoff)
            continue

    if last_error is not None:
        raise last_error
    raise ModelProviderError("execution failed with no error details")
