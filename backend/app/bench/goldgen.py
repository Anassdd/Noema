"""Gold-question drafting — the LLM proposes; the user disposes (in-page editor).

Questions are drafted per document from excerpt windows, tagged by type
(factoid / synthesis / global), each carrying the gold answer and a verbatim
evidence quote so retrieval can be scored mechanically. Drafts stay status
"draft" until approved in the Bench page; only approved questions run.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from app import llm_client
from app.bench import store
from app.bench.datasets import split_windows

_WINDOW_TOKENS = 3000

_GEN_SYS = (
    "You create benchmark questions from a document excerpt. Produce EXACTLY the "
    "requested number of questions, as a JSON array. Each item: "
    '{"question": str, "answer": str, "evidence": str, "type": "factoid"|"synthesis"|"global"}.\n'
    "- factoid: asks one precise fact; answer is short (a name, number, term).\n"
    "- synthesis: asks to explain a mechanism/why; answer is 1-3 sentences.\n"
    "- global: asks about the excerpt's main themes or argument; answer is 1-3 sentences.\n"
    "Rules: every question must be answerable FROM THE EXCERPT ALONE and phrased to stand "
    "alone (name the subject — never 'this text', 'the author', 'the excerpt'). "
    "`evidence` is a VERBATIM quote (max 40 words) from the excerpt that supports the answer. "
    "Reply ONLY the JSON array."
)

# Abstention probes: the RIGHT answer is to refuse. On-topic so retrieval finds
# plausible-looking context — the trap is answering anyway.
NULL_ANSWER = "Not answerable from the corpus."
_NULL_SYS = (
    "You create UNANSWERABLE benchmark questions from a document excerpt: questions that "
    "sound perfectly on-topic (same subject, entities and vocabulary) but whose answer is "
    "NOT in the excerpt — ask for a detail, number, date, person or reason the text never "
    "gives. They must not be answerable by reasoning from the excerpt either. Phrase each "
    "to stand alone (name the subject). Reply ONLY a JSON array: "
    '[{"question": str}]'
)


def _parse_questions(text: str) -> list[dict]:
    try:
        arr = json.loads(text[text.index("["): text.rindex("]") + 1])
    except (ValueError, json.JSONDecodeError):
        return []
    out = []
    for q in arr if isinstance(arr, list) else []:
        if not isinstance(q, dict) or not q.get("question") or not q.get("answer"):
            continue
        out.append({
            "question": str(q["question"]).strip(),
            "answer": str(q["answer"]).strip(),
            "evidence": str(q.get("evidence", "")).strip(),
            "type": q.get("type") if q.get("type") in ("factoid", "synthesis", "global") else "factoid",
        })
    return out


_VERIFY_SYS = (
    "You verify a drafted benchmark question against the source passage it came from. "
    "Check THREE things: (1) the question is self-contained (names its subject — no "
    "'this text' / 'the excerpt'); (2) the question is answerable from the passage; "
    "(3) the given gold answer is correct according to the passage. "
    'Reply ONLY JSON: {"valid": true|false, "reason": "<short — what is wrong, if anything>"}.'
)

_VERIFY_NULL_SYS = (
    "You verify a drafted ABSTENTION probe: a question that must sound on-topic but be "
    "UNANSWERABLE from the passage. It is valid if (1) it is self-contained and on the "
    "passage's topic, and (2) the passage does NOT contain or imply its answer. It is "
    "INVALID if the passage actually answers it. "
    'Reply ONLY JSON: {"valid": true|false, "reason": "<short>"}.'
)


def _passage_around(doc: str, evidence: str, span: int = 4000) -> str:
    """The slice of the document around the evidence quote (fallback: the opening),
    so the verifier judges against real surrounding context, not the quote alone."""
    pos = doc.find(evidence[:60])
    if pos < 0:
        pos = 0
    start = max(0, pos - span // 4)
    return doc[start: start + span]


async def verify(dataset: str) -> AsyncIterator[dict]:
    """Auto-verify every DRAFT question (approved ones are never touched):
    a free mechanical gate (the evidence quote must exist verbatim in its document),
    then one judge call per survivor. Passes become approved; failures stay draft
    with a visible `flag` explaining why — those are the only ones worth human eyes."""
    from app.bench.scoring import evidence_hit

    gold = store.load_gold(dataset)
    docs = {d["id"]: d["text"] for d in store.load_corpus(dataset)}
    drafts = [q for q in gold if q.get("status") != "approved"]
    if not drafts:
        yield {"phase": "done", "checked": 0, "approved": 0, "flagged": 0}
        return

    yield {"phase": "start", "checking": len(drafts)}
    approved = flagged = 0
    for i, q in enumerate(drafts):
        doc = docs.get(q.get("doc_id"), "")
        ev = q.get("evidence", "")
        is_null = q.get("type") == "null"
        if not is_null and (not ev or not doc or not evidence_hit(ev, [doc])):
            q["status"], q["flag"] = "draft", "evidence quote not found in the document"
            flagged += 1
        else:
            res = await asyncio.to_thread(
                llm_client.judge_chat,
                [{"role": "system", "content": _VERIFY_NULL_SYS if is_null else _VERIFY_SYS},
                 {"role": "user", "content": (
                     f"Passage:\n{_passage_around(doc, ev)}\n\n"
                     f"Question: {q['question']}\nGold answer: {q['answer']}")}],
                max_tokens=1200,  # headroom for thinking judges (see scoring.judge)
            )
            txt = (res.text or "").strip()
            try:
                v = json.loads(txt[txt.index("{"): txt.rindex("}") + 1])
            except (ValueError, json.JSONDecodeError):
                v = {"valid": False, "reason": "verifier reply unparseable"}
            if v.get("valid"):
                q["status"] = "approved"
                q.pop("flag", None)
                approved += 1
            else:
                q["status"], q["flag"] = "draft", str(v.get("reason", ""))[:160]
                flagged += 1
        store.save_gold(dataset, gold)
        yield {"phase": "progress", "i": i + 1, "total": len(drafts),
               "approved": approved, "flagged": flagged}

    yield {"phase": "done", "checked": len(drafts), "approved": approved, "flagged": flagged}


async def generate(dataset: str, total: int = 24) -> AsyncIterator[dict]:
    """Draft `total` questions spread across the corpus docs, streaming progress.
    Appends to the existing gold list (drafts) — never touches approved questions."""
    docs = store.load_corpus(dataset)
    if not docs:
        yield {"phase": "error", "detail": "Prepare the dataset first — no corpus."}
        return

    windows = [(d["id"], w) for d in docs for w in split_windows(d["text"], _WINDOW_TOKENS)]
    per_call = 3
    calls = min(len(windows), max(1, round(total / per_call)))
    step = max(1, len(windows) // calls)  # spread the calls across the corpus
    picked = windows[::step][:calls]

    gold = store.load_gold(dataset)
    next_id = max((q.get("n", 0) for q in gold), default=0)
    made = 0
    yield {"phase": "start", "calls": len(picked), "target": total}

    for i, (doc_id, window) in enumerate(picked):
        want = min(per_call, total - made)
        if want <= 0:
            break
        res = await asyncio.to_thread(
            llm_client.chat,
            [{"role": "system", "content": _GEN_SYS},
             {"role": "user", "content": f"Create {want} questions.\n\nExcerpt (from {doc_id}):\n{window}"}],
            temperature=0.3,
        )
        for q in _parse_questions(res.text or "")[:want]:
            next_id += 1
            made += 1
            gold.append({"id": f"q{next_id:03d}", "n": next_id, "doc_id": doc_id,
                         "status": "draft", **q})
        store.save_gold(dataset, gold)
        yield {"phase": "progress", "call": i + 1, "calls": len(picked), "drafted": made}

    # ~1 abstention probe per 6 answerable questions — the false-answer metric's data.
    n_nulls = max(1, made // 6) if made >= 4 else 0
    if n_nulls and picked:
        doc_id, window = picked[0]
        res = await asyncio.to_thread(
            llm_client.chat,
            [{"role": "system", "content": _NULL_SYS},
             {"role": "user", "content": f"Create {n_nulls} unanswerable questions.\n\nExcerpt (from {doc_id}):\n{window}"}],
            temperature=0.4,
        )
        try:
            arr = json.loads(res.text[res.text.index("["): res.text.rindex("]") + 1])
        except (ValueError, json.JSONDecodeError):
            arr = []
        for q in arr[:n_nulls]:
            if not isinstance(q, dict) or not q.get("question"):
                continue
            next_id += 1
            made += 1
            gold.append({"id": f"q{next_id:03d}", "n": next_id, "doc_id": doc_id,
                         "status": "draft", "type": "null", "evidence": "",
                         "question": str(q["question"]).strip(), "answer": NULL_ANSWER})
        store.save_gold(dataset, gold)

    yield {"phase": "done", "drafted": made, "total_gold": len(gold)}
