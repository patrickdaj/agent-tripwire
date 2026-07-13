## 1. Project scaffold

- [x] 1.1 Create `agent-tripwire/` tree: `src/agent_tripwire/`, `pyproject.toml`, `README.md`, `.gitignore` (mirror the ai-eval-harness layout; package name `agent_tripwire`, console script `agent-tripwire`)
- [x] 1.2 Write `pyproject.toml`: `pydantic` as the one runtime dep; optional extras `litellm` (+`tenacity`) and `pretty` (`rich>=13`); `pytest` **and `rich`** in a `dev` group (so the colored path is tested); `[project.scripts] agent-tripwire = "agent_tripwire.__main__:main"`
- [x] 1.3 `uv sync` and confirm the empty package imports (`uv run python -c "import agent_tripwire"`)

## 2. Schema first (the product spec)

- [x] 2.1 In `schema.py` define enums: `Verdict` (risky/benign), `RiskType` (exfiltration_attempt, injection_symptom, out_of_scope_access, destructive_action, secret_exposure, none), `Severity` (none/low/medium/high/critical), `Intervention` (allow/warn/block/confirm)
- [x] 2.2 Define the `RiskClassification` Pydantic model (`BaseModel`) with fields `verdict`, `risk_type`, `severity`, `intervention`, `rationale`; enum-typed fields enforce membership. Set `model_config = ConfigDict(extra="forbid")` so unexpected fields are rejected
- [x] 2.3 Add a `@model_validator(mode="after")` for the cross-field rules (benign ⇒ risk_type=none & severity=none; risky ⇒ a named risk_type), raising `ValueError` (surfaced as Pydantic `ValidationError`) that names the offending field
- [x] 2.4 Add a readable plain-text `__str__`/formatter so a classification prints as human-readable lines, not a raw object dump — this is the fallback renderer used when `rich` is absent or color is off

## 3. Detector + providers

- [x] 3.1 In `providers.py` implement a deterministic offline `mock`: a shallow keyword heuristic over the action text that returns the fields needed to build a `RiskClassification`
- [x] 3.2 Add the `litellm` branch behind the same `complete`-style signature (stub is fine for this slice) so a non-`mock` model routes through it with no caller change
- [x] 3.3 In `detector.py` implement `classify(action, model="mock")` that calls the provider, builds a `RiskClassification`, and returns it only after schema validation passes

## 4. Real inputs + runnable skeleton

- [x] 4.1 Pull 3 real agent actions from own transcripts (via the Week-0 agent-activity server / `~/.claude/projects/...` JSONL); choose distinct kinds (e.g. a destructive shell command, an outbound request, a benign read) and make **one deliberately keyword-blind** — genuinely risky but not obvious to the shallow mock. Store as `inputs.jsonl` (`{"action": ..., "expected": {"verdict": ..., "risk_type": ...}}` per line, a hand-labeled `expected` on each) resolved from the project root
- [x] 4.2 Write `__main__.py` with `main()`: load `inputs.jsonl`, `classify` each on the mock path, print each input with its validated classification **and its `expected` label side by side plus a `✓`/`✗` match marker**. Exit code tracks only wiring + schema validation — a `✗` on a keyword-blind input is shown, **not** fatal (still exit 0); a crash or `ValidationError` exits non-zero
- [x] 4.3 Add the optional `rich` renderer: `try: import rich`; render a colored table only on an interactive TTY with rich installed and color on (honor `NO_COLOR`); otherwise fall back to the plain formatter from 2.4. Same rows either way
- [x] 4.4 Run `uv run python -m agent_tripwire` and confirm all 3 inputs print with a full, valid classification and their `expected` label; the keyword-blind input shows a `✗` yet the process still exits 0; run once with `rich` installed and once without to confirm both render readably

## 5. README

- [x] 5.1 Write a short `README.md`: what the detector primitive is, the schema as the product spec, how to run the skeleton (`uv run python -m agent_tripwire`, plus the optional `pretty`/`rich` extra), and how to read the expected-vs-actual column (a `✗` is an honest known-miss on the keyword-blind input, not a failure); note what is deferred to later pieces (golden set, scoring, CI gate)

## 6. Tests

- [x] 6.1 Add offline `tests/` (pytest): schema (field set, closed enums, both cross-field rules, `extra="forbid"`, readable `__str__`), mock provider (fields contract, determinism, keyword heuristic, the by-design keyword-blind miss), detector (validated result, str/dict input, non-`mock` routes to litellm, `ValidationError` on a bad provider payload), and runner/render (match markers, non-gating error handling, color-resolution rules, rich/plain parity + graceful degrade, `main()` exit codes)
