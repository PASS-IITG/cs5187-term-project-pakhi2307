# Error analysis — Qwen3-coder

Conditions: all graph conditions (NOCTX excluded).

Buckets: **CORRECT** / **callback_gap** / **default_entry** / **not_in_graph** / **wrong_other**

| Q | GT | Entry | SYN-TOOL | CT-TOOL | SYN-TEXT | CT-TEXT | CT-ct_calls | CT-ct_types | CT-source_only | SYN-source_only |
|---|---|---|---|---|---|---|---|---|---|---|
| Q001 | `resolveOrderByTermToExprList` | `sqlite3Select` | **CORRECT**<br/>`resolveOrderByTermToExprL` | callback_gap<br/>`sqlite3Select` | callback_gap<br/>`sqlite3Select` | callback_gap<br/>`sqlite3Select` | callback_gap<br/>`walkWindowList` | callback_gap<br/>`sqlite3ResolveOrderGroupB` | callback_gap<br/>`resolveOrderGroupBy` | callback_gap<br/>`sqlite3SelectPrep` |
| Q002 | `sqlite3Select` | `sqlite3Select` | wrong_other<br/>`codeDistinct` | wrong_other<br/>`codeDistinct` | wrong_other<br/>`selectInnerLoop` | **CORRECT**<br/>`sqlite3Select` | wrong_other<br/>`codeDistinct` | wrong_other<br/>`codeDistinct` | **CORRECT**<br/>`sqlite3Select` | wrong_other<br/>`selectInnerLoop` |
| Q003 | `flattenSubquery` | `sqlite3Select` | wrong_other<br/>`codeDistinct` | wrong_other<br/>`codeDistinct` | wrong_other<br/>`pushDownWhereTerms` | default_entry<br/>`sqlite3Select` | wrong_other<br/>`codeDistinct` | wrong_other<br/>`codeDistinct` | wrong_other<br/>`codeDistinct` | wrong_other<br/>`codeDistinct` |
| Q004 | `withExpand` | `sqlite3Select` | callback_gap<br/>`walkExpr` | callback_gap<br/>`walkExpr` | callback_gap<br/>`sqlite3Select` | callback_gap<br/>`sqlite3Select` | callback_gap<br/>`walkExpr` | callback_gap<br/>`walkExpr` | callback_gap<br/>`sqlite3SelectAddColumnTyp` | callback_gap<br/>`sqlite3Select` |
| Q005 | `sqlite3_str_vappendf` | `sqlite3_step` | wrong_other<br/>`printfTempBuf` | wrong_other<br/>`printfTempBuf` | **CORRECT**<br/>`sqlite3_str_vappendf` | **CORRECT**<br/>`sqlite3_str_vappendf` | wrong_other<br/>`printfTempBuf` | wrong_other<br/>`printfTempBuf` | wrong_other<br/>`printfTempBuf` | wrong_other<br/>`printfTempBuf` |
| Q006 | `resetAccumulator` | `sqlite3Select` | wrong_other<br/>`walkWindowList` | wrong_other<br/>`walkWindowList` | default_entry<br/>`sqlite3Select` | default_entry<br/>`sqlite3Select` | wrong_other<br/>`walkWindowList` | wrong_other<br/>`walkExpr` | wrong_other<br/>`havingToWhereExprCb` | wrong_other<br/>`havingToWhereExprCb` |

## Bucket totals (across all conditions × questions)

| Bucket | Count | Explanation |
|---|---|---|
| CORRECT       | 5       | answer_function == ground truth |
| callback_gap  | 15  | GT unreachable: edge crosses function pointer (Q001, Q004) |
| default_entry | 3 | Model named the entry function (sqlite3Select / sqlite3_step) |
| not_in_graph  | 0  | GT not present as a node in the graph |
| wrong_other   | 25   | GT is in graph; model named a different function |

## Dominant failure per question

- **Q001** (resolveOrderByTermToExprList): dominant=**callback_gap** — {'callback_gap': 7}
- **Q002** (sqlite3Select): dominant=**wrong_other** — {'wrong_other': 6}
- **Q003** (flattenSubquery): dominant=**wrong_other** — {'wrong_other': 7, 'default_entry': 1}
- **Q004** (withExpand): dominant=**callback_gap** — {'callback_gap': 8}
- **Q005** (sqlite3_str_vappendf): dominant=**wrong_other** — {'wrong_other': 6}
- **Q006** (resetAccumulator): dominant=**wrong_other** — {'wrong_other': 6, 'default_entry': 2}
