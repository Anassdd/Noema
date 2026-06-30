"""Turn text into a co-occurrence word network — the InfraNodus method.

Words that appear near each other become connected nodes. Two words inside a
sliding window of `WINDOW` tokens get an edge; the closer they sit, the heavier
the edge (1/distance). This is what makes the network reflect how concepts cluster
in the text, with no LLM in the loop — so it's instant and cheap.
"""

from __future__ import annotations

import re

from .stopwords import STOPWORDS

# Unicode letters only — keeps accents (French) and drops digits/punctuation.
_TOKEN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)

WINDOW = 4      # tokens; InfraNodus uses a 4-gram co-occurrence window
MIN_LEN = 3     # drop very short words (mostly noise once stopwords are gone)


def tokenize(text: str) -> list[str]:
    return [
        w for w in (m.group().lower() for m in _TOKEN_RE.finditer(text))
        if len(w) >= MIN_LEN and w not in STOPWORDS
    ]


def edge_key(a: str, b: str) -> str:
    return f"{a}\t{b}" if a < b else f"{b}\t{a}"


def accumulate(
    tokens: list[str],
    node_counts: dict[str, int],
    edge_weights: dict[str, float],
    window: int = WINDOW,
) -> None:
    """Fold one document's tokens into the running counts (in place)."""
    for i, a in enumerate(tokens):
        node_counts[a] = node_counts.get(a, 0) + 1
        for dist in range(1, window):
            j = i + dist
            if j >= len(tokens):
                break
            b = tokens[j]
            if a == b:
                continue
            key = edge_key(a, b)
            edge_weights[key] = edge_weights.get(key, 0.0) + 1.0 / dist
