#!/usr/bin/env python3
"""Token count of the analysed source files (D3 context-window check).
Run from the repo root:   python src/extractor/count_tokens.py
Reads the file list from extract.py, so the two never disagree. Headers pulled in by #include are NOT counted."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract import CORE, FILES, ROOT  # noqa: E402

ORIGINAL_SIX = {"tokenize.c", "parse.c", "vdbe.c", "vdbeapi.c", "vdbemem.c", "prepare.c"}
try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")
    count, METHOD = (lambda t: len(_enc.encode(t, disallowed_special=()))), "tiktoken cl100k_base"
except Exception:
    count, METHOD = (lambda t: (len(t) + 3) // 4), "chars/4 (approximation: tiktoken not available)"

print(f"tokenizer: {METHOD}\nroot: {ROOT}\n")
print(f"{'file':<16}{'ring':<8}{'lines':>8}{'tokens':>10}")
tot = {"core": 0, "original_six": 0, "all": 0}
for rel in FILES:
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        print(f"{rel:<16}MISSING (did the SQLite build create it?)")
        continue
    text = open(p, errors="replace").read()
    base, c = os.path.basename(rel), count(text)
    ring = "core" if base in CORE else "ring-1"
    print(f"{rel:<16}{ring:<8}{text.count(chr(10)):>8}{c:>10}")
    tot["all"] += c
    tot["core"] += c if base in CORE else 0
    tot["original_six"] += c if base in ORIGINAL_SIX else 0
print(f"\ncore files only:            {tot['core']:>9}")
print(f"original six files:         {tot['original_six']:>9}   (compare with the earlier 84,438)")
print(f"all {len(FILES)} files in the graph:    {tot['all']:>9}")
