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
