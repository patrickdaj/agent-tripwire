"""``agent-tripwire-gate`` — the hook gateway CLI every harness adapter speaks.

Neutral mode (default): one :class:`~agent_tripwire.gate.GateRequest` JSON object on
stdin → one :class:`~agent_tripwire.gate.GateDecision` JSON object on stdout, exit 0.
A block is a *successful gating*, not a process failure — it also exits 0.

``--adapter claude-code``: reads a Claude Code hook event JSON instead, dispatches on
``hook_event_name``, and emits the Claude-Code-shaped response for that event (see
:mod:`agent_tripwire.adapters.claude_code`). Translation only — policy lives in the gate.

Exit-code contract: 0 whenever a decision/response was emitted (including blocks and
exit-2-style blocking responses use their documented codes); any failure to even emit
exits non-zero with one line on stderr. Adapters treat a non-zero or unparseable gateway
as **block** — there is no input, however malformed, that yields silence-plus-success.
"""

import argparse
import json
import os
import sys

from .gate import GateDecision, Intervention, evaluate

# The protocol JSON is written to a saved dup of the original stdout fd. `isolate_stdout()`
# creates it and hands fd 1 to stderr, so anything a library writes to stdout — including
# litellm's banner, emitted at the fd level below `sys.stdout` — lands on stderr and can
# never corrupt the single-JSON-line protocol. The saved fd lives on `sys` (a true
# singleton), not a module global: running via `python -m` loads this module twice
# (`__main__` + the package copy the adapter re-imports), and only a `sys` attribute is
# shared across both. Absent (not isolated, e.g. in-process tests) it defaults to fd 1.
_STDOUT_FD_ATTR = "_agent_tripwire_stdout_fd"


def isolate_stdout() -> None:
    """Save the real stdout fd and point fd 1 at stderr for the rest of the process.

    Done once, on the main thread, before any evaluation — so the fds are stable and the
    deadline's worker thread never touches them (no race with the fail-closed emit). This
    is the only reliable defense against a library that writes to fd 1 directly; a
    Python-level `redirect_stdout` can't see those writes."""
    setattr(sys, _STDOUT_FD_ATTR, os.dup(1))  # saved original stdout — protocol goes here
    os.dup2(2, 1)                              # fd 1 now == stderr; stray noise is diverted


def emit_stdout(text: str) -> None:
    """Write one protocol line to the saved real stdout at the fd level. A dead stdout
    raises here, inside the caller's no-silent-success backstop."""
    os.write(getattr(sys, _STDOUT_FD_ATTR, 1), (text + "\n").encode())


def _emergency_block(reason: str) -> GateDecision:
    """A decision built with no help from the gate — the last-resort fail-closed shape
    for input we couldn't even hand to `evaluate`."""
    return GateDecision(
        decision=Intervention.block,
        rationale=f"fail-closed: {reason}",
        error=reason,
    )


def _neutral(stdin_text: str) -> int:
    """Neutral protocol: GateRequest JSON in, GateDecision JSON out, exit 0."""
    try:
        request = json.loads(stdin_text)
    except json.JSONDecodeError as e:
        decision = _emergency_block(f"stdin is not valid JSON: {e}")
    else:
        if isinstance(request, dict):
            decision = evaluate(request)  # evaluate never raises — fail-closed inside
        else:
            decision = _emergency_block(
                f"expected a JSON object GateRequest, got {type(request).__name__}"
            )
    emit_stdout(decision.model_dump_json())
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(
        description="agent-tripwire hook gateway: gate one request from stdin."
    )
    ap.add_argument("--adapter", choices=["claude-code"], default=None,
                    help="translate a harness's native hook event instead of the neutral protocol")
    args = ap.parse_args()

    try:
        isolate_stdout()  # divert any library stdout noise before we evaluate anything
        stdin_text = sys.stdin.read()
        if args.adapter == "claude-code":
            from .adapters.claude_code import handle_event
            sys.exit(handle_event(stdin_text))
        sys.exit(_neutral(stdin_text))
    except SystemExit:
        raise
    except BaseException as e:  # noqa: BLE001 — the no-silent-success backstop
        print(f"agent-tripwire-gate: failed to emit a decision: {e}", file=sys.stderr)
        sys.exit(1)  # adapters treat non-zero as block


if __name__ == "__main__":
    main()
