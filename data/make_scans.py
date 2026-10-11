"""Render each request as a faxed prior-authorization form: an image-only PDF with no text layer.

Pages are slightly rotated, speckled and JPEG-compressed so they behave like real fax scans and
must go through OCR (or Claude's vision) before any text can be extracted.

    pip install -r requirements-ocr.txt
    python data/make_scans.py            # writes data/scans/<request_id>.pdf
"""
from __future__ import annotations

import io
import json
import random
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

DATA = Path(__file__).resolve().parent
OUT = DATA / "scans"
DPI = 150
W, H = int(8.5 * DPI), int(11 * DPI)
MARGIN = int(0.7 * DPI)
FONT_CANDIDATES = ["DejaVuSansMono.ttf", "LiberationMono-Regular.ttf", "cour.ttf", "Courier New.ttf", "Menlo.ttc"]


def font(size: int) -> ImageFont.FreeTypeFont:
    for name in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


BODY, SMALL, TITLE = font(21), font(18), font(30)
CHARS_PER_LINE = 78
LINE_H = 30


def load(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def wrap_note(note: str) -> list[str]:
    lines = []
    for para in note.split("\n"):
        lines.extend(textwrap.wrap(para, CHARS_PER_LINE) or [""])
    return lines


def degrade(img: Image.Image, rng: random.Random) -> Image.Image:
    img = img.rotate(rng.uniform(-0.8, 0.8), resample=Image.BICUBIC, expand=False, fillcolor=255)
    px = img.load()
    for _ in range(int(W * H * 0.0015)):  # speckle noise
        x, y = rng.randrange(W), rng.randrange(H)
        px[x, y] = rng.choice([0, 90, 160])
    img = img.filter(ImageFilter.GaussianBlur(0.5))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=55)  # fax-like compression artifacts
    return Image.open(io.BytesIO(buf.getvalue())).convert("L")


def render(req: dict, policy: dict) -> list[Image.Image]:
    rng = random.Random(req["request_id"])
    cpt = policy["cpt_codes"][0]
    body = wrap_note(req["clinical_note"])
    first_capacity = (H - MARGIN - 470) // LINE_H
    next_capacity = (H - MARGIN - 200) // LINE_H
    chunks = [body[:first_capacity]]
    rest = body[first_capacity:]
    while rest:
        chunks.append(rest[:next_capacity])
        rest = rest[next_capacity:]
    n = len(chunks)

    pages = []
    for i, chunk in enumerate(chunks, start=1):
        img = Image.new("L", (W, H), 255)
        d = ImageDraw.Draw(img)
        y = MARGIN
        d.text((MARGIN, y), f"FAX TRANSMISSION    10/11/2026 09:{14 + i:02d}    Page {i} of {n}", font=SMALL, fill=0)
        y += 40
        if i == 1:
            d.text((MARGIN, y), f"From: {req['provider']}", font=SMALL, fill=0)
            y += 30
            d.text((MARGIN, y), "To: Utilization Management    Fax: (555) 010-2000", font=SMALL, fill=0)
            y += 40
            d.line((MARGIN, y, W - MARGIN, y), fill=0, width=3)
            y += 25
            d.text((MARGIN, y), "PRIOR AUTHORIZATION REQUEST", font=TITLE, fill=0)
            y += 60
            d.text((MARGIN, y), f"Member ID: {req['member_id']}", font=BODY, fill=0)
            y += LINE_H
            d.text((MARGIN, y), f"Requested service: {policy['service']}", font=BODY, fill=0)
            y += LINE_H
            d.text((MARGIN, y), f"CPT/HCPCS: {cpt}", font=BODY, fill=0)
            y += LINE_H + 20
            d.text((MARGIN, y), "Clinical notes:", font=BODY, fill=0)
            y += LINE_H + 10
        else:
            d.text((MARGIN, y), f"Member ID: {req['member_id']} (continued)", font=SMALL, fill=0)
            y += 50
        for line in chunk:
            d.text((MARGIN, y), line, font=BODY, fill=0)
            y += LINE_H
        pages.append(degrade(img, rng))
    return pages


def main() -> None:
    policies = {p["policy_id"]: p for p in json.loads((DATA / "policies.json").read_text())["policies"]}
    reqs = load(DATA / "requests.jsonl") + load(DATA / "public_notes.jsonl")
    OUT.mkdir(exist_ok=True)
    for req in reqs:
        pages = render(req, policies[req["policy_id"]])
        path = OUT / f"{req['request_id']}.pdf"
        pages[0].save(path, "PDF", resolution=DPI, save_all=True, append_images=pages[1:])
        print(f"{path.name}: {len(pages)} page(s)")


if __name__ == "__main__":
    main()
