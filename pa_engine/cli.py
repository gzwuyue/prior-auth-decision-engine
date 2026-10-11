"""Command line: review text requests or faxed/scanned PDFs.

    python -m pa_engine.cli PA-1001                         # text request, Claude extractor
    python -m pa_engine.cli --all --offline                 # all text requests, keyword baseline
    python -m pa_engine.cli --scan data/scans/PA-2002.pdf   # scanned fax: Claude reads it (vision) and reviews it
    python -m pa_engine.cli --scan data/scans/PA-2002.pdf --ocr tesseract --offline   # fully offline
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .data import load_policies, load_public_notes, load_requests
from .engine import PriorAuthEngine
from .extractors import ClaudeExtractor, KeywordExtractor

ICON = {"APPROVE": "[APPROVE]", "REQUEST_INFO": "[REQUEST INFO]", "PEND_CLINICAL_REVIEW": "[CLINICIAN REVIEW]"}


def print_determination(det, request, transcript=None) -> None:
    print(f"\n{det.request_id}  {det.policy_id}  ->  {ICON[det.decision.value]}")
    if transcript is not None:
        print(f"  Intake: {transcript.reader} read {Path(transcript.source_file).name} "
              f"(member {transcript.member_id or '?'}, code {transcript.cpt_code or '?'}, "
              f"{len(transcript.clinical_note)} chars of notes)")
        if transcript.routing_note:
            print(f"  Routing: {transcript.routing_note}")
    print(f"  Provider: {request.provider}  |  Extractor: {det.extractor}" + (f" ({det.model})" if det.model else ""))
    for r in det.reasons:
        print(f"  Reason: {r}")
    for a in det.assessments:
        quote = f' "{a.evidence_quote}"' if a.evidence_quote else ""
        print(f"    - {a.criterion_id:<22} {a.status.value:<15}{quote}")


def make_reader(kind: str):
    from .intake import ClaudeDocumentReader, TesseractReader

    return TesseractReader() if kind == "tesseract" else ClaudeDocumentReader()


def main() -> None:
    ap = argparse.ArgumentParser(description="Prior-authorization decision engine demo")
    ap.add_argument("request_ids", nargs="*", help="Request IDs to review, e.g. PA-1001 or MTS-2085")
    ap.add_argument("--all", action="store_true", help="Review every request in data/requests.jsonl")
    ap.add_argument("--scan", nargs="+", type=Path, metavar="PDF", help="Faxed/scanned PDF(s) to read and review")
    ap.add_argument("--ocr", choices=["claude", "tesseract"], default="claude",
                    help="How to read scans: Claude vision (default) or offline Tesseract OCR")
    ap.add_argument("--offline", action="store_true", help="Use the keyword baseline instead of Claude for extraction")
    ap.add_argument("--audit-dir", type=Path, default=Path("audit"), help="Where to write JSON audit records")
    args = ap.parse_args()

    policies = load_policies()
    extractor = KeywordExtractor() if args.offline else ClaudeExtractor()
    engine = PriorAuthEngine(policies, extractor, audit_dir=args.audit_dir)

    if args.scan:
        reader = make_reader(args.ocr)
        from .intake import ManualIntakeRequired

        for pdf in args.scan:
            try:
                transcript, request, det = engine.review_scan(pdf, reader)
            except ManualIntakeRequired as e:
                print(f"\n{Path(pdf).stem}  ->  [MANUAL INTAKE]\n  Reason: {e}")
                continue
            print_determination(det, request, transcript)
    else:
        requests = {r.request_id: r for r in load_requests() + load_public_notes()}
        ids = [r for r in requests if r.startswith("PA-")] if args.all or not args.request_ids else args.request_ids
        for rid in ids:
            print_determination(engine.review(requests[rid]), requests[rid])
    print(f"\nAudit records written to {args.audit_dir}/")


if __name__ == "__main__":
    main()
