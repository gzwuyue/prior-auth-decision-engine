"""Evaluate an extractor against the gold-labeled requests.

    python -m eval.run_eval --extractor keyword
    python -m eval.run_eval --extractor claude        # needs ANTHROPIC_API_KEY
    python -m eval.run_eval --extractor claude --from-scan --ocr claude      # faxed PDFs, read by Claude
    python -m eval.run_eval --extractor keyword --from-scan --ocr tesseract  # faxed PDFs, fully offline

Metrics
  decision_accuracy       share of requests whose final decision matches the gold decision
  criterion_accuracy      share of individual criterion calls matching gold (MET / NOT_MET / NOT_DOCUMENTED)
  unsafe_approvals        APPROVE when gold says otherwise; the metric that matters most (target: 0)
  missed_approvals        gold APPROVE routed to review or info request (costs time, not safety)
  ungrounded_evidence     model claims whose quote was not found in the note (caught by the guardrail)
  (scan mode) transcription_similarity  how closely the OCR text matches the original note (0-1)
  (scan mode) routing_accuracy          share of scans routed to the right policy from the OCR'd code
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

from pa_engine import ClaudeExtractor, KeywordExtractor, PriorAuthEngine, load_policies, load_requests
from pa_engine.data import DATA_DIR
from pa_engine.intake import ManualIntakeRequired

OUT_DIR = Path(__file__).resolve().parent / "results"


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip().lower()


def evaluate(extractor, reader=None) -> dict:
    policies = load_policies()
    engine = PriorAuthEngine(policies, extractor)
    rows, crit_total, crit_correct, ungrounded = [], 0, 0, 0
    confusion = Counter()
    sims, routed_ok = [], 0

    for req in load_requests():
        gold = req.gold
        if reader is not None:
            try:
                transcript, scanned, det = engine.review_scan(DATA_DIR / "scans" / f"{req.request_id}.pdf", reader)
            except ManualIntakeRequired as e:
                rows.append({"request_id": req.request_id, "gold": gold["decision"], "pred": "MANUAL_INTAKE",
                             "correct": False, "criterion_misses": [str(e)]})
                confusion[(gold["decision"], "MANUAL_INTAKE")] += 1
                sims.append(0.0)
                continue
            sims.append(SequenceMatcher(None, _norm(transcript.clinical_note), _norm(req.clinical_note)).ratio())
            routed_ok += scanned.policy_id == req.policy_id
        else:
            det = engine.review(req)
        pred = det.decision.value
        confusion[(gold["decision"], pred)] += 1
        misses = []
        for a in det.assessments:
            g = gold["criteria"].get(a.criterion_id)
            if g is None:
                continue
            crit_total += 1
            if a.status.value == g:
                crit_correct += 1
            else:
                misses.append(f"{a.criterion_id}: {a.status.value} (gold {g})")
            ungrounded += 0 if a.grounded else 1
        rows.append({"request_id": req.request_id, "gold": gold["decision"], "pred": pred,
                     "correct": pred == gold["decision"], "criterion_misses": misses})

    n = len(rows)
    scan = {}
    if reader is not None:
        scan = {"ocr": reader.name, "transcription_similarity": round(sum(sims) / len(sims), 3),
                "routing_accuracy": round(routed_ok / n, 3)}
    return scan | {
        "extractor": extractor.name,
        "model": getattr(extractor, "model", None),
        "n_requests": n,
        "decision_accuracy": round(sum(r["correct"] for r in rows) / n, 3),
        "criterion_accuracy": round(crit_correct / crit_total, 3),
        "unsafe_approvals": sum(1 for r in rows if r["pred"] == "APPROVE" and r["gold"] != "APPROVE"),
        "missed_approvals": sum(1 for r in rows if r["gold"] == "APPROVE" and r["pred"] != "APPROVE"),
        "ungrounded_evidence": ungrounded,
        "confusion": {f"{g} -> {p}": c for (g, p), c in sorted(confusion.items())},
        "rows": rows,
    }


def to_markdown(res: dict) -> str:
    title = f"# Eval results: {res['extractor']}" + (f" ({res['model']})" if res["model"] else "")
    if "ocr" in res:
        title += f", from scanned faxes via {res['ocr']}"
    lines = [
        title, "",
        "| Metric | Value |", "| --- | --- |",
        f"| Requests | {res['n_requests']} |",
        f"| Decision accuracy | {res['decision_accuracy']:.0%} |",
        f"| Criterion accuracy | {res['criterion_accuracy']:.0%} |",
        f"| Unsafe approvals (target 0) | {res['unsafe_approvals']} |",
        f"| Missed approvals | {res['missed_approvals']} |",
        f"| Ungrounded evidence caught | {res['ungrounded_evidence']} |",
        *([f"| OCR transcription similarity | {res['transcription_similarity']:.1%} |",
           f"| Policy routing accuracy | {res['routing_accuracy']:.0%} |"] if "ocr" in res else []),
        "", "| Request | Gold | Predicted | Criterion misses |", "| --- | --- | --- | --- |",
    ]
    for r in res["rows"]:
        mark = "" if r["correct"] else " **x**"
        lines.append(f"| {r['request_id']} | {r['gold']} | {r['pred']}{mark} | {'; '.join(r['criterion_misses']) or '-'} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extractor", choices=["keyword", "claude"], default="keyword")
    ap.add_argument("--from-scan", action="store_true", help="Read the faxed PDFs in data/scans instead of the text notes")
    ap.add_argument("--ocr", choices=["claude", "tesseract"], default="claude")
    args = ap.parse_args()
    extractor = KeywordExtractor() if args.extractor == "keyword" else ClaudeExtractor()
    reader = None
    if args.from_scan:
        from pa_engine.cli import make_reader
        reader = make_reader(args.ocr)

    res = evaluate(extractor, reader)
    OUT_DIR.mkdir(exist_ok=True)
    stem = res["extractor"] + (f"__scan-{res['ocr']}" if reader else "")
    (OUT_DIR / f"{stem}.json").write_text(json.dumps(res, indent=2))
    md = to_markdown(res)
    (OUT_DIR / f"{stem}.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
