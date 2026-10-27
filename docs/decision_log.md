
## D1 amendment - 27 Oct 2026
- Change: add src/select.c, src/resolve.c and src/expr.c to the analysed files for BOTH graphs (CT and SYN) as ring-1 (extended tier). The five core files (tokenize.c, parse.c, vdbe.c, vdbeapi.c, vdbemem.c) are unchanged; prepare.c stays ring-1.
- Reason: the first two benchmark candidates have ground truth in select.c and resolve.c.
- Proposed by: Pakhi (B). Confirmed by: Aditi (A). Date: 27 Oct 2026.
- Effects: token count re-measured on the nine-file list (see docs/token_count.txt); CT graph and taint (K=4/6/8) rebuilt; the SYN graph must be rebuilt on the same file list.
- Scope note: questions whose ground truth is outside the five core files are extended tier and reported separately. This departs from the proposal's five-file subsystem and is a disclosed deviation. Instructor to be informed at Progress Meeting 2.
