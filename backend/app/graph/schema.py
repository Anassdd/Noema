"""SOTA domain-adaptive extraction — induce a per-domain schema, then bound extraction.

The problem: graphiti's default extraction is tuned for formal named entities and is
either too narrow (misses domain things) or, fully-open, too noisy. The SOTA fix
(GraphRAG auto-tuning, AutoSchemaKG) is to NOT hand-craft a schema per domain and NOT
extract fully open — instead **sample the corpus, let an LLM derive this domain's entity
and relationship types, then extract bounded by them**. Schema-bounded extraction beats
schema-free by ~10–20 F1 in the literature.

Here the induced schema bounds extraction through a generated domain-specific instruction
(prompt-based, like GraphRAG auto-tuning). It's persisted per domain_id, so each expert
(finance, legal, …) gets its own schema, induced once.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app import llm_client
from app.config import settings

from app.config import state_path

_REPO = Path(__file__).resolve().parents[3]
_SCHEMA_DIR = state_path("schemas", _REPO / "tests" / "results" / "graph_schemas")


@dataclass
class TypeDef:
    name: str
    description: str = ""


@dataclass
class InducedSchema:
    domain: str
    entity_types: list[TypeDef] = field(default_factory=list)
    edge_types: list[TypeDef] = field(default_factory=list)
    sample_chars: int = 0
    model: str = ""

    def to_dict(self) -> dict:
        return {"domain": self.domain, "sample_chars": self.sample_chars, "model": self.model,
                "entity_types": [asdict(t) for t in self.entity_types],
                "edge_types": [asdict(t) for t in self.edge_types]}

    @classmethod
    def from_dict(cls, d: dict) -> "InducedSchema":
        return cls(domain=d.get("domain", ""), sample_chars=d.get("sample_chars", 0),
                   model=d.get("model", ""),
                   entity_types=[TypeDef(**t) for t in d.get("entity_types", [])],
                   edge_types=[TypeDef(**t) for t in d.get("edge_types", [])])


_PROMPT = (
    "You are designing a knowledge-graph schema for a specific domain. Read the SAMPLE "
    "text and propose the entity types and relationship types a domain expert would track "
    "to capture the knowledge in documents like this.\n"
    "Return STRICT JSON only, no prose:\n"
    '{{"entity_types":[{{"name":"PascalCaseType","description":"one line"}}],'
    '"edge_types":[{{"name":"UPPER_SNAKE_RELATION","description":"one line"}}]}}\n'
    "Give 6-14 entity types and 6-14 relationship types. Entity names are PascalCase nouns; "
    "relationship names are UPPER_SNAKE verbs. Be specific to the domain, not generic.\n\n"
    "SAMPLE:\n{sample}"
)


def _ident(s: str, *, snake: bool) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", s)
    if not parts:
        return "Thing"
    if snake:
        out = "_".join(p.upper() for p in parts)
    else:
        out = "".join(p[:1].upper() + p[1:] for p in parts)
    if out[0].isdigit():
        out = "_" + out
    return out


def _parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {"entity_types": [], "edge_types": []}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"entity_types": [], "edge_types": []}


def induce_schema(sample_text: str, *, domain: str, model: str | None = None) -> InducedSchema:
    """One LLM pass over a corpus sample → this domain's entity/relationship types."""
    sample = (sample_text or "").strip()[:8000]
    used = model or settings.parse_model or settings.chat_model
    res = llm_client.chat([{"role": "user", "content": _PROMPT.format(sample=sample)}],
                          model=used, temperature=0)
    data = _parse_json(getattr(res, "text", ""))
    ents = [TypeDef(_ident(t.get("name", ""), snake=False), t.get("description", ""))
            for t in data.get("entity_types", []) if t.get("name")]
    edges = [TypeDef(_ident(t.get("name", ""), snake=True), t.get("description", ""))
             for t in data.get("edge_types", []) if t.get("name")]
    return InducedSchema(domain=domain, entity_types=ents, edge_types=edges,
                         sample_chars=len(sample), model=used)


def schema_instructions(schema: InducedSchema) -> str:
    """Turn an induced schema into a domain-specific extraction instruction."""
    if not schema or not schema.entity_types:
        return ""
    ents = "; ".join(f"{t.name} ({t.description})" if t.description else t.name
                     for t in schema.entity_types)
    edges = "; ".join(f"{t.name} ({t.description})" if t.description else t.name
                      for t in schema.edge_types)
    out = (f"This corpus is about the '{schema.domain}' domain. Extract entities of these "
           f"types where present: {ents}.")
    if edges:
        out += f" Capture relationships of these types where present: {edges}."
    out += (" Prefer these types, but add a clearly-needed new type if the text demands it. "
            "Always include the person or subject of an opinion, action, or preference as an "
            "entity, linked to what it concerns.")
    return out


def save_schema(schema: InducedSchema) -> Path:
    _SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    path = _SCHEMA_DIR / f"{schema.domain}.json"
    path.write_text(json.dumps(schema.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_schema(domain: str) -> InducedSchema | None:
    path = _SCHEMA_DIR / f"{domain}.json"
    if not path.exists():
        return None
    try:
        return InducedSchema.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return None
