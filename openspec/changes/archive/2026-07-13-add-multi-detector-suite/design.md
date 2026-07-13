# Design — add-multi-detector-suite

## Context

agent-tripwire is a mock-first detector primitive: one agent action in, a schema-validated
`RiskClassification` out. The architecture is three thin layers — `schema.py` (the product
spec, closed enums + cross-field invariants), `providers.py` (a deterministic keyword mock and
a litellm/instructor real-model path behind one `complete` signature), `detector.py` (one verb,
`classify`) — plus `__main__.py`, a runner over hand-labeled `inputs.jsonl` rows that prints
verdict-vs-expected with a non-gating match marker.

This change adds three detectors over new subject types: a tool-call **transcript** (what did
the agent touch, was any of it out of scope), a **prompt/input** (injection attempt?), and a
**model output** (sensitive data — secrets, PII, internal names — headed somewhere it
shouldn't). The schema module explicitly deferred these generalizations "to the detector that
first needs them" — this is that change.

Constraints carried forward from the existing design:

- Mock path stays dependency-free (pydantic only), offline, deterministic.
- Mocks stay intentionally shallow — keyword heuristics whose misses are the honest baseline,
  not bugs to hide.
- Every result the caller sees has already passed pydantic validation; malformed producer
  output raises, never coerces.
- The exit code reflects wiring + schema validation only; label disagreement is displayed,
  never fatal.

## Goals / Non-Goals

**Goals:**

- One detector per new subject type, each with its own closed-enum result schema and
  cross-field invariants, its own shallow mock, and real hand-labeled inputs (≥1
  keyword-blind each).
- Reuse the existing litellm/instructor path — including temperature-drop, rate-limit
  retry, and bounded validation-retry behavior — for all detectors by parameterizing it
  with (response schema, system prompt) instead of duplicating it.
- Keep the existing action detector's public surface (`classify(action, model)`) and all
  existing tests unchanged.
- Route mixed `inputs.jsonl` rows to the right detector via a `kind` field and report all
  detectors' results under the existing rendering/exit contracts.

**Non-Goals:**

- No eval harness, pass-rate metrics, or golden set — still deferred.
- No single "uber-schema" union type or `subject` discriminator on the wire; each detector
  returns its own model. (The discriminator lives in the *input* rows, not the results.)
- No redaction/masking of sensitive findings — the flag reports evidence verbatim; handling
  is the operator's call.
- No multi-turn conversation analysis; a transcript is one bounded list of tool calls.

## Decisions

### D1: One result schema per detector, not one generalized union

Each detector gets its own pydantic model in `schema.py`:

- `TranscriptAudit` — `verdict` (`in_scope` | `out_of_scope`), `touched:
  list[TouchedResource]`, `rationale`. `TouchedResource` = `resource: str` (path, URL,
  command, table…), `kind` (`file` | `network` | `process` | `env` | `data_store` | `other`),
  `in_scope: bool`. Invariants: `out_of_scope` ⇔ at least one touched resource has
  `in_scope=False`; `in_scope` ⇒ all touched resources are in scope.
- `InjectionClassification` — `verdict` (`injection_attempt` | `clean`), `technique`
  (`instruction_override` | `role_manipulation` | `context_smuggling` |
  `tool_misuse_lure` | `encoding_obfuscation` | `none`), `severity` (reuses `Severity`),
  `intervention` (reuses `Intervention`), `rationale`. Invariants mirror
  `RiskClassification`: `clean` ⇒ `technique=none` ∧ `severity=none`; `injection_attempt`
  ⇒ a named technique.
- `SensitiveDataFlag` — `verdict` (`flagged` | `clean`), `findings:
  list[SensitiveFinding]`, `severity`, `rationale`. `SensitiveFinding` = `category`
  (`secret` | `pii` | `internal_name`), `evidence: str` (the offending excerpt),
  `destination: str | None` (where it was headed, when visible). Invariants: `flagged` ⇔
  `findings` non-empty; `clean` ⇒ `severity=none`.

*Why not a union?* The three verdict shapes are genuinely different (a scalar verdict, a
resource inventory, a findings list). A discriminated union buys nothing the caller needs —
each entry point already knows its return type statically — and would force every schema to
carry fields it doesn't use. Alternatives considered: a shared `BaseVerdict` with subject
discriminator (rejected: widens every schema for zero callers), stuffing everything into
`RiskClassification` (rejected: breaks its closed invariants and the existing spec).

All new schemas keep `extra="forbid"`, closed enums, `model_validator(mode="after")`
cross-field checks, and a human-readable `__str__` — the same conventions as
`RiskClassification`. `Severity` and `Intervention` are reused where they fit; new enums are
new types, not extensions of existing ones.

### D2: One entry point per detector in `detector.py`

`audit_transcript(transcript, model)`, `detect_injection(prompt, model)`,
`flag_output(output, model)` — alongside the unchanged `classify(action, model)`. Each
normalizes its input to text the same way `classify` does (str passes through, dict/list
renders to compact JSON) and returns its own validated model.

*Why not `detect(kind, payload, model)`?* Separate verbs give static return types and keep
each callsite self-documenting; the dynamic dispatch that does exist (JSONL rows) lives in
the runner, the one place that has a `kind` string in hand.

### D3: Providers parameterized by a detector descriptor

`providers.py` gains a small registry: `DETECTORS: dict[str, Detector]` where `Detector`
bundles `response_model`, `system_prompt`, and `mock` (a callable `str -> dict`). The four
entries are `action`, `transcript`, `prompt`, `output`.

- `complete(text, model, detector="action")` — the existing signature grows one defaulted
  parameter, so current callers and tests are untouched.
- `_litellm(text, model, *, response_model, system_prompt)` — the hardcoded
  `RiskClassification` and `_SYSTEM` become parameters. Everything else (instructor
  extraction, `_MAX_VALIDATION_RETRIES`, temperature-drop learning, rate-limit
  retry-with-budget, `_unwrap`) is shared verbatim — that behavior was spec'd and tested
  once and now covers all detectors for free.
- Each mock is a shallow, ordered keyword table like `_RULES`, deliberately blind to risk
  not spelled out in words. The transcript mock judges scope by matching tool-call text
  against the row's stated task keywords plus a small out-of-scope pattern list (`~/.ssh`,
  `.env`, `/etc/`, URLs not named in the task); the prompt mock looks for
  override/role/smuggling phrases; the output mock regex-matches obvious secret shapes
  (`sk-`, `AKIA`, `-----BEGIN`), email/SSN-ish PII patterns, and module-level
  internal-name marker patterns (e.g. `codename X`, `internal-only`) — kept in the mock
  rather than carried per input row so the mock signature stays `str -> dict`.

### D4: Input rows carry a `kind`; the runner routes and groups

`inputs.jsonl` rows gain `"kind": "action" | "transcript" | "prompt" | "output"`; a missing
`kind` means `action`, so the existing three rows are valid as-is. The payload field stays
`action` for actions and is `transcript` / `prompt` / `output` for the new kinds; `expected`
holds the hand label with per-kind comparable fields (`verdict` always; `risk_type`,
`technique`, or `categories` when the label names them).

The runner maps `kind` → entry point, classifies every row, and renders one report grouped
by detector (a `kind` column in the rich table; a `kind:` line in plain blocks). Match logic
extends `_matches` per kind but keeps the same contract: verdict must match, and the finer
field is compared only when the label names it. Exit code rule is unchanged: non-zero iff
some row errored (bad wiring/validation), never on a miss. An unknown `kind` is a per-row
error (shown, counted in the exit code) — it's a wiring bug, not a classification miss.

### D5: Ship ≥3 labeled inputs per new detector, each set including a keyword-blind row

Same sourcing bar as the original three: real material (from our own transcripts/prompts),
hand-labeled `expected`, and at least one row per detector the shallow mock is *expected* to
miss — e.g. an exfil transcript phrased as routine file ops, an injection written as polite
prose with no trigger phrase, a secret with a nonstandard shape. The visible `✗` rows remain
the point.

## Risks / Trade-offs

- **[Shallow mocks look bad on new detectors]** → Intentional and documented in each mock's
  docstring; the miss markers are the honest baseline the future eval quantifies. Not a bug.
- **[Registry indirection obscures the one-detector simplicity]** → The registry is a flat
  dict of three-field descriptors in one module; each detector entry point stays a two-line
  function. No dynamic imports, no plugins.
- **[Parameterizing `_litellm` could regress the hardened retry behavior]** → The
  temperature/rate-limit/validation-retry tests in `test_providers_litellm.py` keep running
  against the action detector unchanged; new tests only add coverage that the parameters
  (schema, prompt) actually vary per detector.
- **[Transcript scope judgment needs the task, not just the transcript]** → Transcript rows
  carry the stated task alongside the tool calls (both rendered into the text the model
  sees); without a task, scope is unjudgeable and the row is mislabeled, not the detector.
- **[Sensitive-data evidence is reproduced verbatim in output]** → Accepted for this slice;
  inputs are our own curated material, and redaction is an explicit non-goal recorded above.
- **[`inputs.jsonl` schema drift]** → Missing `kind` defaults to `action` (back-compat);
  unknown `kind` fails loud per-row. No silent skips.

## Open Questions

- None blocking. Enum membership (e.g. adding `financial` to `SensitiveCategory`, more
  injection techniques) is expected to evolve; each addition is a one-line schema + spec
  delta later.
