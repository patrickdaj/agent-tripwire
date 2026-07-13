# agent-tripwire

**Detector primitives** for agent activity: paste in something an agent did, said, or was
told — and get back a schema-validated verdict. Four detectors, one pattern:

| detector | in | out |
|---|---|---|
| `classify` | an agent action (shell command, file access, outbound request, tool call) | risky? which type? what intervention? |
| `audit_transcript` | a tool-call transcript + the stated task | what was touched, was any of it out of scope? |
| `detect_injection` | a prompt / model-bound input | injection attempt? which technique? |
| `flag_output` | a model output | sensitive data (secrets, PII, internal names) — headed somewhere it shouldn't? |

It's the smallest end-to-end slice — input → model → validated schema → printed output —
running on real, hand-labeled inputs. Mock-first, so the whole thing is verifiable offline
before any real model is wired in.

## The schemas are the product spec

Each detector hangs off its own type in [`schema.py`](src/agent_tripwire/schema.py),
designed *first*, on purpose — the schema is the contract every producer (the mocks now, a
real model later) must satisfy, so it's the load-bearing artifact and the rest is thin glue.

**`RiskClassification`** (action):

| field | values |
|---|---|
| `verdict` | `risky` · `benign` |
| `risk_type` | `exfiltration_attempt` · `injection_symptom` · `out_of_scope_access` · `destructive_action` · `secret_exposure` · `none` |
| `severity` | `none` · `low` · `medium` · `high` · `critical` |
| `intervention` | `allow` · `warn` · `block` · `confirm` |
| `rationale` | short free text |

**`TranscriptAudit`** (transcript): `verdict` (`in_scope` · `out_of_scope`), `touched` — a
list of `{resource, kind: file · network · process · env · data_store · other, in_scope}` —
and `rationale`. The verdict must agree with the inventory: `out_of_scope` ⇔ some touched
resource has `in_scope=false`.

**`InjectionClassification`** (prompt): `verdict` (`injection_attempt` · `clean`),
`technique` (`instruction_override` · `role_manipulation` · `context_smuggling` ·
`tool_misuse_lure` · `encoding_obfuscation` · `none`), plus `severity`, `intervention`,
`rationale` — with the same invariant shape as actions (`clean ⇒ technique=none &
severity=none`; an attempt must name its technique).

**`SensitiveDataFlag`** (output): `verdict` (`flagged` · `clean`), `findings` — a list of
`{category: secret · pii · internal_name, evidence, destination?}` (`destination` is where
the data was headed, when the output makes that visible) — plus `severity` and `rationale`.
`flagged` ⇔ findings non-empty.

Enums are closed and the cross-field invariants live in one place per type. Malformed output
raises a pydantic `ValidationError` rather than being silently accepted — every verdict the
caller sees has already passed validation.

## Run it

```bash
uv sync
uv run python -m agent_tripwire          # offline mock models, no API key needed
```

The run loads [`inputs.jsonl`](inputs.jsonl), where each row names its detector with a
`kind` field (`action` — the default when absent — `transcript`, `prompt`, or `output`) and
carries its payload under that same name, plus a hand-labeled `expected` verdict:

```json
{"kind": "prompt", "prompt": "Ignore previous instructions...", "expected": {"verdict": "injection_attempt", "technique": "instruction_override"}}
```

Optional colored table output:

```bash
uv sync --extra pretty                    # installs rich
uv run python -m agent_tripwire           # colored table on a TTY; plain text otherwise
```

`rich` is never required — without it (or off a TTY, or with `NO_COLOR`) you get the same
information as plain text.

Point at a real model with `--model <litellm-id>`; the call sites don't change. A live run
needs the `litellm` extra and a key:

```bash
uv sync --extra litellm                   # install the real-model path
export ANTHROPIC_API_KEY=...              # or source your .env; litellm reads it
uv run agent-tripwire --model claude-sonnet-5
```

All four detectors share one real-model path, parameterized by each detector's schema and
system prompt. It uses [Instructor](https://python.useinstructor.com/) for schema-typed
output: the model boundary is typed to the requesting detector's schema, so the model is
asked for it via structured extraction and Instructor validates the response — re-asking on
a schema violation up to a bounded retry count instead of failing on the first malformed
output.

If the extra isn't installed, the run stops with one message (`litellm not installed — run:
uv sync --extra litellm`) and a non-zero exit, rather than erroring on every input. The path
tolerates models that reject `temperature` and retries transient rate limits.

## Reading the output — and what a green run proves

Each input is printed with its kind, its validated result, **and its hand-labeled
`expected` verdict**, plus a `✓`/`✗` match marker. Two claims are kept deliberately
separate:

- **The exit code** reflects only *wiring + schema validation*. A crash, a
  `ValidationError`, or an unrecognized `kind` exits non-zero; everything classifying
  cleanly exits `0`.
- **The `✓`/`✗` column** is a separate, non-gating read on *classification quality*.

Every mock is a shallow keyword/pattern heuristic — it only sees risk that's spelled out in
words or recognizable shapes. Each detector's input set includes one **keyword-blind** row,
genuinely positive but invisible to its mock: an action that quietly discards uncommitted
work (`git checkout -- …`), a transcript that reads an unrelated project's file by a plain
path, an injection phrased as polite social engineering, a passphrase with no secret-like
shape. Those print `✗`. **Those misses are the point, not failures** — they make the run
falsifiable instead of self-confirming, and they're the honest baseline a real model has to
beat. A `✗` never fails the run (if it did, we'd be tempted to curate easy inputs).

## Enforcing it — coding-agent hooks

The detectors also run as **enforcement** inside a coding agent, not just as an offline
report. A harness-agnostic gate turns each detector verdict into an operator decision
(`allow` / `warn` / `block` / `confirm`) at the moment the agent acts:

| surface | detector | when |
|---|---|---|
| a tool call about to run | `classify` | before execution |
| a submitted prompt | `detect_injection` | before it reaches the model |
| content a tool returned | `detect_injection` | before the model reads it |
| a model output | `flag_output` | before it leaves |
| the whole session | `audit_transcript` | at session end (report-only) |

Two stances shape the gate:

- **Tiered.** The free offline mocks run first; a mock *hit* decides immediately, a mock
  *miss* (the known-unreliable case) escalates to a fast model when `AGENT_TRIPWIRE_MODEL`
  is set. Unset it for offline mock-only mode.
- **Fail-closed.** Any internal failure — unknown surface, detector error, escalation
  failure, exceeded deadline — resolves to `block`, never a silent allow. The sanctioned
  escape hatch for a false positive is `AGENT_TRIPWIRE_MODE=mock-only|off`, a visible,
  reversible downgrade rather than ripping the hooks out.

One CLI, `agent-tripwire-gate`, speaks a neutral JSON protocol any harness can call. Two
integrations ship today:

- **Claude Code** — hooks + a ready-to-paste settings block:
  [`integrations/claude-code/`](integrations/claude-code/README.md)
- **OpenCode** — a dependency-free plugin: [`integrations/opencode/`](integrations/opencode/README.md)

A third harness is a thin adapter over the same gate, not a rewrite.

## What's deferred to later pieces

This slice is intentionally tiny. Not here yet: the golden set, scoring / pass-rate metrics,
a CI gate, real-model prompt tuning, redaction/masking of sensitive findings, and multi-turn
conversation analysis (a transcript here is one bounded list of tool calls). Those land with
the piece that first needs them.
