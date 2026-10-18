# Running Neura1 as a public demo

Neura1 runs on this machine and is published through a free Cloudflare quick tunnel; the model runs on the DGX Spark
over Tailscale, with the local Ollama model as an automatic fallback.

```bash
brew install cloudflared             # once
scripts/serve_public.sh              # production build, API, web, tunnel; prints the public URL
scripts/serve_public.sh stop         # take it down
```

- **Anyone with the link can use everything**: read, Ask (limited to 8 AI requests a minute each), approve plans, chat,
  raise purchase orders, add recordings and reset the demo. There is no passcode, so judges never hit a prompt. The data
  is synthetic; if the public link is misused, reset the demo, or require a passcode for every change by setting
  `NEURA1_DEMO_PASSCODE` in `api/.env` and restarting the API (the app then asks for it the first time a change is
  refused). `/api/health` shows `passcode_required`.
- **The URL changes** each time the tunnel restarts. For a fixed address, create a named Cloudflare tunnel
  (free account) or deploy with Docker (`docker compose --profile full up`).
- **Keep the machine awake and on Tailscale.** The script runs `caffeinate`. If the DGX is unreachable, answers come
  from the local model (`NEURA1_LLM_FALLBACK_*`); `/api/health` and the sidebar show which one is active. The
  background reader (`worker` in `/api/health`) pauses until the DGX is back.
- **Reset the story** before a demo: Import → *Reset the demo company*, or `uv run python -m neura1.cli load`.
- Data is synthetic. People appear by first name only.

## Connections: the ERP and planner, and cloud agents

- **ERP and planner sync.** By default Connections reads a simulated Zoho (`python -m neura1.connect.zoho_sim`, launched
  over stdio). To read a real Zoho MCP server, set `NEURA1_ERP_MCP_URL` (Streamable HTTP; Zoho's MCP URLs carry their
  own key, so keep it in `api/.env`). If its tool names differ from `list_items`, `list_purchase_orders`,
  `list_purchase_receives`, `list_projects` and `list_tasks`, map them with `NEURA1_ERP_TOOLS='{"list_items": "..."}'`.
  `NEURA1_ERP_SYNC_MINUTES` syncs on a schedule. Only the directors and leadership can run a sync.
- **Cloud agents (OpenAI Dots, ChatGPT, Claude).** Off unless `NEURA1_AGENT_MCP_TOKEN` is set. The endpoint is
  `<public URL>/api/agent/mcp` with `Authorization: Bearer <token>`, or `<public URL>/api/agent/<token>/mcp` for
  clients that only take a URL. The agent reads as `NEURA1_AGENT_VIEWER` (a person id) with that person's permissions;
  unset, it sees no amounts and nobody's leave. Turning it on sends answers to the agent's provider.
- **Alerts.** `NEURA1_AGENT_ALERT_WEBHOOK` (a Slack incoming webhook or a Teams workflow URL) receives a short,
  permission-filtered plan check on request and a note after each sync.
