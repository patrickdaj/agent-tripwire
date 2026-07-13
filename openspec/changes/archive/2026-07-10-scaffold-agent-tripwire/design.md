## Context

`agent-tripwire` is a new project seeded from the shape of
`00-arm-yourself/ai-eval-harness` (uv-managed, `src/` layout, mock-first so the
core is verifiable offline). This change delivers only the **Monday skeleton**:
input → model → validated schema → printed output, on 3 real inputs. The
overriding constraint is the hint — *design the schema first, it is the product
spec* — so the schema is the load-bearing artifact and everything else is thin
glue around it. Inputs are real agent actions already on disk, surfaced by the
Week-0 agent-activity MCP server (`~/.claude/projects/.../<session>.jsonl`).

## Goals / Non-Goals

**Goals:**
- A `RiskClassification` schema with strict enums and cross-field validation that fails loud.
- `classify(action, model)` returning a validated classification, with a deterministic offline `mock`.
- One command (`python -m agent_tripwire`) that runs end-to-end over 3 real inputs and prints readable output, each input's mock verdict shown next to its expected label.
- One core dependency (`pydantic`) for the schema; the mock path still needs no network or API key; `litellm` reserved (stubbed) behind the same signature.

**Non-Goals:**
- No 30-case golden set, no scoring/pass-rate metrics, no CI gate (later pieces).
- No live interception or hook integration; this is a read-and-print skeleton.
- No fully-wired real-model prompt tuning — the litellm path only needs to exist behind the signature.
- No multi-finding output and no detector for the other three targets (tool-call transcript, prompt, model output) — the skeleton is a single-purpose, single-finding agent-action classifier; generalizing the schema to those is deferred, not pre-built.

## Decisions

- **Schema via `pydantic.BaseModel` + `enum`, cross-field rules in a `model_validator`.**
  Pydantic is a deliberate framework choice for this project — the runtime dependency is
  accepted on its own terms, not justified by a not-yet-built path. It enforces enum
  membership at the field types and gives one place for cross-field validation (and, when the
  litellm path is wired, for parsing model JSON). *Alternative:* stdlib `dataclasses` validated
  in `__post_init__` keeps the core dependency-free as the reference project does — rejected
  because Pydantic is the schema framework we want to build on, not because the dep pays for
  itself yet.
- **Cross-field invariants live in the schema, not the detector.** `benign ⇒ risk_type=none
  & severity=none`; `risky ⇒ a named risk_type`. Centralizing them means every producer
  (mock now, litellm later) is validated the same way and can't drift.
- **`risk_type` and `severity` carry an explicit `none` member** rather than being nullable.
  A closed enum is easier to validate, print, and later tally than `Optional`.
- **Provider split mirrors the reference:** `providers.py` has `mock` (deterministic keyword
  heuristic over the action text) and a `litellm` branch behind one `complete`-style call.
  The mock is intentionally shallow — it will misjudge actions whose risk isn't stated in
  words — which is the honest baseline the later eval will expose.
- **Inputs stored as `inputs.jsonl`** (one row per line, `{"action": ..., "expected":
  {"verdict": ..., "risk_type": ...}}`), resolved from the project root like the reference's
  `cases.jsonl`, so the run works from any directory. The `expected` label is a hand-annotation,
  not a scoring harness.
- **Inputs are hand-labeled and the run shows expected-vs-actual, non-gating.** Each input
  carries an `expected` verdict; the run prints the mock's classification next to it with a
  `✓`/`✗` marker. At least one input is deliberately *keyword-blind* — genuinely risky but
  phrased so the shallow mock misjudges it — so a broken classifier and a working one produce
  visibly different output. Crucially the `✗` does **not** fail the process: the exit code
  tracks only wiring + schema validation. If a mismatch were fatal we'd be incentivized to
  curate keyword-obvious inputs — exactly the self-confirming run we're avoiding. This keeps two
  claims separate: green exit = "pipeline wired and every output schema-valid"; the match column
  = an honest, non-gating read on classification quality. Deliberately *not* a pass-rate summary
  count — that's a metric, deferred with the golden set.
- **Optional `rich` output behind a `pretty` extra, plain-text fallback otherwise.** Mirrors
  ai-eval-harness: `import rich` guarded by `try`, colored rendering only on an interactive
  terminal with rich present (and honoring `NO_COLOR`), and a plain renderer whenever rich is
  absent or color is off. The skeleton runs and prints readable output either way, so `rich`
  never becomes a hard requirement; it's duplicated into the `dev` group so tests exercise the
  colored path.
- **Package name `agent_tripwire`, console entry `agent-tripwire`,** matching the reference's
  `python -m` + console-script pattern.
- **The starting model stays flat and single-purpose — no `subject` discriminator, no
  `findings` list.** We considered making `RiskClassification` the single envelope for four
  eventual detectors (agent action, tool-call transcript, prompt, model output), and chose not
  to: the skeleton only classifies agent actions, which is genuinely single-target and
  single-finding. A `subject` field would be a constant today, and its "can't back-fill later"
  justification is false — every record here *is* an agent action, so defaulting old rows when
  a second target lands is correct, not a lie. The generalizations are additive under Pydantic
  and are deferred to the detector that first needs them (see Risks / Open Questions).

## Risks / Trade-offs

- [The mock is a naive keyword classifier and will be wrong on subtle actions] → That's intended for a skeleton; the printed output makes gaps visible, and the real-model path is already stubbed behind the same signature for the next piece.
- [Hand-labeling only 3 inputs is a thin correctness check] → Acceptable for Monday; the point is the end-to-end wiring and the schema, not statistical confidence. The 30-case set comes later.
- [Schema churn later could ripple through callers] → Mitigated by making the schema the single source of truth with validation in one place, so changes surface as validation failures rather than silent drift.
- [We may eventually want one envelope for four detectors — agent action, tool-call transcript, prompt, model output — but only the agent-action classifier is built] → Deliberate (YAGNI): the starting model stays flat and single-purpose. The generalizations (a `subject` discriminator, a `findings` list, per-target `risk_type` widenings like injection *attempt* vs *symptom* and PII/internal-names alongside secrets, a `redact` intervention) are all additive under Pydantic and land with the detector that first needs them — deferred because their shape isn't known until a second target forces it.
- [Pydantic is a runtime dependency in the core, unlike the dependency-free reference] → Accepted deliberately: Pydantic is the schema framework we want for this project, so the dependency is a chosen tool, not a cost being rationalized. The mock path still runs offline with no key.

## Open Questions

- Which 3 real actions best exercise distinct risk types (e.g. one destructive shell command, one outbound request, one benign read) — and which one is the keyword-blind case the mock is *expected* to miss? To be chosen when pulling from transcripts.
- Should `rationale` be required or optional on the mock path? Leaning required (even a terse mock reason), to keep the printed output honest.
- Scalar-vs-findings: if/when the multi-finding targets (tool-call transcript, model output) land, does `Finding` carry a text span, a resource id, or both? Deferred until a second target is actually on the table.
