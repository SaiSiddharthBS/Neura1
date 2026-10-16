# Flyvi Technologies: demo company data

Flyvi Technologies Pvt. Ltd. and its parent, Datasol (Bangalore) Limited, are real companies. Flyvi designs and
builds power distribution units, power converters, battery chargers and embedded control systems for aerospace
and defence.

**Everything in this folder is synthetic demo data:** products, part numbers, suppliers, customers, orders,
quotes, decisions, tickets, chats, leave and task history. People appear by first name only. Customers are fictional.

- `records/`: system-of-record CSV exports. Organisation, teams, people, reporting lines, skills, items,
  revisions, BOM, quotes, stock, builds, orders, projects, tasks, leave, certifications. Loaded deterministically.
- `chats/`, `tickets/`, `docs/`: unstructured company knowledge. Decisions and meeting action items are extracted
  from these, with verbatim evidence.
- `inbox/`: signals. A supplier notice, a customer escalation and a leave notice.
- `updates/`: new facts that arrive mid-demo (a bench result in chat and a new quote).
- `extracted/`: raw model outputs, replayed and verified on load.
