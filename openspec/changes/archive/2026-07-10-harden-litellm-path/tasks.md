## 1. Harden the litellm request path

- [x] 1.1 In `providers.py` add a module-level `_NO_TEMPERATURE: set[str]` and port `_retry_after(exc)` from the reference (read `retry-after` from `litellm_response_headers` and `exc.response.headers`, return seconds or `None`)
- [x] 1.2 Rewrite `_litellm` to send `temperature=0` only when the model is not in `_NO_TEMPERATURE`; catch `litellm.BadRequestError`, and if the message mentions `temperature`, add the model to `_NO_TEMPERATURE`, drop the param, and retry once
- [x] 1.3 Wrap the completion call in a `tenacity` retry on `litellm.RateLimitError`: wait `_retry_after(exc)` or `wait_exponential(multiplier=2, max=60)`, `stop_after_delay(180)`, `reraise=True` (lazy-import `tenacity` inside `_litellm`, like `litellm`)

## 2. Fail fast on a missing extra

- [x] 2.1 Add `ProviderUnavailable(Exception)` and `ensure_available(model)` to `providers.py`: for a non-`mock` model, attempt `import litellm`; on `ImportError` raise `ProviderUnavailable("litellm not installed — run: uv sync --extra litellm")`
- [x] 2.2 In `__main__.main()`, call `ensure_available(args.model)` once before the run loop; on `ProviderUnavailable`, print the message to stderr and `sys.exit(2)` — so a missing extra is one message, not one error per input

## 3. Surface per-action errors under rich

- [x] 3.1 In `_rich_report`, after printing the table, if any row has an `error`, print an `errors` section listing `[n] <message>` keyed to the row number (red), mirroring what `_plain_report` already shows inline — so a per-action failure is diagnosable in the rich output

## 4. Tests (offline)

- [x] 4.1 Add `tests/test_providers_litellm.py` with a fake `litellm` module (exposing `completion`, `BadRequestError`, `RateLimitError`) injected via `monkeypatch`/`sys.modules`: assert a `temperature` 400 triggers a retry-without-temperature that succeeds, and the model is remembered in `_NO_TEMPERATURE`
- [x] 4.2 Assert `_retry_after` parses a `retry-after` header from both `litellm_response_headers` and `exc.response.headers`, and returns `None` when absent
- [x] 4.3 Assert `ensure_available("claude-sonnet-5")` raises `ProviderUnavailable` with the install hint when litellm is absent, and that `main()` on a non-`mock` model with litellm absent exits non-zero with a single message (not one per input)
- [x] 4.4 Assert `_rich_report` shows an error's message text (not just `ERROR`) when a row errored

## 5. Verify

- [x] 5.1 `uv run pytest -q` green; `uv run agent-tripwire --model claude-sonnet-5` with the `litellm` extra absent shows the one-line install hint and exits non-zero; document that a live run needs `uv sync --extra litellm` and a sourced `ANTHROPIC_API_KEY`
