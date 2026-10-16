# Voltline Controls: synthetic fixture

Everything here is **fictional**: the company, its people, customers, suppliers, manufacturers, and part numbers.

- `records/`: system-of-record CSV exports (ERP/PLM-style). Loaded deterministically.
- `chats/`, `tickets/`, `docs/`: unstructured company knowledge. Decisions and claims are extracted from these, with verbatim evidence spans.
- `inbox/`: the incoming supplier notice that triggers the demo.
- `updates/`: new facts that arrive mid-demo (a bench result in chat and a new quote).
