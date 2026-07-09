"""Answer scoring — the mechanical metrics plus the LLM judge.

EM/F1 and evidence recall are model-free (they cost nothing and can be recomputed
forever from the stored run records). The judge is the only scored call: it grades
the candidate AGAINST the gold answer (never open-ended), through llm_client.judge_chat
— a different model family than the generator when JUDGE_* is configured.
"""

from __future__ import annotations

import json
import os
import re
import string
import threading
import time

from app import llm_client

_ARTICLES = {"a", "an", "the", "le", "la", "les", "un", "une", "des"}

# Function words dropped before measuring evidence CONTENT overlap, so the score reflects
# shared subject matter (entities, terms, numbers), not shared grammar.
_STOP = _ARTICLES | {
    "of", "to", "in", "on", "for", "and", "or", "is", "are", "was", "were", "be", "been",
    "being", "with", "without", "as", "at", "by", "from", "that", "this", "these", "those",
    "it", "its", "their", "they", "them", "we", "you", "our", "your", "which", "who", "whose",
    "what", "when", "where", "why", "how", "not", "no", "nor", "but", "if", "then", "than",
    "so", "such", "can", "could", "may", "might", "will", "would", "shall", "should", "must",
    "do", "does", "did", "has", "have", "had", "having", "more", "most", "some", "any", "all",
    "each", "other", "into", "over", "under", "between", "within", "also", "using", "used",
    "de", "du", "et", "à", "une", "que", "pour", "dans", "sur",
}


def _normalize(text: str) -> list[str]:
    text = text.lower().translate(str.maketrans("", "", string.punctuation))
    return [w for w in text.split() if w not in _ARTICLES]


def _content_words(text: str) -> set[str]:
    text = text.lower().translate(str.maketrans("", "", string.punctuation))
    return {w for w in text.split() if w not in _STOP and len(w) > 2}


def evidence_overlap(evidence: str, retrieved_texts: list[str]) -> float | None:
    """Fraction of the gold evidence's CONTENT words found in the retrieved texts.

    A wording-independent companion to `evidence_hit`: it asks "did retrieval surface the
    evidence's subject matter?" rather than "did it fetch the exact paragraph?". This is the
    only evidence signal that is fair to the graph, whose facts are LLM-distilled paraphrases
    that never contain the annotator's verbatim sentence (so `evidence_hit` is 0 for it by
    construction). Returns None when the evidence has no content words to measure."""
    ev = _content_words(evidence)
    if not ev:
        return None
    hay = _content_words(" ".join(retrieved_texts))
    return round(len(ev & hay) / len(ev), 4)


def exact_match(candidate: str, gold: str) -> bool:
    return _normalize(candidate) == _normalize(gold)


def token_f1(candidate: str, gold: str) -> float:
    c, g = _normalize(candidate), _normalize(gold)
    if not c or not g:
        return float(c == g)
    common = {}
    for w in c:
        common[w] = min(c.count(w), g.count(w))
    overlap = sum(common.values())
    if overlap == 0:
        return 0.0
    precision, recall = overlap / len(c), overlap / len(g)
    return 2 * precision * recall / (precision + recall)


def evidence_hit(evidence: str, retrieved_texts: list[str]) -> bool:
    """Did the retrieved passages contain the gold evidence (whitespace-tolerant)?

    Long evidence (QASPER marks whole paragraphs) can straddle a chunk boundary,
    so an exact substring test would underreport retrieval. Fallback: shingle the
    evidence into 12-word windows — finding a third of them counts as a hit."""
    needle = re.sub(r"\s+", " ", evidence).strip().lower()
    if not needle:
        return False
    hay = re.sub(r"\s+", " ", " ".join(retrieved_texts)).lower()
    if needle in hay:
        return True
    words = needle.split()
    if len(words) <= 16:
        return False
    shingles = [" ".join(words[i: i + 12]) for i in range(0, len(words) - 11, 6)]
    found = sum(1 for s in shingles if s in hay)
    return found >= max(1, len(shingles) // 3)


_JUDGE_SYS = (
    "You grade a candidate answer against GOLD answers for a benchmark question. "
    "The gold answers are the ground truth — grade agreement, not style or length. "
    "If several gold answers are given they are alternative correct answers from "
    "different human annotators: matching ANY of them means correct, and a candidate "
    "that combines or extends them with details is still correct. A candidate that says "
    "the information is unavailable when a gold answer exists is wrong. "
    'Reply ONLY JSON: {"correct": true|false, "score": <0.0-1.0>, "note": "<short reason>"}.'
)

# Free judge tiers are heavily rate-limited (Gemini free ≈ 10 req/min) — a run fires
# hundreds of verdicts, so calls are paced and 429s retried; if the judge endpoint
# stays unavailable, the verdict falls back to the MAIN provider (recorded as such)
# rather than going unscored.
_throttle_lock = threading.Lock()
_next_call_at = 0.0


def _throttle() -> None:
    global _next_call_at
    from app.config import settings
    judge_configured = bool(settings.judge_model and settings.judge_base_url
                            and settings.judge_api_key)
    rpm = float(os.getenv("JUDGE_RPM", "9" if judge_configured else "0"))
    if rpm <= 0:
        return
    with _throttle_lock:
        now = time.time()
        wait = _next_call_at - now
        if wait > 0:
            time.sleep(wait)
            now = time.time()
        _next_call_at = max(now, _next_call_at) + 60.0 / rpm


def _parse_verdict(text: str) -> dict | None:
    try:
        j = json.loads(text[text.index("{"): text.rindex("}") + 1])
        return {"correct": bool(j.get("correct")), "score": float(j.get("score", 0.0)),
                "note": str(j.get("note", ""))[:200]}
    except (ValueError, json.JSONDecodeError, TypeError):
        return None


def _is_rate_error(exc: Exception) -> bool:
    s = str(exc).lower()
    return "429" in s or "rate" in s or "quota" in s or "exhaust" in s


def judge(question: str, gold_answer: str, candidate: str,
          alternatives: tuple[str, ...] = ()) -> dict:
    """Gold-anchored judgement, tolerant of annotator variants. Paced + retried on
    rate limits, falls back to the main provider, and only then goes unscored."""
    golds = f"Gold answer: {gold_answer}"
    if alternatives:
        golds += "\nAlternative gold answers (any counts as correct): " + " | ".join(alternatives)
    messages = [{"role": "system", "content": _JUDGE_SYS},
                {"role": "user", "content": f"Question: {question}\n\n{golds}\n\n"
                                            f"Candidate answer: {candidate}"}]

    for attempt in range(4):
        _throttle()
        try:
            res = llm_client.judge_chat(messages, max_tokens=1500)
        except Exception as exc:  # noqa: BLE001
            if _is_rate_error(exc) and attempt < 3:
                time.sleep(min(30, 6 * (attempt + 1)))
                continue
            break  # non-rate error, or out of retries -> fallback
        v = _parse_verdict(res.text or "")
        if v:
            return {**v, "judge_model": res.model,
                    "usage": res.usage.__dict__ if res.usage else None}
        # unparseable reply: one more attempt, then fallback

    try:
        res = llm_client.chat(messages, temperature=0.0, max_tokens=1500)
        v = _parse_verdict(res.text or "") or {
            "correct": None, "score": None, "note": "fallback judge reply unparseable"}
        return {**v, "judge_model": f"{res.model} (fallback)",
                "usage": res.usage.__dict__ if res.usage else None}
    except Exception as exc:  # noqa: BLE001 — an unscored answer beats a dead run
        return {"correct": None, "score": None, "note": f"judge failed: {exc}"[:200],
                "judge_model": None, "usage": None}
