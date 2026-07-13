# risk-detection Specification

## Purpose

Expose the detector entry point that classifies agent actions into validated
`RiskClassification` results, with a deterministic offline mock provider, a
real-model path behind one signature, a runnable skeleton over real inputs, and
output that renders with or without `rich`.

## Requirements

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

### Requirement: Run output visually delimits each action

The run output SHALL give each classified action a clear visual boundary so that adjacent
entries are distinguishable and do not run together, in both the rich and plain renderers.

#### Scenario: Rich rows are ruled off

- **WHEN** the run renders more than one action with `rich` enabled
- **THEN** each action's row is separated from the next by a horizontal divider

#### Scenario: Plain blocks are numbered and separated

- **WHEN** the run renders the actions in plain text
- **THEN** each action is numbered and separated from the next by a separator line, so where one action ends and the next begins is unambiguous

### Requirement: A misclassification is rendered prominently

The run output SHALL surface a miss — a classification that disagrees with its input's
expected label — with a leading, high-contrast status indicator rather than only a trailing
marker, and SHALL keep it identifiable when color is unavailable. This is a presentation
requirement only: a miss remains non-gating and never changes the exit code.

#### Scenario: A miss leads with a status indicator

- **WHEN** an action's verdict does not match its expected label
- **THEN** the entry is marked at its leading edge with a distinct status (e.g. a `MISS` label), not only a trailing symbol

#### Scenario: A miss is identifiable without color

- **WHEN** the output is rendered in plain text (color unavailable — `NO_COLOR`, a non-TTY, or `rich` absent)
- **THEN** the miss is still identifiable by a textual status word, not by color alone

#### Scenario: An error is distinct from a miss

- **WHEN** an action fails to produce a valid classification (an error) and another action is merely a miss
- **THEN** the two are shown with distinct status labels

#### Scenario: Prominence does not change the exit contract

- **WHEN** the run contains a prominently-marked miss but every action produced a valid classification
- **THEN** the process still exits successfully

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
