# opencode-integration Specification

## Purpose

Wire the gate into OpenCode through a dependency-free plugin — gating tool calls
before execution, prompts on incoming messages, and returned content after tool
use, and auditing the session when idle. The plugin enforces its own deadline
(the harness applies none), fails closed on blocking-capable hooks, and ships
setup documentation with its harness-specific caveats.

## Requirements

### Requirement: Pre-execution tool gating

The integration SHALL provide an OpenCode plugin whose `tool.execute.before` hook evaluates
tool calls (tool name plus arguments) on the `tool_call` surface: allow returns
normally; warn logs a warning through the harness and returns; confirm and block throw an
error carrying the rationale so the tool never executes. Because the harness currently has
no reliable ask primitive, a confirm decision SHALL degrade to a block whose message states
that the call was blocked pending operator confirmation and how to proceed. Because the
harness has no per-hook matcher configuration, the plugin SHALL scope gating via editable
tool-name sets declared as constants at the top of the plugin file: a high-risk set for
`tool.execute.before` and an untrusted-content set for `tool.execute.after`; tools outside
the sets pass through ungated.

#### Scenario: A risky tool call is blocked before execution

- **WHEN** `tool.execute.before` fires for a call the gate decides `block`
- **THEN** the plugin throws with the rationale and the tool does not run

#### Scenario: Confirm degrades to an explanatory block

- **WHEN** the gate decides `confirm`
- **THEN** the plugin throws with a message identifying the block as pending-confirmation and telling the operator how to proceed

#### Scenario: Tools outside the scoped sets pass through

- **WHEN** `tool.execute.before` fires for a tool not in the plugin's high-risk set
- **THEN** the plugin returns without invoking the gateway

### Requirement: Prompt injection gating

The integration SHALL evaluate incoming user messages via the `chat.message` hook on the
`prompt` surface, throwing on a confirm or block decision to abort the prompt flow. The
plugin documentation SHALL flag that aborting via a `chat.message` throw is
verified-but-undocumented harness behavior that may change.

#### Scenario: An injection attempt aborts the prompt

- **WHEN** `chat.message` fires for input the gate decides `block`
- **THEN** the plugin throws with the rationale and the prompt is not sent to the model

### Requirement: Returned-content quarantine

The integration SHALL screen tool results via `tool.execute.after` on the `content`
surface. A warn decision SHALL prepend a clearly marked warning banner to the result text;
a confirm or block decision SHALL replace the result text entirely with a quarantine notice
(finding category, rationale, and original content length) so the blocked content never
reaches the model; an allow decision SHALL leave the result untouched.

#### Scenario: Injected content never reaches the model

- **WHEN** `tool.execute.after` fires and the gate decides `block` for the returned content
- **THEN** the result text delivered to the model is the quarantine notice, not the original content

#### Scenario: A warning banner rides along on warn

- **WHEN** the gate decides `warn`
- **THEN** the original result is preserved with a marked warning banner prepended

### Requirement: Session-idle audit

The integration SHALL, on the `session.idle` event, reconstruct the session's tool calls
through the harness client's session-messages API and evaluate them on the `transcript`
surface, reporting findings through the harness's logging channel. The audit SHALL be
report-only.

#### Scenario: An out-of-scope session is reported at idle

- **WHEN** `session.idle` fires and the transcript audit returns `out_of_scope`
- **THEN** the findings are logged visibly to the operator and nothing is blocked retroactively

### Requirement: Plugin-enforced deadline and fail-closed semantics

The plugin SHALL enforce its own deadline on every gateway invocation — the harness applies
no hook timeouts, so a hung gate would otherwise hang the session — and SHALL treat a
deadline hit, a spawn failure, a non-zero gateway exit, or unparseable gateway output as a
block decision on blocking-capable hooks. No failure path SHALL resolve to an implicit
allow.

#### Scenario: A hung gateway blocks rather than hangs

- **WHEN** the gateway process exceeds the plugin's deadline during a `tool.execute.before` evaluation
- **THEN** the plugin kills it and throws a block naming the timeout, and the session continues

#### Scenario: Gateway failure blocks

- **WHEN** the gateway cannot be spawned or returns unparseable output
- **THEN** the plugin treats the decision as `block` on blocking-capable hooks

### Requirement: Setup instructions

The integration SHALL ship setup documentation covering: where to place the plugin (project
`.opencode/plugins/` or global), that it requires no npm dependencies, configuring the
escalation model and deadline via environment, the `AGENT_TRIPWIRE_MODE` escape hatch,
editing the scoped tool-name sets, a manual smoke checklist, and the documented caveats
(`chat.message` abort semantics, absence of harness hook timeouts,
confirm-degrades-to-block).

#### Scenario: Fresh setup reaches a gated session

- **WHEN** an operator follows the setup instructions in a project where OpenCode runs
- **THEN** the plugin loads at startup and a known-risky tool call is visibly blocked with the gate's rationale
