# Evaluation

46 questions about Flyvi with fixed expected answers ([`api/eval/golden.yaml`](../api/eval/golden.yaml)), plus 2 for the updated state. One model, `ornith-1.5-35b-a3b` on a DGX Spark, answers through three systems:

- **Neura1 graph agent**: plans its own steps over FalkorDB with bounded tools and read-only Cypher.
- **Search only**: the best-matching passages from the same documents, then an answer.
- **Whole corpus in the prompt**: every document and record export pasted into one prompt.

An answer passes only if it contains every required fact. Dev questions may be used to tune prompts; held-out questions may not.

## 1. First run, exactly as scored

| System | Passed | Held-out | Dev | Median seconds |
|---|---|---|---|---|
| Neura1 graph agent | **33/46** (72%) | 24/35 | 9/11 | 18 |
| Search only | **29/46** (63%) | 24/35 | 5/11 | 9 |
| Whole corpus in the prompt | **41/46** (89%) | 31/35 | 10/11 | 8 |

## 2. The same answers, rescored against corrected expected answers

Three expected answers no longer matched the records after the company's org changes (each correction is commented in `golden.yaml`: q23 team name, q33 backup, q43 reporting line). Nothing was re-run; the same answers are scored again, for every system.

| System | Passed | Held-out | Dev | Median seconds |
|---|---|---|---|---|
| Neura1 graph agent | **36/46** (78%) | 27/35 | 9/11 | 18 |
| Search only | **28/46** (61%) | 23/35 | 5/11 | 9 |
| Whole corpus in the prompt | **43/46** (93%) | 33/35 | 10/11 | 8 |

## By question type (latest)

| Category | Neura1 graph agent | Search only | Whole corpus in the prompt |
|---|---|---|---|
| absence | 2/2 | 2/2 | 2/2 |
| abstain | 1/2 | 1/2 | 1/2 |
| cost | 5/6 | 3/6 | 4/6 |
| currency | 0/1 | 1/1 | 1/1 |
| decision | 4/4 | 3/4 | 4/4 |
| dependency | 1/1 | 1/1 | 1/1 |
| escalation | 1/1 | 1/1 | 1/1 |
| exposure | 2/4 | 2/4 | 4/4 |
| history | 1/1 | 1/1 | 1/1 |
| notice | 0/1 | 1/1 | 1/1 |
| org | 1/2 | 1/2 | 2/2 |
| ownership | 4/5 | 3/5 | 5/5 |
| people | 2/3 | 0/3 | 3/3 |
| policy | 1/1 | 1/1 | 1/1 |
| project | 2/2 | 2/2 | 2/2 |
| revision_applicability | 2/2 | 2/2 | 2/2 |
| risk | 2/2 | 1/2 | 2/2 |
| supply | 1/1 | 0/1 | 1/1 |
| where_used | 2/3 | 1/3 | 3/3 |
| who_knows | 2/2 | 1/2 | 2/2 |

## What this shows

**At this size, pasting everything into one prompt works.** Flyvi's demo corpus (all documents plus record exports) is
about 10,000 tokens. A strong 35B model can read all of it for every question, and it answered 43 of 46 correctly once
the expected answers were corrected. That is the honest headline: for lookup questions over a company this small, a graph
is not needed to get the answer.

**Where the graph earns its place**

1. **Scale.** A real 200-person manufacturer has years of chat, tickets, ERP exports and documents: millions of tokens.
   That does not fit in a prompt, and the cost and wait of re-reading everything grow with every question. The graph
   agent's prompt stays small because it fetches only what the question needs. The scalable alternative is search, and
   the graph agent beats search-only clearly (36 vs 28 after correction; 33 vs 29 as first scored).
2. **Exact computation.** Cost questions need arithmetic over the bill of materials, stock and quotes. The graph agent
   gets 5 of 6, the whole-corpus prompt 4, search 3. The ₹37,400 figure is computed by code, not by the model.
3. **Permissions.** A whole-corpus prompt cannot keep prices or someone's leave from an engineer: the model has already
   read them. Neura1 filters by the viewer's place in the graph before the model sees anything.
4. **Evidence.** Graph answers cite passages, and a decision only enters the graph after its quotes are checked word for
   word against the source.

**Why the graph agent lost questions in the first run.** Almost all were bugs in the agent's tools rather than limits of
the graph: assemblies and revisions did not resolve (q05, q22, q30), the cost tool sent so much data that the model timed
out (q26), there was no tool for leadership titles or supplier notices (q25, q44), a Cypher hint was missing property
names (q37), and a step limit sized for a laptop model cut answers short. Section 3 re-runs the graph agent after those
fixes.

**Limits of this evaluation.** 46 questions on synthetic data, one model, scored by required facts in the answer. It
shows what each approach gets right on this company, not how they behave on a large one; the scale argument above is
reasoning, not a measurement.

## Every failure (latest)

Failures are listed, not hidden. *Missing* is what the answer should have contained.

### Neura1 graph agent: 10 failed

- **q05** (exposure, heldout) Which planned builds use PDU-28 Rev C?  
  Missing: BO-0412, BO-0421. Answer: _I could not finish within the step limit._
- **q20** (exposure, heldout) How many units already in the field contain NB54360, and on which revision?  
  Missing: 220, one of ['PDU-28-B', 'Rev B']. Answer: _I could not finish within the step limit._
- **q22** (ownership, heldout) Who plans the PDU-28 builds?  
  Missing: Sharath. Answer: _Not recorded. There is no record of who plans the PDU-28 builds. The exposure lookup for PDU-28 returned no builds, and the who_knows and document searches returned no owner or planner for PDU-28 build planning. I did not find anything assi…_
- **q25** (notice, dev) What lead time does the latest notice give for NB54360?  
  Missing: 22. Answer: _I could not finish within the step limit._
- **q26** (cost, heldout) If NB54360 goes to ₹320 per unit, what is the estimated cost increase for planned builds including requalification?  
  Missing: one of ['37400']. Answer: _The model could not complete this question (Request timed out.)._
- **q27** (abstain, heldout) What is the unit price of the CT-1051 CAN transceiver?  
  Missing: forbidden ₹. Answer: _The unit price of the CT-1051 CAN bus transceiver is not recorded. There are no supplier quotes on file (quotes tool returned empty) and no cost is stored in the part record._
- **q30** (where_used, heldout) Which revision of the PSM-28 module is built into BCU-24 Rev A?  
  Missing: one of ['PSM-28-2', 'Rev 2', 'revision 2']. Answer: _Not recorded. The where_used lookups for both PSM-28 and BCU-24 returned no results, so there is no recorded mapping of a PSM-28 revision into BCU-24 Rev A. I could not confirm any revision from the available data._
- **q37** (currency, heldout) Which supplier quotes expire before the end of 2026?  
  Missing: Q-101, Q-102. Answer: _I could not finish within the step limit._
- **q44** (org, heldout) Who is Flyvi's Managing Director, and who is the Director of Finance?  
  Missing: Jayaram, Sathish. Answer: _I could not finish within the step limit._
- **q47** (people, dev) What has Dileep finished recently?  
  Missing: one of ['pilot assembly', 'PDU-28 Rev C units']. Answer: _Nothing is recorded about what Dileep has finished recently. His profile (P-DILEEP) shows no recent activity, tasks, projects, decisions, or topics, and no document, ticket, chat, or recent-changes entry mentions him. If he has done work, i…_

### Search only: 18 failed

- **q01** (where_used, dev) Which released product revisions use NB54360, and how many does each unit contain?  
  Missing: PDU-28-C, BCU-24-A. Answer: _Not recorded. The provided documents mention that NB54360 passes the TR-112 thermal test (TR-112, page 4) and is used as the reference for the NB54361-L pin-compatibility discussion (Slack #hw-power, 2025-03-04), but none of the records sta…_
- **q06** (cost, heldout) How many NB54360 parts do all planned builds need in total?  
  Missing: 480. Answer: _Not recorded. The only planned build on record is **BO-0412** (rev PDU-28-C, qty=100, planned 2026-11-03). However, no record states how many NB54360 parts are used per PDU-28 unit (no BOM or parts-per-unit data is provided), so the total c…_
- **q07** (cost, dev) After using free stock, how many NB54360 do we need to buy for the planned builds?  
  Missing: 420. Answer: _Free stock can be computed, but the total requirement cannot be, because per-build consumption of NB54360 is not recorded. - **Free stock:** stock record NB54360 → on_hand=180, allocated=120 → **60 free** (stock record). - **Planned builds:…_
- **q11** (decision, heldout) Who decided against using NB54361-L, and when?  
  Missing: Vishwas, 2025-03-12. Answer: _The rationale for not using NB54361-L is documented in **TR-112** (2025-03-10), which is the report explaining "why we do not use NB54361-L" (per the Read-first list). However, the records do not name the specific person who made the decisi…_
- **q14** (ownership, dev) Who owns the firmware that depends on NB54360?  
  Missing: Sai. Answer: _Not recorded. The company records do not explicitly state who owns the firmware that depends on NB54360. Relevant context that does not resolve ownership: - HB-ENG-04 §3 requires a firmware review by "the owner of any module that depends on…_
- **q17** (exposure, dev) Which customer orders are exposed to the NB54360 change?  
  Missing: SO-887. Answer: _**SO-881 (Nilgiri, build BO-0412) is exposed to the NB54360 change.** Why: - The NB54360 is the single-sourced regulator in the power stage (PSM-28); a second source (MX-3360 from Sahyadri) is being qualified, and the supplier has raised pr…_
- **q20** (exposure, heldout) How many units already in the field contain NB54360, and on which revision?  
  Missing: 220, one of ['PDU-28-B', 'Rev B']. Answer: _Not recorded. The provided data mentions the NB54360 soft-start only in the context of firmware tuning (Slack #fw-team, 2026-09-08), but no record states how many field units contain the NB54360 or ties that part to a specific revision's fi…_
- **q23** (ownership, heldout) Which team is Satish in?  
  Missing: Testing. Answer: _Satish is in team **T-QA** (people record id=P-SATISH, team_id=T-QA)._
- **q26** (cost, heldout) If NB54360 goes to ₹320 per unit, what is the estimated cost increase for planned builds including requalification?  
  Missing: one of ['37400']. Answer: _**Price increase:** ₹70/unit (₹320 − ₹250) — Supplier notice 2026-10-14. **Build impact:** - **BO-0412** (100 × PDU-28 Rev C, planned 2026-11-03, after the 2026-11-01 effective date): 100 × ₹70 = **₹7,000** — Operations review 2026-09-28. -…_
- **q27** (abstain, heldout) What is the unit price of the CT-1051 CAN transceiver?  
  Missing: forbidden ₹. Answer: _The unit price of the CT-1051 is not recorded. The items record (CT-1051) lists no price, and while the supplier notice (2026-10-14) mentions a new unit price of ₹320, it does not specify which part it applies to._
- **q29** (supply, heldout) Which supplier currently quotes NB54360?  
  Missing: Deccan Components. Answer: _Supplier **S-DECCAN** currently quotes NB54360, via quote **Q-101** (valid 2026-07-01 to 2026-12-31, 250 INR/unit). The earlier quote Q-099 expired 2026-06-30._
- **q30** (where_used, heldout) Which revision of the PSM-28 module is built into BCU-24 Rev A?  
  Missing: one of ['PSM-28-2', 'Rev 2', 'revision 2']. Answer: _Not recorded. The certifications record for BCU-24 Rev A (id=CERT-BCU24A-JSS) references PSM-28 as the retest trigger item but does not specify which PSM-28 revision is built into it._
- **q33** (who_knows, heldout) Who should I ask about pmic_seq.c, and who covers when they are away?  
  Missing: Vinay. Answer: _Ask **Sai** about pmic_seq.c (firmware, including pmic_seq.c, goes to Sai — [Onboarding: hardware and firmware at Flyvi]; also confirmed by task WRK-106 assignee P-SAI and the PDU-48 kickoff notes). There is **no recorded backup/cover for S…_
- **q36** (people, dev) Which projects is Raghavendra working on?  
  Missing: one of ['cost-down', 'cost down', 'PRJ-COSTDOWN']. Answer: _Based on the provided records, there is no project record assigning Raghavendra to work on any project. The only project on file is **PRJ-NILGIRI** (Nilgiri airborne PDU delivery), whose lead is **P-PRAVEEN** (PRJ-NILGIRI), not Raghavendra.…_
- **q41** (risk, heldout) Which part in released products has only one supplier, and how much open order value depends on it?  
  Missing: one of ['6960000', '69.6', '69.60']. Answer: _**Part:** NB54360 — "effectively single-sourced through Deccan Components" (Ambika, 2026-09-28). **Open order value:** Not recorded. The records show the NB54360 feeds PDU-28 builds (BO-0412, 100× PDU-28 Rev C) that supply SO-881 for Nilgir…_
- **q43** (org, heldout) Who reports to Vishwas?  
  Missing: Sai. Answer: _Not recorded. The provided documents do not contain an org chart or explicit reporting lines. The only people record is: - `P-VISHWAS` (Vishwas, Employee, team T-HW) While the records show Vishwas covering Raghavendra's duties, approving Ra…_
- **q46** (people, heldout) What is Pratham currently working on?  
  Missing: one of ['configuration tool', 'channel settings']. Answer: _Not recorded. The only record for Pratham (id=P-PRATHAM) is the people record showing role=Employee on team T-FW, with no task or assignment details._
- **q47** (people, dev) What has Dileep finished recently?  
  Missing: one of ['pilot assembly', 'PDU-28 Rev C units']. Answer: _Not recorded. The only record mentioning Dileep is the people record (id=P-DILEEP, role=Employee, team_id=T-OPS), which contains no information about recent completed work._

### Whole corpus in the prompt: 3 failed

- **q07** (cost, dev) After using free stock, how many NB54360 do we need to buy for the planned builds?  
  Missing: 420. Answer: _**80 NB54360 units need to be bought.** **Planned builds using NB54360** (BOM: PDU-28-C → NB54360, qty=1 each, refdes U12): - BO-0412 (PDU-28-C): 100 units → 100 × NB54360 - BO-0421 (PDU-28-C): 40 units → 40 × NB54360 - BO-0415 (BCU-24-A): …_
- **q26** (cost, heldout) If NB54360 goes to ₹320 per unit, what is the estimated cost increase for planned builds including requalification?  
  Missing: one of ['37400']. Answer: _**Estimated cost increase: ₹14,000 (parts only); requalification adds ₹0.** **Part price increase:** Supplier notice (2026-10-14) raises NB54360 from ₹250 → ₹320, i.e. **+₹70/unit**, effective 2026-11-01. **NB54360 in planned builds** (each…_
- **q27** (abstain, heldout) What is the unit price of the CT-1051 CAN transceiver?  
  Missing: forbidden ₹. Answer: _The unit price of the CT-1051 CAN transceiver is not recorded. The only quotes on file are for NB54360 (Q-101, ₹250) and NB54361-L (Q-102, ₹190) from Deccan Components; no quote exists for CT-1051._

Raw results with every answer and tool call: `api/eval/results/run1/context-base-all-20261017T070743.json`, `api/eval/results/run1/graph-base-all-20261017T072148.json`, `api/eval/results/run1/rag-base-all-20261017T070739.json`
