"""The detectors: one model-powered verb per subject type.

``classify(action, model)`` takes an agent action; ``audit_transcript(transcript, model)``
a tool-call transcript (with the stated task); ``detect_injection(prompt, model)`` a
prompt/input; ``flag_output(output, model)`` a model output. Each takes a string or a
small structured value, routes it through the chosen provider, and returns its own
validated schema type. The return value has *always* passed schema validation before the
caller sees it: the provider produces raw fields, and constructing the model is what
enforces the enums and cross-field invariants (a bad producer raises ``ValidationError``
here rather than leaking upward).
"""

import json

from .providers import complete
from .schema import (
    InjectionClassification,
    RiskClassification,
    SensitiveDataFlag,
    TranscriptAudit,
)


def _action_text(action) -> str:
    """Normalize an input to the text the provider reasons over. A string passes
    through; a dict or list is rendered to compact JSON so keys and values are both
    visible to the keyword mocks (and to a real model)."""
    if isinstance(action, str):
        return action
    return json.dumps(action, sort_keys=True, default=str)


def classify(action, model: str = "mock") -> RiskClassification:
    """Classify one agent action, returning a schema-validated verdict.

    ``model="mock"`` runs offline and deterministically; any other id routes through the
    litellm path. Raises ``pydantic.ValidationError`` if the provider's output violates
    the schema — the validation is the contract, not an afterthought.
    """
    fields = complete(_action_text(action), model=model)
    return RiskClassification(**fields)


def audit_transcript(transcript, model: str = "mock") -> TranscriptAudit:
    """Audit one tool-call transcript (calls + the stated task), returning a
    schema-validated inventory of what was touched and an in/out-of-scope verdict.
    Same provider routing and validation contract as :func:`classify`."""
    fields = complete(_action_text(transcript), model=model, detector="transcript")
    return TranscriptAudit(**fields)


def detect_injection(prompt, model: str = "mock") -> InjectionClassification:
    """Classify one prompt/input as an injection attempt or clean, returning a
    schema-validated verdict naming the technique and an intervention.
    Same provider routing and validation contract as :func:`classify`."""
    fields = complete(_action_text(prompt), model=model, detector="prompt")
    return InjectionClassification(**fields)


def flag_output(output, model: str = "mock") -> SensitiveDataFlag:
    """Flag sensitive data in one model output, returning a schema-validated findings
    list (secrets, PII, internal names — with destination when visible).
    Same provider routing and validation contract as :func:`classify`."""
    fields = complete(_action_text(output), model=model, detector="output")
    return SensitiveDataFlag(**fields)
