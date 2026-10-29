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
import uuid
from collections import defaultdict, deque
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Optional

from langchain_core.callbacks import BaseCallbackHandler

_feature: ContextVar[str] = ContextVar("llm_feature", default="other")
# The HTTP request being served; LLM calls made while serving it are attached to it.
_request: ContextVar[Optional[Dict[str, Any]]] = ContextVar("llm_request", default=None)
RECENT_CALLS = 50
RECENT_REQUESTS = 50
SAMPLES = 500  # latency samples kept per series for percentiles
TIMELINE = 40  # calls shown in the speed/tokens charts


@contextmanager
def track_feature(name: str):
    """Attribute every LLM call made inside the block to `name`."""
    token = _feature.set(name)
    try:
        yield
    finally:
        _feature.reset(token)


def begin_request(endpoint: str) -> Dict[str, Any]:
    """Open a per-request record; LLM calls in this context are appended to it."""
    req = {"request_id": uuid.uuid4().hex[:12], "endpoint": endpoint, "time": time.time(),
           "calls": [], "has_missing_usage": False}
    _request.set(req)
    return req


def request_usage(req: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Token totals of one request so far (defaults to the current one)."""
    req = req if req is not None else _request.get()
    if req is None:
        return {"request_id": None, "llm_calls": 0, "input_tokens": 0, "output_tokens": 0,
                "total_tokens": 0, "seconds": 0.0, "complete": True, "status": "not_used"}
    calls = list(req["calls"])
    usage = {
        "request_id": req["request_id"],
        "llm_calls": len(calls),
        "input_tokens": sum(c["input_tokens"] for c in calls),
        "output_tokens": sum(c["output_tokens"] for c in calls),
        "total_tokens": sum(c["total_tokens"] for c in calls),
        "seconds": round(sum(c["seconds"] for c in calls), 2),
        "complete": not req["has_missing_usage"],
    }
    usage["status"] = "not_used" if not calls else ("partial" if req["has_missing_usage"] else "reported")
    return usage


def _price(var: str) -> Optional[float]:
    try:
        return float(os.environ[var])
    except (KeyError, ValueError):
        return None


def _percentile(values, q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]


def _bucket() -> Dict[str, Any]:
    return {"calls": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "seconds": 0.0}


def _add(bucket: Dict[str, Any], record: Dict[str, Any]) -> None:
    bucket["calls"] += 1
    bucket["input_tokens"] += record["input_tokens"]
    bucket["output_tokens"] += record["output_tokens"]
    bucket["total_tokens"] += record["total_tokens"]
    bucket["seconds"] += record["seconds"]


class RequestLedger:
    """Persistent per-request log in SQLite (MONITORING_DB_PATH, default logs/requests.sqlite3).

    Stores only technical fields (endpoint, status, duration, token counts, per-step calls):
    never prompts, answers, resumes or user ids. Keeps the newest `max_records` rows.
    Failures are logged and never affect the user's response.
    """

    COLUMNS = ("request_id", "time", "endpoint", "status_code", "duration_ms", "llm_calls",
               "input_tokens", "output_tokens", "total_tokens", "seconds", "complete", "status", "calls")

    def __init__(self, path: str, max_records: int = 10000) -> None:
        import sqlite3

        self.path = path
        self.max_records = max(100, max_records)
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS requests (id INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT, time REAL,"
            " endpoint TEXT, status_code INTEGER, duration_ms INTEGER, llm_calls INTEGER, input_tokens INTEGER,"
            " output_tokens INTEGER, total_tokens INTEGER, seconds REAL, complete INTEGER, status TEXT, calls TEXT)"
        )
        self._db.commit()

    def write(self, row: Dict[str, Any]) -> None:
        import json

        try:
            values = [row.get(c) for c in self.COLUMNS]
            values[self.COLUMNS.index("complete")] = int(bool(row.get("complete")))
            values[self.COLUMNS.index("calls")] = json.dumps(row.get("calls") or [])
            with self._lock:
                self._db.execute(f"INSERT INTO requests ({','.join(self.COLUMNS)}) VALUES ({','.join('?' * len(values))})",
                                 values)
                self._db.execute("DELETE FROM requests WHERE id <= (SELECT MAX(id) FROM requests) - ?", (self.max_records,))
                self._db.commit()
        except Exception as e:
            print(f"Request ledger write failed: {type(e).__name__}")

    def recent(self, limit: int = 50) -> list:
        import json

        with self._lock:
            cur = self._db.execute(f"SELECT {','.join(self.COLUMNS)} FROM requests ORDER BY id DESC LIMIT ?", (limit,))
            rows = [dict(zip(self.COLUMNS, r)) for r in cur.fetchall()]
        for r in rows:
            r["complete"] = bool(r["complete"])
            r["calls"] = json.loads(r["calls"] or "[]")
        return rows

    def totals(self) -> Dict[str, Any]:
        with self._lock:
            r = self._db.execute(
                "SELECT COUNT(*), COALESCE(SUM(total_tokens),0), COALESCE(SUM(input_tokens),0),"
                " COALESCE(SUM(output_tokens),0), COALESCE(AVG(duration_ms),0), COALESCE(SUM(status_code>=400),0),"
                " COALESCE(SUM(llm_calls>0),0), MIN(time) FROM requests"
            ).fetchone()
        return {"requests": r[0], "total_tokens": r[1], "input_tokens": r[2], "output_tokens": r[3],
                "avg_duration_ms": round(r[4]), "errors": r[5], "llm_requests": r[6], "since": r[7],
                "path": self.path}

    def clear(self) -> None:
        with self._lock:
            self._db.execute("DELETE FROM requests")
            self._db.commit()


def create_ledger() -> Optional[RequestLedger]:
    path = os.environ.get("MONITORING_DB_PATH", "logs/requests.sqlite3")
    if path.lower() in ("", "off", "none"):
        return None
    try:
        return RequestLedger(path, int(os.environ.get("MONITORING_MAX_RECORDS", "10000")))
    except Exception as e:
        print(f"Request ledger disabled: {type(e).__name__}: {e}")
        return None


class UsageTracker:
    def __init__(self, ledger: Optional[RequestLedger] = None) -> None:
        self._lock = threading.Lock()
        self.ledger = ledger
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
            self.latencies: deque = deque(maxlen=SAMPLES)
            self.feature_latencies: Dict[str, deque] = defaultdict(lambda: deque(maxlen=SAMPLES))
            self.timeline: deque = deque(maxlen=TIMELINE)
            self.endpoints: Dict[str, deque] = defaultdict(lambda: deque(maxlen=SAMPLES))
            self.endpoint_counts: Dict[str, int] = defaultdict(int)
            self.requests: deque = deque(maxlen=RECENT_REQUESTS)

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
            self.latencies.append(seconds)
            self.feature_latencies[feature].append(seconds)
            self.timeline.append({"time": record["time"], "total_tokens": record["total_tokens"],
                                  "seconds": record["seconds"], "feature": feature})
        req = _request.get()
        if req is not None:
            req["calls"].append(record)
            if not has_usage:
                req["has_missing_usage"] = True

    def record_request(self, path: str, seconds: float, req: Optional[Dict[str, Any]] = None,
                       status_code: int = 200) -> None:
        """HTTP request latency per route, plus the request's own LLM calls when `req` is given."""
        with self._lock:
            self.endpoints[path].append(seconds)
            self.endpoint_counts[path] += 1
            row = None
            if req is not None:
                row = {
                    **request_usage(req),
                    "endpoint": path,
                    "time": req["time"],
                    "status_code": status_code,
                    "duration_ms": round(seconds * 1000),
                    "calls": [{k: c[k] for k in ("step", "model", "input_tokens", "output_tokens", "seconds")}
                              for c in req["calls"]],
                }
                self.requests.appendleft(row)
        if row is not None and self.ledger is not None:
            self.ledger.write(row)

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

        def speed(table: Dict[str, Dict[str, Any]]):
            out = rows(table)
            for r in out:
                lat = self.feature_latencies.get(r["name"], [])
                r["p50_seconds"] = round(_percentile(lat, 0.5), 2)
                r["p95_seconds"] = round(_percentile(lat, 0.95), 2)
            return out

        with self._lock:
            calls = self.total["calls"]
            return {
                "since": self.started_at,
                "total": {**self.total, "seconds": round(self.total["seconds"], 1), "cost_usd": cost(self.total),
                          "avg_tokens_per_call": round(self.total["total_tokens"] / calls) if calls else 0,
                          "avg_seconds_per_call": round(self.total["seconds"] / calls, 1) if calls else 0,
                          "p50_seconds": round(_percentile(self.latencies, 0.5), 2),
                          "p95_seconds": round(_percentile(self.latencies, 0.95), 2),
                          # generation speed: output tokens per second of model time
                          "output_tokens_per_second": round(self.total["output_tokens"] / self.total["seconds"], 1)
                          if self.total["seconds"] else 0},
                "errors": self.errors,
                "calls_without_usage": self.calls_without_usage,
                "pricing_configured": price_in is not None and price_out is not None,
                "by_feature": speed(self.by_feature),
                "by_model": rows(self.by_model),
                "by_step": rows(self.by_step),
                "recent": list(self.recent),
                "timeline": list(self.timeline),
                # With a ledger, the request list and all-time totals come from SQLite (survive restarts).
                "requests": self.ledger.recent(50) if self.ledger is not None else list(self.requests),
                "history": self.ledger.totals() if self.ledger is not None else None,
                "endpoints": sorted(
                    ({"name": k, "requests": self.endpoint_counts[k],
                      "avg_ms": round(1000 * sum(v) / len(v)), "p95_ms": round(1000 * _percentile(v, 0.95))}
                     for k, v in self.endpoints.items() if v),
                    key=lambda r: r["requests"], reverse=True),
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
