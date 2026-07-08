"""Dataset discovery + preparation.

Raw datasets are jsonl files dropped into backend/data/bench/ (one line = one QA
record carrying its long `context`). Preparation turns a raw file into the frozen
bench corpus:

    unique contexts (many records share one textbook) -> stable order (by hash)
    -> the token cap split across several documents (paragraph-aligned prefixes,
       never a mid-sentence cut) so the graph gets cross-document structure even
       at small caps.

Deterministic by construction: same file + same cap -> byte-identical corpus.
"""

from __future__ import annotations

import hashlib
import json

from app.bench import store
from app.chunking.tokens import count_tokens

_CONTEXT_KEYS = ("context", "ctx", "document", "text", "passage")


def _last_used(name: str, raw) -> float:
    """Most recent touch across the dataset's artifacts: raw file (download),
    manifest/gold (prepare, editing) and run reports (runs)."""
    times = [raw.stat().st_mtime]
    workdir = store.WORK_DIR / name
    for p in (workdir / "manifest.json", workdir / "gold.json"):
        if p.exists():
            times.append(p.stat().st_mtime)
    runs = workdir / "runs"
    if runs.exists():
        times += [f.stat().st_mtime for f in runs.glob("*.json")]
    return max(times)


def list_datasets() -> list[dict]:
    store.RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for f in list(store.RAW_DIR.glob("*.jsonl")) + list(store.RAW_DIR.glob("*.json")):
        out.append({"name": f.stem, "file": f.name, "size_mb": round(f.stat().st_size / 1e6, 1),
                    "last_used": _last_used(f.stem, f), **dataset_status(f.stem)})
    return sorted(out, key=lambda d: d["last_used"], reverse=True)


def dataset_status(dataset: str) -> dict:
    manifest = store.load_manifest(dataset)
    gold = store.load_gold(dataset)
    prepared = manifest.get("prepared")
    return {
        "prepared": prepared,
        "builds": [
            {k: b.get(k) for k in ("fingerprint", "save_name", "cap_tokens", "models",
                                   "built_at", "nodes", "edges", "chunks")}
            for b in manifest.get("builds", [])
        ],
        "gold_total": len(gold),
        "gold_approved": sum(1 for q in gold if q.get("status") == "approved"),
        "runs": store.list_runs(dataset)[:10],
    }


def _iter_contexts(path):
    """Yield (sha1, context) per unique context, preserving nothing but uniqueness —
    the file is streamed line by line (they can be >100 MB)."""
    seen: set[str] = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ctx = next((row[k] for k in _CONTEXT_KEYS if isinstance(row.get(k), str) and row[k].strip()), None)
            if not ctx:
                continue
            h = hashlib.sha1(ctx.encode("utf-8")).hexdigest()
            if h in seen:
                continue
            seen.add(h)
            yield h, ctx


def split_windows(text: str, window_tokens: int) -> list[str]:
    """Paragraph-aligned ~window_tokens pieces of `text` — used for graph episodes and
    gold-question excerpts (one shared splitter so both see the same boundaries)."""
    paras, out, cur, used = text.split("\n\n"), [], [], 0
    for p in paras:
        t = count_tokens(p)
        if cur and used + t > window_tokens:
            out.append("\n\n".join(cur))
            cur, used = [], 0
        cur.append(p)
        used += t
    if cur:
        out.append("\n\n".join(cur))
    return out


def _prefix_by_paragraphs(text: str, budget_tokens: int) -> tuple[str, int, bool]:
    """A coherent prefix of `text` up to ~budget_tokens, cut at paragraph boundaries.
    Returns (prefix, tokens, truncated)."""
    total = count_tokens(text)
    if total <= budget_tokens:
        return text, total, False
    parts, used = [], 0
    for para in text.split("\n\n"):
        t = count_tokens(para)
        if parts and used + t > budget_tokens:
            break
        parts.append(para)
        used += t
        if used >= budget_tokens:
            break
    return "\n\n".join(parts), used, True


def prepare(dataset: str, cap_tokens: int) -> dict:
    """Build the frozen corpus for `dataset` at `cap_tokens`; returns the prepared meta.
    QASPER-format .json files route to the qasper loader (whole papers + human gold);
    jsonl corpora split the cap across up to 8 documents (>=2 when available) so even
    a small cap yields cross-document graph structure."""
    raw_json = store.RAW_DIR / f"{dataset}.json"
    if raw_json.exists():
        from app.bench import qasper
        if qasper.is_qasper(raw_json):
            return qasper.prepare(dataset, cap_tokens)
        raise ValueError("Unrecognized .json format (expected QASPER structure).")

    raw = store.RAW_DIR / f"{dataset}.jsonl"
    if not raw.exists():
        raise FileNotFoundError(f"No raw file {raw.name} in {store.RAW_DIR}")

    contexts = sorted(_iter_contexts(raw), key=lambda p: p[0])  # stable, unbiased order
    if not contexts:
        raise ValueError("No usable contexts found in the file (expected a jsonl with a 'context' field).")

    n_docs = max(2, min(8, cap_tokens // 50_000, len(contexts))) if len(contexts) > 1 else 1
    budget = cap_tokens // n_docs

    docs, corpus_hash = [], hashlib.sha256()
    for h, ctx in contexts[:n_docs]:
        text, tokens, truncated = _prefix_by_paragraphs(ctx, budget)
        doc_id = f"{dataset}-{h[:8]}"
        docs.append({"id": doc_id, "text": text, "tokens": tokens, "truncated": truncated})
        corpus_hash.update(h.encode())
        corpus_hash.update(text.encode("utf-8"))

    store.save_corpus(dataset, docs)
    manifest = store.load_manifest(dataset)
    manifest["prepared"] = {
        "cap_tokens": cap_tokens,
        "docs": len(docs),
        "tokens": sum(d["tokens"] for d in docs),
        "corpus_hash": corpus_hash.hexdigest()[:16],
        "unique_contexts_in_file": len(contexts),
    }
    store.save_manifest(dataset, manifest)
    return manifest["prepared"]
