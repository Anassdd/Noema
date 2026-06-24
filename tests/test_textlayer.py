"""Text-route structuring tests (the free path that recovers headings from plain text).

    backend/.venv/bin/python tests/test_textlayer.py
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.parsing import vision  # noqa: E402


def test_heading_detection():
    yes = ["On Reading Documents", "Note en francais", "Méthodes", "Introduction", "Results"]
    no = [
        "This page is ordinary prose with no mathematics, no tables, and no figures.",
        "We agree.",                       # ends with a period
        "1. First item",                   # list item
        "- bullet point here",             # list item
        "A very long line that clearly is not a heading because it carries far too many words",
        "12345 67890",                     # not mostly letters
    ]
    for s in yes:
        assert vision._looks_like_heading(s), f"should be heading: {s!r}"
    for s in no:
        assert not vision._looks_like_heading(s), f"should NOT be heading: {s!r}"
    print(f"  heading_detection: {len(yes)} headings, {len(no)} non-headings ✓")


def test_promotes_title_and_joins_wrapped_lines():
    raw = ("On Reading Documents\r\n"
           "This page is ordinary prose with no mathematics, and it wraps across\r\n"
           "several lines that should be joined back into one paragraph.")
    md = vision._textlayer_to_markdown(raw)
    assert md.startswith("# On Reading Documents"), f"title not promoted: {md[:40]!r}"
    assert "wraps across several lines" in md, "wrapped lines not joined"
    assert "\n# " not in md[3:], "no spurious extra headings expected"
    print("  structure: title -> '# ', wrapped lines joined ✓")


def test_blank_line_paragraph_break():
    raw = "Intro paragraph one ends here.\n\nSecond paragraph starts after a blank line."
    md = vision._textlayer_to_markdown(raw)
    assert md.count("\n\n") == 1, f"expected one paragraph break, got: {md!r}"
    print("  paragraphs: blank line preserved as a break ✓")


def test_empty_and_whitespace():
    assert vision._textlayer_to_markdown("") == ""
    assert vision._textlayer_to_markdown("   \n\n  ") == ""
    print("  empty: returns '' ✓")


def test_no_false_heading_in_body():
    # a short body line that DOES end in punctuation must stay body, not a heading
    raw = "First sentence.\nNo tokens at all.\nThe point continues in plain prose here."
    md = vision._textlayer_to_markdown(raw)
    assert not md.startswith("#"), f"plain prose should not start with a heading: {md[:30]!r}"
    print("  no_false_heading: punctuated short lines stay body ✓")


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    failed = 0
    print("running text-layer tests…")
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
