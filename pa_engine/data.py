"""Loading policies and requests from the data/ folder."""
from __future__ import annotations

import json
from pathlib import Path

from .models import Criterion, PARequest, Policy

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_policies(path: Path | None = None) -> dict[str, Policy]:
    raw = json.loads((path or DATA_DIR / "policies.json").read_text())
    policies = {}
    for p in raw["policies"]:
        policies[p["policy_id"]] = Policy(
            policy_id=p["policy_id"],
            service=p["service"],
            logic=p.get("logic", ""),
            required=[Criterion(**c) for c in p["required"]],
            override_any=[Criterion(**c) for c in p.get("override_any", [])],
        )
    return policies


def load_requests(path: Path | None = None) -> list[PARequest]:
    lines = (path or DATA_DIR / "requests.jsonl").read_text().splitlines()
    return [PARequest(**json.loads(line)) for line in lines if line.strip()]
