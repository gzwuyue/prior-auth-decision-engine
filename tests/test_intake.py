"""Intake tests: fax parsing, CPT routing with OCR correction, mocked Claude vision, and real Tesseract if installed."""
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from pa_engine import KeywordExtractor, PriorAuthEngine, cpt_index, load_policies
from pa_engine.data import DATA_DIR
from pa_engine.intake import ClaudeDocumentReader, ManualIntakeRequired, Transcript, parse_fax_text, route

POLICIES = load_policies()
INDEX = cpt_index(POLICIES)
SCANS = DATA_DIR / "scans"

FAX_TEXT = """FAX TRANSMISSION 10/11/2026 09:15 Page 1 of 1
From: Harbor Endocrinology
To: Utilization Management Fax: (555) 010-2000
PRIOR AUTHORIZATION REQUEST
Member ID: M-39542
CPT/HCPCS:. 33490
Clinical -notes:
29-year-old with BMI 28.1, no hypertension.
Member ID: M-39542 (continued)
Has followed a dietitian-led program for 5 months.
"""


def _t(code="J3490", note="Some note."):
    return Transcript("x.pdf", "Prov", "M-1", code, note, "test")


def test_parse_fax_text_handles_ocr_noise_and_continuation_lines():
    t = parse_fax_text(FAX_TEXT, "x.pdf", "test")
    assert t.member_id == "M-39542" and t.cpt_code == "33490" and t.provider == "Harbor Endocrinology"
    assert "continued" not in t.clinical_note and t.clinical_note.startswith("29-year-old")


def test_route_corrects_single_character_ocr_error():
    t = _t(code="33490")
    req = route(t, POLICIES, INDEX, "PA-X")
    assert req.policy_id == "GLP1-WM-01" and t.cpt_code == "J3490" and "corrected" in t.routing_note


def test_route_unknown_code_goes_to_manual_intake():
    with pytest.raises(ManualIntakeRequired):
        route(_t(code="99999"), POLICIES, INDEX, "PA-X")


def test_route_empty_note_goes_to_manual_intake():
    with pytest.raises(ManualIntakeRequired):
        route(_t(note="   "), POLICIES, INDEX, "PA-X")


def test_every_request_has_an_image_only_scan():
    pymupdf = pytest.importorskip("pymupdf")
    scans = sorted(SCANS.glob("*.pdf"))
    assert len(scans) == 15
    with pymupdf.open(scans[0]) as doc:
        assert doc[0].get_text().strip() == ""  # no text layer: OCR is genuinely required


class FakeVisionClient:
    def __init__(self, payload):
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)
        self.payload = payload

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(self.payload))])


def test_claude_document_reader_sends_pdf_and_parses_transcript():
    client = FakeVisionClient({"provider": "Harbor Endocrinology", "member_id": "M-39542",
                               "cpt_code": "J3490", "clinical_note": "29-year-old with BMI 28.1"})
    t = ClaudeDocumentReader(client=client, model="test-model").transcribe(SCANS / "PA-2002.pdf")
    content = client.calls[0]["messages"][0]["content"]
    assert content[0]["type"] == "document" and content[0]["source"]["media_type"] == "application/pdf"
    assert client.calls[0]["output_config"]["format"]["type"] == "json_schema"
    assert t.cpt_code == "J3490" and t.reader == "claude-vision"


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract binary not installed")
def test_tesseract_end_to_end_on_a_real_scan():
    pytest.importorskip("pytesseract")
    from pa_engine.intake import TesseractReader

    engine = PriorAuthEngine(POLICIES, KeywordExtractor())
    transcript, request, det = engine.review_scan(SCANS / "PA-3001.pdf", TesseractReader())
    assert request.policy_id == "TKA-01" and "Kellgren-Lawrence" in transcript.clinical_note
