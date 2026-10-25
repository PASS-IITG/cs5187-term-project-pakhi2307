## Pilot result: nvidia/nemotron-3-ultra-550b-a55b (NVIDIA hosted endpoint), 25 Oct 2026
-Test 1 (JSON, 5 questions x 5 reps): 25/25 lenient, 25/25 strict. 25 calls, 0 failed attempts. Run uncapped (config max_tokens was not applied by llm.py).
-Completion tokens per call: median 2,116, max 7,194 (mostly hidden reasoning). Latency per call: median 36.5 s, max 113.7 s.
-Test 2 (tools only, 3 questions x 3 reps, 15-turn cap):
--strip_reasoning=true: 0/9 passed (all hit the iteration cap).
--strip_reasoning=false: 3/9 passed (p3 only). 0 bad tool names, 0 bad arguments, 0 ungrounded edges in both runs.
--Tool-turn latency: median 1.6 s.
-Pilot limitation: p1 and p2 cannot be answered with the three pilot tools (no source tool, no gold answer), so cap hits mostly reflect the pilot design.
-nemotron-3-super-120b-a12b (NVIDIA): 7/9 earlier, but later returns 404 (not available).
-Not measured: context window [VERIFY], knowledge cutoff, nemotron-3.5-lightning-30b-a3b.
## Pilot result: nvidia/nemotron-3.5-super-vl-120b-a12b (NVIDIA hosted endpoint), 25 Oct 2026
-Test 2 (tools only, 3 questions x 3 reps, 15-turn cap, strip_reasoning=false): 9/9 passed. 0 bad tool names, 0 bad arguments, 0 ungrounded edges, 0 repeats. Several tool calls per turn; 5-11 turns per episode. 60 calls, median latency 5.0 s, 93,869 completion tokens in total.
-Test 1 (JSON), attempt 1 (timeout 120 s): first call took 116 s and 14,607 completion tokens; the next call timed out on all 7 attempts; run aborted.
-Test 1 (JSON), attempt 2 (timeout_s 300, 1 rep x 5 questions, stopped early): 3 calls finished with 22,163 / 20,046 / 6,586 completion tokens and 204 / 217 / 60 s latency; 1 attempt timed out at 300 s; run stopped by hand. JSON validity not measured.
-Conclusion: passes the tool pilot but is too slow and token-heavy on single-shot JSON answers (roughly 10x ultra's median of ~2,100 tokens). Not pinned. Retest if a way to limit thinking is found [VERIFY].
-Pilot limitation: p1 and p2 cannot be answered with the three pilot tools, so tool-loop pass rates reflect the pilot design as much as the model.
