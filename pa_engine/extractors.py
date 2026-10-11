"""Evidence extractors: read a clinical note and assess each policy criterion.

Two implementations share one interface:
  * ClaudeExtractor - Claude reads the note and returns schema-validated JSON (structured outputs).
  * KeywordExtractor - a regex baseline that runs offline, for comparison in the evals.
"""
from __future__ import annotations

import json
import os
import re
from typing import Protocol

from .models import Assessment, Criterion, PARequest, Policy, Status

DEFAULT_MODEL = os.environ.get("PA_MODEL", "claude-sonnet-5-5")


class Extractor(Protocol):
    name: str

    def assess(self, request: PARequest, policy: Policy) -> list[Assessment]: ...


# --------------------------------------------------------------------------- Claude

SYSTEM_PROMPT = """You are a utilization-management nurse reviewer assisting with prior-authorization requests.
For each coverage criterion, decide from the clinical note alone whether it is:
  - MET: the note clearly documents that the criterion is satisfied
  - NOT_MET: the note clearly documents that the criterion is NOT satisfied
  - NOT_DOCUMENTED: the note does not say enough to decide either way
Rules:
  - Use only facts written in the note. Never assume or infer facts that are not stated.
  - evidence_quote must be copied verbatim from the note (a short phrase or sentence). Use "" when NOT_DOCUMENTED.
  - Pay close attention to negation, timing (duration), and family history.
  - Keep each rationale to one sentence."""

# Structured outputs: Claude's reply is guaranteed to be JSON matching this schema.
ASSESSMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "assessments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criterion_id": {"type": "string"},
                    "status": {"type": "string", "enum": [s.value for s in Status]},
                    "evidence_quote": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["criterion_id", "status", "evidence_quote", "rationale"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["assessments"],
    "additionalProperties": False,
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def ground(assessment: Assessment, note: str) -> Assessment:
    """Guardrail: a MET/NOT_MET call must cite text that actually appears in the note.

    If the quote is missing or invented, downgrade to NOT_DOCUMENTED so the case routes to
    a human or an information request instead of an automated approval.
    """
    if assessment.status == Status.NOT_DOCUMENTED:
        return assessment
    quote = _normalize(assessment.evidence_quote)
    if not quote or quote not in _normalize(note):
        assessment.grounded = False
        assessment.rationale = f"[ungrounded evidence, downgraded] {assessment.rationale}"
        assessment.status = Status.NOT_DOCUMENTED
    return assessment


class ClaudeExtractor:
    name = "claude"

    def __init__(self, client=None, model: str = DEFAULT_MODEL):
        if client is None:
            import anthropic  # imported lazily so the offline baseline needs no SDK

            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise SystemExit(
                    "ANTHROPIC_API_KEY is not set.\n"
                    "  PowerShell:      $env:ANTHROPIC_API_KEY = \"sk-ant-...\"\n"
                    "  Command Prompt:  set ANTHROPIC_API_KEY=sk-ant-...\n"
                    "  macOS / Linux:   export ANTHROPIC_API_KEY=sk-ant-...\n"
                    "Or run with --offline to use the keyword baseline."
                )
            client = anthropic.Anthropic()
        self.client = client
        self.model = model

    def _prompt(self, request: PARequest, policy: Policy) -> str:
        criteria = "\n".join(f"- {c.id}: {c.text}" for c in policy.all_criteria)
        return (
            f"Service requested: {policy.service}\n\n"
            f"Coverage criteria:\n{criteria}\n\n"
            f"<clinical_note>\n{request.clinical_note}\n</clinical_note>\n\n"
            "Assess every criterion listed above."
        )

    def _call(self, **kwargs):
        try:
            return self.client.messages.create(**kwargs)
        except Exception as e:  # turn SDK errors into a clear, actionable message
            name = type(e).__name__
            hints = {
                "AuthenticationError": "Your API key was rejected. Check ANTHROPIC_API_KEY (no quotes or spaces inside).",
                "PermissionDeniedError": "Your key lacks access to this model or workspace.",
                "NotFoundError": f"Model '{self.model}' was not found. Set PA_MODEL to a model your account can use.",
                "RateLimitError": "Rate limited. Wait a minute and retry.",
                "BadRequestError": "Bad request. If the message mentions credit balance, add credits in the Claude Console (Plans & Billing).",
                "APIConnectionError": "Could not reach the API. Check your network, proxy, or VPN.",
            }
            if name in hints:
                raise SystemExit(f"{name}: {hints[name]}\nDetails: {e}") from e
            raise

    def assess(self, request: PARequest, policy: Policy) -> list[Assessment]:
        response = self._call(
            model=self.model,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": self._prompt(request, policy)}],
            output_config={"format": {"type": "json_schema", "schema": ASSESSMENT_SCHEMA}},
        )
        if getattr(response, "stop_reason", None) in ("refusal", "max_tokens"):
            raise RuntimeError(f"{request.request_id}: model stopped early ({response.stop_reason}).")
        text = next(b.text for b in response.content if getattr(b, "type", None) == "text")
        result = json.loads(text)
        by_id = {a["criterion_id"]: a for a in result.get("assessments", [])}

        results = []
        for c in policy.all_criteria:  # every criterion gets an answer, even if the model skipped one
            a = by_id.get(c.id)
            if a is None:
                results.append(Assessment(c.id, Status.NOT_DOCUMENTED, "", "Model returned no assessment."))
                continue
            results.append(ground(Assessment(c.id, Status(a["status"]), a.get("evidence_quote", ""),
                                             a.get("rationale", "")), request.clinical_note))
        return results


# --------------------------------------------------------------------------- Keyword baseline

class KeywordExtractor:
    """Naive baseline: regex patterns per criterion. Fast and transparent, but blind to negation and nuance."""

    name = "keyword-baseline"
    model = None

    @staticmethod
    def _match(patterns: list[str], note: str) -> str | None:
        for p in patterns:
            m = re.search(p, note, flags=re.IGNORECASE)
            if m:
                return m.group(0)
        return None

    def _assess_one(self, c: Criterion, note: str) -> Assessment:
        pats = c.baseline_patterns or {}
        hit = self._match(pats.get("not_met", []), note)
        if hit:
            return Assessment(c.id, Status.NOT_MET, hit, "Matched a not-met pattern.")
        hit = self._match(pats.get("met", []), note)
        if hit:
            return Assessment(c.id, Status.MET, hit, "Matched a met pattern.")
        return Assessment(c.id, Status.NOT_DOCUMENTED, "", "No pattern matched.")

    def assess(self, request: PARequest, policy: Policy) -> list[Assessment]:
        return [self._assess_one(c, request.clinical_note) for c in policy.all_criteria]
