"""Offline tests for the Instructor-backed litellm path: the request is typed to the schema
with a bounded validation-retry count, plus the preserved hardening — temperature-400 recovery,
rate-limit retry, `retry-after` parsing, and the missing-extra fail-fast. A fake `instructor`
module (its `from_litellm` returns a fake client) and a fake `litellm` module are injected via
`sys.modules`, so nothing here touches the network or needs a key. `tenacity` is real (it ships
with the litellm extra); we neutralize its sleep so retries don't actually wait.
"""

from __future__ import annotations

import builtins
import json
import sys
import time
import types

import pytest

from agent_tripwire import providers
from agent_tripwire.schema import RiskClassification

# Valid raw fields → a RiskClassification the fake client can hand back. `model_dump(mode="json")`
# of that model is exactly this dict, which is what `_litellm` returns.
_VALID_FIELDS = {
    "verdict": "benign", "risk_type": "none", "severity": "none",
    "intervention": "allow", "rationale": "ok",
}


def _fake_litellm():
    """A stand-in `litellm` module supplying the exception types the path reasons about. Its
    `completion` is never invoked directly here — Instructor's `create` is the seam we fake."""
    m = types.ModuleType("litellm")
    m.BadRequestError = type("BadRequestError", (Exception,), {})
    m.RateLimitError = type("RateLimitError", (Exception,), {})
    m.completion = lambda **k: (_ for _ in ()).throw(
        AssertionError("litellm.completion should be driven through the Instructor client")
    )
    return m


class _FakeClient:
    """Fake Instructor client. `chat.completions.create(**kwargs)` records each call's kwargs and
    defers to `behavior(kwargs, attempt_number)`, which returns a RiskClassification or raises."""

    def __init__(self, behavior):
        self._behavior = behavior
        self.calls: list[dict] = []
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self._behavior(kwargs, len(self.calls))


def _fake_instructor(client):
    m = types.ModuleType("instructor")
    m.from_litellm = lambda completion, *a, **k: client   # ignore the wrapped completion fn
    return m


def _install(monkeypatch, client, fake_ll=None):
    """Inject the fake instructor + litellm so `_litellm`'s lazy imports resolve to them."""
    monkeypatch.setitem(sys.modules, "instructor", _fake_instructor(client))
    monkeypatch.setitem(sys.modules, "litellm", fake_ll or _fake_litellm())


def test_request_is_typed_to_schema_and_returns_field_dict(monkeypatch):
    client = _FakeClient(lambda kwargs, n: RiskClassification(**_VALID_FIELDS))
    _install(monkeypatch, client)

    out = providers._litellm("some action", "some-model")

    assert out == _VALID_FIELDS and isinstance(out, dict)     # model_dump(mode="json")
    call = client.calls[0]
    assert call["response_model"] is RiskClassification        # typed to the schema
    assert isinstance(call["max_retries"], int) and 1 <= call["max_retries"] <= 5  # bounded
    assert call["model"] == "some-model"


# Note: litellm's "Give Feedback" banner is written at the *fd level* (below sys.stdout),
# so it cannot be contained here in the provider — it is diverted by the gateway's
# process-level stdout isolation instead. See
# tests/test_hook_cli.py::test_gateway_diverts_fd_level_stdout_noise.


def test_temperature_400_retries_without_temperature(monkeypatch):
    providers._NO_TEMPERATURE.discard("temp-model")
    fake_ll = _fake_litellm()

    def behavior(kwargs, n):
        if "temperature" in kwargs:
            raise fake_ll.BadRequestError("BadRequestError: `temperature` is not supported")
        return RiskClassification(**_VALID_FIELDS)

    client = _FakeClient(behavior)
    _install(monkeypatch, client, fake_ll)

    out = providers._litellm("some action", "temp-model")
    assert out["verdict"] == "benign"                         # succeeded after the retry
    assert len(client.calls) == 2                             # first with temp (400), retry without
    assert "temperature" in client.calls[0] and "temperature" not in client.calls[1]
    assert "temp-model" in providers._NO_TEMPERATURE          # remembered

    client.calls.clear()
    providers._litellm("another action", "temp-model")        # same model this run
    assert "temperature" not in client.calls[0]               # never re-sent
    providers._NO_TEMPERATURE.discard("temp-model")           # clean up module state


def test_non_temperature_bad_request_propagates(monkeypatch):
    fake_ll = _fake_litellm()
    client = _FakeClient(
        lambda kwargs, n: (_ for _ in ()).throw(fake_ll.BadRequestError("invalid model id"))
    )
    _install(monkeypatch, client, fake_ll)
    with pytest.raises(fake_ll.BadRequestError):
        providers._litellm("action", "bad-model")


def test_rate_limit_is_retried(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)        # don't actually wait out backoff
    fake_ll = _fake_litellm()

    def behavior(kwargs, n):
        if n == 1:
            raise fake_ll.RateLimitError("rate limited")
        return RiskClassification(**_VALID_FIELDS)

    client = _FakeClient(behavior)
    _install(monkeypatch, client, fake_ll)

    out = providers._litellm("action", "rl-model")
    assert out["verdict"] == "benign"
    assert len(client.calls) == 2                             # failed once, retried, succeeded


def test_retry_after_parses_both_header_sources_and_defaults_none():
    e1 = types.SimpleNamespace(litellm_response_headers={"retry-after": "12"})
    assert providers._retry_after(e1) == 12.0
    e2 = types.SimpleNamespace(response=types.SimpleNamespace(headers={"retry-after": "3"}))
    assert providers._retry_after(e2) == 3.0
    assert providers._retry_after(types.SimpleNamespace()) is None           # no headers
    e4 = types.SimpleNamespace(litellm_response_headers={"retry-after": "soon"})
    assert providers._retry_after(e4) is None                                 # unparseable → None


def test_unwrap_peels_instructor_retry_exception():
    # A provider error surfaces from litellm wrapped in InstructorRetryException; _unwrap peels
    # that one layer so the temperature/rate-limit handling sees the real litellm error. A
    # directly-raised error (the test seam) passes straight through.
    cause = ValueError("underlying")
    wrapper = type("InstructorRetryException", (Exception,), {})("wrapped")
    wrapper.__cause__ = cause
    assert providers._unwrap(wrapper) is cause
    direct = RuntimeError("direct")
    assert providers._unwrap(direct) is direct


def test_ensure_available_fails_fast_when_litellm_absent(monkeypatch):
    real_import = builtins.__import__

    def no_litellm(name, *a, **k):
        if name == "litellm":
            raise ImportError("simulated absent")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_litellm)
    providers.ensure_available("mock")                        # mock never needs the extra
    with pytest.raises(providers.ProviderUnavailable) as ei:
        providers.ensure_available("claude-sonnet-5")
    assert "uv sync --extra litellm" in str(ei.value)


def test_ensure_available_fails_fast_when_instructor_absent(monkeypatch):
    # Instructor ships in the same extra as litellm, so its absence must also fail fast with the
    # one install hint — the real-model path needs both.
    real_import = builtins.__import__

    def no_instructor(name, *a, **k):
        if name == "instructor":
            raise ImportError("simulated absent")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_instructor)
    with pytest.raises(providers.ProviderUnavailable) as ei:
        providers.ensure_available("claude-sonnet-5")
    assert "uv sync --extra litellm" in str(ei.value)


def test_main_fails_fast_once_on_missing_extra(tmp_path, monkeypatch, capsys):
    from agent_tripwire import __main__ as M

    p = tmp_path / "inputs.jsonl"
    p.write_text("".join(
        json.dumps({"action": f"a{i}", "expected": {"verdict": "benign"}}) + "\n"
        for i in range(3)
    ))

    def unavailable(model):
        raise providers.ProviderUnavailable("litellm not installed — run: uv sync --extra litellm")

    monkeypatch.setattr(M, "ensure_available", unavailable)
    monkeypatch.setattr(sys, "argv",
                        ["agent-tripwire", "--model", "claude-sonnet-5", "--inputs", str(p)])
    with pytest.raises(SystemExit) as ei:
        M.main()
    assert ei.value.code == 2                                 # config error, non-zero
    err = capsys.readouterr().err
    assert err.count("litellm not installed") == 1            # one message, not one per input
