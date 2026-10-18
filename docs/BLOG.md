# We built a company brain on a graph, and published where it lost

*Draft for the Graph Hacks blog post. Numbers are from [docs/EVAL.md](EVAL.md).*

Every manufacturer has the same Monday morning. A supplier email arrives: the price of a small part goes up, the lead
time stretches to 22 weeks. Someone forwards it. Someone searches the BOM spreadsheet. Someone remembers, vaguely, that
the cheaper alternative was tried once and "didn't work out". Sales hears about the late order last.

Neura1 is our attempt to make that morning boring. We built it for one kind of company, a 50–500 person electronics
manufacturer, and modelled one in detail: Flyvi Technologies, a Bengaluru maker of power electronics for aerospace and defence, with its
real leadership structure and synthetic operational data.

## Why a graph

The question "what does this change break?" is a traversal. A regulator sits in a power-stage module, which sits in two
product revisions (but not the obsolete one, and not the draft), which are built in three planned builds, which fulfil
three customer orders, one with a penalty clause, owned by the people who look after those accounts, depending on firmware owned by an engineer
who is on leave in November. In FalkorDB that is one variable-length Cypher query with quantities multiplied along the
path. In a document store it is a week of meetings.

We kept everything in one graph: records (BOM, revisions, quotes, stock, builds, orders, customers, people, teams, leave),
documents and chats split into passages linked to what they mention, and the decisions found in them.

## The parts we are proudest of

- **Decisions with proof.** The model reads Slack threads and Jira tickets and proposes decisions. Code accepts one only if
  every quote it cites appears word for word in the source. The rejected cheap regulator (DEC-117) now carries four
  passages from two systems, and its red banner appears exactly where a busy team would reach for that part.
- **Numbers by code, not by model.** The ₹37,400 cost impact is computed from stock, demand and the valid quote, with
  expired quotes ignored and every assumption listed.
- **Permissions from the org chart.** Who may see money and who may see someone's leave is derived from the graph:
  the organisation's tiers and who backs up whom. The rule follows the data into search, chat replies, the agent and documents. Our own
  evaluation of privacy found a leak (leave notices in search) and we fixed it with a regression test.
- **A brain that acts.** A morning brief at 09:00, a mail drop that turns a forwarded supplier email into an analysed
  signal, chat that posts plans and finished work to the right channel.
- **People analytics, carefully.** The capability map shows what the company is good at from recorded work, with no
  scores or rankings, and names only for people allowed to see them.

## Four things a search box cannot do

- **Never the same mistake twice.** Chat checks a message against recorded decisions while it is typed. Suggest the
  part the company rejected in 2025 and the decision appears, with the Slack messages that prove it, before you send.
- **A sandbox for the whole company.** FalkorDB's `GRAPH.COPY` copies the company graph in about a tenth of a second.
  A scenario (a supplier change, an engineer away, a bigger order) runs on the copy, each change alone and then together,
  and the copy is thrown away. The interesting results are the ones that only appear in combination: the regulator
  change needs a firmware review from the one person who will be away that month.
- **Can we promise this?** A delivery date checked across the bill of materials, free stock, the newest lead time on
  record, people, knowledge and certifications. Stock and quotes alone said yes to 50 units by December; a supplier
  notice from the day before made the honest answer April.
- **Knowledge rescue.** Before someone leaves, Neura1 interviews them with questions built from the graph and keeps the
  answers as linked, searchable knowledge. The model only helps with follow-up questions and facts it can quote.

## The evaluation, including where we lost

We wrote expected answers before running anything and compared three systems on the same model (ornith-1.5-35b-a3b on a
DGX Spark): our graph agent, search over passages, and the whole corpus pasted into one prompt.

| | Graph agent | Search only | Whole corpus |
|---|---|---|---|
| First run, 46 questions | 33 | 29 | 41 |
| After fixing stale answers and a scorer bug | 37 | 28 | 43 |
| Blind set, 18 new questions, run once | 15 | 10 | 16 |

The honest headline: our demo company is about 10,000 tokens, so a strong model can simply read all of it, and it did
about as well as the graph on lookups. The first run was worse for us than that table suggests, and the reasons were
instructive: every failure we traced was in the agent's *tools* (a revision that did not resolve, a tool that returned so
much data the model timed out), not in the graph. After fixing them the agent answered all 46 development questions, which
is exactly why we then wrote a blind set.

What the numbers do show: the graph agent is far ahead of search, which is what remains when a real company's data stops
fitting in a prompt; cost questions, which need arithmetic, went 6 of 6 for the graph after the tool fixes (whole corpus 4, search 3); and no prompt-stuffing approach can
keep prices or someone's leave away from a reader who should not see them.

We also found a bug in our own scorer: it stripped the "₹" sign before checking that an abstaining answer contained no
price, so that question could never pass for anyone. We fixed it and rescored every saved answer.

## What we would do next

Connectors for real ERP and PLM exports, a blind evaluation at a larger scale, and per-person briefs. The core idea will
stay: one graph, every claim with its evidence, and permissions that follow the data.

*Neura1 is open source (AGPL-3.0) and runs entirely on open models and FalkorDB.*
