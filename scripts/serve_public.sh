#!/usr/bin/env bash
# Run Neura1 as a public demo from this machine: production API and web servers, a free Cloudflare quick tunnel,
# and caffeinate so the machine does not sleep. Changes are open to anyone with the link unless NEURA1_DEMO_PASSCODE is set in api/.env.
#   scripts/serve_public.sh            start everything and print the public URL
#   scripts/serve_public.sh stop       stop everything it started
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="$ROOT/data/logs"; mkdir -p "$LOGS"
CLOUDFLARED="$(command -v cloudflared || echo /usr/local/opt/cloudflared/bin/cloudflared)"

stop() {
  pkill -f "uvicorn neura1.main:app --host 127.0.0.1 --port 8000" || true
  pkill -f "next start --port 3000" || true
  pkill -f "cloudflared tunnel --no-autoupdate --url http://localhost:3000" || true
  pkill -f "caffeinate -dimsu" || true
}
if [[ "${1:-}" == "stop" ]]; then stop; echo "stopped"; exit 0; fi
stop; sleep 1

(cd "$ROOT/api" && nohup uv run uvicorn neura1.main:app --host 127.0.0.1 --port 8000 --workers 1 > "$LOGS/api.log" 2>&1 &)
(cd "$ROOT/web" && pnpm build > "$LOGS/build.log" 2>&1 && nohup pnpm start --port 3000 > "$LOGS/web.log" 2>&1 &)
until curl -s -o /dev/null --max-time 3 http://localhost:3000/; do sleep 2; done
nohup "$CLOUDFLARED" tunnel --no-autoupdate --url http://localhost:3000 > "$LOGS/tunnel.log" 2>&1 &
nohup caffeinate -dimsu > /dev/null 2>&1 &
until grep -qoE "https://[a-z0-9-]+\.trycloudflare\.com" "$LOGS/tunnel.log"; do sleep 2; done
echo "Neura1 is live at $(grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" "$LOGS/tunnel.log" | head -1)"
