import json

from fastapi.testclient import TestClient

from agent.job_search.roadmap import build_roadmap
from ui.src import api

JOB = {
    "id": "j1",
    "title": "برنامه‌نویس پایتون",
    "description": "تسلط به Python و Docker",
    "skills": ["Python", "Docker"],
    "software": [{"name": "Git", "level": ""}],
    "required_experience_years": 2,
}


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload

    def invoke(self, prompt):
        assert "Skills to learn: Docker، Git" in prompt
        return type("Msg", (), {"content": json.dumps(self.payload)})()


def test_rules_roadmap_excludes_known_skills():
    r = build_roadmap(JOB, ["python"])
    assert r["source"] == "rules" and r["have_skills"] == ["Python"]
    assert [s["skill"] for s in r["stages"]] == ["Docker", "Git"]


def test_llm_roadmap_drops_invented_skills_and_keeps_all_gaps():
    payload = {
        "summary": "خلاصه",
        "stages": [
            {"skill": "Kubernetes", "why": "x", "steps": ["a"], "weeks": 3},
            {"skill": "docker", "why": "طبق آگهی", "steps": ["نصب", "پروژه"], "weeks": 2},
        ],
    }
    r = build_roadmap(JOB, ["Python"], llm=FakeLLM(payload))
    assert r["source"] == "llm" and r["summary"] == "خلاصه"
    assert [s["skill"] for s in r["stages"]] == ["Docker", "Git"]
    assert r["stages"][0]["weeks"] == 2


def test_bad_llm_output_falls_back():
    class Bad:
        def invoke(self, prompt):
            raise TimeoutError

    assert build_roadmap(JOB, [], llm=Bad())["source"] == "rules"


def test_roadmap_endpoint(service, monkeypatch):
    monkeypatch.setattr(api, "load_api_config", lambda: {"chat_enabled": False, "resume_llm_enabled": False})
    monkeypatch.setattr(api, "job_search", service)
    monkeypatch.setattr(api, "resume_llm", None)
    job_id = service.index.jobs[0]["id"]
    with TestClient(api.app) as c:
        r = c.post(f"/jobs/{job_id}/roadmap", json={"known_skills": []})
        assert r.status_code == 200 and r.json()["job_id"] == job_id
        assert c.post("/jobs/nope/roadmap", json={}).status_code == 404
