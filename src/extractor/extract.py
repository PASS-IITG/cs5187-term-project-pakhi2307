#!/usr/bin/env python3
"""Compile-time (CT) graph extractor: SQLite source tree -> src/graphs/graph_ct_v1.db

Run from the repo root (venv active):   python src/extractor/extract.py

Writes nodes (functions, types, fields) AND edges (calls, has_field_of_type) in one pass, from scratch every run
(the old database is deleted first, so re-running never duplicates anything).
Boundary rule: a function that is called but never DEFINED in the parsed files (memcpy, sqlite3_malloc, ...) becomes a
node with file=NULL and meta.is_external=1.  Calls through function pointers are listed in meta.indirect_calls.
"""
import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = "sqlite-src"
FILES = ["src/tokenize.c", "parse.c", "src/vdbe.c", "src/vdbeapi.c", "src/vdbemem.c", "src/prepare.c", "src/select.c", "src/resolve.c", "src/expr.c"]
CORE = {"tokenize.c", "parse.c", "vdbe.c", "vdbeapi.c", "vdbemem.c"}      # in_scope=1. prepare.c is ring-1 (in_scope=0)
OUT = "src/graphs/graph_ct_v1.db"
SCHEMA = os.path.join(HERE, "..", "graphs", "schema.sql")


# ------------------------------------------------------------------ libclang backend
def _fname(c):
    f = c.location.file
    return os.path.realpath(f.name) if f else None


def _idents(cur, CK):
    """Names of local variables / parameters used anywhere inside an expression."""
    out = []
    for d in cur.walk_preorder():
        if d.kind == CK.DECL_REF_EXPR:
            r = d.referenced
            if r is not None and r.kind in (CK.PARM_DECL, CK.VAR_DECL) and d.spelling not in out:
                out.append(d.spelling)
    return out


def _unnamed(c):
    sp = c.spelling or ""
    return (not sp) or "unnamed" in sp or "anonymous" in sp


def _is_plain_assign(cur):
    kids = list(cur.get_children())
    if len(kids) != 2:
        return False
    a, b = kids[0].extent.end.offset, kids[1].extent.start.offset
    try:
        return [t.spelling for t in cur.get_tokens() if a <= t.extent.start.offset < b] == ["="]
    except Exception:
        return False


def libclang_extract(path, args):
    from clang import cindex
    CK = cindex.CursorKind
    tu = cindex.Index.create().parse(path, args=args)
    errs = [d for d in tu.diagnostics if d.severity >= cindex.Diagnostic.Error]
    functions, types, seen = [], [], set()

    def func_ir(c):
        params = [a.spelling for a in c.get_arguments()]
        sig = f"{c.result_type.spelling} {c.spelling}(" + ", ".join(
            f"{a.type.spelling} {a.spelling}".strip() for a in c.get_arguments()) + ")"
        f = {"usr": c.get_usr(), "name": c.spelling, "file": _fname(c), "line": c.location.line,
             "end_line": c.extent.end.line, "signature": sig, "params": params,
             "calls": [], "assigns": [], "indirect": []}
        for d in c.walk_preorder():
            k = d.kind
            if k == CK.CALL_EXPR:
                ref = d.referenced
                if ref is not None and ref.kind == CK.FUNCTION_DECL:
                    f["calls"].append({"callee_usr": ref.get_usr(), "callee_name": ref.spelling,
                                       "line": d.location.line, "file": _fname(d) or f["file"],
                                       "args": [_idents(a, CK) for a in d.get_arguments()]})
                else:
                    expr = "?"
                    for x in d.walk_preorder():
                        if x.kind in (CK.MEMBER_REF_EXPR, CK.DECL_REF_EXPR):
                            expr = x.spelling or "?"
                            break
                    f["indirect"].append({"line": d.location.line, "expr": expr})
            elif k == CK.VAR_DECL and d != c:
                ids = sorted({i for kid in d.get_children() if kid.kind != CK.TYPE_REF for i in _idents(kid, CK)})
                if ids:
                    f["assigns"].append([d.spelling, ids])
            elif k == CK.BINARY_OPERATOR and _is_plain_assign(d):
                lhs, rhs = list(d.get_children())
                li = _idents(lhs, CK)
                if li:
                    f["assigns"].append([li[0], _idents(rhs, CK)])
        return f

    def rec_ir(decl, name, usr, tkind):
        return {"usr": usr, "name": name, "tkind": tkind, "file": _fname(decl), "line": decl.location.line,
                "end_line": decl.extent.end.line,
                "fields": [{"name": x.spelling, "type_name": x.type.spelling, "line": x.location.line}
                           for x in decl.get_children() if x.kind == CK.FIELD_DECL]}

    for c in tu.cursor.get_children():
        if c.kind == CK.FUNCTION_DECL and c.is_definition():
            functions.append(func_ir(c))
        elif c.kind in (CK.STRUCT_DECL, CK.UNION_DECL) and c.is_definition() and not _unnamed(c):
            if c.get_usr() not in seen:
                seen.add(c.get_usr())
                types.append(rec_ir(c, c.spelling, c.get_usr(), "struct" if c.kind == CK.STRUCT_DECL else "union"))
        elif c.kind == CK.TYPEDEF_DECL:                         # typedef struct { ... } Name;
            decl = c.underlying_typedef_type.get_declaration()
            if decl.kind in (CK.STRUCT_DECL, CK.UNION_DECL) and decl.is_definition() and _unnamed(decl):
                usr = "c:@T@" + c.spelling
                if usr not in seen:
                    seen.add(usr)
                    types.append(rec_ir(decl, c.spelling, usr, "struct" if decl.kind == CK.STRUCT_DECL else "union"))
    msgs = [f"{os.path.basename(str(d.location.file))}:{d.location.line}: {d.spelling}" for d in errs[:3]]
    return {"functions": functions, "types": types, "errors": len(errs), "first_errors": msgs}


# ------------------------------------------------------------------ graph builder
class Builder:
    def __init__(self, root):
        self.root = os.path.realpath(root)
        self.nodes = {}                      # usr -> node dict
        self.edges = []                      # (src_usr, dst_usr, kind, meta)
        self.stats = defaultdict(int)

    def inside(self, p):
        return bool(p) and os.path.realpath(p).startswith(self.root + os.sep)

    def rel(self, p):
        return os.path.relpath(os.path.realpath(p), self.root)

    def add_function(self, f):
        if not self.inside(f["file"]):
            return
        old = self.nodes.get(f["usr"])
        if old is not None and old["defined"]:
            return                           # header inline function already seen in an earlier .c file: count once
        rel = self.rel(f["file"])
        self.nodes[f["usr"]] = dict(
            kind="function", name=f["name"], file=rel, line=f["line"], signature=f["signature"], end_line=f["end_line"],
            usr=f["usr"], in_scope=1 if os.path.basename(rel) in CORE else 0, defined=True,
            meta={"params": f["params"], "graph_source": "clang", "assigns": f["assigns"],
                  "indirect_calls": f["indirect"]})
        self.stats["functions_defined"] += 1
        self.stats["indirect_calls_unresolved"] += len(f["indirect"])
        for c in f["calls"]:
            if c["callee_usr"] not in self.nodes:
                self.nodes[c["callee_usr"]] = dict(
                    kind="function", name=c["callee_name"], file=None, line=None, signature=None, end_line=None,
                    usr=c["callee_usr"], in_scope=0, defined=False, meta={"is_external": 1, "graph_source": "clang"})
            self.edges.append((f["usr"], c["callee_usr"], "calls",
                               {"file": self.rel(c["file"]) if self.inside(c["file"]) else rel,
                                "line": c["line"], "args": c["args"]}))
            self.stats["call_sites"] += 1

    def add_type(self, t):
        if not self.inside(t["file"]) or not t["name"]:
            return
        old = self.nodes.get(t["usr"])
        if old is not None and old["defined"]:
            return
        rel = self.rel(t["file"])
        scope = 1 if os.path.basename(rel) in CORE else 0
        self.nodes[t["usr"]] = dict(kind="type", name=t["name"], file=rel, line=t["line"],
                                    signature=f"{t['tkind']} {t['name']}", end_line=t["end_line"], usr=t["usr"],
                                    in_scope=scope, defined=True, meta={"graph_source": "clang", "tkind": t["tkind"]})
        self.stats["types"] += 1
        for fld in t["fields"]:
            fu = f"{t['usr']}@FI@{fld['name']}"
            self.nodes[fu] = dict(kind="field", name=f"{t['name']}.{fld['name']}", file=rel, line=fld["line"],
                                  signature=fld["type_name"], end_line=fld["line"], usr=fu, in_scope=scope,
                                  defined=True, meta={"graph_source": "clang", "owner": t["name"]})
            self.edges.append((t["usr"], fu, "has_field_of_type", {"field_type": fld["type_name"]}))
            self.stats["fields"] += 1

    def link_field_types(self):
        by_name = {}
        for usr, n in sorted(self.nodes.items()):
            if n["kind"] == "type":
                by_name.setdefault(n["name"], usr)
        for usr, n in list(self.nodes.items()):
            if n["kind"] != "field":
                continue
            s = re.sub(r"\[[^\]]*\]", " ", n["signature"])
            s = re.sub(r"\b(const|volatile|restrict|struct|union|enum|unsigned|signed)\b", " ", s).replace("*", " ")
            toks = re.findall(r"[A-Za-z_]\w*", s)
            target = by_name.get(toks[-1]) if toks else None
            if target and target != usr.rsplit("@FI@", 1)[0]:
                self.edges.append((usr, target, "has_field_of_type", {"field_type": n["signature"]}))
                self.stats["field_type_links"] += 1

    def write(self, path):
        self.link_field_types()
        order = sorted(self.nodes.values(), key=lambda n: (n["kind"], n["file"] or "~", n["line"] or 0, n["name"], n["usr"]))
        ids = {n["usr"]: i + 1 for i, n in enumerate(order)}
        if os.path.exists(path):
            os.remove(path)                                   # fresh DB every run -> no duplicates
        con = sqlite3.connect(path)
        con.executescript(open(SCHEMA).read())
        con.executemany("INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?,?,?)",
                        [(ids[n["usr"]], n["kind"], n["name"], n["file"], n["line"], n["signature"], n["end_line"],
                          n["usr"], n["in_scope"], json.dumps(n["meta"], sort_keys=True)) for n in order])
        ed = sorted(self.edges, key=lambda e: (ids[e[0]], ids[e[1]], e[2], e[3].get("line") or 0))
        con.executemany("INSERT INTO edges VALUES (?,?,?,?)",
                        [(ids[s], ids[d], k, json.dumps(m, sort_keys=True)) for s, d, k, m in ed])
        con.commit()
        con.close()
        self.stats["boundary_functions"] = sum(1 for n in order if n["kind"] == "function" and not n["defined"])
        self.stats["nodes_total"], self.stats["edges_total"] = len(order), len(ed)
        return dict(self.stats)


# ------------------------------------------------------------------ driver
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--files", nargs="*", default=FILES)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--backend", default="libclang", choices=["libclang", "json"])
    a = ap.parse_args()
    root = os.path.realpath(a.root)
    resdir = subprocess.check_output(["clang", "-print-resource-dir"], text=True).strip()
    flags = ["-I" + root, "-I" + os.path.join(root, "src"), "-isystem", os.path.join(resdir, "include"),
             "-std=gnu11", "-w"]
    if a.backend == "json":                                   # testing fallback, needs json_backend.py next to this file
        sys.path.insert(0, HERE)
        import json_backend
        extract = lambda p: json_backend.extract_tu(p, flags)
    else:
        extract = lambda p: libclang_extract(p, flags)

    b, report, t0 = Builder(root), {"root": root, "files": []}, time.time()
    for rel in a.files:
        p = os.path.join(root, rel)
        if not os.path.exists(p):
            report["files"].append({"file": rel, "status": "MISSING"})
            print(f"[MISSING] {rel}   <- not found; did the build create it?", file=sys.stderr)
            continue
        try:
            r = extract(p)
            for t in r["types"]:
                b.add_type(t)
            for f in r["functions"]:
                b.add_function(f)
            report["files"].append({"file": rel, "status": "ok" if r["errors"] == 0 else "parse_errors",
                                    "errors": r["errors"], "first_errors": r.get("first_errors", []),
                                    "functions_in_tu": len(r["functions"])})
        except Exception as ex:                               # log and continue; never silent
            report["files"].append({"file": rel, "status": "FAILED", "error": str(ex)[:300]})
        s = report["files"][-1]
        print(f"[{s['status']}] {rel}  errors={s.get('errors', '-')}", file=sys.stderr)
        for m in s.get("first_errors", []):
            print("      ", m, file=sys.stderr)

    report["graph"] = b.write(a.out)
    ok = sum(1 for s in report["files"] if s["status"] == "ok")
    report["files_ok"], report["files_total"] = ok, len(report["files"])
    report["seconds"] = round(time.time() - t0, 1)
    rp = os.path.splitext(a.out)[0] + "_parse_report.json"
    json.dump(report, open(rp, "w"), indent=2)
    print(json.dumps({"db": a.out, **report["graph"], "files_ok": f"{ok}/{len(report['files'])}", "report": rp}, indent=2))


if __name__ == "__main__":
    main()
