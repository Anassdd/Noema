"""Generate a small set of diverse example PDFs into myTestPDFs/ for the Parser lab.

Each targets a different routing outcome (clean prose -> free text layer; tables /
formulas / figures / French -> vision). Run once; then cache via the lab or the seeder.

    backend/.venv/bin/python tests/gen_example_pdfs.py
"""

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parent / "myTestPDFs"
OUT.mkdir(exist_ok=True)
W, H = A4


def _text_page(c, title, paragraphs):
    c.setFont("Helvetica-Bold", 16)
    c.drawString(60, H - 70, title)
    t = c.beginText(60, H - 110)
    t.setFont("Helvetica", 11)
    for para in paragraphs:
        for line in textwrap.wrap(para, width=95):  # wrap on words, never mid-word
            t.textLine(line)
        t.textLine("")
    c.drawText(t)


def clean_prose():
    c = canvas.Canvas(str(OUT / "clean_prose.pdf"), pagesize=A4)
    _text_page(c, "On Reading Documents", [
        "This page is ordinary prose with no mathematics, no tables, and no figures. Its embedded "
        "text layer is clean and fully legible, so the parser should route it to the free text layer "
        "and spend no tokens at all.",
        "The point of this example is to demonstrate the cheap path. When a page is confidently plain "
        "prose, there is nothing a vision model would add, so the router keeps the extracted text and "
        "moves on. Savings like this are what make per page routing worthwhile on a prose heavy corpus.",
        "A second paragraph continues in the same vein, describing the method in plain language and "
        "avoiding any symbol that might trip the math detector. The result should be a single text route.",
    ])
    c.showPage()
    c.save()


def french_note():
    c = canvas.Canvas(str(OUT / "french_note.pdf"), pagesize=A4)
    _text_page(c, "Note en francais", [
        "Cette page est redigee en francais avec des accents tels que e, e, a, c et u afin de verifier "
        "que la couche de texte conserve correctement les caracteres accentues sans recourir au modele "
        "de vision. Le texte reste une prose simple, sans mathematiques ni tableaux.",
        "L objectif est de montrer que le francais emprunte lui aussi le chemin gratuit lorsque la couche "
        "de texte est propre. La provenance par page est conservee pour permettre une citation precise.",
    ])
    c.showPage()
    c.save()


def formula_sheet():
    c = canvas.Canvas(str(OUT / "formula_sheet.pdf"), pagesize=A4)
    _text_page(c, "Formula Sheet", [
        "This page contains mathematics written in LaTeX so the math detector trips and the page is "
        "routed to vision, where formulas are transcribed as LaTeX.",
        "The harmonic sum $\\sum_{i=1}^{n} 1/i$ grows like $\\ln(n)$, and the Gaussian integral "
        "$\\int_{-\\infty}^{\\infty} e^{-x^2} dx = \\sqrt{\\pi}$ is a classic result.",
        "We also note the bound $x^{2} + y^{2} \\ge 2xy$ and the relation $E = mc^2$ for good measure.",
    ])
    c.showPage()
    c.save()


def table_page():
    c = canvas.Canvas(str(OUT / "table_report.pdf"), pagesize=A4)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(60, H - 70, "Quarterly Report")
    c.setFont("Helvetica", 11)
    c.drawString(60, H - 100, "A ruled table follows; its borders are vector paths, so the page routes to vision.")
    rows = [["Quarter", "Revenue", "Growth"], ["Q1", "1.20M", "+4%"],
            ["Q2", "1.31M", "+9%"], ["Q3", "1.28M", "-2%"], ["Q4", "1.45M", "+13%"]]
    x0, y0, cw, rh = 60, H - 140, 140, 22
    for r, row in enumerate(rows):
        for col, val in enumerate(row):
            c.rect(x0 + col * cw, y0 - r * rh, cw, rh)  # each cell border = paths
            c.drawString(x0 + col * cw + 6, y0 - r * rh + 6, val)
    c.showPage()
    c.save()


def figure_page():
    chart = Image.new("RGB", (700, 380), "white")
    d = ImageDraw.Draw(chart)
    for x, h in [(90, 250), (210, 150), (330, 320), (450, 110), (570, 200)]:
        d.rectangle([x, 350 - h, x + 70, 350], fill=(70, 110, 180))
    d.text((250, 14), "Figure 1: results by group", fill="black")
    c = canvas.Canvas(str(OUT / "prose_plus_figure.pdf"), pagesize=A4)
    _text_page(c, "Results with a Figure", [
        "This page mixes a paragraph of clean prose with an embedded chart. Because a real figure is "
        "present, the page must route to vision so the figure is described and not silently dropped.",
    ])
    c.drawImage(ImageReader(chart), 60, H - 430, width=320, height=174)
    c.showPage()
    c.save()


if __name__ == "__main__":
    clean_prose()
    french_note()
    formula_sheet()
    table_page()
    figure_page()
    print("generated:", sorted(p.name for p in OUT.glob("*.pdf")))
