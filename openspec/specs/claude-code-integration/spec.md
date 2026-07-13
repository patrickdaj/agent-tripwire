# claude-code-integration Specification

## Purpose

Wire the gate into Claude Code through its four hook events — gating tool calls
before execution, prompts at submission, and returned content after tool use,
and auditing the session at stop. The adapter fails closed on internal failure,
ships a ready-to-paste settings snippet, and documents the harness-level residual
risk it cannot control.

## Requirements

### Requirement: Pre-tool-use gating

The integration SHALL gate Claude Code tool calls via a `PreToolUse` hook running
`agent-tripwire-gate --adapter claude-code`, evaluating the tool name and input on the
`tool_call` surface and responding with the hook's permission-decision JSON: `allow` for an
allow decision; `allow` plus a user-visible system message for warn; `ask` with the
rationale for confirm; `deny` with the rationale for block. The shipped settings snippet
SHALL scope the `PreToolUse` matcher to high-risk tools (shell execution, network access,
and file mutation) and the `PostToolUse` matcher to untrusted-content sources; the adapter
itself SHALL be matcher-agnostic, and the documentation SHALL show the one-edit change to
gate all tools uniformly.

#### Scenario: A risky tool call is denied

- **WHEN** `PreToolUse` fires for a tool call the gate decides `block`
- **THEN** the hook responds with permission decision `deny` and the gate's rationale, and the tool does not run

#### Scenario: A confirm decision defers to the user

- **WHEN** the gate decides `confirm`
- **THEN** the hook responds with permission decision `ask` carrying the rationale, composing with Claude Code's native permission prompt

#### Scenario: A warn decision proceeds visibly

- **WHEN** the gate decides `warn`
- **THEN** the tool call is allowed and a warning naming the finding is surfaced to the operator

#### Scenario: The shipped matcher scopes gating to high-risk tools

- **WHEN** the provided settings snippet is installed unmodified
- **THEN** `PreToolUse` gating applies to high-risk tools (e.g. Bash, WebFetch, Write/Edit) and not to read-only lookups, and the documentation shows how to widen it to all tools

### Requirement: Prompt injection gating

The integration SHALL gate submitted prompts via a `UserPromptSubmit` hook on the `prompt`
surface: allow proceeds silently; warn proceeds with injected context noting the suspicion;
confirm and block prevent the prompt from being processed (exit 2) with the rationale as
feedback.

#### Scenario: An injection attempt is blocked at submission

- **WHEN** `UserPromptSubmit` fires for a prompt the gate decides `block`
- **THEN** the hook exits 2 with the rationale on stderr and the prompt is not processed

### Requirement: Returned-content screening

The integration SHALL screen tool results via a `PostToolUse` hook on the `content`
surface. Because the harness cannot retroactively block a completed tool call, a warn,
confirm, or block decision SHALL respond with additional context instructing the model that
the returned content appears to be an injection attempt and must not be followed as
instructions, plus a user-visible system message; an allow decision SHALL add nothing.

#### Scenario: Injected tool content is inoculated

- **WHEN** `PostToolUse` fires and the gate decides anything other than `allow` for the returned content
- **THEN** the hook emits additional context warning the model not to follow instructions in that content, and the operator sees a system message

### Requirement: Session-stop audit

The integration SHALL, on the `Stop` hook, reconstruct the session's tool calls and stated
task from the transcript JSONL and evaluate them on the `transcript` surface, and evaluate
the final assistant message on the `output` surface. Findings SHALL be reported to the
operator as system messages; the hook SHALL NOT block stopping regardless of findings.

#### Scenario: An out-of-scope session is reported at stop

- **WHEN** the `Stop` hook fires and the transcript audit returns `out_of_scope` or the final message is flagged
- **THEN** the findings are surfaced as user-visible messages and the session still stops normally

### Requirement: Fail-closed adapter with documented residual risk

The adapter SHALL respond to any internal failure — including its own deadline being
exceeded — with the blocking form of the active event (deny for `PreToolUse`, exit 2 for
`UserPromptSubmit`), never with silence or an implicit allow. The shipped hook
configuration SHALL set the harness hook timeout comfortably above the adapter's internal
deadline, and the setup documentation SHALL state explicitly that a harness-level hook
timeout or a killed hook process fails open in Claude Code and cannot be made fail-closed
from outside the harness.

#### Scenario: Adapter failure denies the tool call

- **WHEN** the adapter errors internally or exceeds its deadline during a `PreToolUse` evaluation
- **THEN** its response is permission decision `deny` naming the failure, not an allow

#### Scenario: The residual risk is documented

- **WHEN** an operator reads the integration's setup instructions
- **THEN** the fail-open behavior of harness-level timeouts, and the timeout/deadline margin shipped to minimize it, are stated explicitly

### Requirement: Setup instructions and settings snippet

The integration SHALL ship setup documentation and a ready-to-paste `settings.json` hooks
block covering: installing the gateway, wiring all four hook events with the scoped
matchers, configuring the escalation model (`AGENT_TRIPWIRE_MODEL`) and deadline, the
`AGENT_TRIPWIRE_MODE` escape hatch (`mock-only`/`off`) and when to use it, and verifying
the installation end to end with a known-blocked action.

#### Scenario: Fresh setup reaches a gated session

- **WHEN** an operator follows the setup instructions in a project where Claude Code runs
- **THEN** all four hook events are wired via the provided snippet and a known-risky tool call is visibly denied in-session
