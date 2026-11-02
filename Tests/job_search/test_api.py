import pytest
from fastapi.testclient import TestClient

from ui.src import api

from .test_query_parser import EXAMPLE


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    # Keep the tests offline: the /chat agent needs an LLM key.
    monkeypatch.setattr(api, "load_api_config", lambda: {"chat_enabled": False, "resume_llm_enabled": False})
    monkeypatch.setattr(api, "resume_llm", None)


@pytest.fixture
def client(service, monkeypatch):
    monkeypatch.setattr(api, "job_search", service)
    with TestClient(api.app) as c:
        yield c


def test_health_reports_job_search(client):
    data = client.get("/health").json()
    assert data["job_search_ready"] is True and data["jobs_indexed"] == 6


def test_search_endpoint_returns_ranked_grounded_results(client):
    r = client.post("/jobs/search", json={"query": EXAMPLE, "top_k": 3})
    assert r.status_code == 200
    data = r.json()
    assert data["query"]["locations"] == ["تهران"] and data["query"]["wants_remote"]
    assert len(data["results"]) == 3
    first = data["results"][0]
    assert first["job"]["url"].startswith("https://jobvision.ir/jobs/")
    assert first["explanation"]["summary"]


def test_search_endpoint_applies_filters(client):
    r = client.post("/jobs/search", json={"query": "حسابدار", "filters": {"internship_only": True}})
    assert [x["job"]["id"] for x in r.json()["results"]] == ["106"]


def test_search_endpoint_validates_input(client):
    assert client.post("/jobs/search", json={"query": ""}).status_code == 422
    assert client.post("/jobs/search", json={"query": "حسابدار", "top_k": 500}).status_code == 422
    assert client.post("/jobs/search", json={"query": "حسابدار", "method": "x"}).status_code == 422


def test_filters_and_job_endpoints(client):
    opts = client.get("/jobs/filters").json()
    assert opts["total"] == 6
    assert client.get("/jobs/101").json()["title"] == "کارشناس هوش مصنوعی"
    assert client.get("/jobs/nope").status_code == 404


def test_returns_503_when_index_missing(monkeypatch):
    monkeypatch.setattr(api, "job_search", None)
    monkeypatch.setattr(api, "job_search_error", "no index")
    app = api.app
    # Avoid loading the real model in the lifespan.
    monkeypatch.setattr("agent.job_search.service.create_search_service", lambda: (_ for _ in ()).throw(FileNotFoundError("no index")))
    with TestClient(app) as c:
        r = c.post("/jobs/search", json={"query": "حسابدار"})
    assert r.status_code == 503 and "not ready" in r.json()["detail"]
