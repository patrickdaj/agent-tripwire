# transcript-audit Delta

## ADDED Requirements

### Requirement: Transcript audit entry point

The system SHALL expose `audit_transcript(transcript, model)` that takes a tool-call
transcript (an ordered collection of tool calls with their arguments, plus the stated task
the agent was given — as a string or a structured value rendered to text) and returns a
validated `TranscriptAudit`. The returned value SHALL always pass schema validation before
it is handed back to the caller.

#### Scenario: Audit returns a validated result

- **WHEN** `audit_transcript(transcript, model)` is called with any supported transcript
- **THEN** it returns a `TranscriptAudit` that satisfies schema validation

#### Scenario: Structured transcripts are normalized to text

- **WHEN** the transcript is passed as a structured value (e.g. a list of tool-call dicts) rather than a string
- **THEN** it is rendered to a deterministic textual form before classification, and the call still returns a validated `TranscriptAudit`

### Requirement: Transcript audit result schema

The system SHALL define a `TranscriptAudit` type with exactly these fields: `verdict`,
`touched`, and `rationale`. `verdict` SHALL be one of exactly two values: `in_scope` or
`out_of_scope`. `touched` SHALL be a list of touched-resource entries, each with exactly:
`resource` (free text naming what was touched — a path, URL, command, table, or similar),
`kind` (one of exactly: `file`, `network`, `process`, `env`, `data_store`, `other`), and
`in_scope` (boolean). Unexpected fields SHALL be rejected rather than accepted or coerced.

#### Scenario: A complete audit

- **WHEN** the detector audits a transcript
- **THEN** the result carries a `verdict`, a `touched` list of resource entries (each with `resource`, `kind`, and `in_scope`), and a short free-text `rationale`

#### Scenario: Out-of-enum resource kind is rejected

- **WHEN** a touched-resource entry has a `kind` outside its allowed set
- **THEN** validation raises an error naming the offending field

### Requirement: Transcript audit cross-field consistency

The system SHALL enforce that the overall `verdict` agrees with the per-resource scope
judgments: `verdict` SHALL be `out_of_scope` if and only if at least one entry in `touched`
has `in_scope` false. A violated rule SHALL raise a validation error rather than being
silently accepted.

#### Scenario: Out-of-scope verdict requires an out-of-scope resource

- **WHEN** an audit has `verdict` `out_of_scope` but every `touched` entry has `in_scope` true (or `touched` is empty)
- **THEN** validation raises an error describing the inconsistency

#### Scenario: In-scope verdict forbids out-of-scope resources

- **WHEN** an audit has `verdict` `in_scope` but some `touched` entry has `in_scope` false
- **THEN** validation raises an error describing the inconsistency

### Requirement: Deterministic offline transcript mock

The system SHALL provide a `mock` model path for transcript audits that runs with no network
call and no API key, and is deterministic: the same transcript yields the same audit every
run. The mock MAY be shallow (keyword/pattern-based) and is expected to miss scope
violations that are not evident from surface text; such misses are displayed by the runner,
not hidden.

#### Scenario: Mock audits offline and deterministically

- **WHEN** `audit_transcript(transcript, model="mock")` is called twice with the same transcript and no network available
- **THEN** it returns the same valid audit both times without any network access
