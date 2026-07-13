## ADDED Requirements

### Requirement: Real-model output is extracted against the schema

The system SHALL obtain a non-`mock` model's classification via structured extraction typed to
the `RiskClassification` schema, requesting it with a bounded number of validation retries so a
schema-invalid model response is re-requested rather than failing immediately. When the retry
bound is exhausted, the system SHALL surface an error for that action, consistent with the
existing per-action error contract (shown, non-fatal).

#### Scenario: A non-mock request is typed to the schema with bounded retries

- **WHEN** a non-`mock` model classifies an action
- **THEN** the request is made typed to the `RiskClassification` schema with a bounded validation-retry count

#### Scenario: A schema-invalid response is re-requested before failing

- **WHEN** the model returns a response that violates the schema
- **THEN** the system re-requests the classification up to the retry bound before treating it as an error

#### Scenario: Exhausted retries surface a non-fatal error

- **WHEN** the model keeps returning schema-invalid responses past the retry bound
- **THEN** an error is surfaced for that action and, per the existing contract, it is shown without changing the exit code beyond the wiring/validation rule
