"""Turn evaluation results into docs/EVAL.md. Nothing is hidden: the first run as scored, the same answers rescored
against the corrected expected answers, the graph agent after its tool fixes, and every failure.

  uv run python eval/report.py
"""

import json
from collections import defaultdict
from pathlib import Path

import yaml

from eval.run_eval import score

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "docs" / "EVAL.md"
NAMES = {"graph": "Neura1 graph agent", "rag": "Search only", "context": "Whole corpus in the prompt"}
ORDER = ("graph", "rag", "context")


def load(folder: Path, split: str = "all") -> dict[str, dict]:
    runs: dict[str, dict] = {}
    for path in sorted(folder.glob(f"*-base-{split}-*.json")):
        data = json.loads(path.read_text())
        runs[data["system"]] = data | {"file": str(path.relative_to(HERE.parent))}
    return runs


def rescored(run: dict, cases: dict) -> list[dict]:
    out = []
    for r in run["results"]:
        ok, why = score(cases[r["id"]], r["answer"]) if r["id"] in cases else (r["pass"], r["missing"])
        out.append(r | {"pass": ok, "missing": why})
    return out


def row(name: str, results: list[dict]) -> str:
    split = lambda s: (sum(x["pass"] for x in results if x["split"] == s), sum(x["split"] == s for x in results))
    h, d = split("heldout"), split("dev")
    secs = sorted(x["seconds"] for x in results)
    passed = sum(x["pass"] for x in results)
    return (f"| {name} | **{passed}/{len(results)}** ({round(100 * passed / max(len(results), 1))}%) | {h[0]}/{h[1]} | "
            f"{d[0]}/{d[1]} | {secs[len(secs) // 2]:.0f} |")


def main() -> None:
    cases = {c["id"]: c for c in yaml.safe_load((HERE / "golden.yaml").read_text())}
    run1 = load(HERE / "results" / "run1")
    run2 = load(HERE / "results")
    model = next(iter(run1.values()))["model"]
    head = "| System | Passed | Held-out | Dev | Median seconds |\n|---|---|---|---|---|"
    lines = [
        "# Evaluation", "",
        f"46 questions about Flyvi with fixed expected answers ([`api/eval/golden.yaml`](../api/eval/golden.yaml)), plus 2 "
        f"for the updated state. One model, `{model}` on a DGX Spark, answers through three systems:", "",
        "- **Neura1 graph agent**: plans its own steps over FalkorDB with bounded tools and read-only Cypher.",
        "- **Search only**: the best-matching passages from the same documents, then an answer.",
        "- **Whole corpus in the prompt**: every document and record export pasted into one prompt.", "",
        "An answer passes only if it contains every required fact. Dev questions may be used to tune prompts; held-out "
        "questions may not.", "",
        "## 1. First run, exactly as scored", "", head]
    lines += [row(NAMES[k], run1[k]["results"]) for k in ORDER if k in run1]
    lines += ["", "## 2. The same answers, rescored after two corrections", "",
              "1. Three expected answers no longer matched the records after the company's org changes (each correction "
              "is commented in `golden.yaml`: q23 team name, q33 backup, q43 reporting line).",
              "2. A scorer bug: forbidden text was normalised like the answer, which turned the forbidden `₹` into an "
              "empty string that matches everything, so the abstain question q27 could never pass for any system "
              "(fixed in `run_eval.py`, with a test).", "",
              "Nothing was re-run; the same saved answers are scored again, for every system.", "", head]
    lines += [row(NAMES[k], rescored(run1[k], cases)) for k in ORDER if k in run1]
    if "graph" in run2:
        lines += ["", "## 3. Graph agent after fixing its tools", "",
                  "The first run exposed bugs in the agent's tools, not in the graph: assemblies and revisions did not "
                  "resolve, the cost tool sent so much data that the model timed out, there was no tool for leadership "
                  "titles or notices, and a step limit sized for a laptop model. These were fixed in code (see "
                  "`api/neura1/agent.py`) and the graph agent was run again. These fixes were found by reading held-out "
                  "failures, so treat this as a development result, not a blind one.", "", head,
                  row(NAMES["graph"] + " (after fixes)", rescored(run2["graph"], cases))]
        lines += [row(NAMES[k] + " (rescored, unchanged)", rescored(run1[k], cases)) for k in ("rag", "context") if k in run1]
    blind = load(HERE / "results", "blind")
    if blind:
        lines += ["", "## 4. Blind set: 18 new questions, one run, as scored", "",
                  "Written after the tool fixes and before any system saw them; expected answers were checked against "
                  "the records. Each system answered once and nothing was changed afterwards.", "", head]
        lines[-1] = "| System | Passed | Median seconds |\n|---|---|---|"
        for k in ORDER:
            if k in blind:
                res = blind[k]["results"]
                secs = sorted(x["seconds"] for x in res)
                passed = sum(x["pass"] for x in res)
                lines.append(f"| {NAMES[k]} | **{passed}/{len(res)}** ({round(100 * passed / len(res))}%) | {secs[len(secs) // 2]:.0f} |")
        lines += ["", "{blind_analysis}"]
        for key in ORDER:
            if key not in blind:
                continue
            fails = [x for x in blind[key]["results"] if not x["pass"]]
            lines += ["", f"**{NAMES[key]}, blind failures ({len(fails)}):**", ""]
            for x in fails:
                ans = " ".join(str(x["answer"]).split())
                lines.append(f"- **{x['id']}** {x['question']} Missing: {', '.join(map(str, x['missing']))}. "
                             f"Answer: _{ans[:200]}{'…' if len(ans) > 200 else ''}_")
    final = {"graph": rescored(run2["graph"], cases) if "graph" in run2 else rescored(run1["graph"], cases)}
    final |= {k: rescored(run1[k], cases) for k in ("rag", "context") if k in run1}
    lines += ["", "## By question type (latest)", "", "| Category | " + " | ".join(NAMES[k] for k in ORDER if k in final) + " |",
              "|---|" + "---|" * len(final)]
    cats: dict[str, dict[str, list]] = defaultdict(dict)
    for key, res in final.items():
        for x in res:
            cats[x["category"]].setdefault(key, []).append(x["pass"])
    for cat in sorted(cats):
        lines.append(f"| {cat} | " + " | ".join(f"{sum(cats[cat].get(k, []))}/{len(cats[cat].get(k, []))}"
                                                 for k in ORDER if k in final) + " |")
    lines += ["", "## What this shows", "", "{analysis}", "", "## Every failure (latest)", "",
              "Failures are listed, not hidden. *Missing* is what the answer should have contained.", ""]
    for key in ORDER:
        if key not in final:
            continue
        fails = [x for x in final[key] if not x["pass"]]
        lines += [f"### {NAMES[key]}: {len(fails)} failed", ""]
        for x in fails:
            ans = " ".join(str(x["answer"]).split())
            lines.append(f"- **{x['id']}** ({x['category']}, {x['split']}) {x['question']}  \n  Missing: "
                         f"{', '.join(map(str, x['missing'])) or '—'}. Answer: _{ans[:240]}{'…' if len(ans) > 240 else ''}_")
        lines.append("")
    files = [r["file"] for r in run1.values()] + [r["file"] for r in run2.values()] + [r["file"] for r in blind.values()]
    lines += ["Raw results with every answer and tool call: " + ", ".join(f"`api/{f}`" for f in files), ""]
    text = "\n".join(lines)
    analysis_path = HERE / "analysis.md"
    text = text.replace("{analysis}", analysis_path.read_text().strip() if analysis_path.exists() else "_Pending._")
    blind_path = HERE / "blind_analysis.md"
    text = text.replace("{blind_analysis}", blind_path.read_text().strip() if blind_path.exists() else "")
    OUT.write_text(text)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
