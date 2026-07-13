## Context

`providers._litellm` currently calls `litellm.completion(...)`, strips a ``` fence, and
`json.loads` the text into a field dict; `providers.complete` returns that dict; `detector.classify`
builds `RiskClassification(**fields)` — which is where validation (enums + cross-field rules)
actually happens. The `harden-litellm-path` change wrapped the completion call in a `temperature`-
drop-and-retry and a `tenacity` rate-limit retry. Instructor replaces only the *parse + validate*
middle: `instructor.from_litellm(litellm.completion)` yields a client whose
`chat.completions.create(response_model=RiskClassification, max_retries=N, ...)` returns a validated
model, re-asking the model on a `ValidationError` up to `N` times.

## Goals / Non-Goals

**Goals:**
- The model boundary is typed to `RiskClassification`; Instructor owns parse + validate + re-ask.
- Our bespoke JSON handling (`json.loads`, fence stripping) is deleted.
- The `temperature` and rate-limit hardening is preserved verbatim.
- Tests stay offline and the blast radius stays small.

**Non-Goals:**
- No change to the mock path, the schema, the `classify` signature, the `complete → dict`
  contract, exit codes, or rendering.

## Decisions

- **Keep `complete → dict`; wrap Instructor inside it.** `_litellm` gets a validated
  `RiskClassification` from Instructor and returns `result.model_dump(mode="json")`, so the
  provider contract, the mock, `detector.classify`, and every mock/detector test stay unchanged.
  The detector remains the single construction site (a cheap re-validation of already-valid
  fields). *Alternative:* change the contract so providers return `RiskClassification` directly —
  more faithful to Instructor, but it churns the mock, the detector, and ~half the test suite for
  no observable gain. The minimal-diff choice wins here.
- **Instructor sits inside the existing wrappers, and we unwrap its error envelope.** The
  `tenacity` rate-limit retry and the `temperature`-400 recovery wrap the Instructor `create`
  call. Instructor's `max_retries` handles *validation* re-asks — a different axis from
  *rate-limit* retries; both coexist. Caveat verified against instructor 1.15: a provider error
  raised by `litellm.completion` underneath Instructor is *not* re-raised bare — it is a
  non-validation error, so Instructor's retry loop wraps it in `InstructorRetryException` with the
  original chained as `__cause__`. So a tiny `_unwrap` helper peels that one layer before the
  temperature/rate-limit handling inspects the error; it is detected by class name (no
  module-load import of Instructor, keeping the mock path dependency-free) and is a no-op on a
  directly-raised error, so the fake-Instructor test seam — which raises the litellm errors
  directly — passes straight through. Without this, the preserved hardening would silently miss
  on the real path. *Alternative:* import `InstructorRetryException` and `isinstance`-check it —
  rejected because it would pull Instructor into the module namespace and break the fake seam.
- **A mockable Instructor seam for offline tests.** Mirror the existing fake-`litellm` approach:
  inject a fake `instructor` module (its `from_litellm` returns a fake client whose
  `chat.completions.create` returns a `RiskClassification` or raises `BadRequestError` /
  `RateLimitError` from a fake `litellm`). This keeps the suite offline and dependency-free of the
  real extra, and lets us assert the temperature/rate-limit paths and the `response_model` /
  `max_retries` wiring.
- **Trim `_SYSTEM` to a task description.** Instructor injects the schema via the model's
  function/tool interface, so the hand-written "reply with ONLY a JSON object with keys…" prose is
  redundant and is cut to one or two sentences about *what* to classify.
- **Preflight covers `instructor` too.** `ensure_available` imports both `litellm` and
  `instructor`; either missing raises `ProviderUnavailable` with the same `uv sync --extra litellm`
  hint (both ship in that extra), so the fail-fast contract is unchanged.

## Risks / Trade-offs

- [`model_dump(mode="json")` then a detector rebuild double-validates] → Negligible cost, and it
  keeps the uniform provider→detector seam and the whole mock/detector test suite intact.
- [Instructor is another runtime dependency on the real-model path] → Accepted and deliberate —
  it *is* the point; it stays confined to the `litellm` extra, so the mock path is untouched.
- [Instructor's structured-output mode depends on the model/provider supporting tools/function
  calling] → True for the Claude models we target; litellm brokers it. Non-supporting models would
  need a different Instructor mode, out of scope here.
- [Testing the *actual* re-ask is the library's job, not ours] → We assert the wiring
  (`response_model`, bounded `max_retries`) via the fake client; the re-ask behavior itself is
  Instructor's tested contract, not re-tested here.
