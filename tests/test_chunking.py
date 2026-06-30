"""Chunker tests — runnable with plain python (no pytest needed):

    backend/.venv/bin/python tests/test_chunking.py

Covers normal use + edge cases. Uses a deterministic word-count tokenizer for size
assertions so results don't depend on whether tiktoken is installed.
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.chunking import Chunk, chunk_markdown, chunk_parsed_doc  # noqa: E402

WC = lambda t: len(t.split())  # deterministic "tokens" = words  # noqa: E731

PAPER = """# Hölder Inequalities

This is the introduction. It motivates the work in plain French-flavored prose and
sets up the notation used throughout the rest of the document without any mathematics.

## Methods

We define the setup carefully. The exponents satisfy a duality relation and the proof
proceeds by a standard convexity argument applied term by term.

$$\\sum_{i=1}^n |a_i b_i| \\le \\left(\\sum |a_i|^p\\right)^{1/p} \\left(\\sum |b_i|^q\\right)^{1/q}$$

### Data

| model | score |
| --- | --- |
| A | 0.91 |
| B | 0.88 |

## Results

The results confirm the bound is tight. We discuss several consequences and edge cases
that arise when one of the exponents tends to infinity, with detailed commentary.
"""


def _checks(name, chunks, *, expect_min=1):
    assert isinstance(chunks, list), f"{name}: not a list"
    assert len(chunks) >= expect_min, f"{name}: expected >= {expect_min} chunks, got {len(chunks)}"
    for i, c in enumerate(chunks):
        assert isinstance(c, Chunk), f"{name}: chunk {i} wrong type"
        assert c.index == i, f"{name}: index mismatch {c.index} != {i}"
        assert c.chunk_id.endswith(f"::{i}"), f"{name}: bad id {c.chunk_id}"
        assert c.text.strip(), f"{name}: empty chunk {i}"
        assert c.char_count == len(c.text), f"{name}: char_count wrong on {i}"


def test_normal_paper():
    chunks = chunk_markdown(PAPER, doc_id="paper.pdf", target_tokens=60, overlap_tokens=0, count_tokens=WC)
    _checks("normal", chunks, expect_min=3)
    # header paths captured and nested correctly
    sections = {c.section for c in chunks}
    assert "Hölder Inequalities" in sections, sections
    assert "Hölder Inequalities › Methods" in sections, sections
    assert "Hölder Inequalities › Methods › Data" in sections, sections
    assert "Hölder Inequalities › Results" in sections, sections
    # the display formula survives intact in some chunk
    assert any("\\sum_{i=1}^n" in c.text for c in chunks), "formula was dropped/mangled"
    print(f"  normal_paper: {len(chunks)} chunks, sections={len(sections)} ✓")


def test_size_bounding():
    chunks = chunk_markdown(PAPER, doc_id="d", target_tokens=40, overlap_tokens=0, count_tokens=WC)
    # allow a small tolerance: atomic blocks (table/formula) can exceed target alone
    atomic = lambda c: "$$" in c.text or "|" in c.text
    overs = [c for c in chunks if WC(c.text) > 40 and not atomic(c)]
    assert not overs, f"non-atomic chunks over target: {[(c.index, WC(c.text)) for c in overs]}"
    print(f"  size_bounding: {len(chunks)} chunks, all non-atomic <= target ✓")


def test_no_headings():
    md = "First paragraph with several words here.\n\nSecond paragraph also present and fine."
    chunks = chunk_markdown(md, target_tokens=200, count_tokens=WC)
    assert len(chunks) >= 1
    assert all(c.header_path == [] for c in chunks), "no-heading doc should have empty header_path"
    assert all(c.section == "" for c in chunks)
    print(f"  no_headings: {len(chunks)} chunk(s), header_path=[] ✓")


def test_giant_paragraph_splits():
    giant = "word " * 1000  # ~1000 tokens, no structure
    chunks = chunk_markdown(giant, target_tokens=100, overlap_tokens=0, count_tokens=WC)
    assert len(chunks) >= 8, f"giant paragraph should split, got {len(chunks)}"
    assert all(WC(c.text) <= 100 for c in chunks), "a split piece exceeds target"
    print(f"  giant_paragraph: split into {len(chunks)} chunks, all <= target ✓")


def test_tiny_and_empty():
    one = chunk_markdown("Just one short sentence.", target_tokens=512, count_tokens=WC)
    assert len(one) == 1, f"tiny doc should be 1 chunk, got {len(one)}"
    empty = chunk_markdown("", count_tokens=WC)
    assert empty == [], f"empty doc should yield no chunks, got {empty}"
    blanks = chunk_markdown("\n\n   \n\n", count_tokens=WC)
    assert blanks == [], "whitespace-only doc should yield no chunks"
    print("  tiny_and_empty: 1 / 0 / 0 ✓")


def test_overlap():
    md = "# H\n\n" + ". ".join(f"Sentence number {i} here" for i in range(60)) + "."
    no = chunk_markdown(md, target_tokens=40, overlap_tokens=0, count_tokens=WC)
    ov = chunk_markdown(md, target_tokens=40, overlap_tokens=12, count_tokens=WC)
    assert len(ov) >= 2, "need multiple chunks to test overlap"
    assert any(c.overlap_tokens > 0 for c in ov[1:]), "overlap not applied"
    assert all(c.overlap_tokens == 0 for c in no), "overlap should be 0 when disabled"
    print(f"  overlap: {len(ov)} chunks, overlap carried on {sum(c.overlap_tokens>0 for c in ov)} ✓")


def test_page_provenance():
    class FakeDoc:
        filename = "two_pages.pdf"
        page_markdown = [
            "# Page One\n\nContent that lives entirely on the first page here.",
            "# Page Two\n\nContent that lives entirely on the second page here.",
        ]

    chunks = chunk_parsed_doc(FakeDoc(), target_tokens=512, count_tokens=WC)
    pages_seen = sorted({p for c in chunks for p in c.pages})
    assert pages_seen == [1, 2], f"expected pages [1,2], got {pages_seen}"
    assert all(c.pages for c in chunks), "every chunk must carry page provenance"
    p1 = [c for c in chunks if c.pages == [1]]
    assert p1 and "first page" in p1[0].text
    print(f"  page_provenance: pages seen={pages_seen}, every chunk has pages ✓")


def test_page_spanning_chunk():
    class FakeDoc:
        filename = "span.pdf"
        # one heading + enough prose that a single chunk straddles the page join
        page_markdown = ["Alpha beta gamma delta.", "Epsilon zeta eta theta."]

    chunks = chunk_parsed_doc(FakeDoc(), target_tokens=512, count_tokens=WC)
    assert len(chunks) == 1, f"expected the two short pages to merge into 1 chunk, got {len(chunks)}"
    assert chunks[0].pages == [1, 2], f"spanning chunk should cite both pages, got {chunks[0].pages}"
    print("  page_spanning_chunk: single chunk cites pages [1, 2] ✓")


def test_serialization():
    c = chunk_markdown("# T\n\nhello world", count_tokens=WC)[0]
    d = c.to_dict()
    for k in ("chunk_id", "doc_id", "index", "text", "header_path", "pages", "token_count", "section"):
        assert k in d, f"missing {k} in to_dict()"
    print("  serialization: to_dict has all fields ✓")


def test_default_tokenizer_runs():
    # exercise the real default counter (tiktoken or heuristic), not the injected WC
    chunks = chunk_markdown(PAPER, doc_id="p", target_tokens=128)
    assert chunks and all(c.token_count > 0 for c in chunks)
    print(f"  default_tokenizer: {len(chunks)} chunks, token_count populated ✓")


def test_oversized_atomic_block_never_split():
    # a display-math block / code block bigger than target must stay whole, not be
    # hard-split mid-formula into broken LaTeX.
    term = r"\frac{a_i}{b_i} + \sum_{k=1}^{n} x_k^{2} \le \int_0^\infty e^{-t}\,dt "
    formula = "$$\n" + term * 80 + "\n$$"   # ~560 words, well over target
    md = "Intro prose for context here.\n\n" + formula + "\n\nClosing prose here too."
    chunks = chunk_markdown(md, doc_id="big", target_tokens=100, count_tokens=WC)
    fc = [c for c in chunks if "frac" in c.text]
    assert len(fc) == 1, f"formula split across {len(fc)} chunks"
    assert fc[0].text.count("$$") == 2, "formula delimiters broken"
    assert fc[0].text.count("frac") == 80, "formula content lost"
    assert fc[0].text.count("{") == fc[0].text.count("}"), "braces unbalanced — split mid-formula"

    code = "```python\n" + "x = compute_value(idx)\n" * 80 + "```"
    md2 = "Lead-in line.\n\n" + code + "\n\nWrap-up line."
    ch2 = chunk_markdown(md2, doc_id="code", target_tokens=100, count_tokens=WC)
    cc = [c for c in ch2 if "compute_value" in c.text]
    assert len(cc) == 1, f"code block split across {len(cc)} chunks"
    assert cc[0].text.count("```") == 2, "code fence broken"
    print(f"  oversized_atomic: formula ({WC(formula)}w) + code kept whole, never split ✓")


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    failed = 0
    print("running chunker tests…")
    for t in TESTS:
        try:
            t()
        except AssertionError as e:
            failed += 1
            print(f"  ✗ {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ✗ {t.__name__}: unexpected {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.exit(1 if failed else 0)
