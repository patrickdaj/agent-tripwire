## ADDED Requirements

### Requirement: Detector entry point

The system SHALL expose `classify(action, model)` that takes an agent action
(a tool call with arguments, a file access, an outbound request, or a shell
command — as a string or a small dict) and returns a validated
`RiskClassification`. The returned value SHALL always pass schema validation
before it is handed back to the caller.

#### Scenario: Classify returns a validated result

- **WHEN** `classify(action, model)` is called with any supported action
- **THEN** it returns a `RiskClassification` that satisfies schema validation

### Requirement: Deterministic offline mock provider

The system SHALL provide a `mock` model that runs with no network call and no API
key, so the skeleton is verifiable end-to-end offline against no live model. The
mock SHALL be deterministic: the same action yields the same classification every
run.

#### Scenario: Mock runs offline and deterministically

- **WHEN** `classify(action, model="mock")` is called twice with the same action and no network available
- **THEN** it returns the same valid classification both times without any network access

### Requirement: Real-model path behind one signature

The system SHALL route any non-`mock` model through a single `litellm`-backed
path that shares the `classify` signature, so swapping to a real model is a
one-word change. This path MAY be a stub in this slice, but its call shape SHALL
match the mock's so no caller code changes when it is enabled.

#### Scenario: Model swap does not change the call site

- **WHEN** the caller changes `model` from `mock` to a real model id
- **THEN** the `classify(action, model)` call site is unchanged and still returns a validated classification

### Requirement: Skeleton runs on three real inputs

The system SHALL ship three real agent actions (sourced from our own
transcripts), each hand-labeled with an `expected` verdict, and SHALL provide a
runnable entry point (`python -m agent_tripwire`) that classifies each input and
prints the input alongside its validated classification and its expected label.
At least one input SHALL be keyword-blind — genuinely risky but not evident to
the shallow mock. The process exit code SHALL reflect only wiring and schema
validation: a classification that disagrees with its expected label SHALL be
displayed but SHALL NOT fail the run.

#### Scenario: End-to-end run over the three inputs

- **WHEN** the operator runs `python -m agent_tripwire` on the mock path
- **THEN** each of the three real inputs is printed with its `verdict`, `risk_type`, `severity`, `intervention`, and `rationale`, alongside its `expected` verdict and a `✓`/`✗` match marker, and the process exits successfully

#### Scenario: A known mock miss is shown but does not fail the run

- **WHEN** the keyword-blind input is classified and the mock's verdict disagrees with the input's `expected` verdict
- **THEN** the mismatch is displayed (a `✗` marker) and the process still exits successfully

#### Scenario: Printed output is readable

- **WHEN** the skeleton prints a classification
- **THEN** the action and each classification field are shown in a human-readable form (not a raw object dump)

### Requirement: Output renders with or without rich

The system SHALL print readable output whether or not the optional `rich`
dependency is installed. When `rich` is present and the terminal supports color,
output MAY be rendered as a colored table; otherwise a plain-text rendering SHALL
be used. `rich` SHALL NOT be required to run the skeleton.

#### Scenario: Runs without rich installed

- **WHEN** the skeleton runs and `rich` is not installed
- **THEN** it prints the same information in plain text and exits successfully

#### Scenario: Colored rendering when rich is available

- **WHEN** the skeleton runs on an interactive terminal with `rich` installed and color enabled
- **THEN** it MAY render the output as a colored table with the same rows
