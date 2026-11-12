#!/usr/bin/env python3
"""Path correctness — edges "not supported by the graph" — for Qwen tool conditions.

For every tool-condition Qwen answer, checks every cited_edge
{"src": X, "dst": Y, "kind": "calls"} against the actual graph.

Verdict per edge:
  valid               – edge exists in the graph exactly as stated
  reversed            – the edge exists but src/dst are swapped
  not_in_graph        – neither direction is present in the graph
                        (includes edges across function pointers, which the graph
                        does not record, so absence does not prove hallucination)

Also checks evidence_path: each consecutive pair (fn_i -> fn_{i+1}) is verified.

Run from repo root:
    python src/eval/path_check.py

Writes: results/path_check.md  (also prints to stdout)
"""
import collections, csv, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC  = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SRC, "tools"))
import graph_tools as gt

CSV_PATH = os.path.expanduser("~/cs5187/benchmark_work/questions.csv")
JSONL    = "results/runs_qwen3-coder-30b-a3b-instruct.jsonl"
DBS = {
    "SYN": "src/graphs/graph_syn.db",
    "CT":  "src/graphs/graph_ct_v2.db",
}
TOOL_CONDS = {"SYN-TOOL","CT-TOOL","CT-ct_calls","CT-ct_types",
              "CT-source_only","SYN-source_only"}


def edge_exists(g, src_name, dst_name):
    """Return (forward_exists, reverse_exists)."""
    src_ids = set(g.find(src_name))
    dst_ids = set(g.find(dst_name))
    fwd = any(d in dst_ids for s in src_ids for d, _ in g.out["calls"].get(s, []))
    rev = any(d in src_ids for t in dst_ids for d, _ in g.out["calls"].get(t, []))
    return fwd, rev


def check_edges(g, edges):
    results = []
    for e in edges:
        src, dst = e.get("src", ""), e.get("dst", "")
        if not src or not dst:
            results.append({"src": src, "dst": dst, "verdict": "malformed"})
            continue
        fwd, rev = edge_exists(g, src, dst)
        verdict = "valid" if fwd else ("reversed" if rev else "not_in_graph")
        results.append({"src": src, "dst": dst, "verdict": verdict})
    return results


def check_path(g, path):
    """Check consecutive pairs in evidence_path."""
    results = []
    for i in range(len(path) - 1):
        src, dst = path[i], path[i + 1]
        fwd, rev = edge_exists(g, src, dst)
        verdict = "valid" if fwd else ("reversed" if rev else "not_in_graph")
        results.append({"src": src, "dst": dst, "verdict": verdict})
    return results


def db_for_cond(cond):
    return DBS["CT"] if cond.startswith("CT") else DBS["SYN"]


def main():
    rows = [json.loads(l) for l in open(JSONL, encoding="utf-8") if l.strip()]
    tool_rows = [r for r in rows
                 if r.get("condition") in TOOL_CONDS and r.get("rep", 1) == 1]

    out = ["# Path correctness and hallucination rate — Qwen3-coder\n",
           "Tool conditions only (TEXT has no cited_edges). One run per (question, condition).\n",
           "## Per-answer edge verdict\n",
           "| Q | Condition | Answer | cited_edges | valid | reversed | not in graph | "
           "evidence_path pairs | path valid | path rev | path not-in-graph |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]

    totals = collections.Counter()   # across all answers
    path_totals = collections.Counter()

    for r in sorted(tool_rows, key=lambda x: (x["question_id"], x["condition"])):
        qid  = r["question_id"]
        cond = r["condition"]
        try:
            o = json.loads(r["final_text"])
        except Exception:
            o = {}
        answer     = o.get("answer_function", "") or "∅"
        cited      = o.get("cited_edges") or []
        ev_path    = o.get("evidence_path") or []

        if not cited and not ev_path:
            out.append(f"| {qid} | {cond} | `{answer[:30]}` | 0 | — | — | — | 0 | — | — | — |")
            continue

        g = gt._g(db_for_cond(cond))

        edge_res  = check_edges(g, cited)
        path_res  = check_path(g, ev_path)

        ec = collections.Counter(e["verdict"] for e in edge_res)
        pc = collections.Counter(p["verdict"] for p in path_res)

        totals.update(ec)
        path_totals.update(pc)

        out.append(
            f"| {qid} | {cond} | `{answer[:25]}` "
            f"| {len(cited)} | {ec['valid']} | {ec['reversed']} | {ec['not_in_graph']} "
            f"| {len(path_res)} | {pc['valid']} | {pc['reversed']} | {pc['not_in_graph']} |"
        )

    # aggregate — overall and broken down by condition type
    SOURCE_ONLY = {"CT-source_only", "SYN-source_only"}
    totals_src   = collections.Counter()
    totals_other = collections.Counter()
    path_src     = collections.Counter()
    path_other   = collections.Counter()

    for r in sorted(tool_rows, key=lambda x: (x["question_id"], x["condition"])):
        cond = r["condition"]
        try:
            o = json.loads(r["final_text"])
        except Exception:
            o = {}
        cited   = o.get("cited_edges") or []
        ev_path = o.get("evidence_path") or []
        if not cited and not ev_path:
            continue
        g        = gt._g(db_for_cond(cond))
        er       = check_edges(g, cited)
        pr       = check_path(g, ev_path)
        ec       = collections.Counter(e["verdict"] for e in er)
        pc       = collections.Counter(p["verdict"] for p in pr)
        if cond in SOURCE_ONLY:
            totals_src.update(ec);  path_src.update(pc)
        else:
            totals_other.update(ec); path_other.update(pc)

    total_edges = sum(totals.values())
    total_path  = sum(path_totals.values())

    def pct(n, d):
        return f"{100*n//d}%" if d else "—"

    se   = sum(totals_src.values())
    oe   = sum(totals_other.values())
    sp   = sum(path_src.values())
    op   = sum(path_other.values())
    nig  = "not_in_graph"

    out += [
        "",
        "## Aggregate (cited_edges)",
        "",
        "| Group | edges | valid | reversed | not in graph | not-in-graph rate |",
        "|---|---|---|---|---|---|",
        f"| Source-only conditions | {se} | {totals_src['valid']} | {totals_src['reversed']} | {totals_src[nig]} | {pct(totals_src[nig], se)} |",
        f"| Other tool conditions  | {oe} | {totals_other['valid']} | {totals_other['reversed']} | {totals_other[nig]} | {pct(totals_other[nig], oe)} |",
        f"| **All tool conditions**| {total_edges} | {totals['valid']} | {totals['reversed']} | {totals[nig]} | {pct(totals[nig], total_edges)} |",
        "",
        "## Aggregate (evidence_path consecutive pairs)",
        "",
        "| Group | pairs | valid | reversed | not in graph | not-in-graph rate |",
        "|---|---|---|---|---|---|",
        f"| Source-only conditions | {sp} | {path_src['valid']} | {path_src['reversed']} | {path_src[nig]} | {pct(path_src[nig], sp)} |",
        f"| Other tool conditions  | {op} | {path_other['valid']} | {path_other['reversed']} | {path_other[nig]} | {pct(path_other[nig], op)} |",
        f"| **All tool conditions**| {total_path} | {path_totals['valid']} | {path_totals['reversed']} | {path_totals[nig]} | {pct(path_totals[nig], total_path)} |",
        "",
        "> **Not-in-graph rate** = edges not supported by the graph / total edges checked.",
        "> An edge absent from the graph may cross a function pointer (not modelled) rather than",
        "> being a model fabrication; the rate is therefore an upper bound on hallucination.",
    ]

    text = "\n".join(out) + "\n"
    os.makedirs("results", exist_ok=True)
    open("results/path_check.md", "w", encoding="utf-8").write(text)
    print(text)
    print("wrote results/path_check.md")


if __name__ == "__main__":
    main()
