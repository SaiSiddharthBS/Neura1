# Prior work and reuse

**Neura1** is an existing project name and vision of the author: an "enterprise company brain". An earlier,
separate Neura1 codebase (a document-intelligence app with RAG over ChromaDB, document editing and chat) was
written in June 2026, before Graph Hacks. It is **not** part of this submission.

This repository was created on **16 October 2026**, during the event. All code here was written during the
event, including:

- the FalkorDB graph model, loaders, importer and validator
- every Cypher query
- the change-impact service, cost engine, actions/investigations
- model extraction with verbatim-quote verification
- the web app
- the synthetic Flyvi fixture

**Carried over from before the event:**
- the Neura1 name;
- the logo;
- the company-brain idea and planning notes;
- the visual design language: dark "obsidian glass" palette, azure accent, Inter/JetBrains Mono pairing and a floating sidebar. It was re-implemented here as new Tailwind tokens and components; no stylesheet or component code was copied.
**Not carried over:** no source code, UI, database schema, or data from the earlier codebase.

Third-party libraries are listed in `api/pyproject.toml` and `web/package.json`. The document editor uses
[SuperDoc](https://github.com/Harbour-Enterprises/superdoc), which is licensed under AGPL-3.0; anyone running a
modified Neura1 as a network service must offer its source under the same terms.
