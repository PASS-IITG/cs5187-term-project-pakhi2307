"""Shared answer format (design doc D13): prompt text and a tolerant parser.
Any change to these field names is a CONTRACT CHANGE (the verifier reads them)."""
import json

SPEC = """Finish your reply with exactly one JSON object and nothing after it:
{
  "answer_function": "<the function you believe is responsible>",
  "top3": ["<best guess>", "<second>", "<third>"],
  "evidence_path": ["<entry function>", "<...>", "<answer function>"],
  "taint_path": null,
  "cited_edges": [{"src": "<caller>", "dst": "<callee>", "kind": "calls"}],
  "explanation": "<short prose>"
}
Rules: taint_path is null for purely structural questions. For taint questions it is a
list such as ["zSql", "...", "memcpy"]. In evidence_path each function must call the next one.
Do not wrap the JSON in markdown code fences."""


def validate(o):
    p = []
    if not isinstance(o, dict):
        return ["not_object"]
    for k, t in [("answer_function", str), ("top3", list), ("evidence_path", list),
                 ("cited_edges", list), ("explanation", str)]:
        if k not in o:
            p.append("missing_" + k)
        elif not isinstance(o[k], t):
            p.append("type_" + k)
    if "taint_path" not in o:
        p.append("missing_taint_path")
    elif o["taint_path"] is not None and not isinstance(o["taint_path"], list):
        p.append("type_taint_path")
    for e in o.get("cited_edges", []) if isinstance(o.get("cited_edges"), list) else []:
        if not (isinstance(e, dict) and {"src", "dst", "kind"} <= set(e)):
            p.append("bad_edge_item")
            break
    return p


def parse_final(text):
    """Return (obj, problems). Uses the LAST top-level JSON object found in the text."""
    probs = []
    if not text:
        return None, ["empty"]
    dec, objs, i = json.JSONDecoder(), [], 0
    while i < len(text):
        if text[i] == "{":
            try:
                o, end = dec.raw_decode(text, i)
                objs.append((o, i, end))
                i = end
                continue
            except ValueError:
                pass
        i += 1
    if not objs:
        return None, ["no_json"]
    if len(objs) > 1:
        probs.append("multiple_objects")
    if "```" in text:
        probs.append("code_fence")
    if text[objs[-1][2]:].strip():
        probs.append("trailing_text")
    obj = objs[-1][0]
    probs += validate(obj)
    return obj, probs


def hard(probs):
    """Problems that make the answer unusable (fences and trailing text are tolerated)."""
    return [p for p in probs if p not in ("code_fence", "trailing_text")]
