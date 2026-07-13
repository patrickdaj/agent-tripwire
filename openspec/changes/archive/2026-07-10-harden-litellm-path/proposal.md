## Why

The real-model path was shipped as a deliberate stub — "behind the same signature, untested."
Now that `--model claude-sonnet-5` is actually being used, two things bite:

- **It doesn't work against modern Claude models.** `_litellm` sends `temperature=0`
  unconditionally, and newer Claude models (Sonnet 5, Opus 4.x) reject `temperature` with a
  400. There's no retry, so a rate-limited key fails outright too. The reference
  `ai-eval-harness` already solved both; our stub skipped them.
- **Its failures are undebuggable.** When a row errors, the rich renderer shows only the word
  `ERROR` — the actual message is hidden (only the plain path prints it). Worse, a missing
  optional dependency (`litellm` not installed) surfaces as *N identical per-row `ERR`s*
  instead of one clear, actionable message — which is exactly the confusion just hit in practice.

The mock path is the verified core; this change makes the real-model path a functioning,
diagnosable sibling rather than a stub that fails opaquely.

## What Changes

- **Harden `providers._litellm`** by porting the reference's handling: learn per-model on the
  first `temperature` 400 and drop the parameter thereafter (a module-level `_NO_TEMPERATURE`
  set, so later inputs skip the wasted 400); and retry rate limits, honoring the server's
  `retry-after` header with an exponential-backoff fallback and an overall time budget.
- **Fail fast on a missing `litellm` extra.** Detect the absent dependency once, before
  classifying, and stop with an actionable message — `litellm not installed — run: uv sync
  --extra litellm` — instead of erroring once per input.
- **Surface per-action error messages in the rich renderer**, matching the plain path, so a
  genuine per-action failure (e.g. one action 400s while others succeed) is diagnosable from
  the output rather than a bare `ERROR` cell.

Out of scope: no change to the schema, the mock provider, the `classify` signature, the
exit-code contract, or prompt tuning. Cost/latency reporting stays out (deferred with scoring).

## Capabilities

### New Capabilities
<!-- None — hardens the real-model path and error display within an existing capability. -->

### Modified Capabilities
- `risk-detection`: strengthens the real-model path (temperature/​rate-limit resilience), adds
  a fail-fast contract when the `litellm` extra is missing, and requires per-action errors to
  be visible in every renderer.

## Impact

- **Code:** `src/agent_tripwire/providers.py` (`_litellm`, `complete`, new `_retry_after` /
  `_NO_TEMPERATURE` helpers, an availability check) and `src/agent_tripwire/__main__.py`
  (rich error surfacing; one-time provider preflight before the run loop). No change to
  `schema.py`, `detector.py`'s signature, or `inputs.jsonl`.
- **Tests:** `tests/` — temperature-400-then-retry-without-it, retry-after parsing, the
  missing-`litellm` fail-fast message, and rich error-message surfacing. All offline (litellm
  and errors are stubbed/monkeypatched — no network, no key).
- **Dependencies:** none new — `tenacity` already ships in the `litellm` extra.
- **Contract:** exit code still tracks wiring + schema validation. A missing extra now exits
  non-zero with a clear message (a config error, not a silent per-row failure); the mock path
  is unaffected.
