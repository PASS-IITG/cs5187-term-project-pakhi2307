#!/usr/bin/env python3
"""Graph slice for the TEXT condition: the call graph around an entry function, written as plain text, within a token budget.

    from tools.graph_slice import graph_slice
    s = graph_slice("src/graphs/graph_ct_v2.db", "sqlite3Select", budget_tokens=6000)
    prompt_part = s["text"]

ONE code base for BOTH graphs (CT and SYN): the db_path is the only thing that differs, and the text never says which
graph it came from. The slice is chosen from the entry function ONLY. It never looks at the answer.

How it is built (deterministic: same DB + same arguments -> byte-identical text):
  * breadth-first from the entry function over `calls` edges (what each function calls), hop by hop;
    inside a hop, functions are taken in alphabetical order of their displayed name
  * a function defined in the analysed files is written as one block (name, file:line, then everything it calls);
    a function that is only called (external / boundary) is not expanded
  * blocks are added whole while the running token count stays <= budget_tokens; the first block that does not fit
    ends the slice (so the slice is a clean breadth-first prefix, never a half block)
  * tokens are counted with tiktoken cl100k_base (same as count_tokens.py); chars/4 if tiktoken is missing

Returns {"text", "tokens", "budget", "functions_shown", "edges_shown", "stopped_by", "entry", "token_method"}
  stopped_by: "budget" (next block did not fit), "exhausted" (everything reachable is shown), "max_hops"
or {"error": "UNKNOWN_FUNCTION", ...} when the entry is not in the graph.

CLI:  python src/tools/graph_slice.py --db src/graphs/graph_ct_v2.db --entry sqlite3Select [--budget 6000]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import graph_tools as gt  # noqa: E402

try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")
    _count, METHOD = (lambda t: len(_enc.encode(t, disallowed_special=()))), "tiktoken cl100k_base"
except Exception:
    _count, METHOD = (lambda t: (len(t) + 3) // 4), "chars/4 (approximation: tiktoken not available)"

HEADER = "Call graph around {entry}. Each block is a function followed by the functions it calls.\n"


def _block(g, i):
    n = g.nodes[i]
    where = f" [{n['file']}:{n['line']}]" if n["file"] and n["line"] else ""
    callees = sorted({g.show(d) for d, _ in g.out["calls"].get(i, [])})
    return f"{g.show(i)}{where} calls: " + (", ".join(callees) if callees else "(nothing in the graph)"), len(callees)


def graph_slice(db_path, entry_function, budget_tokens=6000, max_hops=50):
    g = gt._g(db_path)
    starts = g.find(entry_function)
    if not starts:
        return {"error": "UNKNOWN_FUNCTION", "name": entry_function, "suggestions": g.suggest(entry_function)}
    start = next((i for i in starts if g.nodes[i]["file"]), starts[0])
    header = HEADER.format(entry=g.show(start))
    parts, used, edges, shown = [header], _count(header), 0, 0
    seen, frontier, stopped = {start}, [start], "exhausted"
    for hop in range(max_hops + 1):
        layer = sorted((i for i in frontier if g.nodes[i]["file"]), key=lambda i: (g.show(i), i))   # boundary nodes not expanded
        nxt = []
        for i in layer:
            text, ne = _block(g, i)
            cost = _count(text + "\n")
            if used + cost > budget_tokens:
                stopped = "budget"
                break
            parts.append(text + "\n")
            used, edges, shown = used + cost, edges + ne, shown + 1
            for d, _ in sorted(g.out["calls"].get(i, []), key=lambda x: (g.show(x[0]), x[0])):
                if d not in seen:
                    seen.add(d)
                    nxt.append(d)
        else:
            frontier = nxt
            if not any(g.nodes[i]["file"] for i in frontier):
                break
            if hop == max_hops:
                stopped = "max_hops"
            continue
        break
    text = "".join(parts)
    return {"text": text, "tokens": _count(text), "budget": budget_tokens, "functions_shown": shown,
            "edges_shown": edges, "stopped_by": stopped, "entry": g.show(start), "token_method": METHOD}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--entry", required=True)
    ap.add_argument("--budget", type=int, default=6000)
    ap.add_argument("--max-hops", type=int, default=50)
    ap.add_argument("--quiet", action="store_true", help="print only the summary, not the text")
    a = ap.parse_args()
    r = graph_slice(a.db, a.entry, a.budget, a.max_hops)
    if "error" in r:
        print(r)
        sys.exit(1)
    if not a.quiet:
        print(r["text"])
    print({k: v for k, v in r.items() if k != "text"}, file=sys.stderr)


if __name__ == "__main__":
    main()
