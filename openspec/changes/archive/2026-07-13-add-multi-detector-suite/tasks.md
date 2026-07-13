# Tasks — add-multi-detector-suite

## 1. Schemas (the product spec first)

- [x] 1.1 Add `TranscriptAudit` (+ `ScopeVerdict`, `ResourceKind`, `TouchedResource`) to `schema.py` with `extra="forbid"`, the verdict⇔touched cross-field validator, and a human-readable `__str__`
- [x] 1.2 Add `InjectionClassification` (+ `InjectionVerdict`, `InjectionTechnique`) reusing `Severity`/`Intervention`, with clean/attempt cross-field validators and `__str__`
- [x] 1.3 Add `SensitiveDataFlag` (+ `SensitiveVerdict`, `SensitiveCategory`, `SensitiveFinding` with nullable `destination`) with flagged⇔findings and clean⇒severity-none validators and `__str__`
- [x] 1.4 Tests: per schema, a valid construction, an out-of-enum rejection naming the field, each cross-field inconsistency rejection, and an extra-field rejection (mirror `test_schema.py` style)

## 2. Providers (mocks + parameterized real-model path)

- [x] 2.1 Introduce the `Detector` descriptor (response_model, system_prompt, mock) and the `DETECTORS` registry with the `action` entry wrapping the existing `_mock`/`_SYSTEM`/`RiskClassification`
- [x] 2.2 Parameterize `_litellm(text, model, *, response_model, system_prompt)` and thread `detector="action"` (defaulted) through `complete`; existing callers and litellm tests stay green unmodified
- [x] 2.3 Write the transcript mock: shallow scope heuristic (task-keyword match + out-of-scope pattern list), returning verdict + touched resources consistent with the cross-field rules
- [x] 2.4 Write the injection mock: ordered phrase table for the five techniques, falling through to clean
- [x] 2.5 Write the sensitive-data mock: secret-shape regexes, obvious PII patterns, internal-name markers; findings drive verdict/severity
- [x] 2.6 Tests: each mock is offline-deterministic (same input → same dict, twice) and returns fields that validate; registry test that each detector's `complete` routes to its own mock; a litellm-path test asserting the schema and prompt actually vary per detector (fake instructor seam)

## 3. Detector entry points

- [x] 3.1 Add `audit_transcript`, `detect_injection`, `flag_output` to `detector.py`, each normalizing str/structured input like `_action_text` and validating into its own model; export from `__init__.py`
- [x] 3.2 Tests: each entry point returns its validated type on the mock path; structured (dict/list) input normalizes deterministically; a malformed-producer seam raises `ValidationError` (mirror `test_detector.py`)

## 4. Inputs and runner

- [x] 4.1 Extend `inputs.jsonl`: add ≥3 real hand-labeled rows per new kind (`transcript` rows carrying the stated task, `prompt`, `output`), each set including one keyword-blind row; leave the existing three action rows untouched (no `kind` = `action`)
- [x] 4.2 Runner routing: map `kind` → entry point in `__main__.py`; missing `kind` defaults to `action`; unknown `kind` becomes a per-row error (shown, exit-code-relevant, not skipped)
- [x] 4.3 Per-kind match logic: extend `_matches` — verdict always; `risk_type`/`technique`/`categories` compared only when the label names them
- [x] 4.4 Reporting: add the kind to both renderers (kind column in the rich table, kind tag in plain blocks) and render each result type's fields readably; miss/error prominence and exit-code contracts unchanged
- [x] 4.5 Tests: routing (each kind hits its detector; default; unknown-kind error path), per-kind matching, and both renderers over a mixed-kind row set (mirror `test_main.py`)

## 5. Verify and document

- [x] 5.1 Full offline run: `uv run python -m agent_tripwire` exits 0 with every kind rendered, expected ✗ misses visible on the keyword-blind rows; `uv run pytest` green
- [x] 5.2 Update README: the four detectors, the new schemas table(s), the `kind` field in `inputs.jsonl`; refresh the schema.py scope note that deferred these generalizations
