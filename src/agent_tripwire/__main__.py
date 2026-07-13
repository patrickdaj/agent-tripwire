"""Package entrypoint: ``python -m agent_tripwire`` (or the ``agent-tripwire`` script).

Loads the real inputs, routes each to the detector its ``kind`` names (``action`` —
the default when absent — ``transcript``, ``prompt``, or ``output``), classifies it on
the chosen model (``mock`` by default), and prints each input beside its validated
verdict *and its hand-labeled expectation*, with a ``✓``/``✗`` match marker.

The two claims this run makes are kept separate on purpose:
- **exit code** reflects only wiring + schema validation. A crash or a ``ValidationError``
  exits non-zero; a ``✗`` (the mock disagreeing with a label) does **not** fail the run.
- **the match column** is an honest, non-gating read on classification quality. At least one
  input is keyword-blind, so the shallow mock is *expected* to miss it — the ``✗`` is the
  point, not a failure. If a mismatch were fatal we'd be tempted to curate easy inputs, which
  is exactly the self-confirming run this design avoids. (No pass-rate summary — that's a
  metric, deferred with the golden set.)
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from .detector import audit_transcript, classify, detect_injection, flag_output
from .providers import ProviderUnavailable, ensure_available

# Inputs live at the project root (data you edit, not shipped code). Anchor the default
# to it so the run works from any directory, like the reference's cases.jsonl.
DEFAULT_INPUTS = Path(__file__).resolve().parents[2] / "inputs.jsonl"

# rich is optional: it renders a colored table. Absent, we fall back to plain text, so the
# skeleton runs with nothing but pydantic (`python -m agent_tripwire` needs no rich).
try:
    import rich  # noqa: F401  (imported for availability check only)

    _RICH = True
except ImportError:
    _RICH = False


def load_inputs(path: Path):
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


# kind → how to classify its payload. Lambdas resolve the entry-point names at call time
# (not at dict build), so tests can monkeypatch e.g. `M.classify` and still be routed to.
# The payload field in an input row is named after its kind ("action" for the default).
_CLASSIFIERS = {
    "action": lambda payload, model: classify(payload, model=model),
    "transcript": lambda payload, model: audit_transcript(payload, model=model),
    "prompt": lambda payload, model: detect_injection(payload, model=model),
    "output": lambda payload, model: flag_output(payload, model=model),
}


def _matches(rc, expected: dict) -> bool:
    """Does the result agree with the hand label? Verdict always; the finer field —
    `risk_type` (action), `technique` (prompt), `categories` (output) — only when the
    label names it, so a verdict flip *and* a wrong subtype both show as a miss. Labels
    only name fields their kind's schema has, so the getattrs below never cross kinds."""
    if rc.verdict.value != expected.get("verdict"):
        return False
    if "risk_type" in expected and rc.risk_type.value != expected["risk_type"]:
        return False
    if "technique" in expected and rc.technique.value != expected["technique"]:
        return False
    if "categories" in expected:
        if {f.category.value for f in rc.findings} != set(expected["categories"]):
            return False
    return True


def _display(item, kind: str) -> str:
    """The text shown for an input row: its payload as-is when a string, compact JSON
    when structured, the whole row as a last resort (e.g. an unknown kind)."""
    payload = item.get(kind)
    if isinstance(payload, str):
        return payload
    if payload is not None:
        return json.dumps(payload, sort_keys=True, default=str)
    return json.dumps({k: v for k, v in item.items() if k != "expected"},
                      sort_keys=True, default=str)


def run(inputs, model: str):
    """Route each input to its kind's detector and classify it. A row is either
    {kind, action, rc, expected, match} or, if classification raised, {error}. An
    unrecognized kind is an error row too — a wiring bug, not a miss. The error case is
    what makes the run exit non-zero."""
    rows = []
    for item in inputs:
        kind = item.get("kind", "action")
        expected = item.get("expected", {})
        display = _display(item, kind)
        try:
            if kind not in _CLASSIFIERS:
                raise ValueError(
                    f"unknown kind {kind!r} (expected one of {sorted(_CLASSIFIERS)})"
                )
            rc = _CLASSIFIERS[kind](item[kind], model)
            rows.append({"kind": kind, "action": display, "rc": rc, "expected": expected,
                         "match": _matches(rc, expected), "error": None})
        except Exception as e:  # ValidationError or any provider failure — wiring is broken
            rows.append({"kind": kind, "action": display, "rc": None, "expected": expected,
                         "match": None, "error": f"{type(e).__name__}: {e}"})
    return rows


def _status(row) -> tuple[str, str, str]:
    """(glyph, label, style) for a row — the single status vocabulary both renderers read.
    The *word* (`OK`/`MISS`/`ERR`) carries the signal when color can't (the plain / NO_COLOR
    path); the style is the color enhancement layered on top under rich."""
    if row["error"]:
        return ("!", "ERR", "red")
    if row["match"]:
        return ("✓", "OK", "green")
    return ("✗", "MISS", "red")


def _expected_str(expected: dict) -> str:
    v = expected.get("verdict", "?")
    for key in ("risk_type", "technique"):  # the finer field, when the label names one
        if key in expected:
            return f"{v}/{expected[key]}"
    if "categories" in expected:
        return f"{v}/{'+'.join(expected['categories'])}"
    return v


def _detail_str(rc) -> str:
    """Every result field except the verdict (which gets its own column under rich), as
    the schema's own readable lines — uniform across the four result types."""
    return "\n".join(
        line for line in str(rc).splitlines() if not line.startswith("verdict:")
    )


def _plain_report(rows, model: str):
    """Plain-text fallback — used when rich is absent or color is off. Prominence here is
    color-free: a full-width rule delimits each numbered block, and the leading `[n] ✗ MISS`
    header makes a miss scannable at the left margin without any ANSI."""
    width = min(shutil.get_terminal_size(fallback=(80, 24)).columns, 80)
    rule = "  " + "─" * max(width - 4, 8)
    print(f"\n  model: {model}")
    for i, row in enumerate(rows, 1):
        glyph, label, _ = _status(row)
        print(rule)
        print(f"  [{i}] {glyph} {label} · {row['kind']}")
        first, *rest = row["action"].splitlines() or [""]
        print(f"  input: {first}")
        for line in rest:  # keep multi-line inputs (transcripts) inside the block indent
            print(f"         {line}")
        if row["error"]:
            print(f"    ERROR: {row['error']}")
        else:
            for line in str(row["rc"]).splitlines():
                print(f"    {line}")
        print(f"    expected:     {_expected_str(row['expected'])}")
    print(rule)
    miss_nums = [i for i, r in enumerate(rows, 1) if r["error"] is None and not r["match"]]
    if miss_nums:
        print(f"\n  misses: {miss_nums} — expected on the keyword-blind inputs; not a failure.\n")
    else:
        print()


def _rich_report(rows, model: str, console):
    """Colored table — same rows as the plain report. `show_lines` rules every row off so
    entries can't bleed together; the leading status column plus a red row style make a miss
    read as a red band, not a subtle trailing mark."""
    from rich.table import Table
    from rich.text import Text

    table = Table(title=f"agent-tripwire · {model}", title_style="bold",
                  header_style="bold", show_lines=True)
    table.add_column("status", justify="center")  # leads: glyph + OK/MISS/ERR
    table.add_column("kind")
    table.add_column("input", overflow="fold", max_width=42)
    table.add_column("verdict")
    # One details column instead of per-field columns: the four result types have
    # different fields, and each schema's __str__ already renders its own readably.
    table.add_column("details", overflow="fold", max_width=40)
    table.add_column("expected")

    for row in rows:
        glyph, label, _ = _status(row)
        status = f"{glyph} {label}"
        # Whole row reads red on a miss or error; an OK row stays default.
        row_style = None if (row["error"] is None and row["match"]) else "red"
        expected = _expected_str(row["expected"])
        if row["error"]:
            table.add_row(status, row["kind"], Text(row["action"]), "ERROR", "",
                          expected, style=row_style)
        else:
            rc = row["rc"]
            table.add_row(
                status, row["kind"], Text(row["action"]), rc.verdict.value,
                Text(_detail_str(rc)), expected, style=row_style,
            )
    console.print(table)

    # Surface the actual error text so a per-action failure is diagnosable from rich output,
    # not just a bare ERROR cell. Use Text so a message can't inject console markup.
    errors = [(i, row["error"]) for i, row in enumerate(rows, 1) if row["error"]]
    if errors:
        console.print(Text("errors:", style="bold red"))
        for i, msg in errors:
            console.print(Text(f"  [{i}] {msg}", style="red"))


def color_enabled(no_color: bool) -> bool:
    """Colored output only on an interactive terminal with rich present — never when rich
    is missing, NO_COLOR is set, --no-color is passed, or output is piped."""
    return (
        _RICH
        and sys.stdout.isatty()
        and not os.environ.get("NO_COLOR")
        and not no_color
    )


def report(rows, model: str, *, color: bool):
    if _RICH and color:
        from rich.console import Console

        _rich_report(rows, model, Console())
    else:
        _plain_report(rows, model)


def main():
    ap = argparse.ArgumentParser(description="agent-tripwire: classify agent actions for risk.")
    ap.add_argument("--model", default="mock", help="'mock' (offline) or any litellm model id")
    ap.add_argument("--inputs", default=DEFAULT_INPUTS, type=Path)
    ap.add_argument("--no-color", action="store_true",
                    help="force plain-text output (also off a non-TTY or with NO_COLOR)")
    args = ap.parse_args()

    # Preflight the provider once. A missing optional dependency is a config error about the
    # whole run — fail fast with the fix, rather than erroring identically on every input.
    try:
        ensure_available(args.model)
    except ProviderUnavailable as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)

    rows = run(load_inputs(args.inputs), args.model)
    report(rows, args.model, color=color_enabled(args.no_color))

    # Exit code tracks wiring + schema validation only: non-zero iff some input failed to
    # produce a valid classification. A ✗ (known mock miss) is shown, never fatal.
    had_error = any(r["error"] for r in rows)
    sys.exit(1 if had_error else 0)


if __name__ == "__main__":
    main()
