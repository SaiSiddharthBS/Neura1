**What the blind set shows.** On questions nobody had seen, the whole-corpus prompt answered 16 of 18 and the graph
agent 15 of 18; search alone answered 10. At this demo's size (about 10k tokens) reading everything is as good as the
graph for lookups, and the graph agent is far ahead of search, which is what remains when a company's data no longer fits
in a prompt. The 46/46 in section 3 is therefore a development result; the blind 15/18 is the honest number.

The graph agent's three blind misses were gaps in its tools, not in the graph: the quote tool's "all quotes" view left out
the minimum order quantity and a quote id was not accepted (b04), there was no tool for certifications and what must be
retested (b08), and the person tool did not return stated skills (b14). All three are fixed in `api/neura1/agent.py` after
this run. The blind result above is unchanged; a further blind set would be needed to measure the fixes.
