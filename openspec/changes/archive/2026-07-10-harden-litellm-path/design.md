## Context

`providers._litellm` currently does one thing: `litellm.completion(model=..., messages=...,
temperature=0)`, strip a code fence, `json.loads`. No error handling. `providers.complete`
routes non-`mock` models to it; `detector.classify` builds a `RiskClassification` from the
returned fields; `__main__.run` wraps each `classify` in a broad `except Exception` and records
`{"error": "<Type>: <msg>"}`, which `_plain_report` prints inline but `_rich_report` collapses
to a bare `ERROR` cell. The reference `ai-eval-harness/providers.py` already solves the
model-compat problems we're now hitting; this change ports that shape into our field-returning
provider and closes the error-visibility gap.

## Goals / Non-Goals

**Goals:**
- `--model <modern-claude>` actually classifies: survive the `temperature` 400 and transient rate limits.
- A missing `litellm` extra fails once, fast, with the exact fix — not N identical per-row errors.
- Every per-action error is legible in both renderers.

**Non-Goals:**
- No cost/latency reporting, no prompt tuning, no change to the mock path, the schema, the
  `classify` signature, or the exit-code contract (beyond the new missing-extra fail-fast).

## Decisions

- **Port the reference's `temperature` handling verbatim in spirit.** Keep a module-level
  `_NO_TEMPERATURE: set[str]`. Send `temperature=0` unless the model is in it. Catch
  `litellm.BadRequestError`; if the message mentions `temperature`, add the model to the set,
  drop the param, and retry once. Newer models (Sonnet 5 / Opus 4.x) 400 on `temperature`, and
  litellm's model map is too stale to pre-empt it — so we learn per-model and never pay the
  wasted 400 twice in one run.
- **Retry rate limits with `retry-after`, backoff fallback, and a time budget.** A `tenacity`
  retry on `litellm.RateLimitError`, waiting `_retry_after(exc)` (parsed from the server
  headers) or `wait_exponential(multiplier=2, max=60)`, capped by `stop_after_delay(180)` and
  `reraise=True`. This outlasts a real (possibly multi-window) throttle instead of a blind
  fixed-count guess, then still surfaces the error cleanly if the budget is exhausted. Port
  `_retry_after` (checks `litellm_response_headers` and `response.headers`).
- **Fail fast on a missing extra, once, before the loop.** Add `providers.ensure_available(
  model)`: for a non-`mock` model, attempt the import and, on `ImportError`, raise a
  `ProviderUnavailable` carrying `litellm not installed — run: uv sync --extra litellm`.
  `main()` calls it once up front for non-`mock` models; on failure it prints the message to
  stderr and exits non-zero. This is a *config* error about the whole run, so it belongs before
  the per-action loop — not swallowed into N identical `ERR` rows. Per-action API errors during
  the loop stay per-row (one action can 400 while others succeed).
- **Surface per-action errors in rich.** After the table, if any row errored, print an
  `errors` section listing `[n] <message>` keyed to the row number (mirroring what the plain
  path already shows inline). Fixed-width columns can't hold a stack of error text, so a
  post-table block is the clean place; it keeps the table scannable and the message visible.
- **Keep it testable offline.** Tests inject a fake `litellm` module (exposing `completion`
  plus `BadRequestError`/`RateLimitError`) so temperature-drop, retry-after parsing, and the
  fail-fast path are exercised with no network and no key.

## Risks / Trade-offs

- [Detecting the `temperature` 400 by string-matching the message is brittle] → Accepted: it
  mirrors the reference and litellm's actual error surface; the fallback (drop temperature,
  retry) is safe even if the match is imperfect.
- [A `tenacity` retry can add up to ~180s on sustained throttling] → Intentional — outlasting a
  throttle beats failing instantly; `reraise=True` means it still ends in a clean error.
- [Porting the reference duplicates provider logic across two projects] → Acceptable; it's the
  proven code and stays small. The alternative (a shared package) is out of scope for this slice.
- [`ProviderUnavailable` is a new exception type] → Minimal: one class, used only to route the
  missing-extra case to a fail-fast message instead of the per-row `except`.
