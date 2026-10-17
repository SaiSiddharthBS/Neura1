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
