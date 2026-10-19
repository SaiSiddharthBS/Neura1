# Project status

Last updated: 19 October 2026, after the Graph Hacks submission. Keep this file current at the end of every working
session: what changed, what was decided, and what is next.

## Where things stand

Neura1 was **submitted to Graph Hacks** (WeMakeDevs × FalkorDB) on 18 October 2026, before the 23:59 IST deadline.
Main track: Track 03, Company Brain; also Track 01. Results date: not announced yet (watch the WeMakeDevs Discord,
X account and email).

Submitted:
- Repository: https://github.com/SaiSiddharthBS/Neura1 (the last pre-deadline commit is `f7770f8`).
- Demo video: the narrated YC-style cut, uploaded to YouTube by the author (link in the submission form).
- Live demo: a Cloudflare quick tunnel to the author's Mac (URL in the submission form). It works only while that Mac,
  the API, the web app and the tunnel process are running. Restarting the tunnel changes the URL.
- Blog: a private Claude artifact page, shared by the author.

After the deadline: the Neura1 film (`docs/demo/neura1-film-narrated.mp4`, source in `scripts/film`), the complete product
demo (`docs/demo/neura1-demo.mp4`, 3:06) and these notes were added.

## What is built

| Area | What it does |
|---|---|
| Company graph | FalkorDB; people, organisation (three tiers), parts, revisions, BOM, suppliers, quotes, stock, purchase orders, builds, orders, customers, projects, tasks, decisions, documents, chats, meetings |
| Change impact | Ripple map, cost by code, rejected alternates, tasks from the change policy |
| Never twice | Chat guard against previously rejected decisions; knowledge health of living documents |
| Plan ahead | Can we promise?, Timeline (Gantt with baseline, plan, forecast), sandbox on `GRAPH.COPY`, knowledge rescue |
| Acts | Purchase order drafts and receiving, workboard, morning briefs, chat with slash commands (`/impact`, `/slips`, ...) |
| Department agents | Procurement, Production, Engineering, Sales: goal, scoped engines, channel, permissions (`api/neura1/departments.py`) |
| Connections | Zoho Inventory and Zoho Projects over MCP (simulated Zoho in the demo); field-level diff; sync history |
| Agents outside | Remote MCP endpoint for OpenAI Dots, ChatGPT, Claude: off by default, switched on in the app by leadership |
| Meetings | Local Whisper transcription, decisions and actions verified against the transcript |
| Permissions | Money and leave visible to directors and leadership; applied to every response |
| Models | ornith-1.5 on the NVIDIA DGX Spark (vLLM, over Tailscale), Qwen2.5-7B on Ollama as fallback |
| Quality | 122 tests; blind evaluation in `docs/EVAL.md`; 110 documented Cypher queries in `docs/queries.md` |

## How it runs today

- Mac: FalkorDB (Docker, port 6380, graph `voltline`), API (`api/.venv/bin/uvicorn neura1.main:app --port 8000`),
  web (`cd web && pnpm build && pnpm start --port 3000`), the Cloudflare tunnel, and `caffeinate`.
- Tailscale: members of the company tailnet can open the web app on the Mac's Tailscale address, port 3000.
- DGX Spark: serves the model over Tailscale. Addresses and secrets live only in `api/.env` (never commit it).
- Reset the demo story: Import → Reset the demo company, or `POST /api/admin/reset`.

## What is left

Next, in rough priority:
1. Keep the live demo up until results are announced, or move hosting to the DGX with Tailscale Funnel for a permanent
   public address (needs SSH access to the DGX, and the submission link updated if the form allows it).
2. Real company sign-in (SSO) in place of the demo's "view as" switch, before any real use at Flyvi.
3. A live connection to Flyvi's own Zoho through Zoho's MCP service (needs a Zoho admin to create the MCP server).
4. The long-term plan: replace paid Zoho modules one at a time (inventory and chat first); keep accounting and GST
   e-invoicing on a proper system until Neura1 can carry them.
5. An 8 to 10 minute walkthrough of every feature was not made; the film (1:52) and the complete demo (3:06) exist.
6. Ideas raised but not built: department agents that run on a schedule and draft tasks for approval; agents per
   department in the style of open-dots with their own LLM harness.

## Decisions to keep

- Strict organisation: Suresh, Sathish and Jayaram are directors; Anil, Markande, Hithesh and Praveen are leadership;
  everyone else is "Employee". Never invent a role, title, department or portfolio for anyone.
- All records are synthetic, customers fictional, people by first name only, no leave reasons, gender-neutral language.
- Free and open-source tools only, self-hosted, ₹0 cloud cost. Nothing leaves the building unless leadership switches
  external AI access on.
- Model output is verified by code (quotes word for word); numbers are computed, never generated. Do not hand-edit
  model output snapshots in `fixture/flyvi/extracted/`.
- Videos: the author does not record their own voice.
