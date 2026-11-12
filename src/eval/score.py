import csv, json, os, sys, collections
sys.path.insert(0, "src/agents")
from answer import parse_final
runs = sys.argv[1]
csvp = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser("~/cs5187/benchmark_work/questions.csv")
gt = {r["id"]: r["ground_truth_function"] for r in csv.DictReader(open(csvp, encoding="utf-8"))}
by = collections.defaultdict(list)
for l in open(runs, encoding="utf-8"):
    r = json.loads(l)
    o, _ = parse_final(r["final_text"])
    o = o if isinstance(o, dict) else {}
    by[(r["question_id"], r["condition"])].append((o.get("answer_function"), o.get("top3") or []))
conds = ["NOCTX", "SYN-TOOL", "CT-TOOL"]
print(f"{'Q':5}{'ground truth':26}" + "".join(f"{c:24}" for c in conds))
tot = collections.Counter(); flagged = []
for q in sorted(gt):
    line = f"{q:5}{gt[q][:25]:26}"
    for c in conds:
        L = by.get((q, c), [])
        ex = sum(1 for a, _ in L if a == gt[q])
        # top3: credit if gt is in top3 list OR if answer_function itself is correct
        t3 = sum(1 for a, t in L if gt[q] in t or a == gt[q])
        line += f"{f'exact {ex}/{len(L)} top3 {t3}/{len(L)}':24}"
        if c == "NOCTX" and ex >= 2: flagged.append(q)
        if c != "NOCTX": tot[c] += (ex > 0)
    print(line)
print("exact-correct questions:", dict(tot), "| flagged by 2-of-3 no-context rule:", flagged)
