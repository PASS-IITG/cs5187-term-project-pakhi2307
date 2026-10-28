
## D1 amendment - 27 Oct 2026
- Change: add src/select.c, src/resolve.c and src/expr.c to the analysed files for BOTH graphs (CT and SYN) as ring-1 (extended tier). The five core files (tokenize.c, parse.c, vdbe.c, vdbeapi.c, vdbemem.c) are unchanged; prepare.c stays ring-1.
- Reason: the first two benchmark candidates have ground truth in select.c and resolve.c.
- Proposed by: Pakhi (B). Confirmed by: Aditi (A). Date: 27 Oct 2026.
- Effects: token count re-measured on the nine-file list (see docs/token_count.txt); CT graph and taint (K=4/6/8) rebuilt; the SYN graph must be rebuilt on the same file list.
- Scope note: questions whose ground truth is outside the five core files are extended tier and reported separately. This departs from the proposal's five-file subsystem and is a disclosed deviation. Instructor to be informed at Progress Meeting 2.

## D14 amendment: ground truth is the fault site, not the crash site (2026-10-28)

**Status:** agreed by A (graph engineer); proposed by B (benchmark/agent engineer).

**Decision.** For every benchmark question, the ground-truth function is the function that contains the faulty logic, not the function where the crash or failure is observed. The question is worded the same way for all conditions (CT tool, CT text, SYN tool, SYN text, and the no-context run): "Which function contains the faulty logic that leads to this?"

**Why.** For several bugs the crash site and the faulty logic are different functions (for example, a crash in sqlite3VdbeExec at run time whose cause is flattenSubquery at prepare time). With the crash site as ground truth, such a question would (a) be a giant_function question with a weak call path and (b) score a correct diagnosis of the cause as wrong. The fault site is also the answer that wrong-result and assertion bugs have, so one template covers every bug kind and no second question form is needed.

**Fairness.** The wording and the scoring rule are identical in all five conditions, so the comparison between conditions is unchanged. Only the definition of the correct answer changed.

**Effect on completed work.** None on the graphs, tools, taint pass or token counts. Questions already written with a crash-site answer must be re-checked and their ground_truth_function updated; questions whose fault site is outside the shared file list are handled by the file-list decision below.

**Related, still open.** (1) The shared file list must contain every question's ground-truth function; it will be fixed once, by a stated rule (files needed by verified questions), both graphs rebuilt from it, and the additions disclosed as an extended tier. (2) Extended-tier questions (wrong-result, assertion-only, corrupt-db, OOM) are reported as a separate tier, not mixed into the headline figure. (3) A second pin (3.25.0) is a last resort, since it requires rebuilding both graphs.

**Known limitation recorded.** Calls through function pointers (walker callbacks, xSFunc) are counted as indirect_calls_unresolved and stored in function metadata, not drawn as edges, so call paths through callbacks have gaps in the CT graph. Questions whose true path uses a callback are to be flagged and reported separately.
