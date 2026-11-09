# src/llm.py : the ONLY path to the model.
import json, os, random, time, pathlib, uuid
import yaml
from dotenv import load_dotenv
load_dotenv()
try:
    from openai import (OpenAI, RateLimitError, APIConnectionError,
                        APITimeoutError, APIStatusError)
except ImportError:  # allow mock mode without the package
    OpenAI = None
    RateLimitError = APIConnectionError = APITimeoutError = APIStatusError = Exception


class EmptyResponse(Exception):
    pass


class LLMError(RuntimeError):
    """Raised when the configured model cannot answer. We never fall back to another model."""


def load_config(path="config.yaml"):
    with open(path) as f:
        return yaml.safe_load(f)["llm"]


class LLM:
    def __init__(self, cfg=None, config_path="config.yaml"):
        self.cfg = cfg or load_config(config_path)
        c = self.cfg
        self.model = c["model"]
        self.temperature = c.get("temperature", 0)
        self.extra_body = c.get("extra_body")
        self.mock = bool(c.get("mock")) or os.getenv("LLM_MOCK") == "1"
        self.max_retries = c.get("max_retries", 6)
        self.base_backoff = c.get("base_backoff_s", 2)
        self.max_backoff = c.get("max_backoff_s", 60)
        self.log_path = pathlib.Path(c.get("log_path", "logs/llm_calls.jsonl"))
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.client = None
        if not self.mock:
            if OpenAI is None:
                raise LLMError("pip install openai (or use mock mode)")
            key = os.getenv(c["api_key_env"])
            if not key:
                raise LLMError(f"Missing env var {c['api_key_env']}")
            self.client = OpenAI(base_url=c["base_url"], api_key=key,
                                 timeout=c.get("timeout_s", 120), max_retries=0)

    # ---------- logging ----------
    def _log(self, rec):
        with open(self.log_path, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ---------- mock ----------
    def _mock_call(self, messages, tools):
        time.sleep(0.01)
        used_tool = any(m.get("role") == "tool" for m in messages)
        if tools and not used_tool:
            msg = {"role": "assistant", "content": None, "tool_calls": [{
                "id": "mock_" + uuid.uuid4().hex[:8], "type": "function",
                "function": {"name": tools[0]["function"]["name"],
                             "arguments": json.dumps({"substring": "prepare"})}}]}
            finish = "tool_calls"
        else:
            msg = {"role": "assistant", "content": json.dumps({
                "answer_function": "mock_fn", "top3": ["mock_fn"],
                "evidence_path": ["a", "b"], "taint_path": None,
                "cited_edges": [{"src": "a", "dst": "b", "kind": "calls"}],
                "explanation": "mock"})}
            finish = "stop"
        text_len = sum(len(str(m.get("content") or "")) for m in messages)
        usage = {"prompt_tokens": text_len // 4,
                 "completion_tokens": len(str(msg.get("content") or "")) // 4 + 5}
        return msg, usage, finish, "mock"

    def _clean(self, messages):
        if not self.cfg.get("strip_reasoning"):
            return messages
        return [{k: v for k, v in m.items() if k != "reasoning_content"} for m in messages]

    # ---------- real call ----------
    def _real_call(self, messages, tools, max_tokens):
        kw = dict(model=self.model, messages=self._clean(messages), temperature=self.temperature)
        if self.extra_body:
            kw["extra_body"] = self.extra_body
        if tools:
            kw["tools"] = tools
        if max_tokens:
            kw["max_tokens"] = max_tokens
        if self.cfg.get("seed") is not None:
            kw["seed"] = self.cfg["seed"]
        r = self.client.chat.completions.create(**kw)
        if not r.choices or r.choices[0].message is None:
            fr = r.choices[0].finish_reason if r.choices else None
            raise EmptyResponse(f"empty message from provider (finish_reason={fr})")
        msg = r.choices[0].message.model_dump(exclude_none=True)
        msg.setdefault("role", "assistant")
        u = r.usage
        usage = {"prompt_tokens": getattr(u, "prompt_tokens", 0) or 0,
                 "completion_tokens": getattr(u, "completion_tokens", 0) or 0,
                 "reasoning_tokens": getattr(getattr(u, "completion_tokens_details", None), "reasoning_tokens", 0) or 0}
        return msg, usage, r.choices[0].finish_reason, getattr(r, "model", self.model)

    # ---------- public API ----------
    def chat(self, messages, tools=None, max_tokens=None, **meta):
        """Returns dict: message, usage, latency_s, finish_reason, model.
        `meta` (e.g. question_id=, system=, variant=, turn=) is written to the log."""
        call_id = uuid.uuid4().hex[:12]
        t_start = time.time()
        for attempt in range(self.max_retries + 1):
            t0 = time.time()
            try:
                if self.mock:
                    msg, usage, finish, served = self._mock_call(messages, tools)
                else:
                    msg, usage, finish, served = self._real_call(messages, tools, max_tokens)
                lat = time.time() - t0
                self._log({"ts": time.time(), "call_id": call_id, "ok": True,
                           "attempt": attempt, "model_requested": self.model,
                           "model_served": served, "mock": self.mock,
                           "latency_s": round(lat, 3),
                           "total_latency_s": round(time.time() - t_start, 3),
                           "prompt_tokens": usage["prompt_tokens"],
                           "completion_tokens": usage["completion_tokens"],
                           "reasoning_tokens": usage.get("reasoning_tokens", 0),
                           "finish_reason": finish, "n_tools": len(tools or []),
                           **meta})
                return {"message": msg, "usage": usage, "latency_s": lat,
                        "total_latency_s": time.time() - t_start,
                        "finish_reason": finish, "model": served}
            except Exception as e:  # classify below
                status = getattr(e, "status_code", None)
                retryable = isinstance(e, (RateLimitError, APIConnectionError, APITimeoutError, EmptyResponse)) \
                    or (status is not None and (status == 429 or status >= 500))
                self._log({"ts": time.time(), "call_id": call_id, "ok": False,
                           "attempt": attempt, "error": type(e).__name__,
                           "status": status, "retryable": retryable,
                           "msg": str(e)[:300], **meta})
                if not retryable or attempt == self.max_retries:
                    raise LLMError(
                        f"LLM call failed after {attempt + 1} attempt(s): {e}") from e
                wait = None
                resp = getattr(e, "response", None)
                if resp is not None:
                    ra = resp.headers.get("retry-after")
                    if ra:
                        try:
                            wait = float(ra)
                        except ValueError:
                            pass
                if wait is None:
                    wait = min(self.max_backoff, self.base_backoff * 2 ** attempt)
                time.sleep(wait + random.uniform(0, 1))
        raise LLMError("unreachable")


if __name__ == "__main__":
    llm = LLM()
    out = llm.chat([{"role": "user", "content": "Say hello in one word."}], test="hello")
    print(out["message"], out["usage"], round(out["latency_s"], 2))
