## 1. Shared status vocabulary

- [x] 1.1 In `__main__.py` replace `_mark(row)` with `_status(row) → (glyph, label, style)`: OK `("✓","OK","green")`, miss `("✗","MISS","red")`, error `("!","ERR","red")`. Both renderers consume it so the paths can't drift

## 2. Rich renderer: dividers + prominent misses

- [x] 2.1 In `_rich_report` set `show_lines=True` on the `Table` so every row is ruled off
- [x] 2.2 Add a leading `status` column (glyph + label) as the first column and drop the trailing marker column
- [x] 2.3 Pass `style="red"` on `add_row` for a MISS/ERR row so the whole row reads as a red band; OK rows stay default. Keep the existing action(fold)/verdict/risk_type/sev/interv./expected columns

## 3. Plain renderer: numbered, separated, color-free prominence

- [x] 3.1 In `_plain_report` print a full-width separator rule (`shutil.get_terminal_size`) between action blocks and number each entry `[1]`/`[2]`/`[3]`
- [x] 3.2 Lead each block with a `[n] <glyph> <label>` header at the left margin (e.g. `[3] ✗ MISS`) so the status is scannable in plain text without color
- [x] 3.3 Update the closing summary to list the offending entry numbers (e.g. `misses: [3]`); keep it non-gating wording

## 4. Tests

- [x] 4.1 In `tests/test_main.py` assert rich output rules rows off (`show_lines`) and a miss row carries the leading `MISS` status; update any assertion tied to the old trailing marker
- [x] 4.2 Assert the plain (color-stripped) output contains the `MISS` word, numbered blocks, and a separator between actions — i.e. a miss is identifiable without color and rows don't bleed
- [x] 4.3 Assert `ERR` and `MISS` are distinct labels; re-confirm `main()` still exits 0 on a known miss and non-zero on a broken classification (unchanged)

## 5. Verify

- [x] 5.1 Run `uv run python -m agent_tripwire` (plain) and a forced-rich render; confirm actions are clearly delimited and the keyword-blind miss is obvious at a glance; `uv run pytest -q` green
