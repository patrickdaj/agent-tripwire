## Why

The original intent was to parse model output with **Instructor** — the Pydantic-native
structured-extraction library — but the litellm path shipped with a hand-rolled parser instead:
`litellm.completion(...)` → strip a code fence → `json.loads` → hope the shape is right. That's
exactly the boundary Instructor exists to own. Today a malformed or schema-violating model
response fails on the first try (bad JSON, or a `ValidationError` when the cross-field rules
reject it); there is no re-ask, and the parsing/validation logic is ours to maintain.

Adopting Instructor makes the `RiskClassification` schema the *response contract at the model
boundary*: the model is asked to produce the schema via structured extraction, and Instructor
validates the result — including our cross-field invariants — and re-requests on a schema
violation before giving up. This is the "schema is the product spec" ethos finally reaching the
one place it pays off most, and it deletes our bespoke JSON handling.

## What Changes

- **Replace the hand-rolled litellm JSON path with Instructor.** `_litellm` builds an
  Instructor client over litellm (`instructor.from_litellm(litellm.completion)`) and requests
  `response_model=RiskClassification` with a bounded `max_retries`, so the model self-corrects a
  schema-invalid response instead of erroring on the first bad output. Delete the code-fence
  stripping and `json.loads`.
- **Preserve the hardening we just shipped.** The `temperature`-rejection recovery and the
  rate-limit retry (`retry-after` + backoff + time budget) still wrap the call — Instructor sits
  inside that wrapper, not around it.
- **Simplify the system prompt.** Instructor supplies the schema to the model, so the
  hand-written "reply with ONLY a JSON object with keys…" instructions shrink to a brief task
  description.
- **Fold Instructor into the fail-fast preflight.** The real-model dependency check now covers
  `instructor` too (it ships in the `litellm` extra), so a missing extra still stops once with
  the install hint.

Out of scope: no change to the mock path, the schema itself, the `classify` signature, the
`complete → dict` provider contract, or the exit-code/rendering behavior. The detector stays the
single place that constructs the validated model.

## Capabilities

### New Capabilities
<!-- None — refactors how the existing real-model path obtains its result. -->

### Modified Capabilities
- `risk-detection`: adds a requirement that a non-`mock` model's classification is obtained via
  structured extraction typed to the schema, with a bounded number of validation retries.

## Impact

- **Code:** `src/agent_tripwire/providers.py` (`_litellm` rewritten on Instructor; `_SYSTEM`
  trimmed; `ensure_available` also checks `instructor`). No change to `detector.py`'s contract,
  the mock, `schema.py`, or `__main__.py`.
- **Dependencies:** add `instructor>=1.0` to the `litellm` optional extra (alongside `litellm`
  and `tenacity`). The mock path stays dependency-free of it.
- **Tests:** `tests/test_providers_litellm.py` and the detector routing test move from a fake
  `litellm.completion` to a fake `instructor` client seam; add coverage that the request is
  typed to `RiskClassification` with a bounded `max_retries`. All still offline.
- **Contract:** unchanged for callers — `classify` still returns a validated
  `RiskClassification`; the real-model path just gets there via Instructor and can now recover
  from a schema-invalid model response.
