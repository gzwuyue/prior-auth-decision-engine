"""Document intake: turn a faxed or scanned PA request (image-only PDF) into a structured request.

Two readers share one interface:
  * ClaudeDocumentReader - sends the PDF to Claude, which reads the page images and returns the
    header fields plus a verbatim transcription of the clinical note (structured outputs).
  * TesseractReader      - classic OCR with Tesseract, fully offline; header fields parsed with regex.

Either way, the result is routed to a coverage policy by its CPT/HCPCS code, then reviewed by the
same extractor + decision rules as text requests.
"""
from __future__ import annotations

import base64
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .extractors import DEFAULT_MODEL
from .models import PARequest, Policy


@dataclass
class Transcript:
    source_file: str
    provider: str
    member_id: str
    cpt_code: str
    clinical_note: str
    reader: str
    routing_note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- Claude (vision)

TRANSCRIBE_PROMPT = """This is a faxed prior-authorization request. Read every page.
Return the header fields and transcribe the clinical notes section exactly as written, word for word,
across all pages. Do not summarize, correct, or reorder anything. Leave out fax headers, page numbers
and "(continued)" lines. Use "" for any field that is not present."""

TRANSCRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "provider": {"type": "string"},
        "member_id": {"type": "string"},
        "cpt_code": {"type": "string"},
        "clinical_note": {"type": "string"},
    },
    "required": ["provider", "member_id", "cpt_code", "clinical_note"],
    "additionalProperties": False,
}


class ClaudeDocumentReader:
    name = "claude-vision"

    def __init__(self, client=None, model: str = DEFAULT_MODEL):
        if client is None:
            from .extractors import ClaudeExtractor

            client = ClaudeExtractor(model=model).client  # reuses the API-key check
        self.client = client
        self.model = model

    def transcribe(self, pdf_path: Path) -> Transcript:
        pdf_b64 = base64.standard_b64encode(Path(pdf_path).read_bytes()).decode("utf-8")
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4000,
            messages=[{"role": "user", "content": [
                {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}},
                {"type": "text", "text": TRANSCRIBE_PROMPT},
            ]}],
            output_config={"format": {"type": "json_schema", "schema": TRANSCRIPT_SCHEMA}},
        )
        text = next(b.text for b in response.content if getattr(b, "type", None) == "text")
        data = json.loads(text)
        return Transcript(source_file=str(pdf_path), reader=self.name, **data)


# --------------------------------------------------------------------------- Tesseract (offline OCR)

SKIP_LINE = re.compile(r"^\s*(FAX TRANSMISSION|Member ID:.*\(continued\))", re.IGNORECASE)


def parse_fax_text(text: str, source_file: str, reader: str) -> Transcript:
    """Pull header fields and the clinical-note body out of OCR'd fax text."""
    def field(pattern: str) -> str:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        return m.group(1).strip() if m else ""

    body = re.split(r"Clinical\W*notes\W*", text, maxsplit=1, flags=re.IGNORECASE)
    note_lines = [ln for ln in (body[1] if len(body) > 1 else "").splitlines() if not SKIP_LINE.match(ln)]
    note = re.sub(r"[ \t]+", " ", " ".join(ln.strip() for ln in note_lines if ln.strip()))
    return Transcript(
        source_file=source_file,
        provider=field(r"From\W*(.+)"),
        member_id=field(r"Member\s*ID\W*([A-Z]-?\d+)"),
        cpt_code=field(r"CPT\W*HCPCS\W*([A-Z0-9]{5})"),
        clinical_note=note,
        reader=reader,
    )


class TesseractReader:
    """Requires the Tesseract binary plus `pip install -r requirements-ocr.txt`."""

    name = "tesseract"

    def __init__(self, dpi: int = 300):
        try:
            import pymupdf  # noqa: F401
            import pytesseract

            pytesseract.get_tesseract_version()
        except Exception as e:  # missing package or binary
            raise SystemExit(
                "Tesseract OCR is not available. Install it with `pip install -r requirements-ocr.txt` "
                "and the Tesseract binary (Windows: https://github.com/UB-Mannheim/tesseract/wiki; "
                "macOS: brew install tesseract), or use --ocr claude."
            ) from e
        self.dpi = dpi

    def transcribe(self, pdf_path: Path) -> Transcript:
        import io

        import pymupdf
        import pytesseract
        from PIL import Image

        pages = []
        with pymupdf.open(pdf_path) as doc:
            for page in doc:
                pix = page.get_pixmap(dpi=self.dpi)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                pages.append(pytesseract.image_to_string(img))
        return parse_fax_text("\n".join(pages), str(pdf_path), self.name)


# --------------------------------------------------------------------------- routing

class ManualIntakeRequired(Exception):
    """The request cannot be routed automatically and needs a human at intake."""


def route(transcript: Transcript, policies: dict[str, Policy], cpt_index: dict[str, str], request_id: str) -> PARequest:
    """Map the transcribed CPT/HCPCS code to a coverage policy and build a PARequest.

    OCR often confuses look-alike characters (J/3, O/0, S/5). If the code is not in the code set but
    exactly one known code differs by a single character, use it and record the correction; otherwise
    stop and send the request to manual intake rather than guess.
    """
    code = transcript.cpt_code.strip().upper()
    policy_id = cpt_index.get(code)
    if policy_id is None:
        near = [c for c in cpt_index if len(c) == len(code) and sum(a != b for a, b in zip(c, code)) == 1]
        if len(near) == 1:
            transcript.routing_note = f"OCR code '{code}' corrected to '{near[0]}' (single-character match)"
            transcript.cpt_code, policy_id = near[0], cpt_index[near[0]]
        else:
            raise ManualIntakeRequired(f"{request_id}: code '{transcript.cpt_code}' matches no policy; route to manual intake.")
    if not transcript.clinical_note.strip():
        raise ManualIntakeRequired(f"{request_id}: no clinical notes found in the document; route to manual intake.")
    return PARequest(request_id=request_id, policy_id=policy_id, member_id=transcript.member_id,
                     provider=transcript.provider, clinical_note=transcript.clinical_note)
