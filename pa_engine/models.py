"""Core data types for the prior-authorization decision engine."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum


class Status(str, Enum):
    MET = "MET"
    NOT_MET = "NOT_MET"
    NOT_DOCUMENTED = "NOT_DOCUMENTED"


class Decision(str, Enum):
    APPROVE = "APPROVE"
    REQUEST_INFO = "REQUEST_INFO"
    # The engine never denies. Anything that looks like a denial goes to a licensed clinician.
    PEND_CLINICAL_REVIEW = "PEND_CLINICAL_REVIEW"


@dataclass
class Criterion:
    id: str
    text: str
    baseline_patterns: dict = field(default_factory=dict)


@dataclass
class Policy:
    policy_id: str
    service: str
    required: list[Criterion]
    override_any: list[Criterion] = field(default_factory=list)
    logic: str = ""
    cpt_codes: list[str] = field(default_factory=list)

    @property
    def all_criteria(self) -> list[Criterion]:
        return self.required + self.override_any


@dataclass
class PARequest:
    request_id: str
    policy_id: str
    member_id: str
    provider: str
    clinical_note: str
    gold: dict | None = None
    source: dict | None = None


@dataclass
class Assessment:
    criterion_id: str
    status: Status
    evidence_quote: str = ""
    rationale: str = ""
    grounded: bool = True  # False if the quoted evidence was not found in the note


@dataclass
class Determination:
    request_id: str
    policy_id: str
    decision: Decision
    reasons: list[str]
    assessments: list[Assessment]
    extractor: str
    model: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["decision"] = self.decision.value
        for a in d["assessments"]:
            a["status"] = a["status"].value if hasattr(a["status"], "value") else a["status"]
        return d
