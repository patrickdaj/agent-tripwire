## 1. Dependency

- [x] 1.1 Add `instructor>=1.0` to the `litellm` optional extra in `pyproject.toml` (alongside `litellm>=1.50`, `tenacity`); `uv sync --extra litellm` and confirm `instructor` + `litellm` import

## 2. Refactor the litellm path onto Instructor

- [x] 2.1 In `providers.py` import `RiskClassification` from `.schema`; in `_litellm` build the client with `instructor.from_litellm(litellm.completion)` (lazy imports, like today)
- [x] 2.2 Replace the raw `completion` + code-fence strip + `json.loads` with `client.chat.completions.create(model=..., messages=..., response_model=RiskClassification, max_retries=<N>, temperature=...)`; return `result.model_dump(mode="json")` to keep the `complete → dict` contract
- [x] 2.3 Keep the `temperature`-drop (`_NO_TEMPERATURE` + `BadRequestError` catch) and the `tenacity` rate-limit retry wrapping the Instructor `create` call — same resilience as `harden-litellm-path`, just around the Instructor call now
- [x] 2.4 Trim `_SYSTEM` to a one/two-sentence task description (Instructor supplies the schema); delete the hand-written "reply with ONLY a JSON object with keys…" prose

## 3. Preflight covers Instructor

- [x] 3.1 Update `ensure_available(model)` to import both `litellm` and `instructor` for a non-`mock` model; either missing raises `ProviderUnavailable("litellm not installed — run: uv sync --extra litellm")` (both ship in that extra)

## 4. Tests (offline)

- [x] 4.1 In `tests/test_providers_litellm.py` replace the fake `litellm.completion` seam with a fake `instructor` module: `from_litellm` returns a fake client whose `chat.completions.create` returns a `RiskClassification` (built from valid fields) or raises `BadRequestError`/`RateLimitError` from a fake `litellm`
- [x] 4.2 Assert `_litellm` returns the field dict (from `model_dump`), and that `create` was called with `response_model=RiskClassification` and a bounded `max_retries` (record kwargs on the fake client)
- [x] 4.3 Re-confirm the resilience paths through the new seam: a `temperature` 400 retries without `temperature` (and remembers the model); a `RateLimitError` is retried (neutralize sleep)
- [x] 4.4 Update `tests/test_detector.py::test_non_mock_model_routes_through_litellm` to the Instructor seam and assert a validated `RiskClassification` is returned; update the "bad provider payload" test if the seam changed its trigger point
- [x] 4.5 Extend the missing-extra fail-fast test so absence of `instructor` (not just `litellm`) also raises `ProviderUnavailable`

## 5. Verify

- [x] 5.1 `uv run pytest -q` green; `uv sync --extra litellm` resolves `instructor`; note in the README that the real-model path uses Instructor for schema-typed output (structured extraction with validation retries)
