## Pilot result: nvidia/nemotron-3-ultra-550b-a55b (NVIDIA hosted endpoint), 25 Oct 2026
- Test 1 (JSON, 5 questions x 5 reps): 25/25 lenient, 25/25 strict. 25 calls, 0 failed attempts. Run uncapped (config max_tokens was not applied by llm.py).
- Completion tokens per call: median 2,116, max 7,194 (mostly hidden reasoning). Latency per call: median 36.5 s, max 113.7 s.
- Test 2 (tools only, 3 questions x 3 reps, 15-turn cap):
  - strip_reasoning=true: 0/9 passed (all hit the iteration cap).
  - strip_reasoning=false: 3/9 passed (p3 only). 0 bad tool names, 0 bad arguments, 0 ungrounded edges in both runs.
  - Tool-turn latency: median 1.6 s.
- Pilot limitation: p1 and p2 cannot be answered with the three pilot tools (no source tool, no gold answer), so cap hits mostly reflect the pilot design.
- nemotron-3-super-120b-a12b (NVIDIA): 7/9 earlier, but later returns 404 (not available).
- Not measured: context window [VERIFY], knowledge cutoff, nemotron-3.5-lightning-30b-a3b.
