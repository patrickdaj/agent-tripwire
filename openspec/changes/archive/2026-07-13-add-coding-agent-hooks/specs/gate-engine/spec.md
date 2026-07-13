# gate-engine Delta

## ADDED Requirements

### Requirement: Gate entry point

The system SHALL expose `evaluate(request, ...)` that takes a `GateRequest` — a `surface`
(one of exactly: `tool_call`, `prompt`, `content`, `output`, `transcript`), a payload
(string or structured, normalized to text), and optional context (harness, session id, tool
name, stated task) — and returns a validated `GateDecision` carrying a `decision` (the
existing intervention enum: `allow`, `warn`, `block`, `confirm`), a `rationale`, the
detector that ran, whether escalation occurred, the underlying verdict when a detector ran,
and an `error` field that is set exactly when the decision was produced by the fail-closed
path. A `GateDecision` with `error` set SHALL have `decision` `block`.

#### Scenario: Evaluate returns a validated decision

- **WHEN** `evaluate(request)` is called with any supported surface
- **THEN** it returns a `GateDecision` that satisfies schema validation, naming the detector that produced it

#### Scenario: An errored decision is always a block

- **WHEN** a `GateDecision` is constructed with `error` set and a `decision` other than `block`
- **THEN** validation raises an error describing the inconsistency

### Requirement: Surface routing

The system SHALL route each surface to its detector: `tool_call` to action classification,
`prompt` and `content` to injection detection, `output` to sensitive-data flagging, and
`transcript` to the transcript audit. A request whose surface is not one of the five SHALL
fail closed: a `block` decision with `error` set, not an exception and not an allow.

#### Scenario: Each surface reaches its detector

- **WHEN** requests with each of the five surfaces are evaluated
- **THEN** each decision names the detector matching its surface and carries that detector's verdict shape

#### Scenario: Unknown surface fails closed

- **WHEN** a request carries an unrecognized surface value
- **THEN** the decision is `block` with `error` set describing the unknown surface

### Requirement: Tiered escalation

The system SHALL evaluate every request on the offline mock tier first. A mock positive
verdict (risky, injection_attempt, flagged, or out_of_scope) SHALL decide immediately
without a model call. A mock negative SHALL, when an escalation model is configured,
re-run the detector on that model and decide from its verdict; when no escalation model is
configured (mock-only mode), a mock negative SHALL decide `allow`. Mock-only mode is an
explicit configuration, not a failure fallback.

Exception: the retrospective surfaces (`transcript` and `output`) SHALL be evaluated
directly on the escalation model whenever one is configured — regardless of the mock
verdict — truncating oversized transcript payloads from the oldest tool calls while
preserving the stated task and the most recent activity. With no model configured they use
the mock tier like any other surface.

#### Scenario: Mock positive decides without escalation

- **WHEN** the mock tier returns a positive verdict and an escalation model is configured
- **THEN** the decision derives from the mock verdict and no model call is made, with `escalated` false

#### Scenario: Mock negative escalates when a model is configured

- **WHEN** the mock tier returns a negative verdict and an escalation model is configured
- **THEN** the detector is re-run on that model and the decision derives from the model's verdict, with `escalated` true

#### Scenario: Mock-only mode allows on a mock negative

- **WHEN** the mock tier returns a negative verdict and no escalation model is configured
- **THEN** the decision is `allow`, with `escalated` false and no `error`

#### Scenario: Retrospective surfaces always use the configured model

- **WHEN** a `transcript` or `output` request is evaluated with an escalation model configured
- **THEN** the decision derives from the model's verdict with `escalated` true, even where the mock tier would have returned a positive verdict

#### Scenario: Oversized transcripts are truncated oldest-first

- **WHEN** a `transcript` payload exceeds the bounded payload size for escalation
- **THEN** the oldest tool calls are dropped while the stated task and most recent activity are preserved, and the evaluation still completes

### Requirement: Decision mapping

The system SHALL map verdicts to decisions as follows: for action and injection verdicts,
the verdict's own `intervention` passes through unchanged; for sensitive-data verdicts,
`clean` maps to `allow` and `flagged` maps to `block` when severity is `high` or `critical`
and to `warn` otherwise; for transcript verdicts, `in_scope` maps to `allow` and
`out_of_scope` maps to `warn`. The mapping SHALL live in the gate, not in the detector
schemas.

#### Scenario: Intervention verdicts pass through

- **WHEN** a `tool_call` or `prompt` evaluation produces a verdict with an intervention
- **THEN** the decision equals that intervention

#### Scenario: Sensitive-data severity splits block from warn

- **WHEN** an `output` evaluation is flagged with severity `high` or `critical`
- **THEN** the decision is `block`
- **AND WHEN** it is flagged with severity `low` or `medium`
- **THEN** the decision is `warn`

#### Scenario: Transcript findings warn, never block

- **WHEN** a `transcript` evaluation returns `out_of_scope`
- **THEN** the decision is `warn`

### Requirement: Fail-closed evaluation

The system SHALL produce a `block` decision with `error` set — never an allow and never an
unhandled exception — for every internal failure: a detector or provider exception, a
schema-invalid verdict, an escalation attempt that fails for any reason (missing optional
dependency, authentication, exhausted retries), or an exceeded deadline. The failure
reason SHALL appear in the decision's rationale so an operator can distinguish an
infrastructure block from a detection.

#### Scenario: Detector exception blocks

- **WHEN** the routed detector raises during evaluation
- **THEN** `evaluate` returns (does not raise) a `block` decision with `error` set and the failure in the rationale

#### Scenario: Escalation failure blocks

- **WHEN** a mock negative escalates and the model call fails for any reason
- **THEN** the decision is `block` with `error` set, not `allow`

### Requirement: Evaluation deadline

The system SHALL bound each evaluation by a configurable deadline (default 10 seconds,
configurable via `AGENT_TRIPWIRE_DEADLINE_MS`); an evaluation that exceeds it SHALL resolve
to a `block` decision with `error` set. The escalation model id SHALL be configurable via
`AGENT_TRIPWIRE_MODEL`, with unset meaning mock-only mode.

#### Scenario: Deadline exceeded blocks

- **WHEN** an evaluation (including any escalation call) exceeds the configured deadline
- **THEN** it resolves to a `block` decision with `error` set rather than waiting indefinitely

#### Scenario: Configuration is read from the environment

- **WHEN** `AGENT_TRIPWIRE_MODEL` is set to a model id
- **THEN** mock negatives escalate to that model
- **AND WHEN** it is unset
- **THEN** the gate runs mock-only

### Requirement: Operating mode escape hatch

The system SHALL read `AGENT_TRIPWIRE_MODE` with exactly three recognized values:
`enforce` (the default when unset), `mock-only` (force the mock tier regardless of any
configured model), and `off` (every evaluation returns `allow` immediately, with a
rationale that explicitly marks the gate as bypassed). An unrecognized mode value SHALL
fail closed like any other internal failure. This is the sanctioned operator downgrade for
false positives and infrastructure blocks — visible in the environment and in every
decision it produces, and reversible per session.

#### Scenario: Off mode allows loudly

- **WHEN** `AGENT_TRIPWIRE_MODE=off` and any request is evaluated
- **THEN** the decision is `allow` with a rationale stating the gate was bypassed, and no detector runs

#### Scenario: Mock-only mode overrides a configured model

- **WHEN** `AGENT_TRIPWIRE_MODE=mock-only` and `AGENT_TRIPWIRE_MODEL` is set
- **THEN** no model call is made and decisions derive from the mock tier alone

#### Scenario: Unknown mode fails closed

- **WHEN** `AGENT_TRIPWIRE_MODE` carries an unrecognized value
- **THEN** evaluations resolve to `block` with `error` set describing the bad mode
