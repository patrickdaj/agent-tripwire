## Why

Coding agents take real actions — shell commands, file writes, outbound requests — and nobody inspects any single one until it has already done damage. We want a **detector primitive**: paste one agent action, get back a schema-validated risk verdict. This change is only the **Monday skeleton** — the smallest end-to-end slice: input → model → validated schema → printed output, working on 3 real inputs. The schema is designed first because *the schema is the product spec*; everything later (a golden set, scoring, interventions at scale) grows from it. Keeping this first slice tiny means it's readable end-to-end and verifiable offline before any real model is wired in.

## What Changes

- Scaffold a minimal `agent-tripwire` Python project (uv-managed, structured like `00-arm-yourself/ai-eval-harness`) in this directory — just enough to run one command end-to-end.
- **Design the classification schema first.** A `RiskClassification` with: `verdict` (`risky | benign`), `risk_type` (exfiltration attempt, injection symptom, out-of-scope access, destructive action, secret exposure, or none), `severity`, and recommended `intervention` (allow / warn / block / confirm). Validated so malformed output fails loudly.
- Add a **detector**: `classify(action, model) → RiskClassification`, with a deterministic offline `mock` provider (so the skeleton runs with zero deps / no key) and a `litellm` path stubbed behind the same signature for later.
- Provide **3 real agent actions** (pulled from our own transcripts via the Week-0 agent-activity server) as the skeleton's inputs, **each hand-labeled with its expected verdict** — and make one deliberately *keyword-blind* (genuinely risky but not obvious to the shallow mock) so the run is falsifiable rather than self-confirming.
- **Print** each input with its validated classification *and its expected label side by side* (a per-input `✓`/`✗` match marker), in a readable form, then exit cleanly. A mismatch on a known-blind input is shown, not fatal: the exit code reflects wiring + schema validation, not classification correctness.

Out of scope for this slice (later pieces): the full 30-case golden set, scoring/pass-rate metrics, a CI gate, and a real-model eval run.

## Capabilities

### New Capabilities
- `classification-schema`: The verdict contract, designed first — fields, enums (risk type, severity, intervention), and validation that rejects malformed classifications. This is the product spec.
- `risk-detection`: The skeleton detector — `classify(action, model)` returning a validated `RiskClassification` via a deterministic `mock` provider, run end-to-end over 3 real inputs with printed output.

### Modified Capabilities
<!-- None — new project scaffold; no existing specs in this repo. -->

## Impact

- **New minimal project tree** under `agent-tripwire/`: `src/agent_tripwire/` (`schema.py`, `detector.py`, `providers.py`, `__main__.py`), `tests/` (offline pytest suite), `inputs.jsonl` (3 real actions, each with an `expected` hand-label; one keyword-blind), `pyproject.toml`, `README.md`, `.gitignore`.
- **Dependencies**: `pydantic` for the schema (validation + JSON parsing via `BaseModel`/`enum`); the mock path still makes no network calls and needs no API key; optional `litellm` reserved for the later real-model path; optional `pretty` extra (`rich`) for colored output, with a plain-text fallback when it's absent — mirroring ai-eval-harness.
- **External touchpoint**: the 3 inputs are sourced once, manually, from the agent-activity MCP server's transcripts; the running skeleton makes no network calls.
- **Downstream**: the schema and package layout are the seed the capstone extends — designed to be grown, not replaced.
