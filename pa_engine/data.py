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
            cpt_codes=p.get("cpt_codes", []),
            required=[Criterion(**c) for c in p["required"]],
            override_any=[Criterion(**c) for c in p.get("override_any", [])],
        )
    return policies


def load_requests(path: Path | None = None) -> list[PARequest]:
    lines = (path or DATA_DIR / "requests.jsonl").read_text().splitlines()
    return [PARequest(**json.loads(line)) for line in lines if line.strip()]


def load_public_notes(path: Path | None = None) -> list[PARequest]:
    """Real transcription samples from MTSamples (unlabeled; see data/public_notes_NOTICE.md)."""
    return load_requests(path or DATA_DIR / "public_notes.jsonl")


def cpt_index(policies: dict[str, Policy]) -> dict[str, str]:
    return {code.upper(): pid for pid, p in policies.items() for code in p.cpt_codes}
