"""The classification schema — designed first, because the schema *is* the product spec.

Every verdict the detector produces (mock now, litellm later) is a
:class:`RiskClassification`. The enums are closed and the cross-field invariants live
here, in one place, so no producer can drift: a benign verdict can't smuggle in a risk
type, and a risky verdict can't leave the risk type unnamed. Malformed output raises a
pydantic ``ValidationError`` rather than being silently accepted or coerced.

One result type per detector, not a union: :class:`RiskClassification` for a single agent
action, :class:`TranscriptAudit` for a tool-call transcript, :class:`InjectionClassification`
for a prompt/input, :class:`SensitiveDataFlag` for a model output. The shapes are genuinely
different (a scalar verdict, a resource inventory, a findings list), and each entry point
knows its return type statically — a discriminator would widen every schema for zero callers.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator


class Verdict(str, Enum):
    """Is the action risky at all? The binary spine of every classification."""

    risky = "risky"
    benign = "benign"


class RiskType(str, Enum):
    """*Which* kind of risk. `none` is an explicit member (not a null) so a benign
    verdict is still a closed, printable, tallyable value."""

    exfiltration_attempt = "exfiltration_attempt"
    injection_symptom = "injection_symptom"
    out_of_scope_access = "out_of_scope_access"
    destructive_action = "destructive_action"
    secret_exposure = "secret_exposure"
    none = "none"


class Severity(str, Enum):
    """How bad, if it is bad. `none` pairs with a benign verdict."""

    none = "none"
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class Intervention(str, Enum):
    """What the operator would want done about it."""

    allow = "allow"
    warn = "warn"
    block = "block"
    confirm = "confirm"


class RiskClassification(BaseModel):
    """A schema-validated risk verdict for a single agent action.

    Field membership is enforced by the enum types; the cross-field rules are enforced
    by :meth:`_check_cross_field` below. ``extra="forbid"`` rejects any unexpected field,
    so a chatty or malformed producer fails loud instead of quietly widening the record.
    """

    model_config = ConfigDict(extra="forbid")

    verdict: Verdict
    risk_type: RiskType
    severity: Severity
    intervention: Intervention
    rationale: str

    @model_validator(mode="after")
    def _check_cross_field(self) -> "RiskClassification":
        # benign ⇒ risk_type=none AND severity=none. A "safe" verdict that names a risk
        # type or a nonzero severity is internally contradictory — reject it, naming the
        # offending field so the failure points at what to fix.
        if self.verdict is Verdict.benign:
            if self.risk_type is not RiskType.none:
                raise ValueError(
                    f"benign verdict must have risk_type=none, got risk_type={self.risk_type.value!r}"
                )
            if self.severity is not Severity.none:
                raise ValueError(
                    f"benign verdict must have severity=none, got severity={self.severity.value!r}"
                )
        # risky ⇒ a *named* risk_type (not none). A risky verdict with no named type is
        # the same silent drift in the other direction.
        else:  # Verdict.risky
            if self.risk_type is RiskType.none:
                raise ValueError("risky verdict must name a risk_type, got risk_type='none'")
        return self

    def __str__(self) -> str:
        """Human-readable lines, not a raw object dump. This is the plain-text renderer
        used whenever `rich` is absent or color is off."""
        return (
            f"verdict:      {self.verdict.value}\n"
            f"risk_type:    {self.risk_type.value}\n"
            f"severity:     {self.severity.value}\n"
            f"intervention: {self.intervention.value}\n"
            f"rationale:    {self.rationale}"
        )


# --- transcript audit -----------------------------------------------------------------


class ScopeVerdict(str, Enum):
    """Did the transcript stay inside the stated task? The binary spine of an audit."""

    in_scope = "in_scope"
    out_of_scope = "out_of_scope"


class ResourceKind(str, Enum):
    """What sort of thing a tool call touched. Closed so inventories stay tallyable."""

    file = "file"
    network = "network"
    process = "process"
    env = "env"
    data_store = "data_store"
    other = "other"


class TouchedResource(BaseModel):
    """One resource a transcript touched: what it was, what kind, and whether touching
    it was inside the stated task's scope."""

    model_config = ConfigDict(extra="forbid")

    resource: str
    kind: ResourceKind
    in_scope: bool


class TranscriptAudit(BaseModel):
    """A schema-validated audit of one tool-call transcript: everything the agent
    touched, each scope-judged, plus an overall verdict that must agree with the
    per-resource judgments (enforced below, both directions)."""

    model_config = ConfigDict(extra="forbid")

    verdict: ScopeVerdict
    touched: list[TouchedResource]
    rationale: str

    @model_validator(mode="after")
    def _check_cross_field(self) -> "TranscriptAudit":
        # out_of_scope ⇔ at least one touched resource is out of scope. Either direction
        # of disagreement is internally contradictory — reject, naming what to fix.
        any_out = any(not t.in_scope for t in self.touched)
        if self.verdict is ScopeVerdict.out_of_scope and not any_out:
            raise ValueError(
                "out_of_scope verdict requires at least one touched resource with in_scope=false"
            )
        if self.verdict is ScopeVerdict.in_scope and any_out:
            raise ValueError(
                "in_scope verdict forbids touched resources with in_scope=false"
            )
        return self

    def __str__(self) -> str:
        lines = [f"verdict:      {self.verdict.value}"]
        for t in self.touched:
            mark = "in" if t.in_scope else "OUT"
            lines.append(f"touched:      [{mark}] {t.kind.value}: {t.resource}")
        lines.append(f"rationale:    {self.rationale}")
        return "\n".join(lines)


# --- injection detection --------------------------------------------------------------


class InjectionVerdict(str, Enum):
    """Is the input trying to steer the model off its instructions?"""

    injection_attempt = "injection_attempt"
    clean = "clean"


class InjectionTechnique(str, Enum):
    """*How* the attempt works. `none` pairs with a clean verdict."""

    instruction_override = "instruction_override"
    role_manipulation = "role_manipulation"
    context_smuggling = "context_smuggling"
    tool_misuse_lure = "tool_misuse_lure"
    encoding_obfuscation = "encoding_obfuscation"
    none = "none"


class InjectionClassification(BaseModel):
    """A schema-validated injection verdict for one prompt/input. Mirrors
    :class:`RiskClassification`'s invariant shape: a clean verdict can't smuggle in a
    technique or severity, and an attempt must name its technique."""

    model_config = ConfigDict(extra="forbid")

    verdict: InjectionVerdict
    technique: InjectionTechnique
    severity: Severity
    intervention: Intervention
    rationale: str

    @model_validator(mode="after")
    def _check_cross_field(self) -> "InjectionClassification":
        if self.verdict is InjectionVerdict.clean:
            if self.technique is not InjectionTechnique.none:
                raise ValueError(
                    f"clean verdict must have technique=none, got technique={self.technique.value!r}"
                )
            if self.severity is not Severity.none:
                raise ValueError(
                    f"clean verdict must have severity=none, got severity={self.severity.value!r}"
                )
        else:  # InjectionVerdict.injection_attempt
            if self.technique is InjectionTechnique.none:
                raise ValueError(
                    "injection_attempt verdict must name a technique, got technique='none'"
                )
        return self

    def __str__(self) -> str:
        return (
            f"verdict:      {self.verdict.value}\n"
            f"technique:    {self.technique.value}\n"
            f"severity:     {self.severity.value}\n"
            f"intervention: {self.intervention.value}\n"
            f"rationale:    {self.rationale}"
        )


# --- sensitive-data flag --------------------------------------------------------------


class SensitiveVerdict(str, Enum):
    """Does the output carry sensitive data?"""

    flagged = "flagged"
    clean = "clean"


class SensitiveCategory(str, Enum):
    """What kind of sensitive data a finding is."""

    secret = "secret"
    pii = "pii"
    internal_name = "internal_name"


class SensitiveFinding(BaseModel):
    """One piece of sensitive data found in an output: what category, the offending
    excerpt, and — when the output makes it visible — where the data was headed."""

    model_config = ConfigDict(extra="forbid")

    category: SensitiveCategory
    evidence: str
    destination: str | None = None


class SensitiveDataFlag(BaseModel):
    """A schema-validated sensitive-data flag for one model output. The verdict must
    agree with the findings list (flagged ⇔ non-empty), and a clean output carries no
    severity — enforced below."""

    model_config = ConfigDict(extra="forbid")

    verdict: SensitiveVerdict
    findings: list[SensitiveFinding]
    severity: Severity
    rationale: str

    @model_validator(mode="after")
    def _check_cross_field(self) -> "SensitiveDataFlag":
        if self.verdict is SensitiveVerdict.flagged and not self.findings:
            raise ValueError("flagged verdict requires a non-empty findings list")
        if self.verdict is SensitiveVerdict.clean:
            if self.findings:
                raise ValueError("clean verdict forbids findings, got a non-empty findings list")
            if self.severity is not Severity.none:
                raise ValueError(
                    f"clean verdict must have severity=none, got severity={self.severity.value!r}"
                )
        return self

    def __str__(self) -> str:
        lines = [f"verdict:      {self.verdict.value}"]
        for f in self.findings:
            dest = f" -> {f.destination}" if f.destination else ""
            lines.append(f"finding:      {f.category.value}: {f.evidence}{dest}")
        lines.append(f"severity:     {self.severity.value}")
        lines.append(f"rationale:    {self.rationale}")
        return "\n".join(lines)
