# AI assistance disclosure

Graph Hacks allows coding assistants if their use is disclosed. This is that disclosure.

## Tools used

- **Claude Code (Anthropic, Claude Opus 5.5)**: planning, code generation for the API, importer, tests and web app,
  synthetic fixture writing, and documentation drafts.
- **Codex (OpenAI)**: earlier brainstorming of product direction and market research (planning notes only).
- **Open models inside the product** (not used for writing code): ornith-1.5-35b-a3b served by vLLM on an NVIDIA
  DGX Spark, with Qwen2.5-7B-Instruct through Ollama as the automatic fallback, and open-source Whisper for meeting
  audio. They read supplier notices, extract decisions from documents and meetings, and drive the Ask agent. Their
  outputs are verified by code before they enter the graph; raw outputs are saved in `fixture/flyvi/extracted/`.

## What the participant did

<!-- Author: this draft lists only what is on record in the project. Review it, correct it and add anything else
     you wrote, debugged or decided yourself before submitting. -->
- Chose the product and the market: a company brain for hardware manufacturers, built around Flyvi Technologies.
- Supplied the real organisation (directors, leadership, employees) and held the rule that nobody is given a role or
  portfolio beyond what was stated.
- Set the constraints the design follows: open source and zero cost, models on the company's own DGX Spark, synthetic
  records, first names only.
- Set up the NVIDIA DGX Spark serving the model over Tailscale.
- Reviewed the running product throughout and directed changes, including rejecting designs that did not meet the bar.
- Shared the live demo and repository with a mentor and a senior colleague and brought their feedback into the
  product: ERP integration over MCP, a Gantt with deviations, positioning as an add-on, and OpenAI Dots.
- Decided product policy, such as keeping external AI access off by default.

## How correctness is checked

- 120 automated tests on the fixture: BOM roll-ups, revision applicability, cost edge cases, idempotent imports and
  approvals, import validation, rejection of unverifiable model output, permissions (money and leave), timeline
  forecasts, the ERP sync over MCP and the external AI switch.
- `eval/` compares graph answers against a frozen ground-truth question set.
