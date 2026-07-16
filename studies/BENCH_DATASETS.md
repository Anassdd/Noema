# Bench datasets — provenance and construction

What each benchmark in `backend/data/bench/` is, who built it, how its documents
and QA pairs were created, and exactly which slice Noema uses. Written to be
lifted into the project report.

All three arrive with **human gold** — real questions asked by real people, with
verified answers — so none of them touch the LLM gold-question generator. They
enter the bench through one shared path (`noema-humanqa-v1`, see the last
section) and were converted by deterministic, LLM-free adapters committed under
`backend/app/bench/adapters/`.

| dataset | file | questions | corpus | gold answers by |
|---|---|---|---|---|
| CRAG (finance+open, static) | `crag-fin-open.json` | 487 | 1,881 web pages, ~6M tokens | Meta annotators |
| FinanceBench (open set) | `financebench.json` | 150 | 84 SEC filings, ~10M tokens | Patronus AI analysts |
| Basel-FAQ (GBS-QA-style) | `basel-faq.json` | 424 | 127 Basel chapters, ~0.7M tokens | the BCBS itself |

Token figures are approximate; `prepare()` reports exact counts at the chosen cap.

---

## 1. CRAG — Comprehensive RAG Benchmark (Meta, 2024)

**Who.** Meta (Yang et al., 2024, arXiv:2406.04744) — built as the official
benchmark of the **KDD Cup 2024** challenge and since used as a standard hard
RAG benchmark.

**What.** 4,409 QA pairs across five domains (finance, sports, music, movie,
open encyclopedic) and **eight question types**: simple, simple-with-condition,
set, comparison, aggregation, multi-hop, post-processing, false-premise. Each
question also carries a dynamism label (static / slow-changing / fast-changing /
real-time) and an entity-popularity label (head / torso / tail). The public
release (`facebookresearch/CRAG`, Git LFS) is the 2,706-question dev split of
tasks 1–2.

**How the data was made.** Questions were written by human annotators — partly
from templates over KG entities, partly free-form — then answers were curated
and verified against a fixed `query_time`. The retrieval corpus is what makes
CRAG special: every question ships with the **top-5 web pages a real search
engine returned for it** (full HTML), so systems retrieve from realistic, noisy
web content rather than clean curated passages. False-premise questions have the
literal gold answer "invalid question" (the right behavior is to refuse the
premise).

**Noema's slice** (adapter `adapters/crag.py`):

- domains **finance + open** only;
- **static** questions only — a frozen corpus can't stay correct for questions
  whose answer drifts;
- a question is kept only if ≥4 of its 5 pages yield real text (dead pages would
  make gold unanswerable through no fault of the retriever);
- page HTML → plain text, capped at 6k tokens/page, deduplicated across
  questions → **487 questions over 1,881 pages**;
- **no per-question document scoping**: CRAG is a corpus-wide search benchmark,
  and this is the dataset where multi-hop / comparison / aggregation types let
  the graph memory prove itself — the per-type slices in the bench report map
  1:1 to CRAG's own taxonomy.

## 2. FinanceBench (Patronus AI, 2023)

**Who.** Patronus AI (Islam et al., 2023, arXiv:2311.11944). The full benchmark
is 10,231 questions over 361 public filings; the **open-source sample is 150
questions** plus the filing PDFs (`patronus-ai/financebench`); the remainder is
gated behind Patronus.

**What.** Questions about real SEC filings (10-K, 10-Q, 8-K, earnings releases)
of large US-listed companies. The open set is three slices of 50:

- **domain-relevant** — standard financial-analyst questions (margins, capex,
  dividends...);
- **novel-generated** — freshly written questions unlikely to appear in training
  data;
- **metrics-generated** — questions derived from extracted financial metrics,
  with deterministic numeric answers.

**How the QA was made.** Human annotators wrote each question against one
specific filing and recorded the gold answer, a justification, and the
**evidence string with its page number** — which is why this dataset exercises
the bench's evidence metrics end-to-end. The paper's headline finding: GPT-4-
Turbo with a shared vector store answered **81% of questions incorrectly or
refused** — this is a genuinely hard retrieval benchmark, not a saturated one.

**Noema's build** (adapter `adapters/financebench.py`): all 150 questions; the
84 filings they reference, ingested as **full documents** (text extracted
locally with pypdfium2 — SEC filings carry a digital text layer, tables flatten
roughly but figures survive). Each question is scoped to its own filing
(matching how the benchmark is defined); forcing corpus-wide search with the
runner's `scope="corpus"` reproduces the paper's harder shared-store setting.

## 3. Basel-FAQ — a GBS-QA-style reconstruction (BIS/BCBS source)

**Who (the original).** GBS-QA — "The Global Banking Standards QA Dataset"
(Sohn, Kwon & Choi — KAIST, ECONLP@EMNLP 2021). 186 QA pairs from the Basel
Committee on Banking Supervision's published FAQs, reviewed by **five financial-
regulation experts** who classified questions into four types (binary 72, WH 36,
how 23, conditional 55) and revised them all into yes/no form (70% yes / 30%
no), with majority voting and inter-annotator kappa.

**Why a reconstruction.** The annotated dataset was **never publicly released**
— the paper itself notes disclosure was pending review "confirmed by the BCBS",
and no repository exists. Noema therefore rebuilds from the **same primary
source the paper describes**: the BCBS Basel Framework website
(www.bis.org/basel_framework), whose provisions carry official FAQs — questions
raised by market participants during rule-making, answered formally by the BCBS.

**How ours is built** (adapter `adapters/baselfaq.py`):

- crawl the framework's own JSON API (`/api/bcbs_standards`,
  `/api/bcbs_chapters/<id>`) — one polite request per chapter — taking the
  **current in-force version** of every chapter of the 14 standards
  (127 chapters);
- corpus documents = whole chapters, provisions numbered the way the framework
  cites them (e.g. `RBC30.12`);
- gold = each FAQ **verbatim**: the market participant's question, the BCBS's
  official answer, and the provision paragraph it annotates as the evidence
  span → **424 QA pairs** (of 430 crawled; 6 had no separable question/answer);
- question types by surface form — binary 140, wh 70, how 45, conditional 42,
  other 127 — the same axes GBS-QA classified by hand. Unlike GBS-QA we keep
  answers free-form rather than collapsing to yes/no: the bench's LLM judge
  grades free-form answers directly, so no information needs to be destroyed.

This is also the dataset closest to the project's target domain: dense,
cross-referenced banking regulation, where provisions reference each other the
way a knowledge graph does.

---

## How they enter the bench

All three are converted into one raw format, `noema-humanqa-v1`
(`backend/data/bench/<name>.json`): a list of `documents` (id, title, text) and
a list of `questions` (question, answer, alt_answers, evidence, type, the
`doc_ids` the question needs, and an optional `scope_doc_id`). The loader
(`app/bench/humanqa.py`) mirrors the QASPER path — documents ingested whole,
gold pre-approved as `human` — but selection walks **questions** in stable hash
order and pulls in each question's documents until the token cap is hit, so a
question only enters the gold when every document it needs made it into the
corpus. Re-preparing at a different cap regenerates corpus and gold
deterministically.

Scoping follows each benchmark's design: FinanceBench and Basel-FAQ questions
are scoped to their document; CRAG searches the whole corpus.

**Question yield per cap** (measured with real prepares — plan build budgets with
this, since ingestion cost scales with corpus tokens, not questions):

- `basel-faq` is the densest by far: a **120k cap already yields 247 gold
  questions** (18 chapters); the full 424 needs only ~0.7M tokens.
- `crag-fin-open` costs ~12k corpus tokens per question (5 capped pages each,
  shared pages amortize slowly): 150k cap → 12 questions; all 487 → ~5.9M.
- `financebench` filings average ~120k tokens and carry ~1.8 questions each:
  400k cap → 7 filings / 16 questions; all 150 → ~10.1M.

**Reproducing the raw files** (upstream sources are gitignored under
`backend/data/bench/raw/` — only the converted `.json` files are committed):

```bash
cd backend
# FinanceBench: QA jsonl + 84 PDFs from github.com/patronus-ai/financebench
.venv/bin/python -m app.bench.adapters.financebench
# Basel-FAQ: crawls bis.org if no dump is present
.venv/bin/python -m app.bench.adapters.baselfaq
# CRAG: point at the official LFS release (739 MB)
.venv/bin/python -m app.bench.adapters.crag data/bench/raw/crag_task_1_and_2_dev_v5.jsonl.bz2
```
