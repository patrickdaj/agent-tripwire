# sensitive-output-detection Delta

## ADDED Requirements

### Requirement: Sensitive-data flag entry point

The system SHALL expose `flag_output(output, model)` that takes a model output (as a string
or a structured value rendered to text) and returns a validated `SensitiveDataFlag`. The
returned value SHALL always pass schema validation before it is handed back to the caller.

#### Scenario: Flagging returns a validated result

- **WHEN** `flag_output(output, model)` is called with any supported output
- **THEN** it returns a `SensitiveDataFlag` that satisfies schema validation

### Requirement: Sensitive-data flag schema

The system SHALL define a `SensitiveDataFlag` type with exactly these fields: `verdict`,
`findings`, `severity`, and `rationale`. `verdict` SHALL be one of exactly two values:
`flagged` or `clean`. `findings` SHALL be a list of finding entries, each with exactly:
`category` (one of exactly: `secret`, `pii`, `internal_name`), `evidence` (free text quoting
or naming the sensitive content), and `destination` (free text naming where the data was
headed, or null when not visible). `severity` SHALL use the existing severity enum.
Unexpected fields SHALL be rejected rather than accepted or coerced.

#### Scenario: A complete flag

- **WHEN** the detector flags an output
- **THEN** the result carries a `verdict`, a `findings` list (each finding with `category`, `evidence`, and `destination`), a `severity`, and a short free-text `rationale`

#### Scenario: Out-of-enum category is rejected

- **WHEN** a finding has a `category` outside its allowed set
- **THEN** validation raises an error naming the offending field

#### Scenario: Destination is optional per finding

- **WHEN** a finding's destination is not visible from the output
- **THEN** the finding is valid with a null `destination`, and the rest of the finding is still required

### Requirement: Sensitive-data flag cross-field consistency

The system SHALL enforce that the `verdict` agrees with the findings: `verdict` SHALL be
`flagged` if and only if `findings` is non-empty, and a `clean` verdict SHALL have
`severity` `none`. A violated rule SHALL raise a validation error rather than being silently
accepted.

#### Scenario: Flagged verdict requires findings

- **WHEN** a flag has `verdict` `flagged` but an empty `findings` list
- **THEN** validation raises an error describing the inconsistency

#### Scenario: Clean verdict forbids findings and severity

- **WHEN** a flag has `verdict` `clean` but a non-empty `findings` list or a `severity` other than `none`
- **THEN** validation raises an error describing the inconsistency

### Requirement: Deterministic offline sensitive-data mock

The system SHALL provide a `mock` model path for sensitive-data flagging that runs with no
network call and no API key, and is deterministic: the same output yields the same flag
every run. The mock MAY be shallow (pattern-based — recognizable secret shapes, obvious PII
formats, a supplied internal-name list) and is expected to miss sensitive data without a
recognizable shape; such misses are displayed by the runner, not hidden.

#### Scenario: Mock flags offline and deterministically

- **WHEN** `flag_output(output, model="mock")` is called twice with the same output and no network available
- **THEN** it returns the same valid flag both times without any network access
