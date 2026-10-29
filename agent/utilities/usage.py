"""In-memory LLM usage tracking (tokens, latency, calls) for observability.

Every chat model built by `agent.graphs.models.create_llm` carries `USAGE_CALLBACK`, so all
LLM calls are counted without touching the call sites. The API tags a request with the
feature that caused it via `track_feature("chat")`. Nothing is persisted: the counters live
for the lifetime of the API process, and prompts/answers are never recorded.

Optional price tags (USD per 1M tokens) turn tokens into an estimated cost:
LLM_PRICE_IN_PER_M and LLM_PRICE_OUT_PER_M.
"""

import os
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Optional

from langchain_core.callbacks import BaseCallbackHandler

_feature: ContextVar[str] = ContextVar("llm_feature", default="other")
RECENT_CALLS = 50


@contextmanager
def track_feature(name: str):
    """Attribute every LLM call made inside the block to `name`."""
    token = _feature.set(name)
    try:
        yield
    finally:
        _feature.reset(token)


def _price(var: str) -> Optional[float]:
    try:
        return float(os.environ[var])
    except (KeyError, ValueError):
        return None


def _bucket() -> Dict[str, Any]:
    return {"calls": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "seconds": 0.0}


def _add(bucket: Dict[str, Any], record: Dict[str, Any]) -> None:
    bucket["calls"] += 1
    bucket["input_tokens"] += record["input_tokens"]
    bucket["output_tokens"] += record["output_tokens"]
    bucket["total_tokens"] += record["total_tokens"]
    bucket["seconds"] += record["seconds"]


class UsageTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.started_at = time.time()
            self.total = _bucket()
            self.errors = 0
            self.calls_without_usage = 0
            self.by_feature: Dict[str, Dict[str, Any]] = defaultdict(_bucket)
            self.by_model: Dict[str, Dict[str, Any]] = defaultdict(_bucket)
            self.by_step: Dict[str, Dict[str, Any]] = defaultdict(_bucket)
            self.recent: deque = deque(maxlen=RECENT_CALLS)

    def record(self, *, feature: str, model: str, step: str, input_tokens: int, output_tokens: int,
               seconds: float, has_usage: bool = True) -> None:
        record = {
            "time": time.time(),
            "feature": feature,
            "model": model,
            "step": step,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "seconds": round(seconds, 2),
        }
        with self._lock:
            _add(self.total, record)
            _add(self.by_feature[feature], record)
            _add(self.by_model[model], record)
            if step:
                _add(self.by_step[step], record)
            if not has_usage:
                self.calls_without_usage += 1
            self.recent.appendleft(record)

    def record_error(self) -> None:
        with self._lock:
            self.errors += 1

    def summary(self) -> Dict[str, Any]:
        price_in, price_out = _price("LLM_PRICE_IN_PER_M"), _price("LLM_PRICE_OUT_PER_M")

        def cost(b: Dict[str, Any]) -> Optional[float]:
            if price_in is None or price_out is None:
                return None
            return round((b["input_tokens"] * price_in + b["output_tokens"] * price_out) / 1_000_000, 6)

        def rows(table: Dict[str, Dict[str, Any]]):
            items = [{"name": k, **v, "seconds": round(v["seconds"], 1), "cost_usd": cost(v)} for k, v in table.items()]
            return sorted(items, key=lambda r: r["total_tokens"], reverse=True)

        with self._lock:
            calls = self.total["calls"]
            return {
                "since": self.started_at,
                "total": {**self.total, "seconds": round(self.total["seconds"], 1), "cost_usd": cost(self.total),
                          "avg_tokens_per_call": round(self.total["total_tokens"] / calls) if calls else 0,
                          "avg_seconds_per_call": round(self.total["seconds"] / calls, 1) if calls else 0},
                "errors": self.errors,
                "calls_without_usage": self.calls_without_usage,
                "pricing_configured": price_in is not None and price_out is not None,
                "by_feature": rows(self.by_feature),
                "by_model": rows(self.by_model),
                "by_step": rows(self.by_step),
                "recent": list(self.recent),
            }


USAGE = UsageTracker()


def _tokens(response) -> Optional[tuple]:
    """(input, output) tokens from a LangChain LLMResult, or None when the provider sent none."""
    for generations in response.generations:
        for gen in generations:
            usage = getattr(getattr(gen, "message", None), "usage_metadata", None)
            if usage and (usage.get("input_tokens") or usage.get("output_tokens")):
                return int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
    raw = (response.llm_output or {}).get("token_usage") or {}
    if raw.get("prompt_tokens") or raw.get("completion_tokens"):
        return int(raw.get("prompt_tokens", 0)), int(raw.get("completion_tokens", 0))
    return None


class UsageCallback(BaseCallbackHandler):
    """LangChain callback that feeds `USAGE`."""

    def __init__(self, tracker: UsageTracker = USAGE) -> None:
        self.tracker = tracker
        self._starts: Dict[Any, Dict[str, Any]] = {}

    def on_chat_model_start(self, serialized, messages, *, run_id, metadata=None, **kwargs) -> None:
        params = kwargs.get("invocation_params") or {}
        self._starts[run_id] = {
            "t": time.monotonic(),
            "feature": _feature.get(),
            "model": params.get("model") or params.get("model_name") or "unknown",
            "step": (metadata or {}).get("langgraph_node", ""),
        }

    def on_llm_end(self, response, *, run_id, **kwargs) -> None:
        start = self._starts.pop(run_id, None)
        if start is None:
            return
        tokens = _tokens(response)
        self.tracker.record(
            feature=start["feature"], model=start["model"], step=start["step"],
            input_tokens=tokens[0] if tokens else 0, output_tokens=tokens[1] if tokens else 0,
            seconds=time.monotonic() - start["t"], has_usage=tokens is not None,
        )

    def on_llm_error(self, error, *, run_id, **kwargs) -> None:
        self._starts.pop(run_id, None)
        self.tracker.record_error()


USAGE_CALLBACK = UsageCallback()
