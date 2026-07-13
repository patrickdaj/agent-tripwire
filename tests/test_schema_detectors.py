"""Unit tests for the per-detector schemas added by the multi-detector suite:
TranscriptAudit, InjectionClassification, SensitiveDataFlag. Covers the field sets, the
closed enums, every cross-field invariant (each direction), the extra="forbid" guard,
and the human-readable __str__. All offline.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_tripwire.schema import (
    InjectionClassification,
    InjectionTechnique,
    InjectionVerdict,
    ResourceKind,
    ScopeVerdict,
    SensitiveCategory,
    SensitiveDataFlag,
    SensitiveVerdict,
    TranscriptAudit,
)

# --- TranscriptAudit ---

_IN = {"resource": "src/app.py", "kind": "file", "in_scope": True}
_OUT = {"resource": "~/.ssh/id_rsa", "kind": "file", "in_scope": False}


def _audit(**over):
    base = dict(verdict="out_of_scope", touched=[_IN, _OUT], rationale="read a key file")
    return {**base, **over}


def test_transcript_audit_field_set():
    assert list(TranscriptAudit.model_fields) == ["verdict", "touched", "rationale"]


def test_transcript_enums_are_closed():
    assert {e.value for e in ScopeVerdict} == {"in_scope", "out_of_scope"}
    assert {e.value for e in ResourceKind} == {
        "file", "network", "process", "env", "data_store", "other",
    }


def test_valid_audits_construct():
    a = TranscriptAudit(**_audit())
    assert a.verdict is ScopeVerdict.out_of_scope and len(a.touched) == 2
    b = TranscriptAudit(verdict="in_scope", touched=[_IN], rationale="all within task")
    assert b.verdict is ScopeVerdict.in_scope
    c = TranscriptAudit(verdict="in_scope", touched=[], rationale="touched nothing")
    assert c.touched == []


def test_out_of_enum_resource_kind_is_rejected():
    with pytest.raises(ValidationError) as ei:
        TranscriptAudit(**_audit(touched=[{**_IN, "kind": "astral"}]))
    assert "kind" in str(ei.value)


@pytest.mark.parametrize("kwargs", [
    _audit(touched=[_IN]),                       # out_of_scope but everything in scope
    _audit(touched=[]),                          # out_of_scope with nothing touched
    _audit(verdict="in_scope"),                  # in_scope but an out-of-scope resource
])
def test_transcript_cross_field_rules_are_enforced(kwargs):
    with pytest.raises(ValidationError):
        TranscriptAudit(**kwargs)


def test_transcript_extra_field_is_forbidden():
    with pytest.raises(ValidationError):
        TranscriptAudit(**_audit(), confidence=0.9)
    with pytest.raises(ValidationError):
        TranscriptAudit(**_audit(touched=[{**_OUT, "note": "x"}]))


def test_transcript_str_is_readable_lines_not_object_dump():
    s = str(TranscriptAudit(**_audit()))
    assert "verdict:" in s and "rationale:" in s and "~/.ssh/id_rsa" in s
    assert "TranscriptAudit(" not in s


# --- InjectionClassification ---


def _attempt(**over):
    base = dict(verdict="injection_attempt", technique="instruction_override",
                severity="medium", intervention="warn", rationale="asks to ignore prior")
    return {**base, **over}


def _clean(**over):
    base = dict(verdict="clean", technique="none", severity="none",
                intervention="allow", rationale="ordinary question")
    return {**base, **over}


def test_injection_field_set():
    assert list(InjectionClassification.model_fields) == [
        "verdict", "technique", "severity", "intervention", "rationale",
    ]


def test_injection_enums_are_closed():
    assert {e.value for e in InjectionVerdict} == {"injection_attempt", "clean"}
    assert {e.value for e in InjectionTechnique} == {
        "instruction_override", "role_manipulation", "context_smuggling",
        "tool_misuse_lure", "encoding_obfuscation", "none",
    }


def test_valid_attempt_and_clean_construct():
    a = InjectionClassification(**_attempt())
    assert a.technique is InjectionTechnique.instruction_override
    c = InjectionClassification(**_clean())
    assert c.verdict is InjectionVerdict.clean


def test_injection_out_of_enum_is_rejected():
    with pytest.raises(ValidationError) as ei:
        InjectionClassification(**_attempt(technique="hypnosis"))
    assert "technique" in str(ei.value)


@pytest.mark.parametrize("kwargs, needle", [
    (_clean(technique="role_manipulation"), "technique"),   # clean must have none
    (_clean(severity="low"), "severity"),                    # clean must have none
    (_attempt(technique="none"), "technique"),               # attempt must be named
])
def test_injection_cross_field_rules_name_the_offending_field(kwargs, needle):
    with pytest.raises(ValidationError) as ei:
        InjectionClassification(**kwargs)
    assert needle in str(ei.value)


def test_injection_extra_field_is_forbidden():
    with pytest.raises(ValidationError):
        InjectionClassification(**_clean(), confidence=0.9)


def test_injection_str_is_readable_lines_not_object_dump():
    s = str(InjectionClassification(**_attempt()))
    assert "verdict:" in s and "technique:" in s and "rationale:" in s
    assert "InjectionClassification(" not in s
    assert len(s.splitlines()) == 5


# --- SensitiveDataFlag ---

_SECRET = {"category": "secret", "evidence": "sk-abc123", "destination": "pastebin.com"}
_PII = {"category": "pii", "evidence": "jane@example.com"}  # destination not visible


def _flagged(**over):
    base = dict(verdict="flagged", findings=[_SECRET, _PII], severity="high",
                rationale="key and email in reply body")
    return {**base, **over}


def _clean_flag(**over):
    base = dict(verdict="clean", findings=[], severity="none", rationale="nothing sensitive")
    return {**base, **over}


def test_sensitive_field_set():
    assert list(SensitiveDataFlag.model_fields) == [
        "verdict", "findings", "severity", "rationale",
    ]


def test_sensitive_enums_are_closed():
    assert {e.value for e in SensitiveVerdict} == {"flagged", "clean"}
    assert {e.value for e in SensitiveCategory} == {"secret", "pii", "internal_name"}


def test_valid_flagged_and_clean_construct():
    f = SensitiveDataFlag(**_flagged())
    assert f.verdict is SensitiveVerdict.flagged and len(f.findings) == 2
    assert f.findings[1].destination is None      # destination optional per finding
    c = SensitiveDataFlag(**_clean_flag())
    assert c.verdict is SensitiveVerdict.clean


def test_sensitive_out_of_enum_category_is_rejected():
    with pytest.raises(ValidationError) as ei:
        SensitiveDataFlag(**_flagged(findings=[{**_PII, "category": "gossip"}]))
    assert "category" in str(ei.value)


@pytest.mark.parametrize("kwargs", [
    _flagged(findings=[]),                        # flagged requires findings
    _clean_flag(findings=[_PII]),                 # clean forbids findings
    _clean_flag(severity="medium"),               # clean forbids severity
])
def test_sensitive_cross_field_rules_are_enforced(kwargs):
    with pytest.raises(ValidationError):
        SensitiveDataFlag(**kwargs)


def test_sensitive_extra_field_is_forbidden():
    with pytest.raises(ValidationError):
        SensitiveDataFlag(**_clean_flag(), confidence=0.9)
    with pytest.raises(ValidationError):
        SensitiveDataFlag(**_flagged(findings=[{**_SECRET, "hash": "x"}]))


def test_sensitive_str_is_readable_lines_not_object_dump():
    s = str(SensitiveDataFlag(**_flagged()))
    assert "verdict:" in s and "finding:" in s and "rationale:" in s
    assert "-> pastebin.com" in s                 # destination shown when present
    assert "SensitiveDataFlag(" not in s
