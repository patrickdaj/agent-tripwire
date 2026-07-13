# classification-schema Specification

## Purpose

Define the `RiskClassification` type and its validation rules — the product spec
for the whole detector. Every classification the detector produces is an instance
of this type, constrained by fixed enums and cross-field consistency rules.

## Requirements

### Requirement: Risk classification fields

The system SHALL define a `RiskClassification` type with exactly these fields:
`verdict`, `risk_type`, `severity`, `intervention`, and `rationale`. The type is
the product spec for the whole detector: every classification the detector
produces SHALL be an instance of it.

#### Scenario: A complete classification

- **WHEN** the detector classifies an action
- **THEN** the result carries a `verdict`, a `risk_type`, a `severity`, an `intervention`, and a short free-text `rationale`

### Requirement: Verdict enum

`verdict` SHALL be one of exactly two values: `risky` or `benign`.

#### Scenario: Benign action

- **WHEN** an action is judged safe
- **THEN** `verdict` is `benign`

#### Scenario: Risky action

- **WHEN** an action is judged to carry risk
- **THEN** `verdict` is `risky`

### Requirement: Risk type enum

`risk_type` SHALL be one of: `exfiltration_attempt`, `injection_symptom`,
`out_of_scope_access`, `destructive_action`, `secret_exposure`, or `none`. A
`benign` verdict SHALL use `risk_type` `none`; a `risky` verdict SHALL use one of
the five named risk types (not `none`).

#### Scenario: Risky verdict names a risk type

- **WHEN** `verdict` is `risky`
- **THEN** `risk_type` is one of the five named types and is not `none`

#### Scenario: Benign verdict uses none

- **WHEN** `verdict` is `benign`
- **THEN** `risk_type` is `none`

### Requirement: Severity enum

`severity` SHALL be one of: `none`, `low`, `medium`, `high`, `critical`. A
`benign` verdict SHALL have `severity` `none`.

#### Scenario: Benign severity

- **WHEN** `verdict` is `benign`
- **THEN** `severity` is `none`

### Requirement: Intervention enum

`intervention` SHALL be one of exactly: `allow`, `warn`, `block`, `confirm` —
the action the operator would want taken.

#### Scenario: A recommended intervention is present

- **WHEN** the detector produces a classification
- **THEN** `intervention` is one of `allow`, `warn`, `block`, `confirm`

### Requirement: Validation rejects malformed classifications

The system SHALL validate every classification against the enums above and the
cross-field rules (benign ⇒ `risk_type` `none` and `severity` `none`; risky ⇒ a
named `risk_type`). An invalid value or a violated rule SHALL raise a validation
error rather than being silently accepted or coerced.

#### Scenario: Out-of-enum value is rejected

- **WHEN** a classification has a `verdict`, `risk_type`, `severity`, or `intervention` outside its allowed set
- **THEN** validation raises an error naming the offending field

#### Scenario: Inconsistent verdict and risk type is rejected

- **WHEN** a classification is `benign` but `risk_type` is not `none` (or is `risky` but `risk_type` is `none`)
- **THEN** validation raises an error describing the inconsistency
