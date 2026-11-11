"""run_eval.py - runs benchmark questions under each condition. ONE model per invocation (its config).
Resumable: a run is keyed by (question_id, condition, rep); finished keys in the output file are skipped.
Conditions here: NOCTX (no graph, no tools, sampled reps), SYN-TOOL, CT-TOOL. TEXT arms come with the slicer."""
import argparse, csv, json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
for p in (os.path.join(SRC, "agents"), SRC):
    sys.path.insert(0, p)
from llm import LLM, LLMError, load_config            # noqa: E402
from answer import SPEC, parse_final                   # noqa: E402
from graph_tool import run_tool_agent, run_record      # noqa: E402

from tools.graph_slice import graph_slice              # noqa: E402
DBS = {"SYN-TOOL": "src/graphs/graph_syn.db", "CT-TOOL": "src/graphs/graph_ct_v2.db",
       "SYN-TEXT": "src/graphs/graph_syn.db", "CT-TEXT": "src/graphs/graph_ct_v2.db"}
NOCTX_PREFIX = ("The following question is about the SQLite database engine source code. "
                "No code and no tools are provided. Answer from your own knowledge.\n\n")


def make_llm(config, temperature=None):
    if temperature is None:
        return LLM(config_path=config)
    cfg = load_config(config)
    cfg = dict(cfg.get("llm", cfg))
    cfg["temperature"] = temperature
    return LLM(cfg=cfg)


def run_noctx(llm, qtext, qid, max_tokens):
    t0 = time.time()
    r = llm.chat([{"role": "user", "content": NOCTX_PREFIX + qtext + "\n\n" + SPEC}],
                 tools=None, max_tokens=max_tokens, question_id=qid, variant="noctx")
    return {"final_text": r["message"].get("content") or "", "stopped_by": r["finish_reason"],
            "turns": 1, "tool_calls": 0, "prompt_tokens": r["usage"]["prompt_tokens"],
            "completion_tokens": r["usage"]["completion_tokens"],
            "latency_s": round(time.time() - t0, 3)}


def run_text(llm, q, db, max_tokens, budget):
    t0 = time.time()
    try:
        sl = graph_slice(db, q["entry_function"], budget_tokens=budget)["text"]
    except Exception as e:
        raise LLMError("slice failed: " + repr(e)[:150])
    prompt = ("Below is a slice of a graph of this program (functions and call edges) around the entry function.\n\n"
              + sl + "\n\n" + q["question"] + "\n\n" + SPEC)
    r = llm.chat([{"role": "user", "content": prompt}], tools=None, max_tokens=max_tokens,
                 question_id=q["id"], variant="text")
    return {"final_text": r["message"].get("content") or "", "stopped_by": r["finish_reason"],
            "turns": 1, "tool_calls": 0, "prompt_tokens": r["usage"]["prompt_tokens"],
            "completion_tokens": r["usage"]["completion_tokens"], "latency_s": round(time.time() - t0, 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--csv", default=os.path.expanduser("~/cs5187/benchmark_work/questions.csv"))
    ap.add_argument("--root", default="sqlite-src")
    ap.add_argument("--conds", default="NOCTX,SYN-TOOL,CT-TOOL")
    ap.add_argument("--only", default="", help="comma list of question ids")
    ap.add_argument("--noctx-reps", type=int, default=3)
    ap.add_argument("--noctx-temp", type=float, default=0.7)
    ap.add_argument("--max-tokens", type=int, default=3000)
    ap.add_argument("--budget", type=int, default=6000)
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    qs = list(csv.DictReader(open(a.csv, encoding="utf-8")))
    only = {x for x in a.only.split(",") if x}
    if only:
        qs = [q for q in qs if q["id"] in only]
    conds = [c for c in a.conds.split(",") if c]
    llm = make_llm(a.config)
    model = llm.model
    llm_nc = make_llm(a.config, a.noctx_temp) if "NOCTX" in conds else None
    tag = re.sub(r"[^A-Za-z0-9._-]+", "_", model)
    out = a.out or f"results/runs_{tag}.jsonl"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    done = set()
    if os.path.exists(out):
        for line in open(out, encoding="utf-8"):
            try:
                r = json.loads(line)
                done.add((r["question_id"], r["condition"], r.get("rep", 1)))
            except Exception:
                pass
    print(f"model={model} out={out} questions={len(qs)} conds={conds} already_done={len(done)}")
    n_ok = n_err = 0
    for cond in conds:
        for q in qs:
            reps = a.noctx_reps if cond == "NOCTX" else 1
            for rep in range(1, reps + 1):
                if (q["id"], cond, rep) in done:
                    continue
                try:
                    if cond == "NOCTX":
                        res = run_noctx(llm_nc, q["question"], q["id"], a.max_tokens)
                    elif cond.endswith("-TEXT"):
                        res = run_text(llm, q, DBS[cond], a.max_tokens, a.budget)
                    else:
                        res = run_tool_agent(llm, q["question"], DBS[cond], a.root, "full",
                                             question_id=q["id"])
                except LLMError as e:
                    n_err += 1
                    print(f"ERROR {q['id']} {cond} rep{rep}: {str(e)[:200]}")
                    continue
                rec = run_record(q["id"], cond, res, model)
                rec["rep"] = rep
                with open(out, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                if "trace" in res:
                    with open(f"logs/traces/{tag}_{cond}_{q['id']}.json", "w", encoding="utf-8") as f:
                        json.dump(res["trace"], f, ensure_ascii=False, indent=1)
                obj, probs = parse_final(res["final_text"])
                ans = obj.get("answer_function") if isinstance(obj, dict) else None
                n_ok += 1
                print(f"{q['id']} {cond} rep{rep}: answer={ans} stop={res['stopped_by']} "
                      f"turns={res['turns']} tok={res['prompt_tokens']}+{res['completion_tokens']} "
                      f"{res['latency_s']}s problems={probs}")
    print(f"done ok={n_ok} errors={n_err} -> {out}")


if __name__ == "__main__":
    main()
