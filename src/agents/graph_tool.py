"""Graph-as-tool agent (design doc D12). The same loop serves SYN and CT: only db_path differs."""
import argparse, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, SRC)
from answer import SPEC, parse_final, hard   # noqa: E402
from tools import graph_tools                # noqa: E402

SUPPORT = {"get_function_source", "search_functions"}   # on in every variant (D9, D16)
ABLATIONS = {
    "ct_calls": {"get_callers", "get_callees"},
    "ct_types": {"get_callers", "get_callees", "get_type_hierarchy"},
    "full": None,            # every tool the graph offers
    "source_only": set(),    # control: support tools only
}
# D17 prompt: guidance targeting observed failure modes without question-specific tailoring
TOOL_PROMPT = ("\n\nYou have tools to query a graph of this code and to read function source.\n"
               "Goal: The answer is the function whose code must change to fix the bug, not the function where the crash "
               "or wrong output appears, and not a function that merely has a name matching the symptom keywords.\n"
               "Guidelines:\n"
               "- You have at most {max_turns} tool calls. As soon as you have a candidate function and a supporting call path, "
               "stop and give the final JSON. Do not use all your turns.\n"
               "- Before answering, read the source of your top candidate with get_function_source and check that its logic is wrong for the given input.\n"
               "- Calls made through function pointers are not in the graph. If no direct path exists, search for where the function pointer or callback is set/registered.\n"
               "- Cite only edges that tools returned. If a name is unknown, call search_functions instead of guessing.\n"
               "- In your final JSON, provide one or two concise sentences in the explanation field.\n"
               "- If the tools cannot identify the responsible function, give your best guess and finish.\n\n")


# Harness rule (CONTRACT CHANGE 3 Nov, identical for SYN-TOOL and CT-TOOL): when the turn cap is reached without a
# final answer, one extra call WITHOUT tools asks for the final JSON. Such runs get stopped_by "forced_final".
FORCE_PROMPT = ("You have used all your tool turns. Do not call any more tools. Using only what you have retrieved so far, "
                "give your final answer now as the single JSON object described above. If you are unsure, give your best guess.")


def run_tool_agent(llm, question, db_path, root, variant="full", max_turns=15, **meta):
    allowed = None if ABLATIONS[variant] is None else ABLATIONS[variant] | SUPPORT
    tools = [{"type": "function", "function": s} for s in graph_tools.schemas(db_path, allowed)]
    prompt_text = TOOL_PROMPT.format(max_turns=max_turns)
    msgs = [{"role": "user", "content": question + prompt_text + SPEC}]
    t0 = time.time()
    pt = ct = n_calls = turns = 0
    stopped, text = "iteration_cap", ""
    for turn in range(max_turns):
        r = llm.chat(msgs, tools=tools, turn=turn, **meta)
        m = r["message"]
        msgs.append(m)
        turns = turn + 1
        pt += r["usage"]["prompt_tokens"]
        ct += r["usage"]["completion_tokens"]
        calls = m.get("tool_calls") or []
        if not calls:
            stopped, text = "final", m.get("content") or ""
            break
        for c in calls:
            n_calls += 1
            name = c["function"]["name"]
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
                out = graph_tools.dispatch(db_path, name, args, root, allowed)
            except ValueError as e:
                out = {"error": "BAD_ARGUMENTS", "detail": str(e)}
            msgs.append({"role": "tool", "tool_call_id": c["id"],
                         "content": json.dumps(out, ensure_ascii=False)})

        remaining = max_turns - (turn + 1)
        if remaining > 0:
            nudge = f"Tool calls left: {remaining}."
            if turn >= (2 * max_turns) // 3:
                nudge += " Start converging. If you have a candidate, stop and give the final JSON now."
            msgs.append({"role": "user", "content": nudge})
    if stopped == "iteration_cap":
        msgs.append({"role": "user", "content": FORCE_PROMPT})
        r = llm.chat(msgs, tools=None, turn=max_turns, **meta)
        m = r["message"]
        msgs.append(m)
        pt += r["usage"]["prompt_tokens"]
        ct += r["usage"]["completion_tokens"]
        text = m.get("content") or ""
        stopped = "forced_final"
    return {"final_text": text, "stopped_by": stopped, "turns": turns, "tool_calls": n_calls,
            "prompt_tokens": pt, "completion_tokens": ct,
            "latency_s": round(time.time() - t0, 3), "variant": variant, "trace": msgs}


def run_record(question_id, condition, res, model):
    """One line for runs.jsonl. Field names are a CONTRACT with the verifier."""
    return {"question_id": question_id, "condition": condition, "final_text": res["final_text"],
            "prompt_tokens": res["prompt_tokens"], "completion_tokens": res["completion_tokens"],
            "latency_s": res["latency_s"], "turns": res["turns"], "tool_calls": res["tool_calls"],
            "stopped_by": res["stopped_by"], "model": model, "ts": int(time.time())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--root", default="sqlite-src")
    ap.add_argument("--variant", default="full", choices=list(ABLATIONS))
    ap.add_argument("--question", required=True)
    ap.add_argument("--config", default="config.yaml")
    a = ap.parse_args()
    from llm import LLM
    res = run_tool_agent(LLM(config_path=a.config), a.question, a.db, a.root, a.variant, question_id="smoke")
    os.makedirs("logs", exist_ok=True)
    json.dump(res["trace"], open(f"logs/agent_trace_{a.variant}.json", "w"), ensure_ascii=False, indent=1)
    obj, probs = parse_final(res["final_text"])
    print({k: v for k, v in res.items() if k not in ("trace", "final_text")})
    print("parsed:", obj)
    print("problems:", probs, "| hard:", hard(probs))


if __name__ == "__main__":
    main()
