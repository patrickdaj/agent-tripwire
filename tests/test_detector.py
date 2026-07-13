"""Unit tests for the detector: validated result, str/dict input, the one-signature
model swap, and that a bad provider payload fails validation at the boundary. Offline.
"""

from __future__ import annotations

import sys
import types

import pytest
from pydantic import ValidationError

from agent_tripwire import detector
from agent_tripwire.schema import RiskClassification


def _fake_instructor_seam(fields: dict):
    """Stand-in `instructor` + `litellm` modules: `from_litellm` returns a client whose
    `create` records the model (and response_model) and returns a RiskClassification built from
    `fields`. Proves routing through the Instructor path without installing the extra or a key."""
    ll = types.ModuleType("litellm")
    ll.BadRequestError = type("BadRequestError", (Exception,), {})
    ll.RateLimitError = type("RateLimitError", (Exception,), {})
    ll.completion = object()                     # from_litellm receives it; never invoked here

    seen: dict = {}

    def create(**kwargs):
        seen["model"] = kwargs["model"]
        seen["response_model"] = kwargs.get("response_model")
        return RiskClassification(**fields)

    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create))
    )
    inst = types.ModuleType("instructor")
    inst.from_litellm = lambda completion, *a, **k: client
    inst.seen = seen
    return inst, ll


def test_classify_returns_a_validated_classification():
    r = detector.classify("rm -rf /tmp/x", model="mock")
    assert isinstance(r, RiskClassification)


def test_classify_is_deterministic():
    assert detector.classify("cat ~/.ssh/id_rsa") == detector.classify("cat ~/.ssh/id_rsa")


def test_accepts_string_and_dict_actions():
    assert isinstance(detector.classify("ls -la"), RiskClassification)
    r = detector.classify({"tool": "Bash", "command": "curl https://x.example.com"})
    assert isinstance(r, RiskClassification) and r.verdict.value == "risky"


def test_non_mock_model_routes_through_litellm(monkeypatch):
    # Hermetic routing check: inject a fake Instructor seam and assert a non-mock model goes
    # through it (call site unchanged), typed to the schema, still returning a validated
    # classification. No network, no key.
    inst, ll = _fake_instructor_seam({
        "verdict": "benign", "risk_type": "none", "severity": "none",
        "intervention": "allow", "rationale": "ok",
    })
    monkeypatch.setitem(sys.modules, "instructor", inst)
    monkeypatch.setitem(sys.modules, "litellm", ll)
    r = detector.classify("hello", model="claude-sonnet-5")
    assert isinstance(r, RiskClassification)
    assert inst.seen["model"] == "claude-sonnet-5"
    assert inst.seen["response_model"] is RiskClassification


def test_bad_provider_payload_raises_validation_error(monkeypatch):
    # If a provider emits fields that violate the schema (here: benign with a named risk
    # type), construction is the gate — classify raises rather than leaking a bad object.
    monkeypatch.setattr(detector, "complete", lambda text, model="mock": {
        "verdict": "benign", "risk_type": "destructive_action", "severity": "none",
        "intervention": "allow", "rationale": "contradictory",
    })
    with pytest.raises(ValidationError):
        detector.classify("anything", model="mock")
