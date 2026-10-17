<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/readme/logo-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="docs/readme/logo-light.png">
  <img alt="Neura1" src="docs/readme/logo-light.png" width="200">
</picture>

### Know what a change breaks before it breaks.

The company brain for industrial electronics makers, built on **FalkorDB**.<br>
A supplier changes a part, a customer escalates, a key engineer goes on leave: Neura1 traces each one through<br>
the whole company (people, projects, products, customers, decisions) and turns it into a plan, with a source for every claim.

<p>
  <img alt="FalkorDB" src="https://img.shields.io/badge/graph-FalkorDB-0e8fb0?style=for-the-badge&labelColor=0b1820">
  <img alt="Track 03" src="https://img.shields.io/badge/Graph_Hacks-Track_03_·_Company_Brain-5b6cff?style=for-the-badge&labelColor=0b1820">
  <img alt="Open source models" src="https://img.shields.io/badge/models-local_·_open_weights-11a37f?style=for-the-badge&labelColor=0b1820">
</p>
<p>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white">
  <img alt="Next.js" src="https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white">
  <img alt="React Flow" src="https://img.shields.io/badge/React_Flow-ff0072">
  <img alt="Ollama" src="https://img.shields.io/badge/Ollama-Qwen2.5--7B-111111?logo=ollama&logoColor=white">
  <img alt="Tests" src="https://img.shields.io/badge/tests-63_passing-2fd3a5">
  <img alt="MCP" src="https://img.shields.io/badge/MCP-16_tools-5b6cff">
  <img alt="Licence" src="https://img.shields.io/badge/licence-AGPL--3.0-a42e2b">
  <img alt="Cost" src="https://img.shields.io/badge/running_cost-₹0-2fd3a5">
</p>

[**Demo walkthrough**](docs/DEMO.md) · [**Data model**](docs/data-model.md) · [**Every Cypher query**](docs/queries.md) · [**Who it's for**](docs/target-customer.md) · [**Quick start**](#-quick-start)

</div>

<br>

<img src="docs/readme/hero.svg" alt="Know what a change breaks before it breaks: 3 per unit, 3 of 3 builds at risk, ₹37,400, DEC-117 recalled" width="100%">

> [!NOTE]
> The demo company is **Flyvi Technologies Pvt. Ltd.** (part of Datasol (Bangalore) Limited), a real Bengaluru maker of
> power distribution units, converters, battery chargers and embedded control systems for aerospace and defence.
> **All of its data here is synthetic:** products, customers, orders, decisions, tasks and leave. People appear by
> first name only, and customers are fictional. Every number in this README comes from the running system.

<br>

## ✦ The 30-second story

On 14 October 2026 a distributor emails Flyvi. The **NB54360** 3.3 V regulator goes from **₹250 → ₹320**, and lead time
from **6 → 22 weeks**. Answering "what does this mean for us?" usually takes a day of spreadsheets and Slack searches.
Then someone suggests the cheaper, "pin-compatible" part that engineering rejected two years ago.

Neura1 answers in one view:

<img src="docs/readme/impact-path.svg" alt="NB54360 → PSM-28 Rev 2 (×2) → PDU-28 Rev C (3 per unit) → BO-0412 (short 240) → SO-881 → Nilgiri Aero (penalty clause); NB54361-L rejected in DEC-117; firmware and test dependencies; draft and obsolete revisions excluded" width="100%">

| | What Neura1 finds | How |
|---|---|---|
| 🔩 | **3 regulators per PDU-28 Rev C**: two inside the PSM-28 module, one directly on the board (U12). **1 per BCU-24.** Draft Rev D and obsolete Rev B excluded, with the reason. | One variable-length Cypher traversal with `reduce()` |
| 🏭 | **3 of 3 planned builds at risk.** 60 free parts cover part of the first build; supply ordered today lands around 19 Mar 2027. | Graph + deterministic stock allocation |
| 🤝 | **3 customer orders exposed.** Nilgiri Aero Systems' SO-881 carries a late-delivery penalty (clause 9.2). | Build → order → customer → account manager |
| 💸 | **₹37,400 cost increase** = 420 × (₹320 − ₹250) + ₹8,000 requalification. The cheaper Q-099 quote expired on 30 June and is ignored. | `Decimal` maths in code, never the model |
| 🧠 | **"Do not switch to NB54361-L."** Rejected as **DEC-117** by Vishwas on 12 Mar 2025, for thermal shutdown at 68 °C. Found in both Slack *and* Jira, quoted word for word. | Local model extracts, code verifies quotes |
| ✅ | **11 tasks for 7 people**, from the company's own change policy. Approve once, never duplicated, remembered next session. | Idempotent `Investigation` / `Action` nodes |

<br>

## ✦ See it

<table>
  <tr>
    <td width="50%"><img src="docs/demo/overview.png" alt="Overview"><br><sub><b>Overview</b>: today's signals (a supplier change, a customer escalation, a leave notice), the risk radar, work in flight, projects and the latest knowledge.</sub></td>
    <td width="50%"><img src="docs/demo/overview-light.png" alt="Overview, light theme"><br><sub><b>Light or dark</b>: frosted glass over a slow aurora, following the system theme. OKLCH tokens, Geist with an Instrument Serif accent, View Transitions, Motion, Lenis momentum scroll and scroll-driven reveals.</sub></td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/demo/risk-radar.png" alt="Risk radar"><br><sub><b>Risk radar</b>: FalkorDB betweenness centrality, community detection and traversals find the company's chokepoints, single-sourced parts, one-person knowledge and customer concentration.</sub></td>
    <td width="50%"><img src="docs/demo/my-day.png" alt="My day"><br><sub><b>My day</b>: each person's open work, decisions waiting for them, signals touching what they own, and who in their team is away.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/demo/capability-map.png" alt="Capability map"><br><sub><b>Capability map</b>: what Flyvi is good at, from recorded work. Areas, people with finished work vs active now, and where Flyvi is thin (power sequencing: one person). As leadership sees it.</sub></td>
    <td><img src="docs/demo/capability-map-restricted.png" alt="Capability map for an engineer"><br><sub><b>Private by design</b>: an engineer sees the same map with counts only. A person's expertise is visible to them, their chain, HR and leadership. No scores or rankings exist.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/demo/chat.png" alt="Neura1 Chat"><br><sub><b>Neura1 Chat</b>: the team talks inside the brain. Messages link to the parts and people they mention, slash commands answer from the graph, and approved plans post themselves.</sub></td>
    <td><img src="docs/demo/graph-explorer.png" alt="Graph explorer"><br><sub><b>Graph explorer</b>: NB54360's live neighbourhood in FalkorDB, click to expand, with its full history beside it.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/demo/docs-fact-check.png" alt="Fact check"><br><sub><b>Neura1 Docs, check facts</b>: a draft proposes the rejected NB54361-L, an expired quote, an unapproved part and an obsolete revision. Each is caught by rules over the graph, with the Slack and Jira proof.</sub></td>
    <td><img src="docs/demo/docs-ai-edit.png" alt="AI edit"><br><sub><b>Edit with AI</b>: the local model rewrites the selected sentence; the change arrives as a tracked change by "Neura1 AI" to accept or reject.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/demo/docs-change-notice.png" alt="Change notice"><br><sub><b>Change notice from the graph</b>: affected products, builds, orders, cost, rejected alternates and required reviews, written by code into a real Word document.</sub></td>
    <td><img src="docs/demo/organisation.png" alt="Organisation"><br><sub><b>Organisation</b>: Datasol, Flyvi's directors Jayaram, Suresh and Sathish side by side, and every reporting line from the graph.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/demo/customer-escalation.png" alt="Customer escalation"><br><sub><b>Customer escalation</b>: Konkan Naval threatens to hold acceptance of SO-884. Sales, support, firmware, production and the CTO each get a task.</sub></td>
    <td><img src="docs/demo/absence-plan.png" alt="Absence plan"><br><sub><b>People change</b>: Raghavendra is away in November. Neura1 sees Raghavendra was just assigned the PSM-28 review by the supplier-change plan, and hands it to Vishwas.</sub></td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/demo/impact-overview.png" alt="Impact workspace"><br><sub><b>Impact workspace</b>: headline numbers, the rejected-part banner, the evidence graph and who needs to do what.</sub></td>
    <td width="50%"><img src="docs/demo/evidence-slack.png" alt="Evidence drawer"><br><sub><b>Evidence</b>: one click opens Vishwas's Slack message, highlighted inside its thread.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/demo/after-update.png" alt="Changed since approval"><br><sub><b>New facts arrive</b>: a bench result and a new quote. The approved investigation lists exactly what changed.</sub></td>
    <td><img src="docs/demo/import-errors.png" alt="Import"><br><sub><b>Bring in a real company</b>: KiCad or Altium BOMs and spreadsheets, checked row by row before anything is written.</sub></td>
  </tr>
</table>

<details>
<summary><b>Every team, same graph: open the six department views</b></summary>
<br>

| Engineering | Procurement |
|---|---|
| ![Engineering](docs/demo/lens-engineering.png) | ![Procurement](docs/demo/lens-procurement.png) |
| **Production** | **Sales** |
| ![Production](docs/demo/lens-production.png) | ![Sales](docs/demo/lens-sales.png) |
| **Support** | **Management** |
| ![Support](docs/demo/lens-support.png) | ![Management](docs/demo/lens-management.png) |

</details>

<details>
<summary><b>Ask the company brain: a live answer from a local model</b></summary>
<br>

![Ask](docs/demo/ask.png)

Every answer shows the tools it called and the Cypher they ran. A rule-based check flags any sentence that calls a
part *approved* when the graph says otherwise.

</details>

The full narrated walkthrough, with all 17 screens, is in **[docs/DEMO.md](docs/DEMO.md)**.

<br>

## ✦ Built for one kind of company

A company brain for everyone can't know what a BOM revision is, or why a cross-referenced part isn't approved.
Neura1 starts with **Indian industrial electronics product companies of 20–300 people** that design controllers,
gateways or instruments and build them in-house or at an EMS partner. [Why this market →](docs/target-customer.md)

```mermaid
mindmap
  root((Neura1))
    Products
      PDU-28 power distribution unit
      BCU-24 battery charger
      PSM-28 power stage module
      Revisions and BOM lines
    Supply
      Suppliers and quotes
      Stock and MOQ
      Lead times
    Operations
      Planned builds
      Customer orders
      Penalty clauses
      Units in the field
    People
      Teams
      Owners
      Approvers
    Knowledge
      Slack threads
      Jira tickets
      Test reports
      Change policy
    Projects
      Nilgiri Phase 2 rollout
      PDU-48 controller
      FY27 cost-down
      Firmware 2.4
    Signals
      Supplier changes
      Customer escalations
      People changes
    Decisions
      Rejected substitutes
      Bench evidence
      Approved actions
```

| Who | When | Today | With Neura1 |
|---|---|---|---|
| Founder / Head of Ops (buyer)<br>Engineering, procurement, planning, sales, quality (users) | A supplier price, lead-time, end-of-life or last-time-buy notice | Forward the email. Search the BOM sheet. Dig through Slack. Planning and sales hear late. | Paste the email. Every team sees what it affects, what it costs, what was decided before, and who does what. |

<br>

## ✦ The whole company, one graph

A company is disrupted by more than part changes. Neura1 treats each kind of disruption as a **signal** and traces it
through the same graph:

| Signal | What Neura1 traces | Plan it proposes |
|---|---|---|
| **Supplier change** (price, lead time, end of life) | BOM where-used → builds → orders → customers · firmware and test dependencies · certifications · past decisions | Engineering, firmware, quality, procurement, production and sales tasks (HB-ENG-04) |
| **Customer escalation** | Orders and their value, penalty exposure, field units, open tickets, the products involved, the project that can fix them, account rank | Account reply, root cause, fix decision, acceptance criteria, executive brief for top accounts |
| **People change** (leave, departure) | What they own, open tasks, projects they lead, knowledge the company relies on them for, conflicts with other plans, backup and manager | Handover, interim owners and leads, handover note, manager confirmation (HB-HR-02) |
| **Every day** | Betweenness centrality, community detection and traversals across the whole graph | **Risk radar**: chokepoints, single-sourced parts, one-person knowledge, customer concentration, workload and leave |

**Plans interact because they share one graph.** Approving the supplier-change plan assigns Raghavendra the PSM-28 review. Her
leave plan then flags the conflict and hands that review to Vishwas. Separate tools for each department would miss this.

Track 03 asks for an agent that *understands how a company works*. Here is how Neura1 maps to each point:

| Track 03 asks for | Neura1 | Try it |
|---|---|---|
| People, teams, **projects**, documents, decisions in one graph | 4 projects with leads, members, roles and scope, linked to the same parts, orders, customers and decisions | **Projects** page |
| Knowledge from docs, tickets and chats | Slack threads, Jira tickets, reports, notices and PDFs, split into passages and linked by exact ids and chat aliases ("pmic_seq.c" → `FW-PMIC-SEQ`) | **Company brain** search |
| **Who owns what, and who knows what** | Ownership is stored. Expertise is *derived* from the graph: what people own, decided, wrote about, and work on, plus who covers when they're away. | **Who knows about…** · **People** |
| Tracing decisions to their source | DEC-117 links to the exact Slack message and Jira comment, quoted word for word | Red banner → evidence |
| **Keeping knowledge current** | Re-imports update passages in place. Edited or removed evidence, decisions on obsolete revisions, expiring quotes and unowned records are flagged. | **What's new** |
| Answers with clear sources | Every Ask answer lists the passages it relied on (clickable) and the Cypher it ran | **Ask** |
| **Get work done** | Approve impact tasks; Ask drafts tasks ("Ask Sai to review pmic_seq.c…") that a person confirms | Tasks panel · Ask |

<table>
  <tr>
    <td width="50%"><img src="docs/demo/people.png" alt="People"><br><sub><b>People</b>: what Sai owns, what he knows from what he wrote, his projects, and who covers for him.</sub></td>
    <td width="50%"><img src="docs/demo/projects.png" alt="Projects"><br><sub><b>Projects</b>: members and roles, scope, decisions, open tasks, recent discussion.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/demo/who-knows.png" alt="Who knows"><br><sub><b>Who knows about Nilgiri</b>, ranked, with the reason for each person.</sub></td>
    <td><img src="docs/demo/whats-new.png" alt="What's new"><br><sub><b>What's new</b>, and the knowledge that may no longer be true.</sub></td>
  </tr>
</table>

### Use the brain from any agent (MCP)

Neura1 is also an **MCP server** with 16 tools, including `recall` for shared conversation memory: `where_used`, `change_impact`, `who_knows`, `person`, `project`,
`list_projects`, `customer`, `absence_impact`, `risk_radar`, `decisions`, `alternates`, `search_documents`,
`recent_changes`, `read_only_cypher` and `propose_task`.
Any MCP client (Claude Desktop, IDEs, other agents) can pick the right graph tool for the question. All tools are
read-only, and tasks are drafts until a person confirms them.

```json
{
  "mcpServers": {
    "neura1": { "command": "uv", "args": ["--directory", "/path/to/Neura1/api", "run", "python", "-m", "neura1.mcp_server"] }
  }
}
```

<br>

## ✦ Everything a company brain needs

| Capability | What Neura1 does | Where |
|---|---|---|
| **Organisation** | Datasol (parent) → Flyvi, led by Jayaram (Founder & MD), Anil (President & EO), Suresh (Director BD), Sathish (Director Finance), Markande (COO), Hithesh (CTO) and Praveen (GM) → 10 teams → 30 people, with reporting lines, backups and roles. The org chart shows open work and who is away today. | Organisation |
| **Employee 360** | For anyone: reporting chain, current and finished work, leave, stated skills plus knowledge derived from their work, projects, ownership, decisions, team, recent messages | People |
| **Roles your team can maintain** | Edit role, team, manager, backup, skills and leave in the app, or import CSVs. Every change is stored as an event in the graph. | People → Edit · Import |
| **Permissions from the graph** | "Viewing as" any person. Leave details are visible to that person's management chain, backup, HR and leadership. Money is visible to leadership, BD and purchase. Everyone else sees it redacted, including rupee amounts written inside messages and answers. | Sidebar → Viewing as |
| **Neura1 Chat** | Built-in team chat (channels and DMs). Every message becomes a linked passage in the graph, so chat feeds search, "who knows" and timelines. `@neura1` answers in the thread with sources; `/impact`, `/who`, `/away`, `/risk` answer instantly without a model. Replies only show what *every* reader of that channel may see (money and leave are redacted per audience). #leadership and #supply are open only to people cleared for money, and direct messages stay private by construction: they are never turned into searchable company knowledge. Approved plans, finished tasks and new notices are posted to the right channel automatically. | Chat |
| **Neura1 Docs** | A Word editor inside the brain (pages, toolbar, tables, tracked changes, comments, .docx in and out, PDF). Templates are written from the graph: an engineering change notice (HB-ENG-04), a customer response, a leave handover (HB-HR-02). The **Neura1 AI** side panel rewrites a selection, a section or the whole document on request, and every AI edit lands as a tracked change you accept or reject. **Check facts** tests every claim against the graph with fixed rules (a rejected part, an unapproved alternate, an expired quote, an obsolete revision, a price no quote supports, someone on leave, an ID that doesn't exist) and cites the proof. **Insert facts** drops live tables (where used, decisions, orders, who knows, history) at the cursor. Saved documents become knowledge linked to what they name; documents with amounts or someone's leave are only open to people allowed to see them. | Documents |
| **Capability map** | What Flyvi can do, built from recorded work: the model tags every task and project with the skills it needs, choosing only from Flyvi's own skill list (code rejects anything else). Each area shows people with finished work, people active now, and whether more work lies ahead than behind; **Where Flyvi is thin** lists skills open work needs that only one person holds or nobody has finished work in yet. Evidence, not ratings: no scores or rankings exist anywhere. A person's full expertise is visible only to them, their management chain, HR and leadership; names in the company map only to HR and leadership (managers see their own reports). | Capability map · People |
| **Graph explorer + time travel** | Open any part, person, project, customer or decision and walk its connections live from FalkorDB, click to expand. Beside it, the record's full history: decisions, quotes, messages, tasks, status changes, investigations, leave, newest first. | Graph explorer |
| **My day** | Your open work, decisions waiting for you, signals touching your areas, who in your team is away, and what changed in things you own | My day |
| **Ask with memory** | Conversations stored per person as `Conversation → Turn` nodes, linked to the passages cited and the records discussed. Follow-ups work, and `recall` searches everyone's past answers (shared memory, Track 02). Each tool call streams live. | Ask & search |
| **Semantic + keyword + graph search** | Local embeddings (`nomic-embed-text`) in FalkorDB's **vector index**, fused with the full-text index, then expanded to the records each passage mentions | Ask & search |
| **Live ingestion** | Slack Events API and Jira webhooks in their real formats (Slack signature verified). New messages and ticket changes become linked passages immediately. | `POST /api/webhooks/slack`, `/jira` |
| **Meetings → actions** | The model finds "who will do what" in meeting notes. Each item is kept only with a word-for-word quote and a real owner, then becomes a one-click task. | What's new |

<br>

## ✦ How it works

```mermaid
flowchart LR
    subgraph IN["What the company already has"]
        A["CSV exports<br/>items · BOM · quotes · stock<br/>builds · orders · owners"]
        B["KiCad / Altium<br/>BOM exports"]
        C["Slack · tickets<br/>reports · PDFs"]
        N["Supplier notice<br/>email or PDF"]
    end

    subgraph CORE["Neura1 API · Python"]
        V["Validator<br/>file · row · column errors"]
        L["Loaders<br/>idempotent MERGE"]
        P["Passages<br/>exact-id links"]
        X["Extractor<br/>model proposes"]
        Q["Quote check<br/>code verifies"]
        I["Impact engine<br/>13 named Cypher queries"]
        K["Cost and schedule<br/>deterministic"]
        T["Tasks<br/>idempotent actions"]
        G["Ask agent<br/>bounded graph tools"]
    end

    DB[("FalkorDB<br/>one company graph")]
    M["Local open model<br/>Ollama · Qwen2.5-7B<br/>or a DGX via vLLM"]
    W["Web app<br/>Next.js · React Flow"]

    A --> V --> L --> DB
    B --> V
    C --> P --> DB
    P --> X --> Q --> DB
    N --> X
    X -.-> M
    G -.-> M
    DB <--> I --> K --> T --> DB
    DB <--> G
    I --> W
    G --> W
    T --> W

    classDef graphdb fill:#0e8fb0,stroke:#0b6f88,color:#fff
    classDef model fill:#5b6cff,stroke:#3f4fd6,color:#fff
    class DB graphdb
    class M model
```

### The life of one notice

```mermaid
sequenceDiagram
    autonumber
    actor P as Procurement
    participant W as Neura1 web
    participant A as API
    participant M as Local model
    participant G as FalkorDB
    actor E as Engineering manager

    P->>W: Paste distributor email
    W->>A: POST /api/notices
    A->>M: Read part, price, lead time, dates
    M-->>A: NB54360 · 320 · 22 wk · 2026-11-01
    A->>A: Every number must appear in the email text
    A->>G: WHERE_USED · EXPOSURE · DEPENDENTS · DECISIONS
    G-->>A: Paths, builds, orders, owners, DEC-117
    A->>A: Cost 420 × 70 + 8,000 = ₹37,400
    A-->>W: Impact view with evidence and 11 tasks
    E->>W: Approve and assign
    W->>A: POST /api/actions/approve
    A->>G: MERGE Investigation and Actions by content hash
    Note over A,G: Approving again creates 0 new tasks
```

<br>

## ✦ Why FalkorDB is the product

Without the graph there is nothing to show. The core question is a variable-depth traversal that keeps only released
revisions, multiplies quantities along each path, and adds up repeated uses of the same part:

```cypher
MATCH (prod:Item {kind:'product'})-[:HAS_REV]->(top:Revision)
MATCH p = (top)-[:CONTAINS*1..8]->(part:Item {id:$item_id})
WITH prod, top, p,
     [n IN nodes(p) WHERE n:Revision AND n.status <> 'released' | n.id] AS blocked,
     reduce(q = 1, r IN relationships(p) | q * r.qty) AS path_qty
WITH prod, top,
     sum(CASE WHEN size(blocked) = 0 THEN path_qty ELSE 0 END) AS qty_per_unit,
     collect({nodes: [n IN nodes(p) | n.id], qty: path_qty, blocked_by: blocked}) AS paths
RETURN prod.id AS product, top.id AS revision, qty_per_unit, paths
```

From there the analysis keeps crossing domains with no fixed join path: builds, orders, customers and account
managers; firmware and test owners; alternates, the decisions about them, the passages that prove those decisions,
and the people who said them.

<img src="docs/readme/numbers.svg" alt="Parts needed per build vs free stock; 13 Cypher queries totalling 25.6 ms" width="100%">

**FalkorDB features in use:**
- graph algorithms: `algo.betweenness` (chokepoints) and `algo.labelPropagation` (how work actually clusters);
- variable-length paths;
- `reduce()` and list comprehensions over `nodes(p)` and `relationships(p)`;
- the full-text index (`db.idx.fulltext`) over every document passage;
- read-only parameterised queries (`GRAPH.RO_QUERY`);
- indexes on every id.

Vector indexes (`vecf32`, `db.idx.vector`) are tested and ready for embeddings.

<details>
<summary><b>The graph schema</b></summary>
<br>

```mermaid
flowchart LR
    Item -- HAS_REV --> Revision
    Revision -- "CONTAINS {qty, refdes}" --> Item
    Revision -- "CONTAINS {qty} pinned" --> Revision
    Item -- "ALTERNATE_OF {basis}" --> Item
    Item -- "DEPENDS_ON {note}" --> Item
    Supplier -- QUOTED --> Quote -- FOR --> Item
    Build -- BUILDS --> Revision
    Customer -- PLACED --> Order -- FULFILLED_BY --> Build
    Person -- MEMBER_OF --> Team
    Person -- OWNS --> Item
    Chunk -- PART_OF --> Source
    Chunk -- MENTIONS --> Item
    Decision -- ABOUT --> Item
    Decision -- DECIDED_BY --> Person
    Decision -- "EVIDENCED_BY {quote}" --> Chunk
    Investigation -- PRODUCED --> Action
    Action -- ASSIGNED_TO --> Person
    Action -- "CITES {source_version}" --> Chunk
```

Full description, with authority rules and modelling choices, in **[docs/data-model.md](docs/data-model.md)**.

</details>

```mermaid
pie showData
    title Flyvi graph · 188 nodes · 421 relationships
    "Document passages" : 79
    "Sources" : 41
    "Items" : 14
    "People and teams" : 17
    "Aliases" : 7
    "Revisions" : 6
    "Projects" : 4
    "Customers, orders, builds" : 9
    "Certifications" : 3
    "Quotes and suppliers" : 5
    "Shipments, absences, decisions" : 3
```

<br>

## ✦ How a two-year-old decision came back

```mermaid
timeline
    title DEC-117 · the cheaper regulator nobody should use
    4 Mar 2025 : Procurement proposes NB54361-L at ₹190 in Slack
               : Ticket HW-311 opened
    10 Mar 2025 : TR-112 thermal test
                : shutdown at 68 °C in a sealed enclosure
    12 Mar 2025 : Vishwas rejects it as DEC-117
                : HW-311 closed as Won't Do
    14 Oct 2026 : NB54360 price and lead-time notice arrives
    16 Oct 2026 : Local model finds DEC-117 in Slack and in Jira
                : code verifies every quote word for word
                : red banner on NB54361-L
    17 Oct 2026 : MX-3360 bench check and new quote arrive
                : marked pending approval, never approved
```

<br>

## ✦ Guardrails

A tool that tells a company which part to use has to be careful about what it lets the model decide.

| The model may | The model may not |
|---|---|
| Read a supplier notice into fields | Invent a number. Every value must appear in the notice text. |
| Propose decisions found in chats and tickets | Write a decision whose quote isn't word for word in its source |
| Pick which graph tool to call next | Write to the graph. Cypher runs read-only, write keywords are blocked, `LIMIT` is enforced. |
| Phrase an answer from tool results | Call a part approved. A rule-based check flags any such sentence the graph contradicts. |
| | Do arithmetic, pick quotes, allocate stock or approve tasks. Code and people do those. |

**Other safeguards:**
- If FalkorDB is unreachable, the API returns `503 graph_unavailable`. It never pretends to have traversed the graph.
- A chat message can record a rejection but can never approve a part.
- Approvals are re-computed on the server, so a browser can't submit made-up tasks.

<br>

## ✦ Quick start

> [!TIP]
> Everything below is free and runs on one machine. No paid API keys.

```bash
git clone https://github.com/SaiSiddharthBS/Neura1.git && cd Neura1
docker compose up -d falkordb                      # graph on :6380 · FalkorDB Browser on http://localhost:3001

cd api
cp .env.example .env                               # set NEURA1_DEMO_PASSCODE
uv sync
uv run python -m neura1.cli load                   # load Flyvi Technologies + saved model extractions
uv run pytest -q                                   # 63 tests
uv run uvicorn neura1.main:app --port 8000

cd ../web && pnpm install && pnpm dev              # http://localhost:3000
```

<details>
<summary><b>Run the whole stack in Docker, including the model</b></summary>
<br>

```bash
docker compose --profile full --profile model up --build
docker compose exec ollama ollama pull qwen2.5:7b  # first time only
```

Open http://localhost:3000. The API seeds the demo company on first start.

</details>

<details>
<summary><b>Connect a model (local CPU, or a GPU box such as a DGX Spark)</b></summary>
<br>

Any OpenAI-compatible endpoint works. In `api/.env`:

```bash
NEURA1_LLM_BASE_URL=http://<your-dgx>:8080/v1      # a DGX Spark over Tailscale, or Ollama: http://localhost:11435/v1
NEURA1_LLM_API_KEY=...                             # keep it in api/.env, which is never committed
NEURA1_LLM_MODEL=ornith-1.5-35b-a3b                # or qwen2.5:7b on a laptop
NEURA1_LLM_EMBED_BASE_URL=http://localhost:11435/v1 # embeddings can come from a different server
NEURA1_LLM_EMBED_MODEL=nomic-embed-text
```

```bash
uv run python -m neura1.cli check-model            # chat · structured JSON · tool calling
uv run python -m neura1.cli extract                # read every document; raw outputs saved for replay
uv run python -m neura1.cli load                   # verified decisions enter the graph
uv run python -m neura1.cli embed                  # semantic search (NEURA1_LLM_EMBED_MODEL=nomic-embed-text)
uv run python -m neura1.cli tag-skills             # tag tasks and projects with the skills they need (verified)
```

The agent uses a JSON plan-act loop, so it works even on servers whose native tool calling is unreliable.

</details>

<br>

## ✦ Proof, not promises

| Check | Result |
|---|---|
| Automated tests | **63 passing**: BOM roll-ups, revision applicability, cost edge cases, import validation, CAD BOMs, extraction verification, idempotent approvals, the HTTP flow end to end, and 503 when the graph is down |
| Local model on real fixture documents | DEC-117 found in **Slack and Jira** ✓ · notice read correctly ✓ · MX-3360 bench result ✓ · TR-131 bench note **missed** ✗ · [full table](docs/DEMO.md#what-the-local-model-got-right-and-wrong) |
| Mistakes caught and fixed | The agent once called MX-3360 "approved", which led to the approval wording in tool output and the rule-based check. That check then flagged the incumbent part by mistake, and was narrowed to alternates only. A small model passed two part numbers in one lookup, so the lookup now splits them. |
| Frozen evaluation | 48 ground-truth questions in [`api/eval/golden.yaml`](api/eval/golden.yaml), written before any model ran: graph agent vs search-only vs whole-corpus, same model (ornith-1.5-35b-a3b on a DGX Spark). First run as scored: 33 / 29 / 41 of 46. After correcting three stale answers and a scorer bug: 37 / 28 / 43. After fixing the agent's tools: **graph 46/46** (median 6 s) vs search 28 and whole corpus 43; a development result, since the fixes came from reading held-out failures. At this demo's size (about 10k tokens) pasting everything works; the graph wins on scale, exact cost arithmetic, permissions and evidence. Full results and every failure: [docs/EVAL.md](docs/EVAL.md). |

<br>

## ✦ Zero-cost, open stack

| Layer | Choice | Licence |
|---|---|---|
| Graph | FalkorDB, self-hosted in Docker | Source-available (SSPLv1), free |
| Model runtime | Ollama, or vLLM on a DGX Spark | MIT · Apache-2.0 |
| Model | ornith-1.5-35b-a3b on a DGX Spark (over Tailscale) for chat and extraction; Qwen2.5-7B on a laptop as a fallback; nomic-embed-text for embeddings | open weights |
| API | Python 3.12 · FastAPI · pypdf | MIT · BSD |
| Web | Next.js 16 · React 19.3 (View Transitions) · Tailwind CSS 4 with OKLCH tokens · React Flow · dagre | MIT |
| Interface | Geist, Geist Mono and Instrument Serif · Motion · Lenis smooth scroll · Sonner · react-resizable-panels · lucide | OFL-1.1 · MIT · ISC |
| Document editor | SuperDoc (Word layout, tracked changes, .docx import/export) · pdf.js | AGPL-3.0 · Apache-2.0 |
| Automation | Playwright, which captured every screenshot here | Apache-2.0 |

<br>

## ✦ Repository

```
api/                 FastAPI service
  neura1/queries.py    every Cypher query the product depends on
  neura1/impact.py     the change-impact analysis
  neura1/engine/       deterministic cost engine
  neura1/ingest/       loaders · validator · document passages · verified extraction
  neura1/agent.py      Ask agent with bounded tools and guardrails
  neura1/brain.py      who knows what · people · projects · what changed
  neura1/scenarios.py  absence and escalation plans · risk radar (graph algorithms) · signals
  neura1/people.py     employee 360 · organisation · my day · profile edits
  neura1/access.py     permissions derived from the graph (reporting chain, team)
  neura1/memory.py     conversation memory as graph nodes · recall
  neura1/search.py     hybrid vector + full-text search with graph expansion
  neura1/webhooks.py   Slack and Jira live ingestion
  neura1/mcp_server.py the graph's tools for any MCP client
  tests/  eval/        63 tests · 48-question frozen evaluation
web/                 Next.js app: Inbox · Impact · Company brain · Investigations · Import
fixture/flyvi/    synthetic company: records · chats · tickets · docs · notice · updates · model extractions
docs/                demo walkthrough · data model · queries · target customer · reuse · AI disclosure
scripts/             Playwright demo capture
```

<br>

## ✦ Graph Hacks compliance

Main entry: **Track 03, Company Brain**. Also entered: Track 01, Agents That Act on Connected Data.

- [x] FalkorDB is the primary database and the core of the product
- [x] Public repository, with setup instructions and the graph data model ([docs/data-model.md](docs/data-model.md))
- [x] The Cypher queries the product depends on ([docs/queries.md](docs/queries.md), generated from code)
- [x] Complete local setup, plus Docker for the whole stack
- [x] Built during the event (16–18 Oct 2026). Prior Neura1 work is described in [docs/REUSE.md](docs/REUSE.md).
- [x] AI assistance disclosed in [docs/AI_DISCLOSURE.md](docs/AI_DISCLOSURE.md)
- [ ] Demo video
- [ ] Live deployment

## ✦ Licence

Neura1 is free software under the [GNU Affero General Public License v3.0](LICENSE). You may use, study, change and
share it; if you run a modified version as a network service, offer its source to its users under the same licence.
The document editor it embeds, SuperDoc, uses the same licence.

<br>

<div align="center">
<img src="docs/readme/mark.png" width="56" alt="">

<sub>Neura1 · built for Graph Hacks 2026 by <a href="https://github.com/SaiSiddharthBS">@SaiSiddharthBS</a> · synthetic data, real graph</sub>
</div>
