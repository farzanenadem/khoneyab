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
