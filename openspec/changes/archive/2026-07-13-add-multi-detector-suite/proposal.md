# Add Multi-Detector Suite

## Why

agent-tripwire currently ships one detector: a single agent action in, a `RiskClassification`
out. But the surfaces an operator needs tripwires on are broader than single actions, and the
schema module already names this as deliberately deferred work ("the generalizations… land with
the detector that first needs them"). This change lands those detectors: a tool-call transcript
auditor, a prompt-injection classifier for inputs, and a sensitive-data flag for model outputs —
each following the same mock-first, schema-validated pattern the action detector proved out.

## What Changes

- Add a **transcript audit** detector: a tool-call transcript in, a structured verdict out —
  what resources the agent touched (each named and kind-tagged) and whether any of it was out
  of scope for the stated task.
- Add an **injection detection** detector: a prompt/input in, an injection-attempt
  classification out — attempt or clean, which technique, and a recommended intervention.
- Add a **sensitive-data output** detector: a model output in, a flag out — findings for
  secrets, PII, and internal names, each with the evidence and (when visible) where the data
  was headed.
- Each new detector gets its own closed-enum, cross-field-validated pydantic result schema
  (the schema-is-the-product-spec pattern), its own deterministic offline mock, and rides the
  existing litellm/instructor path — which is generalized from hardcoding
  `RiskClassification` to being parameterized by response schema and system prompt.
- Extend the runnable skeleton: inputs gain a `kind` discriminator routing each line to its
  detector; the run prints every detector's verdicts with the same expected-label / match-marker
  contract (misses shown, never fatal). Ship real, hand-labeled inputs for each new detector,
  including at least one keyword-blind input per detector.
- The existing action detector (`classify`) is unchanged at its call site; no breaking changes.

## Capabilities

### New Capabilities

- `transcript-audit`: classify a tool-call transcript — enumerate touched resources
  (kind-tagged, scope-judged) and return an overall in-scope/out-of-scope verdict, schema-validated.
- `injection-detection`: classify a prompt or other model-bound input as an injection attempt
  or clean, naming the technique and an intervention, schema-validated.
- `sensitive-output-detection`: flag sensitive data in a model output — secrets, PII, internal
  names — as a validated findings list with evidence and destination context.

### Modified Capabilities

- `risk-detection`: the real-model path and mock provider seam become parameterized per
  detector (schema + system prompt) rather than hardcoded to `RiskClassification`; the
  runnable skeleton routes multi-kind inputs to the right detector and reports per-detector
  results under the existing exit-code and miss-rendering contracts.
- `classification-schema`: no changes to `RiskClassification` itself; the capability's scope
  note (single flat shape) is superseded by the per-detector schemas living in their own
  capabilities. Requirements here are unchanged — listed for traceability only, no delta
  needed unless review finds one.

## Impact

- **Code**: `src/agent_tripwire/schema.py` (new result models alongside `RiskClassification`),
  `providers.py` (parameterize `_litellm`/`complete` by schema + prompt; add per-detector
  mocks), `detector.py` (new per-detector entry points), `__main__.py` (kind-routing, grouped
  reporting), `inputs.jsonl` (new labeled rows with `kind`).
- **Tests**: new schema-validation, mock-determinism, and routing tests mirroring the existing
  suites; existing tests stay green unmodified.
- **Dependencies**: none new — pydantic core, litellm/instructor/tenacity stay optional extras,
  rich stays optional.
