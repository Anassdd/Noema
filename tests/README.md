# Noema — Lab (vision PDF parser testbench)

An interactive page to drop **any PDF** — drawings, tables, math, scans, broken
fonts — and see how the **vision parser** transcribes it: each page rendered on the
left, the model's **Markdown + LaTeX** on the right, with timing and token cost.

It's independent of the app (imports `app.parsing.vision` read-only, changes nothing
in the product) and deletes cleanly.

```
tests/
  lab.py            # the Streamlit testbench
  myTestPDFs/       # drop your own PDFs here (gitignored)
  requirements.txt  # streamlit
```

## Run it

```bash
backend/.venv/bin/python -m pip install -r tests/requirements.txt
backend/.venv/bin/python -m streamlit run tests/lab.py   # http://localhost:8501
```

Pick a PDF, set **Pages to parse** (keep it low while experimenting — each page is
a vision-model call, a few cents), and hit **Parse**. Uses whatever your `.env`
points at (OpenAI on the Mac).

## Remove it when done

```bash
rm -rf tests/
backend/.venv/bin/python -m pip uninstall -y streamlit
```

## Why not Docling?

We originally planned local **Docling**, but dropped it as the default. Short
version: Docling runs heavy ML models locally and needs a strong machine — which the
locked-down, Azure-only company PCs aren't, and which made even a dev Mac grind. The
SOTA, hardware-independent answer for an Azure-only, math-heavy, French corpus is
**hosted vision parsing** (render page → image → vision model → Markdown + LaTeX),
which is also what Claude/ChatGPT/Gemini do under the hood. Full rationale, the 2026
benchmarks, and the recommended prod architecture (Azure DI + Azure-hosted vision):
see **`NOEMA_PARSING_SOTA.md`** at the repo root.
