## Why

The run output does its job but is hard to *scan*. Two concrete problems:

- **Actions bleed together.** In both renderers, consecutive entries run into each other —
  the rich table has no row dividers, so a tall wrapped action flows straight into the next
  one, and the plain report separates blocks with only a blank line. You can't tell at a
  glance where one action ends and the next begins.
- **Misses are easy to miss.** The `✓`/`✗` marker is a single narrow trailing column (rich)
  or a bracketed marker at the end of the last line (plain). A `✗` — the whole point of the
  expected-vs-actual design — is the least visible thing on screen, exactly backwards.

The output is the primary way a human reads the detector's verdicts, so legibility is a real
feature, not polish. This change makes boundaries obvious and makes a failed classification
the *first* thing you notice.

## What Changes

- **Delimit every action.** Give each entry a clear visual boundary so adjacent actions never
  bleed together — a horizontal rule between rows in the rich table, and a separator line
  (plus per-action numbering) between blocks in the plain report.
- **Make misses prominent.** Surface a mismatch with a leading, high-contrast status indicator
  rather than a subtle trailing mark: a status column at the *front* of each row using a word
  (`OK` / `MISS`), red row-level styling for a miss under rich, and a left-margin `MISS` marker
  in the plain report. Errors (a broken classification) stay visually distinct from misses.
- Keep the two claims separate exactly as before: prominence is a *readability* change only —
  a `✗`/`MISS` is still non-gating and never changes the exit code.

Out of scope: no change to what is classified, the schema, the exit-code contract, or the
non-gating semantics; no pass-rate summary; only how the run is rendered.

## Capabilities

### New Capabilities
<!-- None — this refines rendering behavior in an existing capability. -->

### Modified Capabilities
- `risk-detection`: adds requirements that the run output visually delimits each action and
  renders a mismatch prominently, in both the rich and plain paths.

## Impact

- **Code:** `src/agent_tripwire/__main__.py` only — the `_rich_report` and `_plain_report`
  renderers (and small helpers like `_mark`). No change to `schema.py`, `providers.py`,
  `detector.py`, `inputs.jsonl`, or the exit-code logic in `main()`.
- **Tests:** `tests/test_main.py` — assertions that rows are delimited and that a miss carries
  a prominent indicator in both render paths; existing exit-code and parity tests unchanged.
- **Dependencies:** none — still `rich` (optional) with the plain-text fallback.
- **Contract:** unchanged. Exit code still tracks only wiring + schema validation; a miss is
  still shown, never fatal.
