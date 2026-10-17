# Running Neura1 as a public demo

Neura1 runs on this machine and is published through a free Cloudflare quick tunnel; the model runs on the DGX Spark
over Tailscale, with the local Ollama model as an automatic fallback.

```bash
brew install cloudflared             # once
scripts/serve_public.sh              # production build, API, web, tunnel; prints the public URL
scripts/serve_public.sh stop         # take it down
```

- **Public visitors can read everything and use Ask**, limited to 8 AI requests a minute each. Anything that writes
  (approving a plan, posting in chat, saving a document, forwarding an email, resetting the demo) needs the passcode
  in `api/.env` (`NEURA1_DEMO_PASSCODE`). Share it only with people who should be able to change the demo.
- **The URL changes** each time the tunnel restarts. For a fixed address, create a named Cloudflare tunnel
  (free account) or deploy with Docker (`docker compose --profile full up`).
- **Keep the machine awake and on Tailscale.** The script runs `caffeinate`. If the DGX is unreachable, answers come
  from the local model (`NEURA1_LLM_FALLBACK_*`); `/api/health` and the sidebar show which one is active. The
  background reader (`worker` in `/api/health`) pauses until the DGX is back.
- **Reset the story** before a demo: Import → *Reset the demo company* (passcode), or `uv run python -m neura1.cli load`.
- Data is synthetic. People appear by first name only.
