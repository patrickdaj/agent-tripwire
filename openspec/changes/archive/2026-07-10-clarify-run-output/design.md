## Context

The run is rendered by two functions in `src/agent_tripwire/__main__.py`: `_rich_report`
(a `rich.table.Table`) and `_plain_report` (indented text blocks), chosen by `color_enabled`.
Today the rich table has no row dividers (`show_lines` unset) and the plain report separates
entries with a single blank line, so tall wrapped actions bleed into their neighbours. The
match state is a lone trailing column / bracketed `[✓]`/`[✗]` — the lowest-salience element on
screen. A shared `_mark(row)` helper returns the `✓`/`✗`/`!` glyph.

Crucial constraint: the plain path is also the **NO_COLOR / non-TTY / rich-absent** path, so
its legibility can carry *no* color. Prominence in plain text must come from words and layout,
not ANSI — that's the path where scannability matters most.

## Goals / Non-Goals

**Goals:**
- Every action is visually delimited so adjacent entries never bleed together, in both renderers.
- A miss is the first thing the eye catches — a leading, high-contrast status, not a trailing mark.
- Misses stay identifiable with color stripped (the plain / NO_COLOR path).
- Errors (a broken classification) remain visually distinct from misses.

**Non-Goals:**
- No change to what is classified, the schema, the exit-code contract, or the non-gating
  semantics of a miss. No pass-rate summary. No new dependency. Rendering only.

## Decisions

- **One status vocabulary, shared by both renderers.** Replace `_mark` with `_status(row) →
  (glyph, label, style)`: `("✓","OK","green")`, `("✗","MISS","red")`, `("!","ERR","red")`. A
  single source so the two paths can't drift, and so the *word* (`OK`/`MISS`/`ERR`) carries the
  signal when color can't.
- **Status moves to the front.** Both renderers lead each entry with `glyph + label`, not a
  trailing column. Rich: a new first `status` column (drop the trailing marker column). Plain:
  a header line `[n] ✗ MISS` at the left margin above the action. The left edge is where the
  eye lands, so the miss signal lives there.
- **Rich: row dividers + row-level red for misses.** Set `show_lines=True` so every row is
  ruled off. Pass `style="red"` on `add_row` for a MISS/ERR row so the whole line is colored,
  not just one cell — a miss reads as a red band, an OK row stays default. Same columns
  otherwise (action folded, verdict/risk_type/sev/interv./expected).
- **Plain: numbered blocks with a separator rule.** Print a full-width rule
  (`shutil.get_terminal_size`) between blocks and number each entry `[1]`/`[2]`/`[3]`. The rule
  gives the boundary; the number + `MISS` word give the identity — both color-free.
- **Errors distinct from misses by word, not just color.** `ERR` vs `MISS` labels distinguish
  them even in plain text; both render red under rich. The error row still shows the exception
  text as it does today.
- **Keep the trailing summary, keyed to the numbers.** The plain report's closing "known
  miss(es)" line now lists the offending entry numbers (e.g. `misses: [3]`), so a reader can
  jump to them.

## Risks / Trade-offs

- [`show_lines=True` makes the rich table taller] → Accepted: for a handful of rows, clear
  boundaries beat density; that's the whole complaint.
- [Reordering columns / dropping the trailing marker changes the rich output shape] → Update
  `tests/test_main.py`; the render-parity and exit-code contracts are unchanged, only assertions
  about where the marker lives.
- [Red styling only appears under rich+color, but misses must be obvious in plain too] →
  Mitigated by design: the `MISS`/`ERR` word and the numbered separator are the primary signal;
  color is an enhancement on top, never the sole cue. A test asserts `MISS` is present in the
  plain (color-stripped) output.
