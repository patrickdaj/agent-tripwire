# injection-detection Specification

## Purpose

Expose the detector entry point that classifies prompts and other model-bound
inputs into validated `InjectionClassification` results, with cross-field
consistency between the verdict and its technique/severity, and a deterministic
offline mock provider.

## Requirements

### Requirement: Injection detection entry point

The system SHALL expose `detect_injection(prompt, model)` that takes a prompt or other
model-bound input (as a string or a structured value rendered to text) and returns a
validated `InjectionClassification`. The returned value SHALL always pass schema validation
before it is handed back to the caller.

#### Scenario: Detection returns a validated result

- **WHEN** `detect_injection(prompt, model)` is called with any supported input
- **THEN** it returns an `InjectionClassification` that satisfies schema validation

### Requirement: Injection classification schema

The system SHALL define an `InjectionClassification` type with exactly these fields:
`verdict`, `technique`, `severity`, `intervention`, and `rationale`. `verdict` SHALL be one
of exactly two values: `injection_attempt` or `clean`. `technique` SHALL be one of exactly:
`instruction_override`, `role_manipulation`, `context_smuggling`, `tool_misuse_lure`,
`encoding_obfuscation`, or `none`. `severity` SHALL use the existing severity enum (`none`,
`low`, `medium`, `high`, `critical`) and `intervention` the existing intervention enum
(`allow`, `warn`, `block`, `confirm`). Unexpected fields SHALL be rejected rather than
accepted or coerced.

#### Scenario: A complete classification

- **WHEN** the detector classifies an input
- **THEN** the result carries a `verdict`, a `technique`, a `severity`, an `intervention`, and a short free-text `rationale`

#### Scenario: Out-of-enum technique is rejected

- **WHEN** a classification has a `technique` outside its allowed set
- **THEN** validation raises an error naming the offending field

### Requirement: Injection classification cross-field consistency

The system SHALL enforce cross-field rules on every injection classification: `clean` ⇒
`technique` is `none` and `severity` is `none`; `injection_attempt` ⇒ `technique` is one of
the named techniques (not `none`). A violated rule SHALL raise a validation error rather
than being silently accepted.

#### Scenario: Clean verdict uses none

- **WHEN** a classification is `clean` but `technique` is not `none` (or `severity` is not `none`)
- **THEN** validation raises an error describing the inconsistency

#### Scenario: An attempt names its technique

- **WHEN** a classification is `injection_attempt` but `technique` is `none`
- **THEN** validation raises an error describing the inconsistency

### Requirement: Deterministic offline injection mock

The system SHALL provide a `mock` model path for injection detection that runs with no
network call and no API key, and is deterministic: the same input yields the same
classification every run. The mock MAY be shallow (phrase-based) and is expected to miss
attempts phrased without recognizable trigger language; such misses are displayed by the
runner, not hidden.

#### Scenario: Mock detects offline and deterministically

- **WHEN** `detect_injection(prompt, model="mock")` is called twice with the same input and no network available
- **THEN** it returns the same valid classification both times without any network access
