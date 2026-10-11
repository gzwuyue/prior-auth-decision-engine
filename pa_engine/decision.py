"""Deterministic decision rules.

The LLM only extracts evidence. The coverage decision itself is plain, auditable code, so the
same evidence always produces the same outcome and every outcome can be explained.

Rules:
  1. Any override criterion MET                    -> APPROVE
  2. All required criteria MET                     -> APPROVE
  3. Any required criterion NOT_MET                -> PEND_CLINICAL_REVIEW (a clinician decides; no auto-denial)
  4. Otherwise (something is NOT_DOCUMENTED)       -> REQUEST_INFO from the provider
"""
from __future__ import annotations

from .models import Assessment, Decision, Policy, Status


def decide(policy: Policy, assessments: list[Assessment]) -> tuple[Decision, list[str]]:
    status = {a.criterion_id: a.status for a in assessments}

    met_overrides = [c.id for c in policy.override_any if status.get(c.id) == Status.MET]
    if met_overrides:
        return Decision.APPROVE, [f"Override criterion met: {', '.join(met_overrides)}"]

    required = [c.id for c in policy.required]
    not_met = [cid for cid in required if status.get(cid) == Status.NOT_MET]
    missing = [cid for cid in required if status.get(cid, Status.NOT_DOCUMENTED) == Status.NOT_DOCUMENTED]

    if not not_met and not missing:
        return Decision.APPROVE, ["All required criteria met"]
    if not_met:
        reasons = [f"Required criterion not met: {', '.join(not_met)}"]
        if missing:
            reasons.append(f"Also not documented: {', '.join(missing)}")
        return Decision.PEND_CLINICAL_REVIEW, reasons
    return Decision.REQUEST_INFO, [f"Missing documentation for: {', '.join(missing)}"]
