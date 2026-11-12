# Path correctness and hallucination rate — Qwen3-coder

Tool conditions only (TEXT has no cited_edges). One run per (question, condition).

## Per-answer edge verdict

| Q | Condition | Answer | cited_edges | valid | reversed | not in graph | evidence_path pairs | path valid | path rev | path not-in-graph |
|---|---|---|---|---|---|---|---|---|---|---|
| Q001 | CT-TOOL | `sqlite3Select` | 3 | 3 | 0 | 0 | 3 | 3 | 0 | 0 |
| Q001 | CT-ct_calls | `walkWindowList` | 4 | 4 | 0 | 0 | 7 | 6 | 0 | 1 |
| Q001 | CT-ct_types | `sqlite3ResolveOrderGroupB` | 3 | 3 | 0 | 0 | 3 | 3 | 0 | 0 |
| Q001 | CT-source_only | `resolveOrderGroupBy` | 5 | 4 | 1 | 0 | 5 | 4 | 1 | 0 |
| Q001 | SYN-TOOL | `resolveOrderByTermToExprL` | 3 | 2 | 0 | 1 | 3 | 2 | 0 | 1 |
| Q001 | SYN-source_only | `sqlite3SelectPrep` | 2 | 1 | 0 | 1 | 2 | 1 | 0 | 1 |
| Q002 | CT-TOOL | `codeDistinct` | 2 | 2 | 0 | 0 | 2 | 2 | 0 | 0 |
| Q002 | CT-ct_calls | `codeDistinct` | 2 | 2 | 0 | 0 | 2 | 2 | 0 | 0 |
| Q002 | CT-ct_types | `codeDistinct` | 2 | 2 | 0 | 0 | 2 | 2 | 0 | 0 |
| Q002 | CT-source_only | `sqlite3Select` | 2 | 2 | 0 | 0 | 2 | 2 | 0 | 0 |
| Q002 | SYN-TOOL | `codeDistinct` | 2 | 2 | 0 | 0 | 2 | 2 | 0 | 0 |
| Q002 | SYN-source_only | `selectInnerLoop` | 3 | 3 | 0 | 0 | 2 | 1 | 0 | 1 |
| Q003 | CT-TOOL | `codeDistinct` | 2 | 2 | 0 | 0 | 2 | 2 | 0 | 0 |
| Q003 | CT-ct_calls | `codeDistinct` | 2 | 2 | 0 | 0 | 2 | 2 | 0 | 0 |
| Q003 | CT-ct_types | `codeDistinct` | 2 | 2 | 0 | 0 | 2 | 2 | 0 | 0 |
| Q003 | CT-source_only | `codeDistinct` | 2 | 2 | 0 | 0 | 2 | 2 | 0 | 0 |
| Q003 | SYN-TOOL | `codeDistinct` | 2 | 2 | 0 | 0 | 2 | 2 | 0 | 0 |
| Q003 | SYN-source_only | `codeDistinct` | 3 | 0 | 2 | 1 | 3 | 0 | 2 | 1 |
| Q004 | CT-TOOL | `walkExpr` | 5 | 4 | 0 | 1 | 5 | 4 | 0 | 1 |
| Q004 | CT-ct_calls | `walkExpr` | 7 | 7 | 0 | 0 | 5 | 4 | 0 | 1 |
| Q004 | CT-ct_types | `walkExpr` | 6 | 5 | 0 | 1 | 6 | 5 | 0 | 1 |
| Q004 | CT-source_only | `sqlite3SelectAddColumnTyp` | 7 | 4 | 0 | 3 | 11 | 5 | 1 | 5 |
| Q004 | SYN-TOOL | `walkExpr` | 4 | 3 | 0 | 1 | 4 | 3 | 0 | 1 |
| Q004 | SYN-source_only | `sqlite3Select` | 11 | 6 | 1 | 4 | 10 | 4 | 1 | 5 |
| Q005 | CT-TOOL | `printfTempBuf` | 6 | 4 | 0 | 2 | 6 | 4 | 0 | 2 |
| Q005 | CT-ct_calls | `printfTempBuf` | 4 | 3 | 0 | 1 | 4 | 3 | 0 | 1 |
| Q005 | CT-ct_types | `printfTempBuf` | 4 | 3 | 0 | 1 | 4 | 3 | 0 | 1 |
| Q005 | CT-source_only | `printfTempBuf` | 4 | 3 | 0 | 1 | 4 | 3 | 0 | 1 |
| Q005 | SYN-TOOL | `printfTempBuf` | 5 | 5 | 0 | 0 | 5 | 5 | 0 | 0 |
| Q005 | SYN-source_only | `printfTempBuf` | 4 | 3 | 0 | 1 | 4 | 3 | 0 | 1 |
| Q006 | CT-TOOL | `walkWindowList` | 4 | 4 | 0 | 0 | 4 | 4 | 0 | 0 |
| Q006 | CT-ct_calls | `walkWindowList` | 4 | 4 | 0 | 0 | 4 | 4 | 0 | 0 |
| Q006 | CT-ct_types | `walkExpr` | 4 | 2 | 0 | 2 | 4 | 2 | 0 | 2 |
| Q006 | CT-source_only | `havingToWhereExprCb` | 2 | 1 | 0 | 1 | 2 | 1 | 0 | 1 |
| Q006 | SYN-TOOL | `walkWindowList` | 4 | 4 | 0 | 0 | 4 | 4 | 0 | 0 |
| Q006 | SYN-source_only | `havingToWhereExprCb` | 2 | 1 | 0 | 1 | 2 | 1 | 0 | 1 |

## Aggregate (cited_edges)

| Group | edges | valid | reversed | not in graph | not-in-graph rate |
|---|---|---|---|---|---|
| Source-only conditions | 47 | 30 | 4 | 13 | 27% |
| Other tool conditions  | 86 | 76 | 0 | 10 | 11% |
| **All tool conditions**| 133 | 106 | 4 | 23 | 17% |

## Aggregate (evidence_path consecutive pairs)

| Group | pairs | valid | reversed | not in graph | not-in-graph rate |
|---|---|---|---|---|---|
| Source-only conditions | 49 | 27 | 5 | 17 | 34% |
| Other tool conditions  | 87 | 75 | 0 | 12 | 13% |
| **All tool conditions**| 136 | 102 | 5 | 29 | 21% |

> **Not-in-graph rate** = edges not supported by the graph / total edges checked.
> An edge absent from the graph may cross a function pointer (not modelled) rather than
> being a model fabrication; the rate is therefore an upper bound on hallucination.
