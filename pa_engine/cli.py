"""Command line: review one request or all of them.

    python -m pa_engine.cli PA-1001            # Claude (needs ANTHROPIC_API_KEY)
    python -m pa_engine.cli --all --offline    # keyword baseline, no API key needed
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .data import load_policies, load_requests
from .engine import PriorAuthEngine
from .extractors import ClaudeExtractor, KeywordExtractor

ICON = {"APPROVE": "[APPROVE]", "REQUEST_INFO": "[REQUEST INFO]", "PEND_CLINICAL_REVIEW": "[CLINICIAN REVIEW]"}


def print_determination(det, request) -> None:
    print(f"\n{det.request_id}  {det.policy_id}  ->  {ICON[det.decision.value]}")
    print(f"  Provider: {request.provider}  |  Extractor: {det.extractor}" + (f" ({det.model})" if det.model else ""))
    for r in det.reasons:
        print(f"  Reason: {r}")
    for a in det.assessments:
        quote = f' "{a.evidence_quote}"' if a.evidence_quote else ""
        print(f"    - {a.criterion_id:<22} {a.status.value:<15}{quote}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Prior-authorization decision engine demo")
    ap.add_argument("request_ids", nargs="*", help="Request IDs to review, e.g. PA-1001")
    ap.add_argument("--all", action="store_true", help="Review every request in data/requests.jsonl")
    ap.add_argument("--offline", action="store_true", help="Use the keyword baseline instead of Claude")
    ap.add_argument("--audit-dir", type=Path, default=Path("audit"), help="Where to write JSON audit records")
    args = ap.parse_args()

    policies = load_policies()
    requests = {r.request_id: r for r in load_requests()}
    ids = list(requests) if args.all or not args.request_ids else args.request_ids

    extractor = KeywordExtractor() if args.offline else ClaudeExtractor()
    engine = PriorAuthEngine(policies, extractor, audit_dir=args.audit_dir)
    for rid in ids:
        print_determination(engine.review(requests[rid]), requests[rid])
    print(f"\nAudit records written to {args.audit_dir}/")


if __name__ == "__main__":
    main()
