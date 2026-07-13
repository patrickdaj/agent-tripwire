# Tasks — add-coding-agent-hooks

## 1. Gate engine

- [x] 1.1 Add `GateRequest`/`GateDecision` models to new `src/agent_tripwire/gate.py` (surface enum, decision reusing `Intervention`, error⇒block cross-field validator, readable `__str__`s)
- [x] 1.2 Implement `evaluate()`: surface→detector routing, context folding into detector text, unknown-surface fail-closed block
- [x] 1.3 Implement tiering: mock-first pass, positive-decides-immediately, negative escalates to `AGENT_TRIPWIRE_MODEL` when set, mock-only allows when unset; retrospective surfaces (`transcript`/`output`) skip straight to the model when configured, with oldest-first transcript truncation preserving task + recent activity
- [x] 1.4 Implement the decision-mapping table (interventions pass through; sensitive severity high/critical→block else warn; transcript out_of_scope→warn)
- [x] 1.5 Implement fail-closed wrapping (detector/provider exceptions, invalid verdicts, escalation failures) and the `AGENT_TRIPWIRE_DEADLINE_MS` deadline (exceeded → block)
- [x] 1.6 Implement `AGENT_TRIPWIRE_MODE` (enforce default / mock-only forces mock tier / off allows immediately with bypass-marked rationale; unknown value fails closed)
- [x] 1.7 Tests: schema validation (incl. error⇒block), routing per surface + unknown surface, both tiers with a faked `complete` seam, retrospective always-escalate + truncation, every mapping row, every fail-closed trigger (incl. unknown mode), deadline expiry, all three modes

## 2. Gateway CLI

- [x] 2.1 Add `src/agent_tripwire/hook_cli.py` + `agent-tripwire-gate` console script: neutral mode (one GateRequest JSON in → one GateDecision JSON out, exit 0 incl. blocks)
- [x] 2.2 Malformed/empty/schema-invalid stdin → emitted block decision (exit 0); emission failure → non-zero exit with one-line stderr
- [x] 2.3 Tests: subprocess round-trip, block-exits-zero, garbage-input block, no-silent-success contract

## 3. Claude Code adapter

- [x] 3.1 Add `src/agent_tripwire/adapters/claude_code.py` + `--adapter claude-code` flag: dispatch on `hook_event_name`, translate events → GateRequests (PreToolUse→tool_call, UserPromptSubmit→prompt, PostToolUse→content, Stop→transcript+output), no policy in the adapter
- [x] 3.2 Implement per-event responses: permissionDecision allow/ask/deny (+systemMessage on warn), exit-2 prompt block (+additionalContext on warn), PostToolUse inoculation context + systemMessage, Stop report-only systemMessage
- [x] 3.3 Implement transcript-JSONL parsing for Stop (tool_use/tool_result blocks → transcript text; first user prompt → stated task; last assistant text → output surface)
- [x] 3.4 Fail-closed adapter wrapper: any internal error/deadline → the event's blocking form; unsupported event → blocking form
- [x] 3.5 Write `integrations/claude-code/settings.snippet.json` (scoped matchers: PreToolUse→`Bash|WebFetch|WebSearch|Write|Edit|NotebookEdit`, PostToolUse→`Read|WebFetch|Bash|WebSearch`; 30s hook timeout above the gate deadline) and `integrations/claude-code/README.md` (install, model/deadline config, `AGENT_TRIPWIRE_MODE` escape hatch, the one-edit change to gate all tools, end-to-end verification with a known-blocked action, explicit harness fail-open residual-risk note)
- [x] 3.6 Tests: recorded event payloads through `--adapter claude-code` asserting exact response JSON/exit codes for all decisions per event, fail-closed responses, Stop against a fixture transcript JSONL

## 4. OpenCode adapter

- [x] 4.1 Write `integrations/opencode/agent-tripwire.ts`: plugin exporting hooks for tool.execute.before (throw on block/confirm-with-degrade-message, log on warn), chat.message (throw on block), tool.execute.after (warn banner / quarantine rewrite of output.output), event session.idle (client.session.messages → transcript audit → client.app.log report); editable `HIGH_RISK_TOOLS` / untrusted-content tool-name sets as top-of-file constants, tools outside the sets pass through ungated
- [x] 4.2 Implement the plugin's own deadline + fail-closed handling around the spawned `agent-tripwire-gate` (kill on deadline, treat spawn failure/non-zero/unparseable as block on blocking-capable hooks)
- [x] 4.3 Write `integrations/opencode/README.md` (plugin placement, no npm deps, env config incl. `AGENT_TRIPWIRE_MODE`, editing the scoped tool sets, manual smoke checklist, caveats: chat.message abort is undocumented behavior, harness has no hook timeouts, confirm degrades to block)
- [x] 4.4 Tests: neutral-mode CLI tests exercising the exact request shapes the plugin sends (all four surfaces); TypeScript typecheck of the plugin when `bun` is available, skipped otherwise

## 5. Verify and document

- [x] 5.1 `uv run pytest` green; manual end-to-end check of the Claude Code path in this repo (known-blocked action denied in-session) recorded in the README
- [x] 5.2 Update the project README: gating section (four surfaces, tiering, fail-closed stance), pointers to both integration READMEs
