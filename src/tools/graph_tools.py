#!/usr/bin/env python3
"""Graph query tools for the LLM agent.  ONE code base for BOTH graphs: every function takes db_path first.

    from tools.graph_tools import get_callers, get_callees, find_call_path, get_type_hierarchy, \
        get_function_source, search_functions, get_taint_paths, TOOL_SCHEMAS, available_tools, dispatch

Contract (CONTRACT with Pakhi):
  * every tool returns a dict:  {"result": ..., "truncated": bool}   or   {"error": CODE, ...}
  * lists are sorted (deterministic) and capped at MAX_ITEMS (50); "truncated" says if the cap cut anything
  * names: plain "helper" returns ALL matches; "src/tokenize.c:helper" or "tokenize.c:helper" selects one file.
    When two functions share a name, results show them as "file:name".
  * unknown name -> {"error": "UNKNOWN_FUNCTION", "name": ..., "suggestions": [...]}
  * get_type_hierarchy is offered only if the graph has types; get_taint_paths only if it has taint_reaches edges
    (see available_tools(db_path)).  Tool descriptions never say which graph is behind them.

CLI test:  python src/tools/graph_tools.py --db src/graphs/graph_ct_v1.db --call get_callees '{"function_name":"sqlite3Prepare"}'
"""
import argparse
import json
import os
import sqlite3
import sys
from collections import defaultdict, deque

MAX_ITEMS = 50
DEFAULT_ROOT = "sqlite-src"
_CACHE = {}


class _G:
    """In-memory copy of one graph DB."""

    def __init__(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"graph database not found: {path}")
        con = sqlite3.connect(path)
        con.row_factory = sqlite3.Row
        self.nodes = {r["id"]: dict(r) for r in con.execute("SELECT * FROM nodes")}
        for n in self.nodes.values():
            n["meta"] = json.loads(n["meta"] or "{}")
        self.out, self.inn = defaultdict(lambda: defaultdict(list)), defaultdict(lambda: defaultdict(list))
        for r in con.execute("SELECT src_id,dst_id,kind,meta FROM edges"):
            m = json.loads(r["meta"] or "{}")
            self.out[r["kind"]][r["src_id"]].append((r["dst_id"], m))
            self.inn[r["kind"]][r["dst_id"]].append((r["src_id"], m))
        con.close()
        self.by_name = defaultdict(list)
        counts = defaultdict(int)
        for i, n in self.nodes.items():
            self.by_name[n["name"]].append(i)
            if n["kind"] == "function" and n["file"]:
                counts[n["name"]] += 1
        self.dup = {k for k, v in counts.items() if v > 1}

    def has_types(self):
        return any(n["kind"] == "type" for n in self.nodes.values())

    def has_taint(self):
        return bool(self.out.get("taint_reaches"))

    def show(self, i):
        n = self.nodes[i]
        return f"{n['file']}:{n['name']}" if n["name"] in self.dup and n["file"] else n["name"]

    def find(self, name, kind="function"):
        if ":" in name:
            f, nm = name.rsplit(":", 1)
            ids = [i for i in self.by_name.get(nm, []) if self.nodes[i]["kind"] == kind
                   and (self.nodes[i]["file"] or "").endswith(f)]
        else:
            ids = [i for i in self.by_name.get(name, []) if self.nodes[i]["kind"] == kind]
        return sorted(ids)

    def suggest(self, name, kind="function", n=5):
        low = name.rsplit(":", 1)[-1].lower()
        return sorted({x["name"] for x in self.nodes.values() if x["kind"] == kind and low in x["name"].lower()})[:n]


def _g(db_path):
    key = os.path.realpath(db_path)
    mtime = os.path.getmtime(key) if os.path.exists(key) else 0
    if key not in _CACHE or _CACHE[key][0] != mtime:
        _CACHE[key] = (mtime, _G(key))
    return _CACHE[key][1]


def _cap(items):
    return {"result": items[:MAX_ITEMS], "truncated": len(items) > MAX_ITEMS, "total": len(items)}


def _unknown(g, name, kind="function"):
    return {"error": "UNKNOWN_FUNCTION" if kind == "function" else "UNKNOWN_TYPE", "name": name,
            "suggestions": g.suggest(name, kind)}


# ------------------------------------------------------------------ the tools
def get_callers(db_path, function_name):
    g = _g(db_path)
    ids = g.find(function_name)
    if not ids:
        return _unknown(g, function_name)
    return _cap(sorted({g.show(s) for i in ids for s, _ in g.inn["calls"].get(i, [])}))


def get_callees(db_path, function_name):
    g = _g(db_path)
    ids = g.find(function_name)
    if not ids:
        return _unknown(g, function_name)
    return _cap(sorted({g.show(d) for i in ids for d, _ in g.out["calls"].get(i, [])}))


def get_type_hierarchy(db_path, type_name):
    g = _g(db_path)
    ids = g.find(type_name, "type")
    if not ids:
        return _unknown(g, type_name, "type")
    t = g.nodes[ids[0]]
    fields = []
    for fid, _ in g.out["has_field_of_type"].get(ids[0], []):
        f = g.nodes[fid]
        if f["kind"] == "field":
            link = [g.nodes[x]["name"] for x, _ in g.out["has_field_of_type"].get(fid, [])]
            fields.append({"field": f["name"].split(".", 1)[-1], "type": f["signature"], "line": f["line"],
                           "type_node": link[0] if link else None})
    fields.sort(key=lambda x: (x["line"] or 0, x["field"]))
    return {"result": {"type": t["name"], "kind": t["meta"].get("tkind"), "file": t["file"], "line": t["line"],
                       "fields": fields[:MAX_ITEMS]}, "truncated": len(fields) > MAX_ITEMS}


def find_call_path(db_path, entry_function, target_function, max_hops=10):
    """One shortest call chain entry -> target, or {"result": null}. Ties are broken alphabetically (deterministic)."""
    g = _g(db_path)
    starts, goals = g.find(entry_function), set(g.find(target_function))
    for nm, ids in ((entry_function, starts), (target_function, goals)):
        if not ids:
            return _unknown(g, nm)
    prev, dq = {s: None for s in starts}, deque((s, 0) for s in starts)
    while dq:
        cur, d = dq.popleft()
        if cur in goals:
            path = []
            while cur is not None:
                path.append(g.show(cur))
                cur = prev[cur]
            return {"result": path[::-1], "truncated": False}
        if d >= max_hops:
            continue
        for nxt in sorted({x for x, _ in g.out["calls"].get(cur, [])}, key=lambda i: (g.nodes[i]["name"], i)):
            if nxt not in prev:
                prev[nxt] = cur
                dq.append((nxt, d + 1))
    return {"result": None, "truncated": False}


def get_taint_paths(db_path, source_param):
    g = _g(db_path)
    rows = []
    for src, lst in g.out["taint_reaches"].items():
        for dst, m in lst:
            sp = m.get("source_param", "")
            if sp == source_param or sp.split(":")[-1] == source_param:
                rows.append({"sink": g.nodes[dst]["name"], "path": m["path"], "call_site": m.get("call_site"),
                             "sink_class": m.get("sink_class")})
    rows.sort(key=lambda r: (r["sink"], len(r["path"]), r["path"]))
    return _cap(rows)


def get_function_source(db_path, function_name, root=DEFAULT_ROOT):
    g = _g(db_path)
    ids = g.find(function_name)
    if not ids:
        return _unknown(g, function_name)
    n = next((g.nodes[i] for i in ids if g.nodes[i]["file"]), None)
    if n is None:
        return {"result": f"/* {function_name} is not defined in the analysed files (external function) */",
                "truncated": False}
    path = os.path.join(root, n["file"])
    if not os.path.exists(path):
        return {"error": "SOURCE_NOT_FOUND", "path": path}
    lines = open(path, errors="replace").read().splitlines()
    end = n["end_line"]
    if not end:                      # graph without end lines: stop just before the next function in the same file
        later = sorted(x["line"] for x in g.nodes.values()
                       if x["kind"] == "function" and x["file"] == n["file"] and x["line"] and x["line"] > n["line"])
        end = later[0] - 1 if later else n["line"] + 80
    text = "\n".join(f"{i}: {lines[i - 1]}" for i in range(n["line"], min(end, len(lines)) + 1))
    return {"result": text[:60000], "truncated": len(text) > 60000, "file": n["file"], "start_line": n["line"]}


def search_functions(db_path, substring, limit=20):
    g = _g(db_path)
    low = substring.lower()
    names = sorted({g.show(i) for i, n in g.nodes.items() if n["kind"] == "function" and low in n["name"].lower()})
    return {"result": names[:min(limit, MAX_ITEMS)], "truncated": len(names) > min(limit, MAX_ITEMS), "total": len(names)}


# ------------------------------------------------------------------ for the agent loop
def _obj(**props):
    return {"type": "object", "properties": props, "required": [k for k in props if k not in ("max_hops", "limit")]}


_S = {"type": "string"}
TOOL_SCHEMAS = {
    "get_callers": ("List the functions that directly call the given function.", _obj(function_name=_S)),
    "get_callees": ("List the functions directly called by the given function.", _obj(function_name=_S)),
    "get_type_hierarchy": ("Return the fields of a struct/union/typedef and each field's type.", _obj(type_name=_S)),
    "find_call_path": ("Return one shortest call chain from entry_function to target_function, or null if unreachable "
                       "within max_hops. Use before asserting any multi-hop path.",
                       _obj(entry_function=_S, target_function=_S, max_hops={"type": "integer"})),
    "get_taint_paths": ("Given a source parameter (e.g. 'zSql'), list sink functions that data from it can reach, "
                        "each with its call path.", _obj(source_param=_S)),
    "get_function_source": ("Return the source code of a function with line numbers.", _obj(function_name=_S)),
    "search_functions": ("Find function names containing a substring (case-insensitive). Use this instead of "
                         "guessing a name.", _obj(substring=_S, limit={"type": "integer"})),
}
_FUNCS = {"get_callers": get_callers, "get_callees": get_callees, "get_type_hierarchy": get_type_hierarchy,
          "find_call_path": find_call_path, "get_taint_paths": get_taint_paths,
          "get_function_source": get_function_source, "search_functions": search_functions}


def available_tools(db_path, allowed=None):
    """Tool names offered for this graph (types / taint tools only if the graph has that data)."""
    g = _g(db_path)
    names = [t for t in TOOL_SCHEMAS if not (t == "get_type_hierarchy" and not g.has_types())
             and not (t == "get_taint_paths" and not g.has_taint())]
    return [t for t in names if allowed is None or t in allowed]


def schemas(db_path, allowed=None):
    """List of {name, description, parameters} for the LLM's function-calling interface."""
    return [{"name": t, "description": TOOL_SCHEMAS[t][0], "parameters": TOOL_SCHEMAS[t][1]}
            for t in available_tools(db_path, allowed)]


def dispatch(db_path, tool_name, args, root=DEFAULT_ROOT, allowed=None):
    """Run one tool call from the model. Never raises: errors come back as dicts the model can read."""
    if tool_name not in available_tools(db_path, allowed):
        return {"error": "TOOL_NOT_AVAILABLE", "name": tool_name, "available": available_tools(db_path, allowed)}
    try:
        kw = dict(args or {})
        if tool_name == "get_function_source":
            kw.setdefault("root", root)
        return _FUNCS[tool_name](db_path, **kw)
    except TypeError as e:
        return {"error": "BAD_ARGUMENTS", "detail": str(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--schemas", action="store_true")
    ap.add_argument("--call", nargs=2, metavar=("TOOL", "JSON_ARGS"))
    a = ap.parse_args()
    if a.list:
        print("\n".join(available_tools(a.db)))
    if a.schemas:
        print(json.dumps(schemas(a.db), indent=2))
    if a.call:
        print(json.dumps(dispatch(a.db, a.call[0], json.loads(a.call[1]), a.root), indent=2))


if __name__ == "__main__":
    main()
