# risk-detection Delta

## ADDED Requirements

### Requirement: Inputs are routed by kind

The system SHALL route each input row to the detector its `kind` names: `action` to the
action classifier, `transcript` to the transcript audit, `prompt` to injection detection,
and `output` to the sensitive-data flag. A row with no `kind` SHALL be treated as an
`action` row, so pre-existing inputs remain valid unmodified. A row with an unrecognized
`kind` SHALL surface a per-row error under the existing per-action error contract (shown in
the output, counted by the exit code) rather than being silently skipped.

#### Scenario: Each kind reaches its detector

- **WHEN** the run loads rows of kinds `action`, `transcript`, `prompt`, and `output`
- **THEN** each row is classified by the detector matching its kind and reported with that detector's validated result fields

#### Scenario: A missing kind defaults to action

- **WHEN** a row has no `kind` field
- **THEN** it is classified by the action detector, and the pre-existing input rows run unchanged

#### Scenario: An unknown kind fails loud per-row

- **WHEN** a row carries a `kind` outside the recognized set
- **THEN** an error is shown for that row and the process exit code reflects the error, and the row is not silently skipped

## MODIFIED Requirements

### Requirement: Real-model path behind one signature

The system SHALL route any non-`mock` model through a single `litellm`-backed path shared by
all detectors, parameterized by each detector's result schema and system prompt, so swapping
to a real model is a one-word change at any detector's call site. This path SHALL tolerate
provider constraints that would otherwise fail a valid request: when the model rejects the
`temperature` parameter, the system SHALL retry the request without it and SHALL NOT resend
`temperature` to that model for the rest of the run; and when the provider rate-limits, the
system SHALL retry within a bounded time budget, honoring a `retry-after` hint when present.
These tolerances SHALL apply identically whichever detector issued the request.

#### Scenario: Model swap does not change the call site

- **WHEN** the caller changes `model` from `mock` to a real model id on any detector entry point
- **THEN** that entry point's call site is unchanged and still returns a validated result of that detector's type

#### Scenario: Detectors share one real-model path

- **WHEN** two different detectors classify with the same non-`mock` model
- **THEN** both requests flow through the same litellm-backed path, differing only in the result schema and system prompt supplied

#### Scenario: A model that rejects temperature still succeeds

- **WHEN** the selected model rejects the `temperature` parameter with a client error
- **THEN** the system retries the request without `temperature`
- **AND** it does not resend `temperature` to that model for the remainder of the run

#### Scenario: A rate-limited request is retried within a budget

- **WHEN** the provider returns a rate-limit error
- **THEN** the system waits — honoring a `retry-after` hint when present, otherwise backing off — and retries within a bounded time budget before surfacing an error

### Requirement: Real-model output is extracted against the schema

The system SHALL obtain a non-`mock` model's result via structured extraction typed to the
requesting detector's result schema (`RiskClassification`, `TranscriptAudit`,
`InjectionClassification`, or `SensitiveDataFlag`), requesting it with a bounded number of
validation retries so a schema-invalid model response is re-requested rather than failing
immediately. When the retry bound is exhausted, the system SHALL surface an error for that
input, consistent with the existing per-action error contract (shown, non-fatal).

#### Scenario: A non-mock request is typed to the requesting detector's schema

- **WHEN** a non-`mock` model classifies an input for any detector
- **THEN** the request is made typed to that detector's result schema with a bounded validation-retry count

#### Scenario: A schema-invalid response is re-requested before failing

- **WHEN** the model returns a response that violates the requesting detector's schema
- **THEN** the system re-requests the result up to the retry bound before treating it as an error

#### Scenario: Exhausted retries surface a non-fatal error

- **WHEN** the model keeps returning schema-invalid responses past the retry bound
- **THEN** an error is surfaced for that input and, per the existing contract, it is shown without changing the exit code beyond the wiring/validation rule

### Requirement: Skeleton runs on real labeled inputs for every detector

The system SHALL ship real inputs (sourced from our own transcripts and prompts) for every
detector — agent actions, tool-call transcripts, prompts, and model outputs — each
hand-labeled with an `expected` verdict, with at least three inputs per detector. The
runnable entry point (`python -m agent_tripwire`) SHALL classify each input with the
detector its kind names and print the input alongside its validated result, its expected
label, and a match marker, identifying which detector produced each row. For every detector,
at least one input SHALL be keyword-blind — genuinely positive but not evident to that
detector's shallow mock. The process exit code SHALL reflect only wiring and schema
validation: a result that disagrees with its expected label SHALL be displayed but SHALL NOT
fail the run.

#### Scenario: End-to-end run over all detectors

- **WHEN** the operator runs `python -m agent_tripwire` on the mock path
- **THEN** every input of every kind is printed with its detector's validated result fields, alongside its `expected` label and a `✓`/`✗` match marker, and the process exits successfully

#### Scenario: A known mock miss is shown but does not fail the run

- **WHEN** a keyword-blind input of any kind is classified and the mock's verdict disagrees with the input's `expected` verdict
- **THEN** the mismatch is displayed (a `✗` marker) and the process still exits successfully

#### Scenario: Printed output is readable

- **WHEN** the skeleton prints a result
- **THEN** the input, its kind, and each result field are shown in a human-readable form (not a raw object dump)

## RENAMED Requirements

- FROM: `### Requirement: Skeleton runs on three real inputs`
- TO: `### Requirement: Skeleton runs on real labeled inputs for every detector`
