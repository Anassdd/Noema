"""Generate the edge-case PDF fixtures for the parse tests. Deterministic.

reportlab builds the text/structure/table/multipage PDFs; Pillow paints a fake
"scanned" image-only page (no text layer) to exercise OCR. Output: pdfs/.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

PDFS = Path(__file__).resolve().parent / "pdfs"
PDFS.mkdir(parents=True, exist_ok=True)
S = getSampleStyleSheet()

_LOREM = (
    "Noema keeps a living graph of entities and the relationships between them. "
    "A consolidation pass promotes the durable parts into long-term nodes, scored "
    "by recency, co-activation, and relational density."
)


def simple():
    doc = SimpleDocTemplate(str(PDFS / "simple.pdf"), pagesize=LETTER)
    doc.build([Paragraph("Noema parse smoke test.", S["Title"]),
               Paragraph(_LOREM, S["BodyText"])])


def multipage():
    doc = SimpleDocTemplate(str(PDFS / "multipage.pdf"), pagesize=LETTER)
    flow = []
    for i in range(1, 4):
        flow += [Paragraph(f"Page {i}", S["Heading1"]),
                 Paragraph(_LOREM, S["BodyText"]), PageBreak()]
    doc.build(flow)


def headings():
    doc = SimpleDocTemplate(str(PDFS / "headings.pdf"), pagesize=LETTER)
    doc.build([
        Paragraph("Promotion Criteria", S["Title"]),
        Paragraph("Overview", S["Heading1"]),
        Paragraph(_LOREM, S["BodyText"]),
        Paragraph("Scoring signals", S["Heading2"]),
        Paragraph("Recency, co-activation, and relational density.", S["BodyText"]),
    ])


def table():
    data = [
        ["Substrate", "Multi-hop", "Cleans", "Simplicity"],
        ["HippoRAG-2", "best", "weakest", "medium"],
        ["Graphiti", "good", "best", "medium"],
        ["LightRAG", "medium", "good", "best"],
    ]
    t = Table(data, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f6bff")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ]))
    doc = SimpleDocTemplate(str(PDFS / "table.pdf"), pagesize=LETTER)
    doc.build([Paragraph("Graph substrate comparison", S["Heading1"]),
               Spacer(1, 12), t])


def long_doc(pages=12):
    doc = SimpleDocTemplate(str(PDFS / "long.pdf"), pagesize=LETTER)
    flow = []
    for i in range(1, pages + 1):
        flow += [Paragraph(f"Section {i}", S["Heading2"])]
        flow += [Paragraph(_LOREM, S["BodyText"]) for _ in range(4)]
        flow += [PageBreak()]
    doc.build(flow)


def empty():
    c = canvas.Canvas(str(PDFS / "empty.pdf"), pagesize=LETTER)
    c.showPage()  # one blank page, nothing drawn
    c.save()


def scanned():
    """An image-only page: text is painted into a PNG, embedded with no text layer."""
    img = Image.new("RGB", (1240, 1600), "white")
    d = ImageDraw.Draw(img)
    font = _big_font(46)
    lines = ["This page is a scanned image.",
             "There is no text layer.",
             "Reading it requires OCR."]
    y = 120
    for line in lines:
        d.text((90, y), line, fill="black", font=font)
        y += 90
    png = PDFS / "_scanned.png"
    img.save(png)
    c = canvas.Canvas(str(PDFS / "scanned.pdf"), pagesize=LETTER)
    c.drawImage(str(png), 0, 0, width=612, height=792)
    c.showPage()
    c.save()
    png.unlink(missing_ok=True)


def _big_font(size):
    for path in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


if __name__ == "__main__":
    simple()
    multipage()
    headings()
    table()
    long_doc()
    empty()
    scanned()
    made = sorted(p.name for p in PDFS.glob("*.pdf"))
    print(f"wrote {len(made)} fixtures to {PDFS}:")
    for name in made:
        print(" -", name)
