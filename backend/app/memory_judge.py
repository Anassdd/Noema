"""LLM-judged memory extraction.

The automatic counterpart to the manual /remember command. Given the latest
exchange, a cheap chat call decides whether it contains durable, user-specific
facts worth keeping, and returns them as concise standalone statements. Anything
it finds lands in the same JSON store as /remember.

All model access goes through llm_client, so this stays provider-agnostic.
"""

from __future__ import annotations

import json

from app import llm_client

_SYSTEM = """You curate a long-term memory about the user from a chat transcript.

Extract ONLY durable, user-specific facts: their name, role, stable preferences,
ongoing goals, or lasting constraints. Each fact must be a short, self-contained
sentence that still makes sense with no other context. Always write the subject
as "The user" (e.g. "The user's name is Anas.", "The user is from Lebanon.") —
never use the user's name as the subject.

CRITICAL — only trust the USER. Extract a fact ONLY if the user explicitly
stated or confirmed it about themselves. NEVER extract anything the assistant
guessed, asked, assumed, or suggested. If the assistant is asking a question or
guessing (e.g. "are you from Morocco?"), that is NOT confirmed — extract nothing
from it. If the user has not actually asserted the fact, return an empty list.

Do NOT extract: one-off questions, transient task details, general knowledge,
facts about the assistant, or anything already in the "Already remembered" list.

Respond with ONLY a JSON object of the form {"facts": ["...", "..."]}. Use an
empty list when nothing qualifies. No prose, no code fences."""


def extract_facts(messages: list[dict], known: list[str]) -> list[str]:
    """Return new memorable facts from `messages` not already in `known`."""
    transcript = "\n".join(
        f"{m['role']}: {m['content']}" for m in messages if m.get("content")
    )
    if not transcript.strip():
        return []

    known_block = "\n".join(f"- {k}" for k in known) or "(none)"
    user = (
        f"Already remembered:\n{known_block}\n\n"
        f"Recent conversation:\n{transcript}\n\n"
        "Return only genuinely new, durable facts."
    )

    result = llm_client.chat(
        [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user},
        ],
        stream=False,
        temperature=0,
    )
    return _parse_facts(result.text, known)


def _parse_facts(text: str, known: list[str]) -> list[str]:
    data = _loads_lenient(text)
    if not isinstance(data, dict):
        return []
    facts = data.get("facts", [])
    if not isinstance(facts, list):
        return []

    known_lower = {k.strip().lower() for k in known}
    out: list[str] = []
    for fact in facts:
        if isinstance(fact, str):
            fact = fact.strip()
            if fact and fact.lower() not in known_lower and fact not in out:
                out.append(fact)
    return out


def _loads_lenient(text: str):
    """Parse JSON even if the model wrapped it in prose or code fences."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
        return None
