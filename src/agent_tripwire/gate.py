"""The gate: where detector verdicts become enforcement decisions. ALL policy lives here.

``evaluate(request)`` takes a :class:`GateRequest` (or a raw dict — validated inside the
fail-closed boundary), routes its ``surface`` to the right detector, applies the tiered
mock→model strategy, maps the verdict to a decision, and returns a validated
:class:`GateDecision`. It never raises and never silently allows on failure: every
internal failure — unknown surface, detector exception, escalation failure, exceeded
deadline, unrecognized mode — resolves to a ``block`` decision with ``error`` set. A
fail-open path is not a security control.

Configuration (environment, overridable per call):
- ``AGENT_TRIPWIRE_MODEL``    — litellm id for tier-2 escalation; unset = mock-only.
- ``AGENT_TRIPWIRE_DEADLINE_MS`` — bound on one evaluation (default 10000); exceeded → block.
- ``AGENT_TRIPWIRE_MODE``     — ``enforce`` (default) | ``mock-only`` | ``off``. The
  sanctioned escape hatch: ``off`` allows *loudly* (every rationale says bypassed);
  an unknown value fails closed.
"""

import os
import threading
from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from .detector import (
    _action_text,
    audit_transcript,
    classify,
    detect_injection,
    flag_output,
)
from .schema import Intervention

DEFAULT_DEADLINE_MS = 10_000

# Transcript payloads sent to the escalation model are bounded; oversized ones are
# truncated oldest-first, preserving the stated task (the head) and the most recent
# activity (the tail) — the two ends an auditor actually needs.
MAX_TRANSCRIPT_CHARS = 24_000

_MODES = ("enforce", "mock-only", "off")


class Surface(str, Enum):
    """What kind of thing is being gated — the request's routing key."""

    tool_call = "tool_call"
    prompt = "prompt"
    content = "content"
    output = "output"
    transcript = "transcript"


# The retrospective surfaces: evaluated at session end, no latency pressure, and the
# mock tier is nearly decorative on them — so they go straight to the model when one
# is configured (see _evaluate).
_RETROSPECTIVE = frozenset({Surface.output, Surface.transcript})


class GateRequest(BaseModel):
    """One thing to gate: a surface, its payload (string or structured), and optional
    context (harness, session id, tool name, stated task) folded into what the
    detector sees."""

    model_config = ConfigDict(extra="forbid")

    surface: Surface
    payload: object
    context: dict | None = None


class GateDecision(BaseModel):
    """The gate's answer. ``decision`` reuses the detectors' intervention vocabulary —
    it was designed as the operator action. ``error`` is set exactly when the decision
    came from the fail-closed path, and an errored decision is always a block."""

    model_config = ConfigDict(extra="forbid")

    decision: Intervention
    rationale: str
    detector: str | None = None
    escalated: bool = False
    verdict: dict | None = None
    error: str | None = None

    @model_validator(mode="after")
    def _check_cross_field(self) -> "GateDecision":
        if self.error is not None and self.decision is not Intervention.block:
            raise ValueError(
                f"a decision with error set must be block, got decision={self.decision.value!r}"
            )
        return self

    def __str__(self) -> str:
        lines = [f"decision:     {self.decision.value}"]
        if self.detector:
            lines.append(f"detector:     {self.detector}{' (escalated)' if self.escalated else ''}")
        if self.error:
            lines.append(f"error:        {self.error}")
        lines.append(f"rationale:    {self.rationale}")
        return "\n".join(lines)


# surface → (detector name, callable). Lambdas resolve the entry-point names at call
# time so tests can monkeypatch e.g. `gate.classify` and still be routed to.
_DETECTORS = {
    Surface.tool_call: ("classify", lambda text, m: classify(text, model=m)),
    Surface.prompt: ("detect_injection", lambda text, m: detect_injection(text, model=m)),
    Surface.content: ("detect_injection", lambda text, m: detect_injection(text, model=m)),
    Surface.output: ("flag_output", lambda text, m: flag_output(text, model=m)),
    Surface.transcript: ("audit_transcript", lambda text, m: audit_transcript(text, model=m)),
}

# surface → the verdict value that counts as a positive (tripwire fired) at either tier.
_POSITIVE = {
    Surface.tool_call: "risky",
    Surface.prompt: "injection_attempt",
    Surface.content: "injection_attempt",
    Surface.output: "flagged",
    Surface.transcript: "out_of_scope",
}


def _blocked(reason: str) -> GateDecision:
    """The fail-closed decision. Every internal failure funnels through here."""
    return GateDecision(
        decision=Intervention.block,
        rationale=f"fail-closed: {reason}",
        error=reason,
    )


def _decide(surface: Surface, verdict) -> Intervention:
    """Map a validated detector verdict to a decision — the policy table from the
    design. Action and injection verdicts carry their own intervention; the other two
    schemas don't, so their mapping lives here, not bolted onto the schemas."""
    if surface in (Surface.tool_call, Surface.prompt, Surface.content):
        return Intervention(verdict.intervention.value)
    if surface is Surface.output:
        if verdict.verdict.value == "clean":
            return Intervention.allow
        if verdict.severity.value in ("high", "critical"):
            return Intervention.block
        return Intervention.warn
    # Surface.transcript — retrospective: the actions already ran; warn, never block.
    if verdict.verdict.value == "in_scope":
        return Intervention.allow
    return Intervention.warn


def _request_text(request: GateRequest) -> str:
    """The text the detector reasons over: the payload, with any context folded in so
    the model (and the keyword mocks) can see harness, tool name, and stated task."""
    if request.context:
        return _action_text({"context": request.context, "payload": request.payload})
    return _action_text(request.payload)


def _truncate_transcript(text: str) -> str:
    """Oldest-first truncation for oversized transcripts: keep the head (the stated
    task) and the tail (the most recent activity), drop the middle with a marker."""
    if len(text) <= MAX_TRANSCRIPT_CHARS:
        return text
    head_len = min(text.find("\n") + 1 or 200, 400)
    head = text[:head_len]
    tail_budget = MAX_TRANSCRIPT_CHARS - head_len - 64  # marker allowance
    tail = text[-tail_budget:]
    dropped = len(text) - head_len - tail_budget
    return f"{head}[... {dropped} chars of older activity truncated ...]\n{tail}"


def _evaluate(request: GateRequest, model: str | None, mode: str) -> GateDecision:
    """The tiered core (already inside the fail-closed boundary)."""
    name, run = _DETECTORS[request.surface]
    text = _request_text(request)
    effective_model = None if mode == "mock-only" else model

    # Retrospective surfaces: mock tier is nearly decorative on whole-session material
    # and there is no latency pressure at session end — go straight to the model.
    if request.surface in _RETROSPECTIVE and effective_model:
        if request.surface is Surface.transcript:
            text = _truncate_transcript(text)
        verdict = run(text, effective_model)
        return GateDecision(
            decision=_decide(request.surface, verdict), rationale=verdict.rationale,
            detector=name, escalated=True, verdict=verdict.model_dump(mode="json"),
        )

    # Tier 1: the free, offline mock. A positive is high-precision — decide from it.
    mock_verdict = run(text, "mock")
    if mock_verdict.verdict.value == _POSITIVE[request.surface]:
        return GateDecision(
            decision=_decide(request.surface, mock_verdict), rationale=mock_verdict.rationale,
            detector=name, escalated=False, verdict=mock_verdict.model_dump(mode="json"),
        )

    # Mock negative — the known-unreliable case. Tier 2 when a model is configured.
    if effective_model:
        verdict = run(text, effective_model)
        return GateDecision(
            decision=_decide(request.surface, verdict), rationale=verdict.rationale,
            detector=name, escalated=True, verdict=verdict.model_dump(mode="json"),
        )

    # Mock-only mode: an explicit configuration (keyword-level coverage was chosen),
    # not a failure path — so a mock negative allows.
    return GateDecision(
        decision=Intervention.allow, rationale=mock_verdict.rationale,
        detector=name, escalated=False, verdict=mock_verdict.model_dump(mode="json"),
    )


def _run_with_deadline(fn, deadline_ms: int):
    """Run `fn` on a daemon thread, bounded by the deadline. A hung evaluation raises
    TimeoutError here (→ block upstream) instead of hanging the hook — and the daemon
    thread can't keep the process alive after the decision is emitted."""
    result: dict = {}

    def target():
        try:
            result["value"] = fn()
        except BaseException as e:  # noqa: BLE001 — re-raised on the caller's thread below
            result["exc"] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(deadline_ms / 1000)
    if t.is_alive():
        raise TimeoutError(f"evaluation exceeded deadline of {deadline_ms}ms")
    if "exc" in result:
        raise result["exc"]
    return result["value"]


def evaluate(request, *, model: str | None = None,
             deadline_ms: int | None = None, mode: str | None = None) -> GateDecision:
    """Gate one request, returning a validated decision. Never raises.

    ``request`` may be a :class:`GateRequest` or a raw dict (validated inside the
    fail-closed boundary, so an unknown surface or malformed request blocks rather
    than raising). Keyword overrides beat the environment; the environment beats the
    defaults.
    """
    try:
        mode = mode or os.environ.get("AGENT_TRIPWIRE_MODE") or "enforce"
        if mode not in _MODES:
            return _blocked(f"unrecognized AGENT_TRIPWIRE_MODE {mode!r} (expected one of {_MODES})")
        if mode == "off":
            return GateDecision(
                decision=Intervention.allow,
                rationale="gate bypassed via AGENT_TRIPWIRE_MODE=off — no detector ran",
            )
        model = model or os.environ.get("AGENT_TRIPWIRE_MODEL") or None
        deadline = deadline_ms or int(os.environ.get("AGENT_TRIPWIRE_DEADLINE_MS", DEFAULT_DEADLINE_MS))
        if not isinstance(request, GateRequest):
            request = GateRequest(**request)  # a bad request (unknown surface) blocks below
        return _run_with_deadline(lambda: _evaluate(request, model, mode), deadline)
    except Exception as e:  # noqa: BLE001 — the fail-closed boundary
        return _blocked(f"{type(e).__name__}: {e}")
