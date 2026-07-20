"""LLM-driven memory EVOLUTION — the automatic counterpart to /remember and /note.

The design follows what the field converged on (ChatGPT memory, Claude's automatic
memory, Mem0, Letta/MemGPT): every exchange is screened automatically, and the
memory evolves through structured operations — add, update (replace a stale fact),
delete (retract a contradicted one) — never append-only, so "actually I moved to
Paris" rewrites the old fact instead of piling a contradiction next to it. A
consolidation pass (Letta's "sleep-time" idea, Claude's synthesis) merges overlap
once the list grows past a threshold.

Two deliberate adaptations to Noema's scale:
- The WHOLE memory list rides in the judge's context instead of a vector-similarity
  pre-selection. Mem0 needs retrieval because its stores hold thousands of
  memories; a curated per-user list of dozens doesn't — and skipping embeddings
  keeps personal facts out of the vector stores entirely.
- Domain OPINIONS the user asserts are routed to the per-context beliefs file, not
  the fact list: Noema keeps "what the user is like" (memory) and "what the user
  thinks about the domain" (beliefs, contrasted against sources) apart by design.

All model access goes through llm_client, so this stays provider-agnostic.
"""

from __future__ import annotations

import json

from app import llm_client

_SYSTEM = """You maintain a long-term memory about the user from a chat transcript.
You receive the CURRENT memory (a list of facts) and the latest exchange, and reply
with the OPERATIONS that evolve the memory — not a new list.

Operations, most specific wins:
- {"op": "update", "replaces": "<exact existing fact>", "fact": "<revised fact>"}
  when the exchange refines or supersedes an existing fact (a move, a new role, a
  changed preference). "replaces" must quote one CURRENT fact verbatim.
- {"op": "delete", "fact": "<exact existing fact>"}
  when the user retracts or contradicts an existing fact and nothing replaces it.
- {"op": "add", "fact": "<new fact>"}
  for a genuinely new durable, user-specific fact: name, role, stable preference,
  ongoing goal, lasting constraint. Short, self-contained, subject written as
  "The user" (e.g. "The user's name is Anas.") — never the user's name as subject.

Write every fact in the LANGUAGE THE USER SPEAKS, using that language's equivalent
subject — e.g. a French speaker gets "L'utilisateur travaille chez BNP.", not an
English translation. When updating an existing fact, keep that fact's language.

Separately, list "beliefs": OPINIONS or stances the user asserts about the DOMAIN
under discussion ("I think X is overrated", "in my view the limit should be 3%") —
their view, not a personal fact and not established knowledge. Reword each into a
short standalone note that keeps the user's exact claim and language.

CRITICAL — only trust the USER. Record ONLY what the user explicitly stated or
confirmed. NEVER record what the assistant guessed, asked, assumed, or suggested.
Do NOT record: one-off questions, transient task details, general knowledge, facts
about the assistant, or anything already covered by the current memory (omit —
there is no noop operation). When nothing qualifies, return empty lists.

Respond with ONLY JSON: {"operations": [...], "beliefs": ["..."]}. No prose."""


def evolve(messages: list[dict], known: list[str]) -> dict:
    """Judge the latest exchange against the current memory. Returns validated
    operations: {"add": [...], "update": [(old, new), ...], "delete": [...],
    "beliefs": [...]} — update/delete targets that don't match a current fact are
    downgraded (update -> add) or dropped (delete), so a hallucinated target can
    never destroy a real memory."""
    transcript = "\n".join(
        f"{m['role']}: {m['content']}" for m in messages if m.get("content")
    )
    empty = {"add": [], "update": [], "delete": [], "beliefs": []}
    if not transcript.strip():
        return empty

    known_block = "\n".join(f"- {k}" for k in known) or "(empty)"
    user = (
        f"Current memory:\n{known_block}\n\n"
        f"Latest exchange:\n{transcript}\n\n"
        "Return the operations (and any asserted beliefs)."
    )
    result = llm_client.chat(
        [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
        stream=False,
        temperature=0,
    )
    return _parse_operations(result.text, known)


# Above this many facts, the post-update consolidation pass runs (merge overlap,
# drop redundancy) — the list stays reviewable instead of growing without bound.
CONSOLIDATE_AT = 30


def consolidate(memories: list[str]) -> list[str] | None:
    """One rewrite pass over the whole list: merge overlapping facts, drop
    redundant ones, never invent. Returns the new list, or None when the reply
    fails validation (caller keeps the original — consolidation must never be
    able to lose the memory to a bad model day)."""
    numbered = "\n".join(f"- {m}" for m in memories)
    result = llm_client.chat(
        [
            {
                "role": "system",
                "content": (
                    "You compact a list of remembered facts about a user. Merge facts "
                    "that say overlapping things, drop exact redundancy, keep every "
                    "distinct piece of information, and NEVER invent anything new. "
                    "Keep each fact short, standalone, subject \"The user\". Respond "
                    'with ONLY JSON: {"facts": ["..."]}.'
                ),
            },
            {"role": "user", "content": numbered},
        ],
        stream=False,
        temperature=0,
    )
    data = _loads_lenient(result.text)
    facts = data.get("facts") if isinstance(data, dict) else None
    if not isinstance(facts, list):
        return None
    cleaned = [f.strip() for f in facts if isinstance(f, str) and f.strip()]
    # A valid compaction is smaller (or equal) and non-empty — anything else is suspect.
    if not cleaned or len(cleaned) > len(memories):
        return None
    return cleaned


def _parse_operations(text: str, known: list[str]) -> dict:
    out = {"add": [], "update": [], "delete": [], "beliefs": []}
    data = _loads_lenient(text)
    if not isinstance(data, dict):
        return out

    by_lower = {k.strip().lower(): k for k in known}
    known_lower = set(by_lower)
    seen = {k.lower() for k in known}

    for op in data.get("operations", []) if isinstance(data.get("operations"), list) else []:
        if not isinstance(op, dict):
            continue
        fact = (op.get("fact") or "").strip()
        kind = op.get("op")
        if not fact:
            continue
        if kind == "update":
            target = (op.get("replaces") or "").strip().lower()
            if target in known_lower:
                out["update"].append((by_lower[target], fact))
                seen.add(fact.lower())
            elif fact.lower() not in seen:  # unknown target -> the info is still new
                out["add"].append(fact)
                seen.add(fact.lower())
        elif kind == "delete":
            if fact.strip().lower() in known_lower:
                out["delete"].append(by_lower[fact.strip().lower()])
        elif kind == "add":
            if fact.lower() not in seen:
                out["add"].append(fact)
                seen.add(fact.lower())

    beliefs = data.get("beliefs", [])
    if isinstance(beliefs, list):
        out["beliefs"] = [b.strip() for b in beliefs if isinstance(b, str) and b.strip()]
    return out


def _loads_lenient(text: str):
    """Parse JSON even if the model wrapped it in prose or code fences."""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start: end + 1])
            except json.JSONDecodeError:
                return None
        return None
