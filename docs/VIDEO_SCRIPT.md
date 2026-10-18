# Demo video script (about 3 minutes)

One story, told in order: a supplier notice arrives at Flyvi Technologies on a Monday morning. Record at 1440×900 in the
dark theme, browser zoom 100%, with the graph freshly reset (Import → Reset the demo company). The guided tour
(Overview → *Take the tour*) covers the same ground, so you can rehearse with it.

Before recording: open http://localhost:3000, choose *Viewing as Hithesh* (CTO), and close other tabs.

| Time | Screen | What to do | What to say |
|---|---|---|---|
| 0:00 | Overview | Let the ripple play, then hover a build and click it | "This is Neura1, a company brain for hardware manufacturers, shown on Flyvi Technologies, a Bengaluru maker of power electronics for aerospace and defence. Every record you will see is synthetic. A supplier raises the price of one 3.3-volt regulator and stretches its lead time to 22 weeks. Watch it ripple through the company: revisions, builds, customer orders, customers, the people who own each one. One FalkorDB traversal." |
| 0:18 | Impact (click *Open the impact*) | Hover the headline numbers, then the red banner | "Three of three builds at risk, three orders exposed, one with a penalty clause, ₹37,400 computed by code. And the company remembers: the cheaper pin-compatible part was rejected in March 2025 because it shut down at 68 °C, found in Slack and Jira and checked word for word." |
| 0:38 | Chat, #engineering | Type `Can we go for NB54361-L to save cost?` and pause | "Most companies lose this the moment someone new suggests it. Here, before I even send, Neura1 stops me with the decision and the two messages that prove it. Sending anyway takes a second Enter, and Neura1 answers in the thread so everyone sees why. Never the same mistake twice." |
| 0:58 | Can we promise? | Click *50 × PDU-28 by 31 Dec* | "Sales wants to promise fifty units by the end of December. Stock and quotes say yes. Neura1 says no: yesterday's supplier notice moved the lead time to 22 weeks, so the honest date is April. It says what would change the answer." |
| 1:15 | Timeline (click *Only deviations*, then SO-881) | Let the bars grow; follow the red line from BO-0412 to SO-881 | "The whole plan on one Gantt. The outline is the original plan, red is what will really happen, worked out by code from stock, open orders, supplier notices and leave. The Nilgiri order ships a hundred and forty-two days late, because BO-0412 waits for the regulator; the same date Can we promise gives. Every slip explains itself." |
| 1:35 | Connections → *Preview changes* → *Sync now* | Point at the field changes, then reopen the Timeline | "Neura1 is an add-on to the ERP and planner a company already uses. It reads Zoho over MCP, finds exactly what changed, field by field, validates it and loads only that: a due date moved in Zoho now shows against the original plan. The other way round, OpenAI Dots and other agents can ask Neura1 through a protected MCP endpoint, with a person's permissions." |
| 2:00 | Sandbox | Click *The perfect storm* | "Before deciding, try it on a copy of the company. FalkorDB copies the whole graph in a tenth of a second. Three changes at once, each alone and then together, and Neura1 shows what only the combination breaks: the firmware review lands on Sai in exactly the weeks Sai is away." |
| 2:22 | Organisation, then the sidebar *Demo* switch | Switch from Hithesh to Keerthana on Can we promise? | "Permissions come from the graph. The directors and leadership see amounts and leave plans; an employee sees the same answer without them. Chat, documents, the agent and the sandbox follow the same rule." |
| 2:38 | docs/EVAL.md | Show the blind table | "We published our evaluation, failures included. On eighteen blind questions the graph agent answered fifteen, search alone ten. At this size, pasting everything into a prompt does about as well; the graph is what still works at a real company's scale, with permissions and evidence." |
| 2:55 | Overview | — | "Neura1: one graph of a company's people, products, customers, documents and decisions, that remembers, shows where the plan is slipping, works alongside the ERP and the agents a team already uses, and keeps what people know. Open source, running on a DGX Spark." |

Tips: keep the cursor still while speaking; cut between scenes rather than waiting for loads; the Ask answer can be
recorded separately and spliced in, since it takes a few seconds on the DGX.

## Extended cut (about 70 seconds more)

| Screen | What to do | What to say |
|---|---|---|
| Knowledge rescue | Pick Sai, answer the pmic_seq.c question, wait for the facts | "So capture what only Sai knows, before November. The questions come from the graph. The answer becomes company knowledge, linked to the firmware and the regulator. Our DGX Spark reads it, keeps only facts it can quote word for word, and asks the follow-up a good engineer would." |
| Inventory → NB54360 → *Draft purchase order* | Let the panel open; point at the saving and the warnings; approve | "Neura1 doesn't just warn, it drafts the order: six hundred units, from the valid quote, before the price rises on the first of November, which saves forty-two thousand rupees. It says honestly that at twenty-two weeks this order cannot save the November builds, sizes a last-time-buy from real usage, and refuses the rejected part. A leader approves; stock, promises and the sandbox count it at once." |
| Meetings → *Try the sample* | Let it process; click the first decision | "A build meeting, recorded. Whisper runs on our own machine, primed with Flyvi's names and part numbers; the DGX finds the decisions and action items, and keeps only what it can quote from the transcript. Click a decision and you hear the moment it was made." |
| Knowledge health → Buying guide | Expand; click *Ask Ambika to update it* | "And it keeps our documents honest. This buying guide still says six weeks and still suggests the rejected part. Each stale sentence, with its proof, goes to the person who maintains the page." |
