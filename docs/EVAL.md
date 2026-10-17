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

## 2. The same answers, rescored after two corrections

1. Three expected answers no longer matched the records after the company's org changes (each correction is commented in `golden.yaml`: q23 team name, q33 backup, q43 reporting line).
2. A scorer bug: forbidden text was normalised like the answer, which turned the forbidden `₹` into an empty string that matches everything, so the abstain question q27 could never pass for any system (fixed in `run_eval.py`, with a test).

Nothing was re-run; the same saved answers are scored again, for every system.

| System | Passed | Held-out | Dev | Median seconds |
|---|---|---|---|---|
| Neura1 graph agent | **37/46** (80%) | 28/35 | 9/11 | 18 |
| Search only | **28/46** (61%) | 23/35 | 5/11 | 9 |
| Whole corpus in the prompt | **43/46** (93%) | 33/35 | 10/11 | 8 |

## 3. Graph agent after fixing its tools

The first run exposed bugs in the agent's tools, not in the graph: assemblies and revisions did not resolve, the cost tool sent so much data that the model timed out, there was no tool for leadership titles or notices, and a step limit sized for a laptop model. These were fixed in code (see `api/neura1/agent.py`) and the graph agent was run again. These fixes were found by reading held-out failures, so treat this as a development result, not a blind one.

| System | Passed | Held-out | Dev | Median seconds |
|---|---|---|---|---|
| Neura1 graph agent (after fixes) | **46/46** (100%) | 35/35 | 11/11 | 6 |
| Search only (rescored, unchanged) | **28/46** (61%) | 23/35 | 5/11 | 9 |
| Whole corpus in the prompt (rescored, unchanged) | **43/46** (93%) | 33/35 | 10/11 | 8 |

## 4. Blind set: 18 new questions, one run, as scored

Written after the tool fixes and before any system saw them; expected answers were checked against the records. Each system answered once and nothing was changed afterwards.

| System | Passed | Median seconds |
|---|---|---|
| Neura1 graph agent | **15/18** (83%) | 6 |
| Search only | **10/18** (56%) | 3 |
| Whole corpus in the prompt | **16/18** (89%) | 4 |

**What the blind set shows.** On questions nobody had seen, the whole-corpus prompt answered 16 of 18 and the graph
agent 15 of 18; search alone answered 10. At this demo's size (about 10k tokens) reading everything is as good as the
graph for lookups, and the graph agent is far ahead of search, which is what remains when a company's data no longer fits
in a prompt. The 46/46 in section 3 is therefore a development result; the blind 15/18 is the honest number.

The graph agent's three blind misses were gaps in its tools, not in the graph: the quote tool's "all quotes" view left out
the minimum order quantity and a quote id was not accepted (b04), there was no tool for certifications and what must be
retested (b08), and the person tool did not return stated skills (b14). All three are fixed in `api/neura1/agent.py` after
this run. The blind result above is unchanged; a further blind set would be needed to measure the fixes.

**Neura1 graph agent, blind failures (3):**

- **b04** What is the minimum order quantity on quote Q-102, and which part is it for? Missing: 250. Answer: _Quote Q-102 is for part **NB54361-L** (Buck regulator 3.3V 3A, low-cost, Northbridge Semi). The quote itself (Q-102) has no minimum order quantity recorded — the only MOQ on record is 100, but that is…_
- **b08** Which certifications must be retested if the PSM-28 module changes? Missing: one of ['CERT-PDU28C-461', 'EMI/EMC'], one of ['CERT-PDU28C-704', 'aircraft power'], one of ['CERT-BCU24A-JSS', 'environmental']. Answer: _A change to the PSM-28 module requires re-testing under two records: **1. TP-PSM-07 (power stage thermal and load qualification)** — required for any change to the regulator, inductor, or output capac…_
- **b14** Which skills has Vinay stated? Missing: Embedded C. Answer: _Not recorded. There is nothing in the records about Vinay stating any skills. The person record for Vinay (P-VINAY) lists his role (Software team), project (Firmware 2.4 release, CAN and comms), and a…_

**Search only, blind failures (8):**

- **b02** Which project does Pruthvi work on? Missing: Firmware 2.4. Answer: _Not recorded. The only record for Pruthvi is the people record (id=P-PRUTHVI, team_id=T-FW), which lists a team but no project assignment. No task or other record links Pruthvi to a specific project._
- **b03** Who covers for Keerthana when Keerthana is away? Missing: Praveen. Answer: _Not recorded. The provided documents mention Keerthana's role (Employee, team T-SALES) and her involvement in the Konkan Naval BCU-24 escalation, but there is no record of who covers for her when she …_
- **b07** Which team is Gurumurthy in? Missing: Quality Assurance. Answer: _Gurumurthy is in team **T-QAD** (people record id=P-GURUMURTHY)._
- **b10** Who reports directly to Markande? Missing: Sharath, Ambika, Tejaswini. Answer: _P-PRAVEEN and P-GURUMURTHY report directly to Markande. - reports_to: person_id=P-PRAVEEN, manager_id=P-MARKANDE - reports_to: person_id=P-GURUMURTHY, manager_id=P-MARKANDE_
- **b13** What is the unit price of the PSM-28 power stage module? Missing: forbidden ₹. Answer: _Not recorded. The supplier notice (2026-10-14) states a new unit price of ₹320 (previously ₹250), but it does not identify which part or component the price applies to. There is no record linking that…_
- **b14** Which skills has Vinay stated? Missing: Embedded C, CAN bus. Answer: _Not recorded. The provided skills records only list skills for P-RAGHAVENDRA (Power stage design, Thermal derating, DC-DC converters). No skills are recorded for P-VINAY._
- **b15** Which product revisions use the CT-1051 CAN transceiver? Missing: one of ['BCU-24-A', 'BCU-24 Rev A', 'BCU-24 revision A']. Answer: _Based on the records, the CT-1051 CAN transceiver is associated with the **BCU-24** (SUP-1057), which logs CAN telemetry drops during cold-start inrush. However, **no specific product revision is reco…_
- **b18** Who reports to Sharath? Missing: Dileep, Pradeep. Answer: _No one reports to Sharath. The `reports_to` records show managers P-JAYARAM, P-ANIL, and P-MARKANDE, but no record lists P-SHARATH as a manager._

**Whole corpus in the prompt, blind failures (2):**

- **b10** Who reports directly to Markande? Missing: Praveen. Answer: _P-GURUMURTHY, P-SHARATH, P-AMBIKA, and P-TEJASWINI report directly to P-MARKANDE (reports_to records)._
- **b13** What is the unit price of the PSM-28 power stage module? Missing: forbidden ₹. Answer: _Not recorded. The records contain pricing only for the NB54360 part (quotes Q-099 at ₹230, Q-101 at ₹250), not for the PSM-28 assembly itself._

## By question type (latest)

| Category | Neura1 graph agent | Search only | Whole corpus in the prompt |
|---|---|---|---|
| absence | 2/2 | 2/2 | 2/2 |
| abstain | 2/2 | 1/2 | 1/2 |
| cost | 6/6 | 3/6 | 4/6 |
| currency | 1/1 | 1/1 | 1/1 |
| decision | 4/4 | 3/4 | 4/4 |
| dependency | 1/1 | 1/1 | 1/1 |
| escalation | 1/1 | 1/1 | 1/1 |
| exposure | 4/4 | 2/4 | 4/4 |
| history | 1/1 | 1/1 | 1/1 |
| notice | 1/1 | 1/1 | 1/1 |
| org | 2/2 | 1/2 | 2/2 |
| ownership | 5/5 | 3/5 | 5/5 |
| people | 3/3 | 0/3 | 3/3 |
| policy | 1/1 | 1/1 | 1/1 |
| project | 2/2 | 2/2 | 2/2 |
| revision_applicability | 2/2 | 2/2 | 2/2 |
| risk | 2/2 | 1/2 | 2/2 |
| supply | 1/1 | 0/1 | 1/1 |
| where_used | 3/3 | 1/3 | 3/3 |
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
   the graph agent beats search-only clearly: 33 vs 29 as first scored, 37 vs 28 after the corrections, 46 vs 28 after the tool fixes.
2. **Exact computation.** Cost questions need arithmetic over the bill of materials, stock and quotes. The graph agent
   gets 6 of 6 after the tool fixes (5 before), the whole-corpus prompt 4, search 3. The ₹37,400 figure is computed by code, not by the model.
3. **Permissions.** A whole-corpus prompt cannot keep prices or someone's leave from an engineer: the model has already
   read them. Neura1 filters by the viewer's place in the graph before the model sees anything.
4. **Evidence.** Graph answers cite passages, and a decision only enters the graph after its quotes are checked word for
   word against the source.

**After the tool fixes, the graph agent answered all 46**, with a median of 6 seconds (whole corpus: 43, 8 seconds;
search: 28). Read that with care. The fixes were found by studying held-out failures, so 46/46 is a development result,
not a blind test, and 46 questions is a small set. What it does show is that the remaining gap was in the agent's tools,
not in the graph: once the tools could reach revisions, builds, leadership titles and notices, the graph answered everything,
and the cost questions stay exact because code does the arithmetic. Section 4 is that blind check: 18 new questions,
where the graph agent answered 15.

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

### Neura1 graph agent: 0 failed


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

Raw results with every answer and tool call: `api/eval/results/run1/context-base-all-20261017T070743.json`, `api/eval/results/run1/graph-base-all-20261017T072148.json`, `api/eval/results/run1/rag-base-all-20261017T070739.json`, `api/eval/results/graph-base-all-20261017T084236.json`, `api/eval/results/context-base-blind-20261017T100807.json`, `api/eval/results/graph-base-blind-20261017T101406.json`, `api/eval/results/rag-base-blind-20261017T100817.json`
