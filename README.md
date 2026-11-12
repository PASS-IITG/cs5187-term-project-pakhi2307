# cs5187_graph — LLM Agent for SQLite Fault Localisation via Code Call-Graphs

CS 5187 term project (Nov 2026). An LLM-driven agent that navigates a code call-graph to answer fault-localisation questions about the SQLite 3.30.1 source. The agent runs in several conditions: tool-using (graph traversal via function-calling API), text-slice (BFS subgraph as plain text context), and no-context baseline. Two graph back-ends are supported — a compile-time graph built with libclang and a syntactic graph built with graphify/tree-sitter — and four tool-ablation variants isolate which graph tools contribute to accuracy.

---

## Repository Layout

```
cs5187_graph/
├── src/
│   ├── llm.py                    # OpenAI-compatible LLM gateway (all models)
│   ├── agents/
│   │   ├── graph_tool.py         # Tool-using agent loop (SYN-TOOL / CT-TOOL / ablations)
│   │   └── answer.py             # Answer JSON spec + tolerant parser
│   ├── eval/
│   │   ├── run_eval.py           # Main evaluation runner (all conditions)
│   │   ├── summary.py            # Generates results/summary.md
│   │   ├── score.py              # Quick per-question score table
│   │   ├── error_analysis.py     # Classifies wrong answers by failure type
│   │   └── path_check.py         # Checks cited edges + evidence paths vs graph DB
│   ├── extractor/
│   │   └── extract.py            # libclang CT graph extractor → graph_ct_v1.db
│   ├── graphs/
│   │   ├── schema.sql            # Shared DB schema (nodes + edges tables)
│   │   ├── taint.py              # Shallow taint pass: v1 → v2 (adds taint_reaches)
│   │   ├── make_meta.py          # Writes graph_meta.json
│   │   └── syn/
│   │       ├── adapter.py        # Converts graphify graph.json → graph_syn.db
│   │       └── run_graphify.sh   # Runs graphify on SQLite source
│   └── tools/
│       ├── graph_tools.py        # Core tool library (get_callers, get_callees, …)
│       └── graph_slice.py        # TEXT condition: BFS call-graph slice as plain text
├── results/
│   ├── runs_qwen3-coder-30b-a3b-instruct.jsonl
│   ├── runs_nvidia_nemotron-3-ultra-550b-a55b.jsonl
│   ├── summary.md
│   ├── error_analysis.md
│   └── path_check.md
├── config_local_qwen.yaml        # Config for Qwen (LM Studio)
├── config_nemotron.yaml          # Config for Nemotron (NVIDIA API)
├── config.yaml.example           # Template — copy to config.yaml and fill in
├── benchmark_work/
│   └── questions.csv             # 6 benchmark questions with ground-truth functions
├── LICENSE
└── README.md
```

> **Not in repo** (too large or secret): `.env` (API keys), `src/graphs/*.db` (graph databases), `sqlite-src/` (SQLite source tree), `logs/` (trace files).

---

## Dependencies

| Package / Tool | Version | Purpose |
|---|---|---|
| Python | 3.12 | Runtime |
| libclang (clang) | 18.1.3 | CT graph extraction (`extract.py`) |
| `clang` Python binding | 18.x | Same |
| `openai` | ≥ 1.30 | LLM API client |
| `tiktoken` | ≥ 0.7 | Token counting in `graph_slice.py` |
| `python-dotenv` | ≥ 1.0 | Loads `.env` |
| `pyyaml` | ≥ 6.0 | Config loading |
| `sqlite3` | stdlib | Graph DB queries |
| graphify | any | Syntactic graph extraction (must be on `PATH`) |
| SQLite 3.30.1 source | tag `version-3.30.1`, commit `25e9591` | Input to extractor + source serving |

Install Python packages:

```bash
python -m pip install openai tiktoken python-dotenv pyyaml clang
```

> `libclang` system library must also be present. On Ubuntu:
> ```bash
> sudo apt install libclang-18-dev clang-18
> ```

---

## Setup

### 1. Clone and configure

```bash
git clone <repo-url> cs5187_graph
cd cs5187_graph
python -m venv .venv && source .venv/bin/activate
pip install openai tiktoken python-dotenv pyyaml clang
```

Copy the config template and fill in your endpoint + model:

```bash
cp config.yaml.example config.yaml
```

Create `.env` with your API keys (never commit this file):

```
NVIDIA_API_KEY=nvapi-...
LLM_API_KEY=...           # for local LM Studio or other provider
```

### 2. Fetch the SQLite source tree

```bash
git clone https://github.com/sqlite/sqlite.git sqlite-src
cd sqlite-src && git checkout version-3.30.1 && cd ..
```

Confirm commit: `25e9591`.

### 3. Build the graph databases

**Compile-time graph (CT):**

```bash
# Step 1: Extract CT graph (requires libclang 18)
python src/extractor/extract.py

# Step 2: Add taint_reaches edges (v1 → v2)
python src/graphs/taint.py

# Step 3: Write provenance metadata
python src/graphs/make_meta.py
```

Outputs: `src/graphs/graph_ct_v1.db` (417 functions, 2438 call edges), `src/graphs/graph_ct_v2.db` (+84 taint_reaches edges).

**Syntactic graph (SYN):**

```bash
# Step 1: Run graphify on the SQLite source (graphify must be on PATH)
bash src/graphs/syn/run_graphify.sh

# Step 2: Convert graph.json to SQLite DB
python src/graphs/syn/adapter.py
```

Output: `src/graphs/graph_syn.db`.

---

## One-Command Reproduction of the Headline Result

Run all evaluation conditions for Qwen and generate the summary table:

```bash
python src/eval/run_eval.py --config config_local_qwen.yaml --conds NOCTX,SYN-TOOL,CT-TOOL,SYN-TEXT,CT-TEXT,CT-ct_calls,CT-ct_types,CT-source_only,SYN-source_only
python src/eval/summary.py
```

Output: `results/summary.md` — the accuracy, token-usage, and latency table used in the paper.

For Nemotron (requires NVIDIA API key):

```bash
python src/eval/run_eval.py --config config_nemotron.yaml --conds NOCTX,SYN-TOOL,CT-TOOL,SYN-TEXT,CT-TEXT
python src/eval/summary.py
```

> **Note**: The evaluation is **resumable**. If interrupted, re-running the same command skips already-completed `(question_id, condition, rep)` triples. The Nemotron ablation conditions (`CT-ct_calls`, `CT-ct_types`, `CT-source_only`, `SYN-source_only`) are excluded because the NVIDIA API returned empty completions for every tool subset; this is noted in the paper's Limitations section.

### Additional analysis scripts

```bash
# Classify wrong answers by failure type → results/error_analysis.md
python src/eval/error_analysis.py

# Check cited edges and evidence paths against graph DBs → results/path_check.md
python src/eval/path_check.py
```

Pre-computed results from our runs are already in `results/`.

---

## Evaluation Conditions

| Condition | Graph | Context delivery | Tools available |
|---|---|---|---|
| `NOCTX` | — | None | None |
| `SYN-TOOL` | Syntactic | Tool calls | All 7 tools |
| `CT-TOOL` | Compile-time (v2) | Tool calls | All 7 tools |
| `SYN-TEXT` | Syntactic | BFS text slice in prompt | None |
| `CT-TEXT` | Compile-time (v2) | BFS text slice in prompt | None |
| `CT-ct_calls` | Compile-time (v2) | Tool calls | callers, callees, source, search |
| `CT-ct_types` | Compile-time (v2) | Tool calls | callers, callees, type hierarchy, source, search |
| `CT-source_only` | Compile-time (v2) | Tool calls | source + search only |
| `SYN-source_only` | Syntactic | Tool calls | source + search only |

All tool conditions run up to 15 turns; if no final answer is given the agent is force-prompted on turn 15.

---

## Available Graph Tools

| Tool | Description |
|---|---|
| `get_callers(fn)` | Direct callers of a function |
| `get_callees(fn)` | Direct callees of a function |
| `get_type_hierarchy(type)` | Struct/union fields and their types |
| `find_call_path(entry, target)` | BFS shortest call chain |
| `get_taint_paths(param)` | Sink functions reachable from a tainted parameter |
| `get_function_source(fn)` | Source lines with pagination |
| `search_functions(substr)` | Fuzzy name search |

---

## Configuration

`config.yaml` (not committed — copy from `config.yaml.example`):

```yaml
llm:
  base_url: http://172.16.116.23:1234/v1   # LM Studio endpoint, or NVIDIA/OpenRouter/etc.
  model: qwen3-coder-30b-a3b-instruct
  api_key_env: LLM_API_KEY
  temperature: 0.0
  max_tokens: 2048
  strip_reasoning: false
  enable_thinking: false
```

For Nemotron use `config_nemotron.yaml` (committed — no keys, reads `NVIDIA_API_KEY` from `.env`).

---

## Key Results

Full tables in [`results/summary.md`](results/summary.md). Summary:

- **Accuracy is low across all conditions** (≤ 1/6 exact on either model in any single condition), driven by two structural factors: function-pointer gaps that make Q001 and Q004 unreachable in both graphs (31% of Qwen wrong-answer slots), and incorrect function identification for questions where the graph does contain the ground truth (52% of slots).
- **Tool vs. text**: on Qwen, the TEXT conditions match or exceed the TOOL conditions in exact accuracy, at 10–15× lower token cost. Nemotron solved Q005 in both tool conditions while Qwen's tool conditions failed it, so the pattern is model-dependent.
- **Source-only control**: consuming ~209,000 mean prompt tokens (4–5× the full Qwen tool conditions), source-only never scored above zero exact on the five unflagged questions, showing that raw source access without graph navigation tools does not help.
- **Path correctness**: 28% of edges cited by source-only conditions are not supported by the graph vs. 12% for conditions with caller/callee tools (~2.4×). Absent edges may reflect function-pointer gaps rather than model fabrication.

---

## Benchmark Questions

Six fault-localisation questions over SQLite 3.30.1, targeting functions involved in SQL query processing. Ground-truth functions:

| Q | Ground truth |
|---|---|
| Q001 | `resolveOrderByTermToExprList` |
| Q002 | `sqlite3Select` *(flagged — likely memorised; correct in 3/3 NOCTX)* |
| Q003 | `flattenSubquery` |
| Q004 | `withExpand` |
| Q005 | `sqlite3_str_vappendf` |
| Q006 | `resetAccumulator` |

Questions and expected answers are in [`benchmark_work/questions.csv`](benchmark_work/questions.csv).

---

## Upstream Bug Reports / Patches

No upstream bug reports or patches were filed against SQLite as part of this project. The `src/benchmark/oomloop.c` stress tester was developed for OOM-path testing but no reproducible bugs were isolated within the project timeline.

---

## License

MIT — see [LICENSE](LICENSE).

