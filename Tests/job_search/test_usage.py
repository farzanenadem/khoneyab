from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from agent.utilities.usage import USAGE, UsageCallback, UsageTracker, track_feature
from ui.src import api


def _result(input_tokens, output_tokens):
    message = AIMessage(
        content="x",
        usage_metadata={"input_tokens": input_tokens, "output_tokens": output_tokens,
                        "total_tokens": input_tokens + output_tokens},
    )
    return LLMResult(generations=[[ChatGeneration(message=message)]])


def _call(callback, result, **start):
    run_id = uuid4()
    callback.on_chat_model_start({}, [], run_id=run_id, metadata=start.get("metadata"),
                                 invocation_params={"model": start.get("model", "m1")})
    callback.on_llm_end(result, run_id=run_id)


def test_tokens_are_aggregated_by_feature_model_and_step():
    tracker = UsageTracker()
    callback = UsageCallback(tracker)
    with track_feature("chat"):
        _call(callback, _result(100, 20), metadata={"langgraph_node": "router"})
        _call(callback, _result(300, 80), model="m2", metadata={"langgraph_node": "generate"})
    with track_feature("resume"):
        _call(callback, _result(50, 10))

    s = tracker.summary()
    assert s["total"]["calls"] == 3
    assert s["total"]["input_tokens"] == 450 and s["total"]["output_tokens"] == 110
    assert s["total"]["total_tokens"] == 560
    assert {r["name"]: r["total_tokens"] for r in s["by_feature"]} == {"chat": 500, "resume": 60}
    assert {r["name"] for r in s["by_model"]} == {"m1", "m2"}
    assert {r["name"] for r in s["by_step"]} == {"router", "generate"}
    assert s["recent"][0]["feature"] == "resume"  # newest first
    assert s["calls_without_usage"] == 0


def test_provider_without_usage_is_reported_not_guessed():
    tracker = UsageTracker()
    callback = UsageCallback(tracker)
    _call(callback, LLMResult(generations=[[ChatGeneration(message=AIMessage(content="x"))]]))
    s = tracker.summary()
    assert s["total"]["calls"] == 1 and s["total"]["total_tokens"] == 0
    assert s["calls_without_usage"] == 1


def test_errors_are_counted():
    tracker = UsageTracker()
    callback = UsageCallback(tracker)
    run_id = uuid4()
    callback.on_chat_model_start({}, [], run_id=run_id, invocation_params={"model": "m"})
    callback.on_llm_error(RuntimeError("boom"), run_id=run_id)
    assert tracker.summary()["errors"] == 1 and tracker.summary()["total"]["calls"] == 0


def test_cost_only_when_prices_are_configured(monkeypatch):
    tracker = UsageTracker()
    _call(UsageCallback(tracker), _result(1_000_000, 500_000))
    assert tracker.summary()["total"]["cost_usd"] is None
    monkeypatch.setenv("LLM_PRICE_IN_PER_M", "0.5")
    monkeypatch.setenv("LLM_PRICE_OUT_PER_M", "2")
    s = tracker.summary()
    assert s["pricing_configured"] is True and s["total"]["cost_usd"] == pytest.approx(1.5)


def test_usage_endpoint_and_reset(monkeypatch):
    monkeypatch.setattr(api, "load_api_config", lambda: {"chat_enabled": False, "resume_llm_enabled": False})
    USAGE.reset()
    _call(UsageCallback(USAGE), _result(10, 5))
    with TestClient(api.app) as client:
        data = client.get("/usage").json()
        assert data["total"]["total_tokens"] == 15
        assert client.post("/usage/reset").json()["status"] == "reset"
        assert client.get("/usage").json()["total"]["calls"] == 0


def test_speed_metrics_percentiles_and_throughput():
    tracker = UsageTracker()
    for seconds, out in [(1.0, 100), (2.0, 100), (3.0, 100), (10.0, 100)]:
        tracker.record(feature="chat", model="m", step="", input_tokens=10, output_tokens=out, seconds=seconds)
    s = tracker.summary()["total"]
    assert s["p50_seconds"] in (2.0, 3.0) and s["p95_seconds"] == 10.0
    assert s["output_tokens_per_second"] == pytest.approx(400 / 16, abs=0.1)
    chat = tracker.summary()["by_feature"][0]
    assert chat["p95_seconds"] == 10.0
    assert len(tracker.summary()["timeline"]) == 4


def test_request_latency_is_recorded_per_route(monkeypatch):
    monkeypatch.setattr(api, "load_api_config", lambda: {"chat_enabled": False, "resume_llm_enabled": False})
    USAGE.reset()
    with TestClient(api.app) as client:
        client.get("/jobs/filters")
        client.get("/health")
        endpoints = {e["name"]: e for e in client.get("/usage").json()["endpoints"]}
    assert "GET /jobs/filters" in endpoints and endpoints["GET /jobs/filters"]["requests"] == 1
    assert not any(name.startswith(("GET /usage", "GET /health")) for name in endpoints)


def test_calls_are_attributed_to_the_current_request():
    from agent.utilities.usage import begin_request, request_usage

    tracker = UsageTracker()
    req = begin_request("/chat")
    tracker.record(feature="chat", model="m", step="router", input_tokens=40, output_tokens=5, seconds=0.5)
    tracker.record(feature="chat", model="m", step="generate", input_tokens=900, output_tokens=200, seconds=3.0)
    u = request_usage(req)
    assert u["llm_calls"] == 2 and u["total_tokens"] == 1145 and u["status"] == "reported"
    tracker.record_request("POST /chat", 3.6, req, 200)
    row = tracker.summary()["requests"][0]
    assert row["endpoint"] == "POST /chat" and row["duration_ms"] == 3600
    assert [c["step"] for c in row["calls"]] == ["router", "generate"]


def test_search_request_is_logged_without_llm(monkeypatch):
    monkeypatch.setattr(api, "load_api_config", lambda: {"chat_enabled": False, "resume_llm_enabled": False})
    USAGE.reset()
    with TestClient(api.app) as client:
        r = client.get("/jobs/filters")
        assert r.headers.get("X-Request-ID")
        rows = client.get("/usage").json()["requests"]
    assert rows[0]["endpoint"] == "GET /jobs/filters"
    assert rows[0]["status"] == "not_used" and rows[0]["llm_calls"] == 0


def test_ledger_persists_requests_across_restarts(tmp_path):
    from agent.utilities.usage import RequestLedger, begin_request

    path = str(tmp_path / "requests.sqlite3")
    tracker = UsageTracker(RequestLedger(path))
    req = begin_request("/chat")
    tracker.record(feature="chat", model="m", step="generate", input_tokens=900, output_tokens=100, seconds=2.0)
    tracker.record_request("POST /chat", 2.5, req, 200)
    tracker.record_request("POST /jobs/search", 0.3, begin_request("/jobs/search"), 500)

    restarted = UsageTracker(RequestLedger(path))  # new process, same file
    s = restarted.summary()
    assert s["history"]["requests"] == 2 and s["history"]["total_tokens"] == 1000
    assert s["history"]["errors"] == 1 and s["history"]["llm_requests"] == 1
    assert s["requests"][0]["endpoint"] == "POST /jobs/search"
    assert s["requests"][1]["calls"][0]["step"] == "generate"
    assert s["total"]["calls"] == 0  # live counters start from zero, history does not


def test_ledger_keeps_only_newest_records(tmp_path):
    from agent.utilities.usage import RequestLedger, begin_request

    ledger = RequestLedger(str(tmp_path / "r.sqlite3"), max_records=100)
    tracker = UsageTracker(ledger)
    for _ in range(130):
        tracker.record_request("GET /jobs/filters", 0.01, begin_request("/jobs/filters"), 200)
    assert ledger.totals()["requests"] == 100
