# Add Coding-Agent Hooks (Claude Code + OpenCode)

## Why

The four detectors exist as a library and an offline runner, but nothing *enforces* them at
the moment an agent actually acts. Coding-agent harnesses expose exactly the right
interception points — a hook before a tool call runs, on a prompt entering the session, on
content returned into context, at session end — and the detectors' `intervention` vocabulary
(`allow`/`warn`/`block`/`confirm`) was designed to be an operator decision. This change
wires the two together for the two harnesses in daily use here (Claude Code and OpenCode),
behind a harness-agnostic core so a third tool is a new thin adapter, not a rewrite.

## What Changes

- Add a **gate engine**: a harness-agnostic layer that takes a normalized gate request
  (surface: `tool_call`, `prompt`, `content`, `output`, or `transcript`, plus payload and
  context), routes it to the right detector, and returns a validated **gate decision**
  (`allow`/`warn`/`block`/`confirm` + rationale + the underlying verdict).
- **Tiered escalation** inside the gate: the shallow mocks run as a free, instant first
  pass; a mock *positive* decides immediately (its keyword hits are high-precision), while a
  mock *negative* — the known-unreliable case — escalates to a configured fast real model.
  With no model configured, the gate runs mock-only and stays fully offline.
- **Fail-closed everywhere**: any error, timeout, unknown surface, or schema-invalid verdict
  inside the gate yields a `block` decision with the failure as its rationale — never a
  silent allow. A fail-open path is not a security control.
- Add a **hook gateway CLI** (`agent-tripwire-gate`): one JSON request on stdin → one gate
  decision JSON on stdout, with strict exit-code semantics. This is the stable protocol
  every harness adapter speaks, current and future.
- Add a **Claude Code adapter**: hook scripts plus a ready-to-paste `settings.json` hooks
  block mapping harness events to surfaces (pre-tool-use → action classification,
  user-prompt-submit → injection detection, post-tool-use → injection screening of returned
  content, session-stop → transcript audit and sensitive-output flagging), with setup docs.
- Add an **OpenCode adapter**: a TypeScript plugin mapping the equivalent OpenCode hook
  points to the same gateway protocol, with setup docs.
- Setup instructions for both adapters, including the residual-risk note on harness-side
  timeout behavior that the adapter cannot fully control.

## Capabilities

### New Capabilities

- `gate-engine`: the normalized surface→detector routing, tiered mock→model escalation,
  decision mapping, and fail-closed semantics, as a validated-schema core.
- `hook-gateway`: the harness-agnostic stdin/stdout JSON protocol (`agent-tripwire-gate`)
  that adapters call, including its error and exit-code contract.
- `claude-code-integration`: the Claude Code hook scripts, settings snippet, event→surface
  mapping, and setup instructions.
- `opencode-integration`: the OpenCode plugin, event→surface mapping, and setup
  instructions.

### Modified Capabilities

None — the four detector capabilities (`risk-detection`, `transcript-audit`,
`injection-detection`, `sensitive-output-detection`) and `classification-schema` are
consumed unchanged; the gate sits on top of their public entry points.

## Impact

- **Code**: new `gate.py` (engine + request/decision schemas) and `hook_cli.py` (gateway
  CLI, new console script) in `src/agent_tripwire/`; new `integrations/claude-code/`
  (hook wrapper + settings snippet + README) and `integrations/opencode/` (plugin `.ts` +
  README) at the repo root; README section pointing at both.
- **Tests**: gate-engine unit tests (routing, tiering, fail-closed paths), gateway CLI
  tests (protocol, malformed input, exit codes), adapter contract tests exercising the
  wrappers against recorded harness event payloads. Existing suites untouched.
- **Dependencies**: none new at runtime for the mock tier (pydantic only); escalation reuses
  the existing optional `litellm` extra. The OpenCode plugin is dependency-free TypeScript
  calling the CLI.
