"""Unit tests. No API key needed: the Claude client is mocked."""
import json
from types import SimpleNamespace

from pa_engine import ClaudeExtractor, KeywordExtractor, PriorAuthEngine, decide, load_policies, load_requests
from pa_engine.models import Assessment, Decision, Status

POLICIES = load_policies()
REQUESTS = {r.request_id: r for r in load_requests()}


def _a(cid, status):
    return Assessment(cid, Status(status))


# ---------------------------------------------------------------- decision rules

def test_all_required_met_approves():
    p = POLICIES["GLP1-WM-01"]
    d, _ = decide(p, [_a("BMI_THRESHOLD", "MET"), _a("LIFESTYLE_PROGRAM", "MET"), _a("NO_MTC_MEN2", "MET")])
    assert d == Decision.APPROVE


def test_override_approves_even_if_required_not_met():
    p = POLICIES["MRI-LSPINE-01"]
    d, reasons = decide(p, [_a("LBP_DURATION", "NOT_MET"), _a("CONSERVATIVE_TX", "NOT_MET"), _a("RED_FLAGS", "MET")])
    assert d == Decision.APPROVE and "RED_FLAGS" in reasons[0]


def test_not_met_goes_to_clinician_never_denies():
    p = POLICIES["TKA-01"]
    d, _ = decide(p, [_a("RADIOGRAPHIC_OA", "NOT_MET"), _a("FAILED_CONSERVATIVE", "MET"),
                      _a("FUNCTIONAL_LIMITATION", "MET"), _a("BMI_UNDER_40", "MET")])
    assert d == Decision.PEND_CLINICAL_REVIEW
    assert "DENY" not in [x.value for x in Decision]


def test_missing_documentation_requests_info():
    p = POLICIES["GLP1-WM-01"]
    d, _ = decide(p, [_a("BMI_THRESHOLD", "MET"), _a("LIFESTYLE_PROGRAM", "NOT_DOCUMENTED"), _a("NO_MTC_MEN2", "MET")])
    assert d == Decision.REQUEST_INFO


# ---------------------------------------------------------------- Claude extractor (mocked)

class FakeClient:
    """Mimics anthropic.Anthropic().messages.create returning structured JSON in a text block."""

    def __init__(self, assessments):
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)
        self._assessments = assessments

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        block = SimpleNamespace(type="text", text=json.dumps({"assessments": self._assessments}))
        return SimpleNamespace(content=[block], stop_reason="end_turn")


def test_claude_extractor_parses_structured_output():
    req = REQUESTS["PA-2001"]
    client = FakeClient([
        {"criterion_id": "BMI_THRESHOLD", "status": "MET", "evidence_quote": "BMI 34.2", "rationale": "BMI over 30."},
        {"criterion_id": "LIFESTYLE_PROGRAM", "status": "MET",
         "evidence_quote": "structured weight management program", "rationale": "8 months."},
        {"criterion_id": "NO_MTC_MEN2", "status": "MET",
         "evidence_quote": "No personal or family history of medullary thyroid carcinoma or MEN2",
         "rationale": "Explicitly negative."},
    ])
    det = PriorAuthEngine(POLICIES, ClaudeExtractor(client=client, model="test-model")).review(req)
    assert det.decision == Decision.APPROVE
    call = client.calls[0]
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert "<clinical_note>" in call["messages"][0]["content"]


def test_ungrounded_quote_is_downgraded_and_blocks_auto_approval():
    req = REQUESTS["PA-2004"]  # note never mentions a lifestyle program or thyroid history
    client = FakeClient([
        {"criterion_id": "BMI_THRESHOLD", "status": "MET", "evidence_quote": "BMI 31.5", "rationale": "Over 30."},
        {"criterion_id": "LIFESTYLE_PROGRAM", "status": "MET",
         "evidence_quote": "completed a 6-month lifestyle program", "rationale": "Hallucinated."},
        {"criterion_id": "NO_MTC_MEN2", "status": "MET", "evidence_quote": "no thyroid history", "rationale": "Hallucinated."},
    ])
    det = PriorAuthEngine(POLICIES, ClaudeExtractor(client=client, model="test-model")).review(req)
    assert det.decision == Decision.REQUEST_INFO
    assert sum(not a.grounded for a in det.assessments) == 2


def test_missing_criterion_from_model_defaults_to_not_documented():
    req = REQUESTS["PA-3001"]
    client = FakeClient([{"criterion_id": "RADIOGRAPHIC_OA", "status": "MET",
                          "evidence_quote": "Kellgren-Lawrence grade 4", "rationale": "KL4."}])
    det = PriorAuthEngine(POLICIES, ClaudeExtractor(client=client, model="test-model")).review(req)
    assert det.decision == Decision.REQUEST_INFO


# ---------------------------------------------------------------- baseline smoke test

def test_keyword_baseline_runs_on_all_requests():
    engine = PriorAuthEngine(POLICIES, KeywordExtractor())
    for req in REQUESTS.values():
        assert engine.review(req).decision in set(Decision)
