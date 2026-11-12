#!/usr/bin/env python3
"""Error analysis for wrong answers.

Classifies every Qwen answer (across all tool/text conditions) into:
  callback_gap   – ground truth has no path from entry in either graph
                   (Q001, Q004 — callback pointer gap, confirmed by slice_coverage)
  default_entry  – model answered the entry function itself (sqlite3Select / sqlite3_step)
  not_in_slice   – GT is in the graph but model named something else; GT was present in slice
  wrong_other    – GT is in graph, not a default-to-entry; catch-all

Run from repo root:
    python src/eval/error_analysis.py

Writes: results/error_analysis.md  (also prints to stdout)
"""
import collections, csv, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC  = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SRC, "tools"))
import graph_tools as gt

CSV_PATH  = os.path.expanduser("~/cs5187/benchmark_work/questions.csv")
JSONL     = "results/runs_qwen3-coder-30b-a3b-instruct.jsonl"
DBS = {
    "SYN": "src/graphs/graph_syn.db",
    "CT":  "src/graphs/graph_ct_v2.db",
}

# Questions where the GT is unreachable from entry in both graphs
# because the edge crosses a callback pointer (confirmed by slice_coverage)
CALLBACK_GAP_QS = {"Q001", "Q004"}

TOOL_CONDS  = {"SYN-TOOL", "CT-TOOL", "CT-ct_calls", "CT-ct_types",
               "CT-source_only", "SYN-source_only"}
TEXT_CONDS  = {"SYN-TEXT", "CT-TEXT"}
SKIP_CONDS  = {"NOCTX"}   # no-context baseline — excluded from error analysis

def load_gt():
    return {r["id"]: {"gt": r["ground_truth_function"],
                      "entry": r["entry_function"]}
            for r in csv.DictReader(open(CSV_PATH, encoding="utf-8"))}

def gt_in_graph(qid, gt_fn, graph_key):
    """True if the GT function appears as a node in the given graph."""
    g = gt._g(DBS[graph_key])
    return bool(g.find(gt_fn))

def classify(qid, cond, answer, top3, q_meta):
    gt_fn   = q_meta["gt"]
    entry   = q_meta["entry"]
    if answer == gt_fn:
        return "CORRECT"
    # callback gap — structurally unreachable in any graph
    if qid in CALLBACK_GAP_QS:
        return "callback_gap"
    # model answered the entry function
    if answer and answer.strip().lower() == entry.strip().lower():
        return "default_entry"
    # check if GT is even in the relevant graph(s) for this condition
    gkey = "CT" if cond.startswith("CT") else "SYN"
    if not gt_in_graph(qid, gt_fn, gkey):
        return "not_in_graph"   # shouldn't happen for non-callback questions but guard anyway
    # everything else
    return "wrong_other"

def main():
    q_meta = load_gt()
    rows = [json.loads(l) for l in open(JSONL, encoding="utf-8") if l.strip()]

    # one record per (qid, cond) — skip NOCTX and reps > 1
    records = [r for r in rows
               if r.get("condition") not in SKIP_CONDS and r.get("rep", 1) == 1]

    by_qcond = {}
    for r in records:
        try:
            o = json.loads(r["final_text"])
        except Exception:
            o = {}
        key = (r["question_id"], r["condition"])
        by_qcond[key] = {
            "answer": o.get("answer_function", "") or "",
            "top3":   o.get("top3") or [],
        }

    # ---- per-question × per-condition table ----
    conds = ["SYN-TOOL","CT-TOOL","SYN-TEXT","CT-TEXT",
             "CT-ct_calls","CT-ct_types","CT-source_only","SYN-source_only"]
    out = ["# Error analysis — Qwen3-coder\n",
           "Conditions: all graph conditions (NOCTX excluded).\n",
           "Buckets: **CORRECT** / **callback_gap** / **default_entry** / **not_in_graph** / **wrong_other**\n",
           "| Q | GT | Entry | " + " | ".join(conds) + " |",
           "|---|---|---|" + "---|" * len(conds)]

    bucket_total = collections.Counter()
    q_buckets    = collections.defaultdict(list)   # qid -> list of buckets (non-CORRECT)

    for qid in sorted(q_meta):
        entry = q_meta[qid]["entry"]
        gt_fn = q_meta[qid]["gt"]
        cells = []
        for c in conds:
            rec = by_qcond.get((qid, c))
            if rec is None:
                cells.append("—")
                continue
            b = classify(qid, c, rec["answer"], rec["top3"], q_meta[qid])
            bucket_total[b] += 1
            if b != "CORRECT":
                q_buckets[qid].append(b)
            answer_shown = rec["answer"][:25] if rec["answer"] else "∅"
            label = f"**{b}**" if b == "CORRECT" else b
            cells.append(f"{label}<br/>`{answer_shown}`")
        out.append(f"| {qid} | `{gt_fn}` | `{entry}` | " + " | ".join(cells) + " |")

    # ---- summary by bucket ----
    out += [
        "",
        "## Bucket totals (across all conditions × questions)",
        "",
        "| Bucket | Count | Explanation |",
        "|---|---|---|",
        f"| CORRECT       | {bucket_total['CORRECT']}       | answer_function == ground truth |",
        f"| callback_gap  | {bucket_total['callback_gap']}  | GT unreachable: edge crosses function pointer (Q001, Q004) |",
        f"| default_entry | {bucket_total['default_entry']} | Model named the entry function (sqlite3Select / sqlite3_step) |",
        f"| not_in_graph  | {bucket_total['not_in_graph']}  | GT not present as a node in the graph |",
        f"| wrong_other   | {bucket_total['wrong_other']}   | GT is in graph; model named a different function |",
        "",
    ]

    # ---- per-question dominant failure ----
    out += ["## Dominant failure per question", ""]
    for qid in sorted(q_meta):
        if not q_buckets[qid]:
            out.append(f"- **{qid}**: all conditions correct")
            continue
        cnt = collections.Counter(q_buckets[qid])
        dominant = cnt.most_common(1)[0][0]
        out.append(f"- **{qid}** ({q_meta[qid]['gt']}): dominant=**{dominant}** — {dict(cnt)}")

    text = "\n".join(out) + "\n"
    os.makedirs("results", exist_ok=True)
    open("results/error_analysis.md", "w", encoding="utf-8").write(text)
    print(text)
    print("wrote results/error_analysis.md")

if __name__ == "__main__":
    main()
