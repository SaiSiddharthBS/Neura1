# Demo video script (about 3 minutes)

One story, told in order: a supplier notice arrives at Flyvi Technologies on a Monday morning. Record at 1440×900 in the
dark theme, browser zoom 100%, with the graph freshly reset (Import → Reset the demo company). The guided tour
(Overview → *Take the 3-minute tour*) follows the same path, so you can rehearse with it.

Before recording: open http://localhost:3000, choose *Viewing as Hithesh* (CTO), and close other tabs.

| Time | Screen | What to do | What to say |
|---|---|---|---|
| 0:00 | Overview | Let the ripple play | "This is Neura1, the company brain for Flyvi Technologies, a defence and rail electronics maker in Bangalore. At 9 a.m. a supplier raises the price of one 3.3-volt regulator and stretches its lead time to 22 weeks. Watch it ripple through the company: product revisions, builds, customer orders, customers, and the people who own each one. That is one FalkorDB traversal." |
| 0:20 | Overview | Point at *Needs attention* and the greeting | "Neura1 already knows three things need a decision today, and it posted a morning brief to the team on its own." |
| 0:28 | Impact (click *Open the impact*) | Hover the headline numbers | "Three of three builds at risk, three customer orders exposed, one with a penalty clause, and a ₹37,400 cost increase. That number is computed by code from the bill of materials, stock and quotes, not guessed by a model." |
| 0:45 | Impact, red banner | Click a Slack evidence chip | "And the company remembers. The cheaper, pin-compatible part was rejected in March 2025 because it shut down at 68 °C. That decision lived in a Slack thread and a Jira ticket. The model found it in both, and code checked every quote word for word before it entered the graph." |
| 1:05 | Impact, *Who needs to do what* | Scroll the task list; click *Approve* | "Every team gets its task, from Flyvi's own change policy: engineering, the firmware owner, test, procurement, production and sales. Approve once; they land on the Workboard and in each person's day." |
| 1:20 | Chat (#general) | Type `/impact NB54360 320 22` | "The team works inside the brain. Messages become linked knowledge. Slash commands answer from the graph, and replies only show what everyone in the channel may see: here, no rupee figures in a public channel." |
| 1:38 | Signals | Drop `fixture/flyvi/samples/eol_CT-1051.eml` on *Forward an email* | "New information arrives the way it really does: a forwarded email. Neura1 classifies it, reads it, checks it, and the CAN transceiver's impact is ready: one build short, Konkan Naval's order exposed." |
| 1:55 | Documents → *Engineering change notice* | Open it, then *Check facts* on a draft that proposes NB54361-L | "Documents are written with the brain. The change notice is composed from the graph, and the fact checker, rules not a model, catches a rejected part, an expired quote and an obsolete revision, each with its proof." |
| 2:15 | Capability map | Point at *Where Flyvi is thin* | "From recorded work, Neura1 shows what Flyvi is good at and where it is thin: power sequencing is held by one person, and this exact change depends on it. No scores, no rankings, and names only for people allowed to see them." |
| 2:32 | Ask & search | Ask "Who should review pmic_seq.c and who covers when they're away?" | "Ask anything. The agent plans its own graph queries, shows every step and cites its sources." |
| 2:45 | docs/EVAL.md (or README) | Show the blind table | "We published our evaluation, failures included. On eighteen blind questions the graph agent answered fifteen, search alone ten. At this small size, pasting everything into a prompt does about as well; the graph is what still works at a real company's scale, with permissions and evidence." |
| 2:58 | Overview | — | "Neura1: one graph of a company's people, products, customers, documents and decisions. Open source, running on a DGX Spark." |

Tips: keep the cursor still while speaking; cut between scenes rather than waiting for loads; the Ask answer can be
recorded separately and spliced in, since it takes a few seconds on the DGX.
