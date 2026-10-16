# Neura1

**Know what a change breaks before it breaks.** Neura1 is a FalkorDB company brain for hardware companies. It traces part changes across BOMs, builds, customers, and owners, and recalls the decisions behind them.

Graph Hacks 2026 · **Track 03: Company Brain** (also entered: Track 01, Agents That Act on Connected Data)

> All company data here (Voltline Controls, its people, parts, suppliers, customers) is **synthetic**.

---

## The problem, for one kind of company

Neura1 is built for **industrial electronics product companies (20–300 people)** that design controllers, gateways
or instruments and build them in-house or at an EMS partner. [Who it's for and why →](docs/target-customer.md)

A supplier emails: *the 3.3 V regulator in your power module is now ₹320 instead of ₹250, and lead time is
22 weeks.* Answering "what does this mean for us?" today takes a day:

- the BOM spreadsheet, to find every product that uses it, through sub-assemblies, on released revisions only;
- the production plan and open orders, to see who is exposed;
- Slack and old tickets, to remember why the cheaper "pin-compatible" alternate was never used;
- and a round of messages to find who owns the firmware, the test procedure, and the customer.

Neura1 keeps all of this in **one FalkorDB graph** and answers it in one view, with a source for every claim.

## What it does

| Step | What happens | Where |
|---|---|---|
| **Bring in the company** | Import existing CSV exports (items, BOM, revisions, quotes, stock, builds, orders, owners), including **BOMs straight from KiCad or Altium** (Reference/Qty/MPN columns, matched to existing parts by MPN), plus documents (Slack exports, tickets, PDFs). Column names like "Manufacturer Part Number" or "Due Date" and semicolon-separated files are understood. Every row is validated, with file/row/column errors, before anything is written. | `/import` |
| **Read the notice** | Paste the supplier email or upload the PDF. A model extracts part, price, lead time and dates; without a model, a person types them in. Either way, code checks every number against the notice text, and an unrecognised part number gets suggestions (e.g. `NB54360-T/R` → `NB54360`) instead of a guess. | Inbox |
| **Trace the impact** | One revision-aware traversal from part → sub-assembly → product revision → build → customer order, plus firmware/test dependencies, field units, alternates and owners. | Impact workspace |
| **Recall decisions** | Decisions extracted from chats and tickets (kept only if their quote is verbatim in the source) surface where they matter: *"Do not switch to NB54361-L. Rejected in DEC-117 by Arjun Mehta: thermal shutdown at 68 °C (TR-112 p.4)."* | Alternate banners, evidence drawer |
| **Do the maths** | Deterministic cost scenario: valid quote, free stock, MOQ, requalification, with the formula, assumptions and exclusions shown. | Cost card, Procurement tab |
| **Assign the work** | Tasks from the company's change policy go to recorded owners. Approval re-runs the analysis on the server and stores the tasks in the graph, idempotently, citing the evidence versions used. Copy as a message (Slack, Teams, WhatsApp, email) or download as CSV. | Tasks panel, Investigations |
| **See what changed** | When new quotes, test results or decisions arrive, reopening an approved investigation lists exactly what moved since approval (cost, baseline quote, alternate status, builds at risk). | Impact workspace |
| **Ask anything** | A tool-calling agent over bounded graph tools and guarded read-only Cypher. Shows every tool call and query. | Company brain |

Five department views (Engineering, Procurement, Production, Sales, Support) plus a Management summary all read the same graph.

## Why FalkorDB is central

Without the graph there is no product. The core question is a variable-depth, revision-filtered traversal with quantity
multiplication along each path, summed over repeated occurrences:

```cypher
MATCH (prod:Item {kind:'product'})-[:HAS_REV]->(top:Revision)
MATCH p = (top)-[:CONTAINS*1..8]->(part:Item {id:$item_id})
WITH prod, top, p,
     [n IN nodes(p) WHERE n:Revision AND n.status <> 'released' | n.id] AS blocked,
     reduce(q = 1, r IN relationships(p) | q * r.qty) AS path_qty
...
```

For the demo part this returns **3 per VC-200 Rev C** (2 power modules × 1, plus 1 direct) and **1 per VG-50 Rev A**.
It excludes the draft Rev D and obsolete Rev B and names the revision that blocked each one.

From there the impact continues across domains with no fixed join path: builds, orders, customers, account managers,
firmware owners, alternates, decisions and the Slack message that holds the evidence.

- **Data model and authority rules:** [docs/data-model.md](docs/data-model.md)
- **Every Cypher query the product depends on:** [docs/queries.md](docs/queries.md), generated from `api/neura1/queries.py`

FalkorDB features used: variable-length paths, `reduce()` and list comprehensions over paths, full-text index
(`db.idx.fulltext`) over document passages, parameterised read-only queries (`GRAPH.RO_QUERY`), and indexes on ids.

## Architecture

```
            ┌───────────────────────── web (Next.js 16) ─────────────────────────┐
            │ Inbox · Impact workspace · Company brain · Investigations · Import │
            └───────────────────────────────┬────────────────────────────────────┘
                                            │ /api
┌───────────────────────────── api (FastAPI, Python) ─────────────────────────────┐
│ ingest/structured   CSV → MERGE (idempotent, cycle-checked)                      │
│ ingest/validate     row-level import validation                                  │
│ ingest/unstructured chats/tickets/PDFs → Source → Chunk, exact-id MENTIONS links  │
│ ingest/extract      model proposes decisions/notice fields → code verifies quotes │
│ queries             named, parameterised Cypher                                   │
│ impact + engine/cost  traversal results → deterministic cost, stock, schedule      │
│ actions             Investigation/Action nodes, content-hash ids                  │
│ agent               tool-calling loop over bounded graph tools                    │
└───────────────┬──────────────────────────────────────────────┬────────────────────┘
                │                                              │
        FalkorDB (graph)                    any OpenAI-compatible model endpoint
                                            (local DGX Spark via vLLM/Ollama, or hosted)
```

| Job | Done by |
|---|---|
| Where-used, applicability, exposure, ownership, evidence links | FalkorDB Cypher |
| Arithmetic, dates, stock allocation, quote validity, idempotency, approvals | Deterministic Python |
| Reading notices; finding decisions in chats and tickets; answering questions | Model, with every extraction verified by code |
| Approving a substitute part | A person, always |

If FalkorDB is unreachable the API returns `503 graph_unavailable`. It never falls back to an answer that pretends to have
traversed the graph. Without a model, everything except notice reading, decision extraction and Ask still works.

## Zero-cost, open-source stack

Every component is free to run on your own hardware. No paid API is required.

| Part | What | Licence |
|---|---|---|
| Graph database | [FalkorDB](https://github.com/FalkorDB/FalkorDB) (Docker) | Source-available (SSPLv1), free to self-host |
| Model runtime | [Ollama](https://github.com/ollama/ollama) in Docker, or vLLM on a DGX Spark | MIT / Apache-2.0 |
| Model | [Qwen2.5-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct) (any OpenAI-compatible model works) | Apache-2.0 |
| API | Python, FastAPI, pypdf | MIT / BSD |
| Web | Next.js, React Flow, dagre, Tailwind CSS, lucide | MIT / ISC |
| Demo automation | Playwright | Apache-2.0 |

`docker compose --profile full --profile model up` runs the graph, the model, the API and the web app on one machine.

## Run it locally

Requirements: Docker, [uv](https://docs.astral.sh/uv/), Node 20+ with pnpm.

```bash
docker compose up -d falkordb                 # graph on :6380, FalkorDB Browser on http://localhost:3001

cd api
cp .env.example .env                          # set NEURA1_DEMO_PASSCODE; optionally a model endpoint
uv sync
uv run python -m neura1.cli load              # load the synthetic Voltline company
uv run pytest -q                              # BOM, cost, import, extraction-verification, idempotency tests
uv run uvicorn neura1.main:app --port 8000

cd ../web
pnpm install
pnpm dev                                      # http://localhost:3000
```

Or the whole stack: `docker compose --profile full up --build`, then open http://localhost:3000.

### Connecting a model (optional)

Set in `api/.env` any OpenAI-compatible endpoint, e.g. a local DGX Spark serving through vLLM:

```
NEURA1_LLM_BASE_URL=http://<dgx-host>:8000/v1
NEURA1_LLM_MODEL=<served model name>
```

Then `uv run python -m neura1.cli extract` reads every document and saves the model's raw output to
`fixture/voltline/extracted/`. Loading verifies each item and drops anything whose quote is not verbatim in its source.

## Demo walkthrough

1. **Inbox** → the Northbridge notice for NB54360 → *Trace impact*. Without a model, use the what-if form with NB54360, 320, 22.
2. Read the headline: 2 product revisions affected (draft and obsolete excluded), 3 builds at risk, 3 customer orders
   (Kaveri with a penalty clause), **₹37,400** cost increase (`420 × (320 − 250) + 8000`).
3. The red banner (after model extraction has run): the cheap NB54361-L was **rejected in DEC-117**. Click the source to see Arjun's Slack message and
   TR-112 page 4.
4. Flip through Engineering → Procurement → Production → Sales → Support.
5. *Approve and assign tasks*. Approve again and see 0 created, 11 already existed. Reload: the investigation is remembered.
6. *How it was computed* shows every Cypher query, its parameters, row count and time.
7. Company brain → *Ask*: "Can we switch to NB54361-L?"
8. Import → drop a broken BOM and see row-level errors.

## Evaluation

`api/eval/golden.yaml` holds 32 questions with ground truth written from the fixture **before** any model ran. They are
split into dev and held-out sets and cover where-used, revision applicability, cost, decisions, ownership, exposure and
abstention. The same model answers them three ways, on the same data:

```bash
uv run python -m eval.run_eval --system graph     # Neura1 agent + graph tools
uv run python -m eval.run_eval --system rag       # lexical top-8 retrieval + same model
uv run python -m eval.run_eval --system context   # whole corpus in the prompt + same model
```

Results: *to be filled in from `api/eval/results/` once run. Failures are reported, not hidden.*

## Repository

```
api/            FastAPI service, graph loaders, queries, cost engine, agent, tests, eval
web/            Next.js app
fixture/voltline/  synthetic company: records/ (CSV), chats/, tickets/, docs/, inbox/, updates/, extracted/
docs/           target customer, data model, queries, reuse statement, AI disclosure
```

## Honesty notes

- Built during Graph Hacks (16–18 Oct 2026). Prior Neura1 work is described in [docs/REUSE.md](docs/REUSE.md).
- AI assistance is disclosed in [docs/AI_DISCLOSURE.md](docs/AI_DISCLOSURE.md).
- No live connectors: data comes in as exports and documents. Customer demand is a hypothesis, not a result.
