# Who Neura1 is for

Neura1 is built for **one kind of business first: Indian industrial electronics product companies with
20–300 people**. These companies design their own power electronics, controllers, instruments or embedded systems, often for aerospace, defence and industrial customers, and
have them assembled in-house or at an EMS partner.

This is a deliberate choice. A "company brain for everyone" can't know what a BOM revision is, why a
cross-referenced part isn't approved, or that a late power unit can trigger a penalty clause. A company brain
for this business can.

> Status: this is our target hypothesis. The demo uses Flyvi Technologies, a real company, with synthetic data. We have not yet run
> interviews or pilots. See "What we still need to prove" below.

## The people and the moment

| | |
|---|---|
| **Buyer** | Founder/CEO or Head of Operations, the person who hears about a late order first |
| **Daily users** | Hardware engineering lead, procurement lead, production planner, account managers, quality |
| **Trigger** | A supplier notice: price increase, lead-time jump, end of life, or a last-time-buy date. Notices like this are routine in electronics. |
| **Today** | Procurement forwards the email. Someone opens the BOM spreadsheet, someone else searches Slack for "why did we pick this part", planning finds out late, sales finds out last. Someone suggests the cheaper "pin-compatible" part that engineering rejected two years ago. |
| **With Neura1** | Forward the notice. In seconds every team sees what it affects, what it costs, what was decided before and why, and who has to do what, with the source for every claim. |

## The end-to-end workflow

1. **Bring in the company.** Import the spreadsheets the company already keeps: item master, BOM export, revisions,
   quotes, stock, planned builds, customer orders, owners. Add the places decisions live: Slack exports, tickets,
   test reports and PDFs. The importer checks every row and names the file, row and column of each problem
   before writing anything (`/import`).
2. **A notice arrives.** Neura1 reads it, resolves the part number to the internal item, and checks every number it
   extracted against the notice text.
3. **Trace the impact.** One graph traversal follows the part through sub-assemblies to released product revisions
   (drafts and obsolete revisions excluded, with the reason), then to planned builds, customer orders and contract
   notes, firmware and test dependencies, field units, alternates and quotes.
4. **Recall what the company already decided.** Decisions extracted from chats and tickets, each tied to a
   verbatim quote, show up where they matter: "Do not switch to NB54361-L. It was rejected in DEC-117."
5. **Do the maths, not a guess.** Cost increase from the valid quote, free stock and MOQ, with the formula and
   every assumption and exclusion listed.
6. **Assign the work.** Tasks follow the company's change policy and go to the owners recorded in the graph.
   Approving them stores them in the graph with the evidence version they relied on, with no duplicates and
   still there next session. Copy them as a message for Slack, Teams, WhatsApp or email, or download a CSV.
7. **Keep it current.** When a new quote or test result arrives, import it, and the analysis changes. A chat
   message can propose a part but cannot approve one.

## Why not what they already have?

| Alternative | What it covers | What it misses for this trigger |
|---|---|---|
| PLM (Arena, OpenBOM, Odoo PLM) | BOMs, revisions, change orders | The *why* in Slack and tickets; customer orders and penalties; usually a migration project |
| ERP / Tally / Zoho | Stock, orders, purchasing | Revision-aware BOM structure, engineering rationale |
| Enterprise search / chat assistant | Finding documents | Quantity roll-ups, revision applicability, exact cost; it will happily suggest the rejected part |
| A careful engineer | Everything, eventually | A day of their time, every notice, and the risk of missing one dependency |

Neura1 sits **on top of** the exports a company already has. It does not ask anyone to migrate to a new
system of record.

## What we still need to prove

- That supplier notices cause enough pain often enough (interviews with 10 such companies).
- That the "why" really lives in chats and tickets for these teams.
- Time to the first useful answer on a real company's exports (target: one afternoon).
- Whether incumbents' change-impact features already satisfy them.
