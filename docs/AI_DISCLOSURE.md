# AI assistance disclosure

Graph Hacks allows coding assistants if their use is disclosed. This is that disclosure.

## Tools used

- **Claude Code (Anthropic, Claude Opus 5.5)**: planning, code generation for the API, importer, tests and web app,
  synthetic fixture writing, and documentation drafts.
- **Codex (OpenAI)**: earlier brainstorming of product direction and market research (planning notes only).
- **Local open-source model inside the product** (not used for writing code): Qwen2.5-7B-Instruct through Ollama
  (and, when available, a DGX Spark). It reads supplier notices, extracts decisions from documents, and drives the
  Ask agent. Its outputs are verified by code before they enter the graph; raw outputs are saved in
  `fixture/voltline/extracted/`.

## What the participant did

<!-- TODO(author): replace with your own honest account before submitting. For example: -->
- Chose the target customer and product direction (with mentor input).
- Reviewed and verified the graph model, the Cypher queries and the cost logic, and ran the tests.
- <!-- Write which parts you changed, debugged or wrote yourself, and which design decisions you made. -->

## How correctness is checked

- 17+ automated tests on the fixture: BOM roll-ups, revision applicability, cost edge cases, idempotent imports and
  approvals, import validation, and rejection of unverifiable model output.
- `eval/` compares graph answers against a frozen ground-truth question set.
