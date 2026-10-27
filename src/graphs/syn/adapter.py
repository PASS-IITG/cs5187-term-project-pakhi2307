#!/usr/bin/env python3
"""graphify graph.json -> graph_syn.db, same two-table schema as graph_ct (src/graphs/schema.sql)."""
import argparse, collections, json, os, re, sqlite3

CORE = {"src/tokenize.c", "parse.c", "src/vdbe.c", "src/vdbeapi.c", "src/vdbemem.c"}

def brace_end(lines, start):
    """1-based start line of a definition -> 1-based line of its closing brace, or None."""
    depth, opened, in_block = 0, False, False
    for ln in range(start - 1, len(lines)):
        s = lines[ln]
        if s.lstrip().startswith("#") and not in_block:
            continue
        i, n = 0, len(s)
        while i < n:
            c = s[i]
            if in_block:
                if c == "*" and i + 1 < n and s[i + 1] == "/":
                    in_block = False
                    i += 2
                    continue
                i += 1
                continue
            if c == "/" and i + 1 < n and s[i + 1] == "*":
                in_block = True
                i += 2
                continue
            if c == "/" and i + 1 < n and s[i + 1] == "/":
                break
            if c in "\"'":
                q = c
                i += 1
                while i < n and s[i] != q:
                    if s[i] == "\\":
                        i += 1
                    i += 1
                i += 1
                continue
            if c == "{":
                depth += 1
                opened = True
            elif c == "}":
                depth -= 1
                if opened and depth == 0:
                    return ln + 1
            i += 1
    return None

def line_of(loc):
    m = re.search(r"(\d+)", str(loc or ""))
    return int(m.group(1)) if m else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", required=True)
    ap.add_argument("--src", required=True, help="SQLite tree the files were copied from")
    ap.add_argument("--files", required=True, help="the same relative file list given to run_graphify.sh")
    ap.add_argument("--schema", default="src/graphs/schema.sql")
    ap.add_argument("--out", default="src/graphs/graph_syn.db")
    a = ap.parse_args()

    rel = {}
    for f in a.files.split():
        b = os.path.basename(f)
        assert b not in rel, "two files share the basename " + b
        rel[b] = f

    g = json.load(open(a.graph))
    nodes = g["nodes"]
    edges = g.get("edges") or g.get("links") or []
    print("graph.json keys:", list(g.keys()), "| nodes:", len(nodes), "| edges:", len(edges))

    funcs, skipped_nodes = [], collections.Counter()
    for n in nodes:
        if not n.get("_callable"):
            skipped_nodes["not_callable"] += 1
            continue
        f = rel.get(os.path.basename(n.get("source_file") or ""))
        ln = line_of(n.get("source_location"))
        if f is None or ln is None:
            skipped_nodes["callable_without_file_or_line"] += 1
            continue
        funcs.append((f, ln, re.sub(r"\(\)$", "", n["label"]), n["id"]))
    funcs.sort()

    nlines, flines = {}, {}
    for f in {t[0] for t in funcs}:
        with open(os.path.join(a.src, f), errors="replace") as fh:
            flines[f] = fh.read().splitlines()
            nlines[f] = len(flines[f])
    byfile = collections.defaultdict(list)
    for t in funcs:
        byfile[t[0]].append(t)

    if os.path.exists(a.out):
        os.remove(a.out)
    con = sqlite3.connect(a.out)
    con.executescript(open(a.schema).read())

    gid2db, id2file, per_file = {}, {}, collections.Counter()
    methods, diffs = collections.Counter(), []
    for f, items in byfile.items():
        for i, (_, ln, name, gid) in enumerate(items):
            fb = max(ln, items[i + 1][1] - 1) if i + 1 < len(items) else nlines[f]
            be = brace_end(flines[f], ln)
            if be is not None and be > ln and not flines[f][be - 1].startswith("}"):
                be = next((k + 1 for k in range(be, len(flines[f])) if flines[f][k].startswith("}")), be)
            if be is not None and be <= fb:
                end, how = be, "brace"
                if fb - be > 3:
                    diffs.append((f, name, fb - be))
            else:
                end, how = fb, "next_def"
            methods[how] += 1
            meta = {"graph_source": "graphify", "is_external": False, "params": [], "end_line_method": how}
            cur = con.execute(
                "INSERT INTO nodes(kind,name,file,line,signature,end_line,usr,in_scope,meta) VALUES('function',?,?,?,?,?,?,?,?)",
                (name, f, ln, None, end, f"{f}:{name}:{ln}", 1 if f in CORE else 0, json.dumps(meta)))
            gid2db[gid] = cur.lastrowid
            id2file[gid] = f
            per_file[f] += 1

    print("end_line method:", dict(methods), "| brace end more than 3 lines before next-def:", sorted(diffs, key=lambda x: -x[2])[:8])
    skipped_edges, conf, n_edges = collections.Counter(), collections.Counter(), 0
    for e in edges:
        r = e.get("relation")
        if r != "calls":
            skipped_edges["relation:" + str(r)] += 1
            continue
        s, d = e.get("source"), e.get("target")
        if s not in gid2db or d not in gid2db:
            skipped_edges["calls_endpoint_not_a_scanned_function"] += 1
            continue
        c = e.get("confidence")
        conf[c] += 1
        meta = {"file": id2file[s], "line": line_of(e.get("source_location")), "confidence": c, "graph_source": "graphify"}
        con.execute("INSERT INTO edges(src_id,dst_id,kind,meta) VALUES(?,?,?,?)", (gid2db[s], gid2db[d], "calls", json.dumps(meta)))
        n_edges += 1
    con.commit()
    con.close()

    print("function nodes:", sum(per_file.values()), dict(sorted(per_file.items())))
    print("call edges written:", n_edges, "| by confidence:", dict(conf))
    print("skipped nodes:", dict(skipped_nodes))
    print("skipped edges:", dict(skipped_edges))
    if n_edges == 0 and edges:
        print("NO CALL EDGES WRITTEN. First edge keys:", list(edges[0].keys()), "sample:", edges[0])
    print("wrote", a.out)

main()
