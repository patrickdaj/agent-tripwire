"""Unit tests for the classification schema — the product spec.

Covers the field set, the closed enums, both cross-field invariants (each direction),
the extra="forbid" guard, and the human-readable __str__. All offline.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_tripwire.schema import (
    Intervention,
    RiskClassification,
    RiskType,
    Severity,
    Verdict,
)


def _risky(**over):
    base = dict(verdict="risky", risk_type="destructive_action", severity="high",
                intervention="block", rationale="rm -rf on home")
    return {**base, **over}


def _benign(**over):
    base = dict(verdict="benign", risk_type="none", severity="none",
                intervention="allow", rationale="read-only")
    return {**base, **over}


def test_field_set_is_exactly_the_five():
    assert list(RiskClassification.model_fields) == [
        "verdict", "risk_type", "severity", "intervention", "rationale",
    ]


def test_enum_membership_is_closed():
    assert {e.value for e in Verdict} == {"risky", "benign"}
    assert {e.value for e in RiskType} == {
        "exfiltration_attempt", "injection_symptom", "out_of_scope_access",
        "destructive_action", "secret_exposure", "none",
    }
    assert {e.value for e in Severity} == {"none", "low", "medium", "high", "critical"}
    assert {e.value for e in Intervention} == {"allow", "warn", "block", "confirm"}


def test_valid_risky_and_benign_construct():
    r = RiskClassification(**_risky())
    assert r.verdict is Verdict.risky and r.risk_type is RiskType.destructive_action
    b = RiskClassification(**_benign())
    assert b.verdict is Verdict.benign and b.severity is Severity.none


@pytest.mark.parametrize("bad", [
    dict(verdict="spicy"),          # out-of-enum verdict
    dict(risk_type="meltdown"),     # out-of-enum risk_type
    dict(severity="apocalyptic"),   # out-of-enum severity
    dict(intervention="pray"),      # out-of-enum intervention
])
def test_out_of_enum_is_rejected(bad):
    with pytest.raises(ValidationError):
        RiskClassification(**_risky(**bad))


@pytest.mark.parametrize("kwargs, needle", [
    (_benign(risk_type="destructive_action"), "risk_type"),   # benign must have none
    (_benign(severity="high"), "severity"),                    # benign must have none
    (_risky(risk_type="none"), "risk_type"),                   # risky must be named
])
def test_cross_field_rules_name_the_offending_field(kwargs, needle):
    with pytest.raises(ValidationError) as ei:
        RiskClassification(**kwargs)
    assert needle in str(ei.value)


def test_extra_field_is_forbidden():
    with pytest.raises(ValidationError):
        RiskClassification(**_benign(), confidence=0.9)


def test_str_is_readable_lines_not_object_dump():
    s = str(RiskClassification(**_risky()))
    assert "verdict:" in s and "rationale:" in s
    assert "RiskClassification(" not in s
    assert len(s.splitlines()) == 5
