#!/usr/bin/env python3
"""Write src/graphs/graph_meta.json for the CT graph DBs.  Run after extract.py and taint.py:
    python src/graphs/make_meta.py
"""
import datetime, hashlib, json, os, platform, sqlite3, subprocess, sys
from importlib import metadata

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "extractor"))
from extract import CORE, FILES, ROOT  # noqa: E402

DBS = ["src/graphs/graph_ct_v1.db", "src/graphs/graph_ct_v2.db"]
REPORT = "src/graphs/graph_ct_v1_parse_report.json"


def sh(*cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()
    except Exception as e:
        return f"unavailable: {e}"


def describe(db):
    con = sqlite3.connect(db)
    q = lambda s: con.execute(s).fetchall()
    out = {"file": db,
           "sha256": hashlib.sha256(open(db, "rb").read()).hexdigest(),
           "built_utc": datetime.datetime.fromtimestamp(os.path.getmtime(db), datetime.timezone.utc).isoformat(),
           "nodes_by_kind": dict(q("SELECT kind, COUNT(*) FROM nodes GROUP BY kind")),
           "edges_by_kind": dict(q("SELECT kind, COUNT(*) FROM edges GROUP BY kind")),
           "functions_in_scope": q("SELECT COUNT(*) FROM nodes WHERE kind='function' AND in_scope=1")[0][0],
           "boundary_functions": q("SELECT COUNT(*) FROM nodes WHERE kind='function' AND file IS NULL")[0][0]}
    con.close()
    return out


meta = {
    "sqlite_tag": sh("git", "-C", ROOT, "describe", "--tags", "--exact-match"),
    "sqlite_commit": sh("git", "-C", ROOT, "rev-parse", "HEAD"),
    "clang": sh("clang", "--version").splitlines()[0],
    "libclang": metadata.version("libclang"),
    "python": platform.python_version(),
    "meta_written_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "files": FILES,
    "core_files": sorted(CORE),
    "dbs": [describe(d) for d in DBS if os.path.exists(d)],
    "parse_report": json.load(open(REPORT)) if os.path.exists(REPORT) else None,
}
json.dump(meta, open("src/graphs/graph_meta.json", "w"), indent=2, sort_keys=True)
print(json.dumps({k: meta[k] for k in ("sqlite_tag", "sqlite_commit", "clang", "libclang", "python")}, indent=2))
print("wrote src/graphs/graph_meta.json")
