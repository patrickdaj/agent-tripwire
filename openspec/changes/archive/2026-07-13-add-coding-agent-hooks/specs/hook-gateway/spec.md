# hook-gateway Delta

## ADDED Requirements

### Requirement: Neutral gateway protocol

The system SHALL provide an `agent-tripwire-gate` console script that, in its default
(neutral) mode, reads exactly one `GateRequest` JSON object from stdin, evaluates it
through the gate engine, and writes exactly one `GateDecision` JSON object to stdout with
exit code 0. This protocol is the stable seam every harness adapter — current and future —
speaks.

#### Scenario: Round trip

- **WHEN** a valid `GateRequest` JSON is piped to `agent-tripwire-gate`
- **THEN** stdout carries one `GateDecision` JSON matching the gate engine's evaluation and the exit code is 0

#### Scenario: Decisions of every kind exit zero

- **WHEN** the evaluation yields `block` (including a fail-closed block)
- **THEN** the decision is still emitted on stdout with exit code 0 — a block is a successful gating, not a process failure

### Requirement: Malformed input fails closed

The system SHALL respond to unparseable, empty, or schema-invalid stdin by emitting a
`block` `GateDecision` with `error` set (exit 0), not by crashing, hanging, or exiting
silently. There SHALL be no input for which the gateway produces neither a decision nor a
non-zero exit.

#### Scenario: Garbage input yields a blocking decision

- **WHEN** stdin is not valid JSON or is not a valid `GateRequest`
- **THEN** stdout carries a `block` decision whose rationale describes the input failure, with exit code 0

#### Scenario: No silent success

- **WHEN** the gateway cannot emit a decision for any reason
- **THEN** it exits non-zero with a one-line stderr message — and adapters are specified to treat any non-zero or unparseable gateway result as `block`

### Requirement: Claude Code adapter mode

The system SHALL provide `agent-tripwire-gate --adapter claude-code`, which reads a Claude
Code hook event JSON from stdin, dispatches on `hook_event_name`, translates the event into
the corresponding `GateRequest`, and emits the Claude-Code-shaped response for that event
type (permission decision JSON, additional-context JSON, system message, or exit-2 block)
per the claude-code-integration capability. Translation SHALL contain no gating policy —
policy lives in the gate engine only.

#### Scenario: Adapter mode dispatches on the event name

- **WHEN** a Claude Code event JSON with a supported `hook_event_name` is piped in adapter mode
- **THEN** the output is that event type's response shape, derived from the gate decision for the translated request

#### Scenario: Unsupported event fails closed

- **WHEN** adapter mode receives an event it does not recognize
- **THEN** it responds with that mode's blocking form rather than allowing by default
