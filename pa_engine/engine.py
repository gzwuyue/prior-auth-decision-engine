"""Orchestrates extraction + decision and writes an audit record per request."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .decision import decide
from .extractors import Extractor
from .data import cpt_index
from .models import Determination, PARequest, Policy


class PriorAuthEngine:
    def __init__(self, policies: dict[str, Policy], extractor: Extractor, audit_dir: Path | None = None):
        self.policies = policies
        self.extractor = extractor
        self.audit_dir = audit_dir

    def review_scan(self, pdf_path: Path, reader) -> tuple:
        """Faxed/scanned PDF -> OCR transcript -> policy routing by CPT -> review."""
        from .intake import route

        transcript = reader.transcribe(Path(pdf_path))
        request = route(transcript, self.policies, cpt_index(self.policies), request_id=Path(pdf_path).stem)
        det = self.review(request, transcript=transcript)
        return transcript, request, det

    def review(self, request: PARequest, transcript=None) -> Determination:
        policy = self.policies[request.policy_id]
        assessments = self.extractor.assess(request, policy)
        decision, reasons = decide(policy, assessments)
        det = Determination(
            request_id=request.request_id,
            policy_id=policy.policy_id,
            decision=decision,
            reasons=reasons,
            assessments=assessments,
            extractor=self.extractor.name,
            model=getattr(self.extractor, "model", None),
        )
        if self.audit_dir:
            self._write_audit(det, transcript)
        return det

    def _write_audit(self, det: Determination, transcript=None) -> None:
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        record = det.to_dict() | {"reviewed_at": datetime.now(timezone.utc).isoformat()}
        if transcript is not None:
            record["intake"] = transcript.to_dict()
        (self.audit_dir / f"{det.request_id}.json").write_text(json.dumps(record, indent=2))
