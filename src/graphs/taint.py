#!/usr/bin/env python3
"""Shallow taint pass over the CT graph.  graph_ct_v1.db  ->  graph_ct_v2.db (+ taint_reaches edges).

    python src/graphs/taint.py                       # default K = 6
    python src/graphs/taint.py --k 4                 # sensitivity runs: 4 and 8 (write to different --out-db)

Idea: start at a SOURCE function with its source parameter marked tainted. Inside a function, a variable becomes tainted if it is
assigned from a tainted variable (uses the 'assigns' facts the extractor stored). At every call site whose arguments include a
tainted variable: if the callee is a SINK, record a taint_reaches edge (source -> sink, with the whole call path);
otherwise, if the callee is defined in the analysed files and fewer than K hops were used, continue into it with the matching
parameters tainted.

LIMITS (say them in the report): purely syntactic; no aliasing or pointer analysis; no flow through struct fields, globals, heap
or function pointers; ignores branch conditions; so it OVER-approximates. Edge counts are 'candidate' paths, not proven bugs.
"""
import argparse
import fnmatch
import json
import os
import random
import shutil
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from tools.graph_tools import _G  # noqa: E402  (reuse the graph reader)

# ---- fixed lists from the design doc (D8). Parameter names verified against SQLite 3.30.1 signatures.
SOURCES = [("sqlite3_prepare*", "zSql"), ("sqlite3_bind_text*", "zData"), ("sqlite3_bind_blob*", "zData")]
SINKS = {
    "copy": ["memcpy", "memmove", "strcpy", "strcat", "sprintf"],
    "alloc": ["sqlite3_malloc", "sqlite3_malloc64", "sqlite3Malloc", "sqlite3DbMallocRaw", "sqlite3DbMallocRawNN",
              "sqlite3DbMallocZero", "sqlite3_realloc", "sqlite3DbRealloc"],
    "free": ["sqlite3_free", "sqlite3DbFree", "sqlite3DbFreeNN"],
}
SINK_CLASS = {name: cls for cls, names in SINKS.items() for name in names}


def close(g, fid, tainted):
    """Tainted variables inside function fid, closed under its recorded assignments."""
    t, assigns, changed = set(tainted), g.nodes[fid]["meta"].get("assigns", []), True
    while changed:
        changed = False
        for lhs, rhs in assigns:
            if lhs not in t and t.intersection(rhs):
                t.add(lhs)
                changed = True
    return t


def run(g, k):
    found, warnings, seen = [], [], set()
    for pattern, param in SOURCES:
        starts = sorted(i for i, n in g.nodes.items() if n["kind"] == "function" and n["file"]
                        and fnmatch.fnmatchcase(n["name"], pattern))
        if not starts:
            warnings.append(f"source {pattern}: no defined function matches (is its file in the graph?)")
        for sid in starts:
            if param not in g.nodes[sid]["meta"].get("params", []):
                warnings.append(f"source {g.nodes[sid]['name']}: no parameter named {param} "
                                f"(has {g.nodes[sid]['meta'].get('params')})")
                continue
            visited = set()

            def dfs(fid, tainted, path):
                key = (fid, frozenset(tainted))
                if key in visited:
                    return
                visited.add(key)
                tset = close(g, fid, tainted)
                for dst, meta in g.out["calls"].get(fid, []):
                    flags = [bool(tset.intersection(a)) for a in meta.get("args", [])]
                    if not any(flags):
                        continue
                    dname = g.nodes[dst]["name"]
                    if dname in SINK_CLASS:
                        names = [g.nodes[x]["name"] for x in path] + [dname]
                        ek = (sid, dst, tuple(names), meta.get("line"))
                        if ek not in seen:
                            seen.add(ek)
                            found.append((sid, dst, {
                                "source_param": f"{g.nodes[sid]['name']}:{param}", "path": names,
                                "hops": len(names) - 1, "sink_class": SINK_CLASS[dname],
                                "call_site": {"file": meta.get("file"), "line": meta.get("line")},
                                "tainted_arg_positions": [i for i, f in enumerate(flags) if f]}))
                    elif g.nodes[dst]["file"] and len(path) < k:          # callee has a body: follow it
                        cp = g.nodes[dst]["meta"].get("params", [])
                        nxt = {cp[i] for i, f in enumerate(flags) if f and i < len(cp) and cp[i]}
                        if nxt:
                            dfs(dst, nxt, path + [dst])

            dfs(sid, {param}, [sid])
    return found, warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-db", default="src/graphs/graph_ct_v1.db")
    ap.add_argument("--out-db", default="src/graphs/graph_ct_v2.db")
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--sample", type=int, default=15)
    a = ap.parse_args()
    g = _G(a.in_db)
    found, warns = run(g, a.k)
    shutil.copyfile(a.in_db, a.out_db)                       # v2 = v1 + taint edges (v1 is never modified)
    con = sqlite3.connect(a.out_db)
    con.execute("DELETE FROM edges WHERE kind='taint_reaches'")
    con.executemany("INSERT INTO edges(src_id,dst_id,kind,meta) VALUES(?,?,'taint_reaches',?)",
                    [(s, d, json.dumps(m, sort_keys=True)) for s, d, m in found])
    con.commit()
    con.close()
    for w in warns:
        print("WARNING:", w, file=sys.stderr)
    by_class, by_source = {}, {}
    for _, _, m in found:
        by_class[m["sink_class"]] = by_class.get(m["sink_class"], 0) + 1
        by_source[m["source_param"]] = by_source.get(m["source_param"], 0) + 1
    print(json.dumps({"k": a.k, "taint_edges": len(found), "by_sink_class": by_class, "sources_with_edges": len(by_source),
                      "out": a.out_db}, indent=2))
    rows = [m for _, _, m in found]
    random.Random(0).shuffle(rows)
    print(f"\n--- {min(a.sample, len(rows))} random edges: label each plausible / implausible BY HAND against the source ---")
    for m in rows[:a.sample]:
        print(f"{m['source_param']:30s} {' > '.join(m['path'])}   @{m['call_site']['file']}:{m['call_site']['line']}")


if __name__ == "__main__":
    main()
