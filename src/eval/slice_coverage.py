import csv, os, re, sys
sys.path.insert(0, "src")
from tools.graph_slice import graph_slice
CSV = os.path.expanduser("~/cs5187/benchmark_work/questions.csv")
DB = {"SYN": "src/graphs/graph_syn.db", "CT": "src/graphs/graph_ct_v2.db"}
rows = list(csv.DictReader(open(CSV, encoding="utf-8")))
out = [["question", "graph", "entry", "ground_truth", "gt_in_slice", "slice_chars", "tokens", "stopped_by"]]
shown = False
for r in rows:
    for g, db in DB.items():
        try:
            s = graph_slice(db, r["entry_function"], budget_tokens=6000)
            if not shown:
                print("graph_slice returns keys:", list(s.keys()) if isinstance(s, dict) else type(s)); shown = True
            t = s["text"]
            hit = bool(re.search(r"\b" + re.escape(r["ground_truth_function"]) + r"\b", t))
            out.append([r["id"], g, r["entry_function"], r["ground_truth_function"], hit, len(t), s["tokens"], s["stopped_by"]])
        except Exception as e:
            out.append([r["id"], g, r["entry_function"], r["ground_truth_function"], False, 0, 0, repr(e)[:80]])
for row in out:
    print(" | ".join(str(x) for x in row))
csv.writer(open("results/slice_coverage.csv", "w", newline="", encoding="utf-8")).writerows(out)
