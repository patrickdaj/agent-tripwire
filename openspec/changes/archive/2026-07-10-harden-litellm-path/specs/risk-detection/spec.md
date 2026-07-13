## MODIFIED Requirements

### Requirement: Real-model path behind one signature

The system SHALL route any non-`mock` model through a single `litellm`-backed path that shares
the `classify` signature, so swapping to a real model is a one-word change. This path SHALL
tolerate provider constraints that would otherwise fail a valid request: when the model rejects
the `temperature` parameter, the system SHALL retry the request without it and SHALL NOT resend
`temperature` to that model for the rest of the run; and when the provider rate-limits, the
system SHALL retry within a bounded time budget, honoring a `retry-after` hint when present.

#### Scenario: Model swap does not change the call site

- **WHEN** the caller changes `model` from `mock` to a real model id
- **THEN** the `classify(action, model)` call site is unchanged and still returns a validated classification

#### Scenario: A model that rejects temperature still succeeds

- **WHEN** the selected model rejects the `temperature` parameter with a client error
- **THEN** the system retries the request without `temperature`
- **AND** it does not resend `temperature` to that model for the remainder of the run

#### Scenario: A rate-limited request is retried within a budget

- **WHEN** the provider returns a rate-limit error
- **THEN** the system waits — honoring a `retry-after` hint when present, otherwise backing off — and retries within a bounded time budget before surfacing an error

## ADDED Requirements

### Requirement: Missing real-model dependency fails fast with guidance

The system SHALL, when a non-`mock` model is selected but the optional `litellm` dependency is
not installed, stop before classifying and report a single actionable message naming the fix,
and SHALL exit non-zero — rather than emitting a separate error for each input.

#### Scenario: litellm extra not installed

- **WHEN** a non-`mock` model is selected and the `litellm` extra is not installed
- **THEN** the run stops with one message stating that `litellm` is not installed and how to install it, and exits non-zero
- **AND** it does not print a separate error entry per input

### Requirement: Per-action errors are visible in every renderer

The system SHALL, when an individual action fails to produce a valid classification, show that
error's message (not merely an `ERROR` marker) in whichever renderer is active, so the failure
is diagnosable from the output.

#### Scenario: Error message shown under rich

- **WHEN** an action errors and output is rendered with `rich`
- **THEN** the error's message is shown in the output, not only a bare `ERROR` cell

#### Scenario: Error message shown in plain text

- **WHEN** an action errors and output is rendered in plain text
- **THEN** the error's message is shown for that action
