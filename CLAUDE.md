# Neura1

Neura1 is a company brain for hardware manufacturers, built on FalkorDB, with Flyvi Technologies (part of Datasol
(Bangalore) Limited) as the reference company and synthetic demo data.

**Start every session by reading `docs/STATUS.md`**: where the project stands, how it runs, what is left and the
decisions to keep. Update it at the end of the session with what changed and what is next.

## Rules

- Never print, log or commit secrets. They live only in `api/.env` (gitignored). The DGX API key is never shown.
- Never invent a role, title, department or portfolio for anyone. The organisation is fixed in `docs/STATUS.md`.
- Synthetic records only; customers fictional; first names only; no leave reasons; they/them for anyone unstated.
- Free and open-source tools only, self-hosted; nothing leaves the building unless leadership switches it on.
- Model output is verified by code; numbers are computed. Never hand-edit `fixture/flyvi/extracted/` snapshots.
- Do not publish, submit, or contact anyone without the author's explicit go-ahead. Do not push without being asked.
- The live demo may be in use: test changes on a separate graph (`NEURA1_GRAPH_NAME=flyvi_dev`) and other ports first.

## Working on it

```bash
cd api && uv sync && uv run pytest -q             # 122 tests
api/.venv/bin/uvicorn neura1.main:app --port 8000  # API (use the venv's uvicorn, not the system one)
cd web && pnpm lint && npx tsc --noEmit && pnpm build && pnpm start --port 3000
uv run python -m neura1.docs                       # regenerate docs/queries.md after changing Cypher
```

Commits: author SaiSiddharthBS <saisiddharthbs@gmail.com>, with the co-author line the session specifies.
