"""Evaluate an extractor against the gold-labeled requests.

    python -m eval.run_eval --extractor keyword
    python -m eval.run_eval --extractor claude        # needs ANTHROPIC_API_KEY

Metrics
  decision_accuracy       share of requests whose final decision matches the gold decision
  criterion_accuracy      share of individual criterion calls matching gold (MET / NOT_MET / NOT_DOCUMENTED)
  unsafe_approvals        APPROVE when gold says otherwise; the metric that matters most (target: 0)
  missed_approvals        gold APPROVE routed to review or info request (costs time, not safety)
  ungrounded_evidence     model claims whose quote was not found in the note (caught by the guardrail)
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from pa_engine import ClaudeExtractor, KeywordExtractor, PriorAuthEngine, load_policies, load_requests

OUT_DIR = Path(__file__).resolve().parent / "results"


def evaluate(extractor) -> dict:
    policies = load_policies()
    engine = PriorAuthEngine(policies, extractor)
    rows, crit_total, crit_correct, ungrounded = [], 0, 0, 0
    confusion = Counter()

    for req in load_requests():
        det = engine.review(req)
        gold = req.gold
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
    return {
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
    lines = [
        f"# Eval results: {res['extractor']}" + (f" ({res['model']})" if res["model"] else ""),
        "",
        "| Metric | Value |", "| --- | --- |",
        f"| Requests | {res['n_requests']} |",
        f"| Decision accuracy | {res['decision_accuracy']:.0%} |",
        f"| Criterion accuracy | {res['criterion_accuracy']:.0%} |",
        f"| Unsafe approvals (target 0) | {res['unsafe_approvals']} |",
        f"| Missed approvals | {res['missed_approvals']} |",
        f"| Ungrounded evidence caught | {res['ungrounded_evidence']} |",
        "", "| Request | Gold | Predicted | Criterion misses |", "| --- | --- | --- | --- |",
    ]
    for r in res["rows"]:
        mark = "" if r["correct"] else " **x**"
        lines.append(f"| {r['request_id']} | {r['gold']} | {r['pred']}{mark} | {'; '.join(r['criterion_misses']) or '-'} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extractor", choices=["keyword", "claude"], default="keyword")
    args = ap.parse_args()
    extractor = KeywordExtractor() if args.extractor == "keyword" else ClaudeExtractor()

    res = evaluate(extractor)
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / f"{res['extractor']}.json").write_text(json.dumps(res, indent=2))
    md = to_markdown(res)
    (OUT_DIR / f"{res['extractor']}.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
